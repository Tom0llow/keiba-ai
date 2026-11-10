"""Evaluate yearly-fold PL variants against the market with the real LightGBM backend."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import pyarrow as pa
import pytest

from models.dataset.race_arrays import RaceArrays
from models.experiments.pl_evaluation import (
    COMPARED_METRICS,
    PREDICTION_SCHEMA,
    PLEvaluationSettings,
    PLVariant,
    evaluate_pl,
)
from tests.pl_fixtures import pl_parameters, synthetic_race_arrays

YEARS = (2020, 2021, 2022, 2023)


def _settings(**changes: object) -> PLEvaluationSettings:
    settings = PLEvaluationSettings(
        train_start_year=2020,
        test_years=(2022, 2023),
        variants=(
            PLVariant("all_columns"),
            PLVariant("without_market", ("market_feature",)),
        ),
        lightgbm=pl_parameters(),
        num_boost_round=60,
        early_stopping_rounds=10,
        temperature_bounds=(0.05, 20.0),
        probability_chunk_races=16,
        bootstrap_resamples=200,
        bootstrap_seed=0,
        bootstrap_confidence=0.95,
        probability_bands=(0.0, 0.1, 0.3, 1.0),
        odds_bands=(1.0, 5.0, 20.0),
    )
    return replace(settings, **changes)  # type: ignore[arg-type]


def _arrays() -> RaceArrays:
    return synthetic_race_arrays(YEARS, races_per_year=60, seed=11)


def test_evaluation_reports_every_variant_fold_and_the_market_complete_comparison() -> None:
    arrays = _arrays()

    result = evaluate_pl(arrays, _settings())

    report = result.report
    variants = cast(list[dict[str, object]], report["variants"])
    assert [variant["name"] for variant in variants] == ["all_columns", "without_market"]
    assert variants[1]["feature_names"] == ["signal", "noise"]
    folds = cast(list[dict[str, object]], report["folds"])
    assert [fold["test_year"] for fold in folds] == [2022, 2023]
    first = folds[0]
    counts = cast(dict[str, int], first["counts"])
    assert counts["test_races"] == 60
    assert counts["test_market_incomplete_races"] == 1
    assert counts["test_market_complete_races"] == 59
    assert first["train_years"] == [2020, 2020]
    fold_variants = cast(dict[str, dict[str, object]], first["variants"])
    assert fold_variants["without_market"]["feature_names"] == ["signal", "noise"]
    assert fold_variants["all_columns"]["feature_names"] == ["signal", "noise", "market_feature"]
    comparison = cast(dict[str, object], fold_variants["all_columns"]["market_complete_races"])
    assert comparison["race_count"] == 59
    calibrated = cast(dict[str, dict[str, object]], comparison["comparison"])["calibrated"]
    assert set(calibrated) == set(COMPARED_METRICS)
    complete_calibration = cast(dict[str, list[dict[str, object]]], comparison["calibration"])
    assert set(complete_calibration) == {"win", "top2", "top3"}
    first_test_race = next(index for index, year in enumerate(arrays.years) if year == 2022)
    complete_rows = counts["test_rows"] - int(arrays.group_sizes[first_test_race])
    assert sum(cast(int, item["count"]) for item in complete_calibration["win"]) == complete_rows
    assert sum(cast(int, item["count"]) for item in complete_calibration["top2"]) == complete_rows
    assert sum(cast(int, item["count"]) for item in complete_calibration["top3"]) == complete_rows
    pooled = cast(dict[str, dict[str, object]], report["pooled"])
    pooled_market = cast(dict[str, object], pooled["all_columns"]["market_complete_races"])
    assert pooled_market["race_count"] == 118
    pooled_all = cast(dict[str, dict[str, object]], pooled["all_columns"]["all_test_races"])
    assert pooled_all["calibrated"]["race_count"] == 120


def test_predictions_follow_the_schema_and_leave_incomplete_market_q_null() -> None:
    arrays = _arrays()

    predictions = evaluate_pl(arrays, _settings()).predictions

    assert predictions.schema.equals(PREDICTION_SCHEMA)
    assert predictions.num_rows == 2 * sum(
        int(size)
        for size, year in zip(arrays.group_sizes, arrays.years, strict=True)
        if year >= 2022
    )
    rows = predictions.filter(
        pa.compute.equal(predictions.column("variant"), "all_columns")
    ).to_pylist()
    incomplete = {row["race_id"] for row in rows if row["market_win_odds"] is None}
    assert len(incomplete) == 2
    assert all(row["market_q"] is None for row in rows if row["race_id"] in incomplete)
    assert all(row["market_q"] is not None for row in rows if row["race_id"] not in incomplete)
    for race_id in {row["race_id"] for row in rows}:
        race = [row for row in rows if row["race_id"] == race_id]
        assert sum(row["p_win"] for row in race) == pytest.approx(1.0)
        assert sum(row["p_top3"] for row in race) == pytest.approx(3.0)


def test_test_finishing_positions_change_only_metrics() -> None:
    arrays = _arrays()
    reversed_test = arrays.finish_positions.copy()
    offsets = np.concatenate(([0], np.cumsum(arrays.group_sizes)))
    for race, year in enumerate(arrays.years):
        if year == 2023:
            start, stop = offsets[race], offsets[race + 1]
            reversed_test[start:stop] = stop - start + 1 - reversed_test[start:stop]
    changed = replace(arrays, finish_positions=reversed_test)
    settings = _settings(test_years=(2023,))

    original = evaluate_pl(arrays, settings)
    altered = evaluate_pl(changed, settings)

    for name in ("score", "p_win", "p_top2", "p_top3", "temperature"):
        np.testing.assert_array_equal(
            original.predictions.column(name).to_numpy(),
            altered.predictions.column(name).to_numpy(),
        )
    original_fold = cast(list[dict[str, dict[str, dict[str, object]]]], original.report["folds"])[0]
    altered_fold = cast(list[dict[str, dict[str, dict[str, object]]]], altered.report["folds"])[0]
    for variant in ("all_columns", "without_market"):
        before = original_fold["variants"][variant]
        after = altered_fold["variants"][variant]
        assert before["best_iteration"] == after["best_iteration"]
        assert before["temperature"] == after["temperature"]
        assert before["all_test_races"] != after["all_test_races"]


def test_variants_must_exclude_known_columns_and_keep_one_feature() -> None:
    arrays = _arrays()

    with pytest.raises(ValueError, match="unknown columns"):
        evaluate_pl(arrays, _settings(variants=(PLVariant("bad", ("missing",)),)))
    with pytest.raises(ValueError, match="no feature"):
        evaluate_pl(
            arrays,
            _settings(variants=(PLVariant("empty", ("signal", "noise", "market_feature")),)),
        )
    with pytest.raises(ValueError, match="unique"):
        _settings(variants=(PLVariant("same"), PLVariant("same")))
