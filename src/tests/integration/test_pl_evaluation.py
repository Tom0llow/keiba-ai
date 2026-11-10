"""Evaluate yearly-fold PL variants against the market with the real LightGBM backend."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import pyarrow as pa
import pytest

from models.dataset.race_arrays import RaceArrays
from models.evaluation.probability_metrics import race_probability_metrics
from models.experiments.pl_evaluation import (
    COMPARED_METRICS,
    PREDICTION_SCHEMA,
    PLEvaluationSettings,
    PLVariant,
    evaluate_pl,
)
from models.probability.plackett_luce import RaceLayout
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1
from tests.pl_fixtures import pl_parameters, synthetic_race_arrays

YEARS = (2020, 2021, 2022, 2023)
_INCOMPLETE_SUBSET = "incomplete_market_subset"
_NO_GRADED_RACES = {JRA_FLAT_GRADED_STAKES_V1: frozenset[str]()}


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

    result = evaluate_pl(arrays, _settings(), race_subsets=_NO_GRADED_RACES)

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

    predictions = evaluate_pl(arrays, _settings(), race_subsets=_NO_GRADED_RACES).predictions

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


def test_evaluation_reports_directly_scored_race_subsets_and_pools_them() -> None:
    arrays = _arrays()
    test_indexes = [index for index, year in enumerate(arrays.years) if year == 2022]
    incomplete_index, subset_index = test_indexes[:2]
    subset_id = arrays.race_ids[subset_index]
    result = evaluate_pl(
        arrays,
        _settings(),
        race_subsets={
            JRA_FLAT_GRADED_STAKES_V1: frozenset({subset_id}),
            _INCOMPLETE_SUBSET: frozenset({arrays.race_ids[incomplete_index]}),
        },
    )

    folds = cast(list[dict[str, object]], result.report["folds"])
    first, second = folds
    first_subsets = cast(dict[str, object], first["subsets"])
    subset_counts = cast(dict[str, object], first_subsets[JRA_FLAT_GRADED_STAKES_V1])
    assert subset_counts["race_count"] == 1
    assert subset_counts["market_complete_race_count"] == 1
    assert subset_counts["market_incomplete_race_count"] == 0
    assert subset_counts["market"] is not None
    assert subset_counts["market_calibration"] is not None
    assert cast(dict[str, object], second["subsets"])[JRA_FLAT_GRADED_STAKES_V1] is None
    incomplete_counts = cast(dict[str, object], first_subsets[_INCOMPLETE_SUBSET])
    assert incomplete_counts["market_complete_race_count"] == 0
    assert incomplete_counts["market"] is None
    assert incomplete_counts["market_calibration"] is None

    first_variants = cast(dict[str, dict[str, object]], first["variants"])
    subset_report = cast(
        dict[str, object],
        cast(dict[str, object], first_variants["all_columns"]["subsets"])[
            JRA_FLAT_GRADED_STAKES_V1
        ],
    )
    complete_report = cast(dict[str, object], subset_report["market_complete_races"])
    calibration = cast(
        dict[str, dict[str, list[dict[str, object]]]], complete_report["calibration"]
    )
    assert set(calibration) == {"calibrated_model", "market"}
    incomplete_variant = cast(
        dict[str, object],
        cast(dict[str, object], first_variants["all_columns"]["subsets"])[_INCOMPLETE_SUBSET],
    )
    assert incomplete_variant["market_complete_races"] is None

    prediction_rows = [
        row
        for row in result.predictions.to_pylist()
        if row["variant"] == "all_columns"
        and row["test_year"] == 2022
        and row["race_id"] == subset_id
    ]
    assert prediction_rows
    assert all(
        row["in_jra_flat_graded_stakes"] is (row["race_id"] == subset_id)
        for row in result.predictions.to_pylist()
    )
    subset = arrays.subset([subset_index])
    layout = RaceLayout.from_group_sizes(subset.group_sizes.tolist())
    scores = np.asarray([cast(float, row["score"]) for row in prediction_rows])
    temperature = cast(float, prediction_rows[0]["temperature"])
    raw = race_probability_metrics(scores, subset.finish_positions, layout)
    calibrated = race_probability_metrics(
        scores,
        subset.finish_positions,
        layout,
        temperature=temperature,
    )
    market = race_probability_metrics(
        np.log(np.asarray([cast(float, row["market_q"]) for row in prediction_rows])),
        subset.finish_positions,
        layout,
    )
    all_report = cast(dict[str, dict[str, object]], subset_report["all_test_races"])
    raw_summary = all_report["raw"]
    calibrated_summary = all_report["calibrated"]
    comparison = cast(dict[str, dict[str, dict[str, object]]], complete_report["comparison"])
    for metric in COMPARED_METRICS:
        assert raw_summary[metric] == pytest.approx(float(np.mean(getattr(raw, metric))))
        assert calibrated_summary[metric] == pytest.approx(
            float(np.mean(getattr(calibrated, metric)))
        )
        assert comparison["calibrated"][metric]["model_mean"] == pytest.approx(
            float(np.mean(getattr(calibrated, metric)))
        )
        assert comparison["calibrated"][metric]["market_mean"] == pytest.approx(
            float(np.mean(getattr(market, metric)))
        )
    assert sum(cast(int, item["count"]) for item in calibration["calibrated_model"]["win"]) == len(
        scores
    )
    assert sum(cast(int, item["count"]) for item in calibration["market"]["win"]) == len(scores)

    pooled = cast(dict[str, dict[str, object]], result.report["pooled"])
    pooled_subset = cast(
        dict[str, object],
        cast(dict[str, object], pooled["all_columns"]["subsets"])[JRA_FLAT_GRADED_STAKES_V1],
    )
    assert (
        cast(dict[str, dict[str, object]], pooled_subset["all_test_races"])["raw"]["race_count"]
        == 1
    )
    incomplete_pooled = cast(
        dict[str, object],
        cast(dict[str, object], pooled["all_columns"]["subsets"])[_INCOMPLETE_SUBSET],
    )
    assert incomplete_pooled["market_complete_races"] is None


def test_pooled_subset_reports_combine_every_fold_and_match_direct_scoring() -> None:
    arrays = _arrays()
    chosen: list[int] = []
    for year in (2022, 2023):
        indexes = [index for index, value in enumerate(arrays.years) if value == year]
        # The first race of each year lacks one market quote (see the fixture).
        chosen.extend(indexes[:3])
    subset_ids = frozenset(arrays.race_ids[index] for index in chosen)
    result = evaluate_pl(arrays, _settings(), race_subsets={JRA_FLAT_GRADED_STAKES_V1: subset_ids})

    folds = cast(list[dict[str, dict[str, dict[str, object]]]], result.report["folds"])
    fold_counts = [fold["subsets"][JRA_FLAT_GRADED_STAKES_V1] for fold in folds]
    assert [counts["race_count"] for counts in fold_counts] == [3, 3]
    assert [counts["market_complete_race_count"] for counts in fold_counts] == [2, 2]
    pooled = cast(dict[str, dict[str, dict[str, dict[str, object]]]], result.report["pooled"])
    for variant in ("all_columns", "without_market"):
        pooled_subset = pooled[variant]["subsets"][JRA_FLAT_GRADED_STAKES_V1]
        all_races = cast(dict[str, dict[str, object]], pooled_subset["all_test_races"])
        complete = cast(dict[str, object], pooled_subset["market_complete_races"])
        assert all_races["raw"]["race_count"] == 6
        assert complete["race_count"] == 4

        rows = [
            row
            for row in result.predictions.to_pylist()
            if row["variant"] == variant and row["race_id"] in subset_ids
        ]
        assert all(row["in_jra_flat_graded_stakes"] for row in rows)
        raw_values: dict[str, list[float]] = {metric: [] for metric in COMPARED_METRICS}
        calibrated_values: dict[str, list[float]] = {metric: [] for metric in COMPARED_METRICS}
        complete_model: dict[str, list[float]] = {metric: [] for metric in COMPARED_METRICS}
        complete_market: dict[str, list[float]] = {metric: [] for metric in COMPARED_METRICS}
        complete_rows = 0
        for index in chosen:
            race_id = arrays.race_ids[index]
            race_rows = [row for row in rows if row["race_id"] == race_id]
            race = arrays.subset([index])
            layout = RaceLayout.from_group_sizes(race.group_sizes.tolist())
            by_horse = {cast(str, row["horse_id"]): row for row in race_rows}
            ordered = [by_horse[horse] for horse in race.horse_ids]
            scores = np.asarray([cast(float, row["score"]) for row in ordered])
            temperature = cast(float, ordered[0]["temperature"])
            raw = race_probability_metrics(scores, race.finish_positions, layout)
            calibrated = race_probability_metrics(
                scores, race.finish_positions, layout, temperature=temperature
            )
            for metric in COMPARED_METRICS:
                raw_values[metric].append(float(getattr(raw, metric)[0]))
                calibrated_values[metric].append(float(getattr(calibrated, metric)[0]))
            if all(row["market_q"] is not None for row in ordered):
                complete_rows += len(ordered)
                market = race_probability_metrics(
                    np.log(np.asarray([cast(float, row["market_q"]) for row in ordered])),
                    race.finish_positions,
                    layout,
                )
                for metric in COMPARED_METRICS:
                    complete_model[metric].append(float(getattr(calibrated, metric)[0]))
                    complete_market[metric].append(float(getattr(market, metric)[0]))
        comparison = cast(dict[str, dict[str, dict[str, object]]], complete["comparison"])
        for metric in COMPARED_METRICS:
            assert all_races["raw"][metric] == pytest.approx(np.mean(raw_values[metric]))
            assert all_races["calibrated"][metric] == pytest.approx(
                np.mean(calibrated_values[metric])
            )
            assert comparison["calibrated"][metric]["model_mean"] == pytest.approx(
                np.mean(complete_model[metric])
            )
            assert comparison["calibrated"][metric]["market_mean"] == pytest.approx(
                np.mean(complete_market[metric])
            )
        calibration = cast(dict[str, dict[str, list[dict[str, object]]]], complete["calibration"])
        for source in ("calibrated_model", "market"):
            for kind in ("win", "top2", "top3"):
                assert (
                    sum(cast(int, item["count"]) for item in calibration[source][kind])
                    == complete_rows
                )
        # Recompute the pooled win/top-3 tables from the complete races' prediction rows.
        bands = _settings().probability_bands
        model_win: list[float] = []
        model_top3: list[float] = []
        market_win: list[float] = []
        won: list[float] = []
        placed: list[float] = []
        for index in chosen:
            race_rows = [row for row in rows if row["race_id"] == arrays.race_ids[index]]
            if any(row["market_q"] is None for row in race_rows):
                continue
            for row in race_rows:
                model_win.append(cast(float, row["p_win"]))
                model_top3.append(cast(float, row["p_top3"]))
                market_win.append(cast(float, row["market_q"]))
                won.append(float(row["finish_position"] == 1))
                placed.append(float(cast(int, row["finish_position"]) <= 3))
        for kind, source, values, outcomes in (
            ("win", "calibrated_model", model_win, won),
            ("top3", "calibrated_model", model_top3, placed),
            ("win", "market", market_win, won),
        ):
            for position, item in enumerate(calibration[source][kind]):
                lower, upper = bands[position], bands[position + 1]
                last = position == len(bands) - 2
                selected = [
                    (value, outcome)
                    for value, outcome in zip(values, outcomes, strict=True)
                    if lower <= value and (value <= upper if last else value < upper)
                ]
                assert item["count"] == len(selected)
                if selected:
                    assert item["mean_prediction"] == pytest.approx(
                        np.mean([value for value, _ in selected])
                    )
                    assert item["observed_rate"] == pytest.approx(
                        np.mean([outcome for _, outcome in selected])
                    )


def test_evaluation_requires_the_predictions_column_subset() -> None:
    with pytest.raises(ValueError, match=JRA_FLAT_GRADED_STAKES_V1):
        evaluate_pl(_arrays(), _settings(), race_subsets={"other": frozenset[str]()})


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
    race_subsets = {
        JRA_FLAT_GRADED_STAKES_V1: frozenset(
            race_id
            for race_id, year in zip(arrays.race_ids, arrays.years, strict=True)
            if year == 2023
        )
    }

    original = evaluate_pl(arrays, settings, race_subsets=race_subsets)
    altered = evaluate_pl(changed, settings, race_subsets=race_subsets)

    for name in (
        "score",
        "p_win",
        "p_top2",
        "p_top3",
        "temperature",
        "in_jra_flat_graded_stakes",
    ):
        np.testing.assert_array_equal(
            original.predictions.column(name).to_numpy(),
            altered.predictions.column(name).to_numpy(),
        )
    original_fold = cast(dict[str, object], cast(list[object], original.report["folds"])[0])
    altered_fold = cast(dict[str, object], cast(list[object], altered.report["folds"])[0])
    original_variants = cast(dict[str, dict[str, object]], original_fold["variants"])
    altered_variants = cast(dict[str, dict[str, object]], altered_fold["variants"])
    for variant in ("all_columns", "without_market"):
        before = original_variants[variant]
        after = altered_variants[variant]
        assert before["best_iteration"] == after["best_iteration"]
        assert before["temperature"] == after["temperature"]
        assert before["all_test_races"] != after["all_test_races"]
    original_subsets = cast(dict[str, dict[str, object]], original_fold["subsets"])
    altered_subsets = cast(dict[str, dict[str, object]], altered_fold["subsets"])
    assert original_subsets[JRA_FLAT_GRADED_STAKES_V1]["race_count"] == 60
    assert altered_subsets[JRA_FLAT_GRADED_STAKES_V1]["race_count"] == 60


def test_variants_must_exclude_known_columns_and_keep_one_feature() -> None:
    arrays = _arrays()

    with pytest.raises(ValueError, match="unknown columns"):
        evaluate_pl(
            arrays,
            _settings(variants=(PLVariant("bad", ("missing",)),)),
            race_subsets=_NO_GRADED_RACES,
        )
    with pytest.raises(ValueError, match="no feature"):
        evaluate_pl(
            arrays,
            _settings(variants=(PLVariant("empty", ("signal", "noise", "market_feature")),)),
            race_subsets=_NO_GRADED_RACES,
        )
    with pytest.raises(ValueError, match="unique"):
        _settings(variants=(PLVariant("same"), PLVariant("same")))
