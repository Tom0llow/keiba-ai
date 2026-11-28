"""Test pure PL-variant comparison and residual calculations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pytest

from models.evaluation.probability_metrics import (
    paired_bootstrap_comparison,
    race_probability_metrics,
)
from models.experiments.pl_comparison import (
    PLComparisonSettings,
    VariantComparison,
    build_pl_comparison_report,
    normalize_pl_predictions,
)
from models.probability.plackett_luce import RaceLayout, top3_marginal_probabilities
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1
from models.serialization.residual_segments import (
    ResidualSegmentAssignments,
    assign_residual_segments,
)

type FloatArray = npt.NDArray[np.float64]
type ScoreSets = Mapping[str, tuple[FloatArray, ...]]


@dataclass(frozen=True)
class _Race:
    year: int
    race_id: str
    finish_positions: tuple[int, int, int]
    graded: bool


_RACES = (
    _Race(2022, "2022-race-a", (1, 2, 3), True),
    _Race(2022, "2022-race-b", (2, 1, 3), False),
    _Race(2023, "2023-race-a", (1, 3, 2), True),
    _Race(2023, "2023-race-b", (3, 1, 2), False),
)
_SCORES: ScoreSets = {
    "candidate": (
        np.array([1.0, 0.0, -0.5]),
        np.array([0.1, 1.1, -0.4]),
        np.array([0.8, -0.2, 0.3]),
        np.array([-0.5, 0.7, 0.1]),
    ),
    "baseline": (
        np.array([0.2, 0.1, -0.1]),
        np.array([0.3, 0.4, -0.2]),
        np.array([0.5, 0.2, 0.0]),
        np.array([-0.2, 0.1, 0.4]),
    ),
}
_TEMPERATURES = {
    "candidate": {2022: 0.7, 2023: 1.4},
    "baseline": {2022: 1.1, 2023: 0.9},
}


def _prediction_table(
    *,
    graded: Mapping[str, bool] | None = None,
    temperatures: Mapping[str, Mapping[int, float]] | None = None,
    scores_by_variant: ScoreSets | None = None,
) -> pa.Table:
    rows: list[dict[str, object]] = []
    selected_temperatures = _TEMPERATURES if temperatures is None else temperatures
    selected_scores = _SCORES if scores_by_variant is None else scores_by_variant
    for variant in ("candidate", "baseline"):
        variant_rows: list[dict[str, object]] = []
        for race_index, race in enumerate(_RACES):
            scores = selected_scores[variant][race_index]
            temperature = selected_temperatures[variant][race.year]
            marginals = top3_marginal_probabilities(
                scores,
                RaceLayout((3,)),
                temperature=temperature,
            )
            for horse_index, finish_position in enumerate(race.finish_positions, start=1):
                variant_rows.append(
                    {
                        "variant": variant,
                        "test_year": race.year,
                        "race_id": race.race_id,
                        "horse_id": f"h{horse_index}",
                        "finish_position": finish_position,
                        "score": float(scores[horse_index - 1]),
                        "temperature": temperature,
                        "p_win": float(marginals.win[horse_index - 1]),
                        "p_top2": float(marginals.top2[horse_index - 1]),
                        "p_top3": float(marginals.top3[horse_index - 1]),
                        "in_jra_flat_graded_stakes": (
                            race.graded if graded is None else graded[race.race_id]
                        ),
                    }
                )
        rows.extend(variant_rows if variant == "candidate" else list(reversed(variant_rows)))
    return pa.Table.from_pylist(rows)


def _segments(*, signed_gaps_available: bool = True) -> ResidualSegmentAssignments:
    return assign_residual_segments(
        track_codes=["23", "23", "23", "10", "10", "10", "24", "24", "24", "25", "25", "25"],
        distances_m=[1200, 1200, 1200, 1600, 1600, 1600, 1400, 1400, 1400, 1800, 1800, 1800],
        horse_numbers=[1, 2, 3] * 4,
        field_sizes=[3] * 12,
        ages=[3] * 12,
        prior_finish_positions=[1, 2, 3] * 4,
        prior_signed_gap_seconds=([-0.3, 0.1, np.nan] * 4 if signed_gaps_available else None),
    )


def _settings() -> PLComparisonSettings:
    return PLComparisonSettings(
        comparisons=(VariantComparison("candidate", "baseline"),),
        bootstrap_resamples=40,
        bootstrap_seed=7,
        bootstrap_confidence=0.95,
    )


def _direct_winner_losses(variant: str) -> FloatArray:
    losses: list[FloatArray] = []
    for race_index, race in enumerate(_RACES):
        losses.append(
            race_probability_metrics(
                _SCORES[variant][race_index],
                np.asarray(race.finish_positions, dtype=np.int64),
                RaceLayout((3,)),
                temperature=_TEMPERATURES[variant][race.year],
            ).winner_log_loss
        )
    return np.concatenate(losses)


def _direct_stage1_losses(variant: str) -> FloatArray:
    return np.asarray(
        [
            race_probability_metrics(
                _SCORES[variant][race_index],
                np.asarray(race.finish_positions, dtype=np.int64),
                RaceLayout((3,)),
                temperature=_TEMPERATURES[variant][race.year],
            ).stage_nll[0, 0]
            for race_index, race in enumerate(_RACES)
        ],
        dtype=np.float64,
    )


def test_comparison_report_matches_direct_metrics_and_bootstrap_with_yearly_temperatures() -> None:
    report = build_pl_comparison_report(
        normalize_pl_predictions(_prediction_table()), _settings(), _segments()
    )

    comparison = cast(list[dict[str, object]], report["comparisons"])[0]
    all_races = cast(dict[str, object], comparison["all_test_races"])
    pooled = cast(dict[str, object], all_races["pooled"])
    winner = cast(dict[str, object], pooled["winner_log_loss"])
    direct = paired_bootstrap_comparison(
        _direct_winner_losses("candidate"),
        _direct_winner_losses("baseline"),
        resamples=40,
        seed=7,
        confidence=0.95,
    )

    assert pooled["race_count"] == 4
    assert winner["candidate_mean"] == pytest.approx(direct.model_mean)
    assert winner["baseline_mean"] == pytest.approx(direct.market_mean)
    assert winner["mean_difference"] == pytest.approx(direct.mean_difference)
    assert winner["confidence_interval_lower"] == pytest.approx(direct.confidence_interval_lower)
    assert winner["confidence_interval_upper"] == pytest.approx(direct.confidence_interval_upper)
    assert (
        winner["conclusion"]
        == {
            "model_better": "candidate_better",
            "market_better": "baseline_better",
            "inconclusive": "inconclusive",
        }[direct.conclusion]
    )
    assert set(pooled) == {
        "race_count",
        *(
            "winner_log_loss",
            "multiclass_brier",
            "exacta_log_loss",
            "quinella_log_loss",
            "trifecta_log_loss",
            "trio_log_loss",
            "stage1_nll",
            "stage2_nll",
            "stage3_nll",
        ),
    }
    variants = cast(dict[str, object], report["variants"])
    assert set(variants) == {"candidate", "baseline"}
    candidate_scopes = cast(dict[str, object], variants["candidate"])
    assert set(candidate_scopes) == {"all_test_races", JRA_FLAT_GRADED_STAKES_V1}
    candidate_all_races = cast(dict[str, object], candidate_scopes["all_test_races"])
    assert set(candidate_all_races) == {"pooled", "by_test_year"}
    assert set(cast(dict[str, object], candidate_all_races["pooled"])) == {
        "race_count",
        *(
            "winner_log_loss",
            "multiclass_brier",
            "exacta_log_loss",
            "quinella_log_loss",
            "trifecta_log_loss",
            "trio_log_loss",
            "stage1_nll",
            "stage2_nll",
            "stage3_nll",
        ),
    }
    assert set(cast(dict[str, object], candidate_all_races["by_test_year"])) == {"2022", "2023"}

    by_year = cast(dict[str, object], all_races["by_test_year"])
    stage1 = cast(dict[str, object], cast(dict[str, object], by_year["2022"])["stage1_nll"])
    direct_stage1 = paired_bootstrap_comparison(
        _direct_stage1_losses("candidate")[:2],
        _direct_stage1_losses("baseline")[:2],
        resamples=40,
        seed=7,
        confidence=0.95,
    )
    assert stage1["candidate_mean"] == pytest.approx(direct_stage1.model_mean)
    assert stage1["baseline_mean"] == pytest.approx(direct_stage1.market_mean)
    assert stage1["mean_difference"] == pytest.approx(direct_stage1.mean_difference)
    assert stage1["confidence_interval_lower"] == pytest.approx(
        direct_stage1.confidence_interval_lower
    )
    assert stage1["confidence_interval_upper"] == pytest.approx(
        direct_stage1.confidence_interval_upper
    )
    assert (
        stage1["conclusion"]
        == {
            "model_better": "candidate_better",
            "market_better": "baseline_better",
            "inconclusive": "inconclusive",
        }[direct_stage1.conclusion]
    )

    swapped = {
        **_TEMPERATURES,
        "candidate": {2022: 1.4, 2023: 0.7},
    }
    changed = build_pl_comparison_report(
        normalize_pl_predictions(_prediction_table(temperatures=swapped)),
        _settings(),
        _segments(),
    )
    changed_winner = cast(
        dict[str, object],
        cast(
            dict[str, object],
            cast(list[dict[str, object]], changed["comparisons"])[0]["all_test_races"],
        )["pooled"],
    )["winner_log_loss"]
    assert cast(dict[str, object], changed_winner)["candidate_mean"] != pytest.approx(
        cast(float, winner["candidate_mean"])
    )


def test_comparison_uses_only_graded_races_and_reports_an_empty_subset_as_null() -> None:
    report = build_pl_comparison_report(
        normalize_pl_predictions(_prediction_table()), _settings(), _segments()
    )
    comparison = cast(list[dict[str, object]], report["comparisons"])[0]
    graded = cast(dict[str, object], comparison[JRA_FLAT_GRADED_STAKES_V1])
    pooled = cast(dict[str, object], graded["pooled"])

    assert pooled["race_count"] == 2
    assert cast(dict[str, object], graded["by_test_year"])["2022"] is not None
    assert cast(dict[str, object], graded["by_test_year"])["2023"] is not None
    graded_winner = cast(dict[str, object], pooled["winner_log_loss"])
    direct_graded = paired_bootstrap_comparison(
        _direct_winner_losses("candidate")[::2],
        _direct_winner_losses("baseline")[::2],
        resamples=40,
        seed=7,
        confidence=0.95,
    )
    assert graded_winner["candidate_mean"] == pytest.approx(direct_graded.model_mean)
    assert graded_winner["baseline_mean"] == pytest.approx(direct_graded.market_mean)
    assert graded_winner["mean_difference"] == pytest.approx(direct_graded.mean_difference)
    assert graded_winner["confidence_interval_lower"] == pytest.approx(
        direct_graded.confidence_interval_lower
    )
    assert graded_winner["confidence_interval_upper"] == pytest.approx(
        direct_graded.confidence_interval_upper
    )

    graded_2022 = cast(dict[str, object], cast(dict[str, object], graded["by_test_year"])["2022"])
    graded_2022_winner = cast(dict[str, object], graded_2022["winner_log_loss"])
    direct_graded_2022 = paired_bootstrap_comparison(
        _direct_winner_losses("candidate")[:1],
        _direct_winner_losses("baseline")[:1],
        resamples=40,
        seed=7,
        confidence=0.95,
    )
    assert graded_2022_winner["candidate_mean"] == pytest.approx(direct_graded_2022.model_mean)
    assert graded_2022_winner["baseline_mean"] == pytest.approx(direct_graded_2022.market_mean)
    assert graded_2022_winner["mean_difference"] == pytest.approx(
        direct_graded_2022.mean_difference
    )
    assert graded_2022_winner["confidence_interval_lower"] == pytest.approx(
        direct_graded_2022.confidence_interval_lower
    )
    assert graded_2022_winner["confidence_interval_upper"] == pytest.approx(
        direct_graded_2022.confidence_interval_upper
    )

    no_graded = build_pl_comparison_report(
        normalize_pl_predictions(
            _prediction_table(graded={race.race_id: False for race in _RACES})
        ),
        _settings(),
        _segments(),
    )
    no_graded_comparison = cast(list[dict[str, object]], no_graded["comparisons"])[0]
    empty = cast(dict[str, object], no_graded_comparison[JRA_FLAT_GRADED_STAKES_V1])
    assert empty["pooled"] is None
    assert all(value is None for value in cast(dict[str, object], empty["by_test_year"]).values())


def test_segment_residuals_report_hand_calculated_values_and_three_horse_top3_null_z() -> None:
    report = build_pl_comparison_report(
        normalize_pl_predictions(_prediction_table()), _settings(), _segments()
    )
    segments = cast(dict[str, object], report["segments"])
    assert segments["residual_definition"] == {
        "ratio": (
            "actual / expected; expected at most 1e-12 per horse is reported as 0 and the ratio is null."
        ),
        "z": (
            "(actual - expected) / sqrt(sum(p * (1 - p))); null when sum(p * (1 - p)) is at most "
            "1e-12 per horse. "
            "This is an independent-Bernoulli approximation, not a test statistic."
        ),
    }
    all_horses = cast(dict[str, object], segments["all_horses"])
    candidate = cast(
        dict[str, object], cast(dict[str, object], all_horses["variants"])["candidate"]
    )
    win = cast(dict[str, object], candidate["win"])
    top3 = cast(dict[str, object], candidate["top3"])

    normalized = normalize_pl_predictions(_prediction_table()).variants["candidate"]
    expected = float(normalized.marginals.win.sum())
    variance = float(np.sum(normalized.marginals.win * (1.0 - normalized.marginals.win)))
    actual = int((normalized.finish_positions == 1).sum())
    assert candidate["horses"] == 12
    assert win["actual"] == actual
    assert win["expected"] == pytest.approx(expected)
    assert win["ratio"] == pytest.approx(actual / expected)
    assert win["z"] == pytest.approx((actual - expected) / np.sqrt(variance))
    assert top3["ratio"] == pytest.approx(1.0)
    assert top3["z"] is None

    random = np.random.default_rng(0)
    random_scores: ScoreSets = {
        variant: tuple(random.normal(size=3) for _ in _RACES)
        for variant in ("candidate", "baseline")
    }
    randomized = normalize_pl_predictions(_prediction_table(scores_by_variant=random_scores))
    randomized_top3 = randomized.variants["candidate"].marginals.top3
    assert 0.0 < float(np.sum(randomized_top3 * (1.0 - randomized_top3))) < 1e-12
    randomized_report = build_pl_comparison_report(randomized, _settings(), _segments())
    randomized_segments = cast(dict[str, object], randomized_report["segments"])
    randomized_all_horses = cast(dict[str, object], randomized_segments["all_horses"])
    randomized_candidate = cast(
        dict[str, object], cast(dict[str, object], randomized_all_horses["variants"])["candidate"]
    )
    assert cast(dict[str, object], randomized_candidate["top3"])["z"] is None

    empty_age = cast(dict[str, object], segments["age_2"])
    empty_variant = cast(dict[str, object], empty_age["variants"])
    empty_candidate = cast(dict[str, object], empty_variant["candidate"])
    empty_win = cast(dict[str, object], empty_candidate["win"])
    assert empty_win == {"actual": 0, "expected": 0.0, "ratio": None, "z": None}

    unavailable = build_pl_comparison_report(
        normalize_pl_predictions(_prediction_table()),
        _settings(),
        _segments(signed_gaps_available=False),
    )
    unavailable_segments = cast(dict[str, object], unavailable["segments"])
    prior_win = cast(dict[str, object], unavailable_segments["prior_win_margin_ge_0_3s"])
    assert prior_win["available"] is False
    assert "variants" not in prior_win


def test_normalization_sorts_variant_rows_without_changing_the_report() -> None:
    predictions = _prediction_table()
    normalized = normalize_pl_predictions(predictions)
    assert normalized.variants["candidate"].horse_ids == normalized.variants["baseline"].horse_ids
    assert (
        normalized.variants["candidate"].row_race_ids
        == normalized.variants["baseline"].row_race_ids
    )

    ordered = pa.Table.from_pylist(
        sorted(
            predictions.to_pylist(),
            key=lambda row: (row["variant"], row["test_year"], row["race_id"], row["horse_id"]),
        )
    )
    assert build_pl_comparison_report(
        normalized, _settings(), _segments()
    ) == build_pl_comparison_report(normalize_pl_predictions(ordered), _settings(), _segments())


def test_normalization_rejects_invalid_shared_prediction_data() -> None:
    predictions = _prediction_table()

    rows = predictions.to_pylist()
    duplicate = pa.Table.from_pylist([*rows, rows[0]])
    with pytest.raises(ValueError, match="duplicate"):
        normalize_pl_predictions(duplicate)

    wrong_finish = [dict(row) for row in rows]
    wrong_finish[-2]["finish_position"] = 1
    with pytest.raises(ValueError, match="finish_position"):
        normalize_pl_predictions(pa.Table.from_pylist(wrong_finish))

    missing = [dict(row) for row in rows if row is not rows[-1]]
    with pytest.raises(ValueError, match="group sizes must be at least 3"):
        normalize_pl_predictions(pa.Table.from_pylist(missing))

    wrong_graded = [dict(row) for row in rows]
    wrong_graded[-1]["in_jra_flat_graded_stakes"] = not cast(
        bool, wrong_graded[-1]["in_jra_flat_graded_stakes"]
    )
    with pytest.raises(ValueError, match="in_jra_flat_graded_stakes"):
        normalize_pl_predictions(pa.Table.from_pylist(wrong_graded))

    varying_temperature = [dict(row) for row in rows]
    varying_temperature[0]["temperature"] = 0.8
    with pytest.raises(ValueError, match="temperature must be constant"):
        normalize_pl_predictions(pa.Table.from_pylist(varying_temperature))

    wrong_probability = [dict(row) for row in rows]
    wrong_probability[0]["p_win"] = 0.9
    with pytest.raises(ValueError, match="does not match"):
        normalize_pl_predictions(pa.Table.from_pylist(wrong_probability))


def test_normalization_rejects_variant_alignment_drift() -> None:
    rows = _prediction_table().to_pylist()

    wrong_finish = [dict(row) for row in rows]
    finish_indexes = [
        index
        for index, row in enumerate(wrong_finish)
        if row["variant"] == "baseline" and row["race_id"] == "2022-race-a"
    ]
    first, second = finish_indexes[:2]
    wrong_finish[first]["finish_position"], wrong_finish[second]["finish_position"] = (
        wrong_finish[second]["finish_position"],
        wrong_finish[first]["finish_position"],
    )
    with pytest.raises(ValueError, match="variants must agree on finish_position"):
        normalize_pl_predictions(pa.Table.from_pylist(wrong_finish))

    renamed_horse = [dict(row) for row in rows]
    next(
        row
        for row in renamed_horse
        if row["variant"] == "baseline"
        and row["race_id"] == "2022-race-a"
        and row["horse_id"] == "h1"
    )["horse_id"] = "h4"
    with pytest.raises(ValueError, match="same test-year/race/horse keys"):
        normalize_pl_predictions(pa.Table.from_pylist(renamed_horse))

    renamed_race = [dict(row) for row in rows]
    for row in renamed_race:
        if row["variant"] == "baseline" and row["race_id"] == "2022-race-a":
            row["race_id"] = "2022-race-renamed"
    with pytest.raises(ValueError, match="same test-year/race/horse keys"):
        normalize_pl_predictions(pa.Table.from_pylist(renamed_race))

    missing_race = [
        dict(row)
        for row in rows
        if not (row["variant"] == "baseline" and row["race_id"] == "2022-race-a")
    ]
    with pytest.raises(ValueError, match="same test-year/race/horse keys"):
        normalize_pl_predictions(pa.Table.from_pylist(missing_race))

    wrong_graded = [dict(row) for row in rows]
    for row in wrong_graded:
        if row["variant"] == "baseline" and row["race_id"] == "2022-race-a":
            row["in_jra_flat_graded_stakes"] = False
    with pytest.raises(ValueError, match="variants must agree on in_jra_flat_graded_stakes"):
        normalize_pl_predictions(pa.Table.from_pylist(wrong_graded))
