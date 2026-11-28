"""Compare saved Plackett--Luce evaluation variants without performing I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.compute as pc

from models.evaluation.probability_metrics import (
    RaceProbabilityMetrics,
    paired_bootstrap_comparison,
    race_probability_metrics,
)
from models.probability.plackett_luce import (
    MarginalProbabilities,
    RaceLayout,
    top3_marginal_probabilities,
)
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1
from models.serialization.residual_segments import (
    PL_RESIDUAL_SEGMENTS_V1,
    RESIDUAL_SEGMENT_DEFINITIONS,
    ResidualSegmentAssignments,
)

type BoolArray = npt.NDArray[np.bool_]
type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]

_LOSS_METRICS = (
    "winner_log_loss",
    "multiclass_brier",
    "exacta_log_loss",
    "quinella_log_loss",
    "trifecta_log_loss",
    "trio_log_loss",
)
_METRIC_NAMES = (*_LOSS_METRICS, "stage1_nll", "stage2_nll", "stage3_nll")
_REQUIRED_PREDICTION_TYPES = {
    "variant": pa.string(),
    "test_year": pa.int64(),
    "race_id": pa.string(),
    "horse_id": pa.string(),
    "finish_position": pa.int64(),
    "score": pa.float64(),
    "temperature": pa.float64(),
    "p_win": pa.float64(),
    "p_top2": pa.float64(),
    "p_top3": pa.float64(),
    "in_jra_flat_graded_stakes": pa.bool_(),
}
_PROBABILITY_TOLERANCE = 1e-9
_RESIDUAL_ZERO_TOLERANCE = 1e-12
_RESIDUAL_DEFINITION = {
    "ratio": (
        "actual / expected; expected at most 1e-12 per horse is reported as 0 and the ratio is null."
    ),
    "z": (
        "(actual - expected) / sqrt(sum(p * (1 - p))); null when sum(p * (1 - p)) is at most "
        "1e-12 per horse. "
        "This is an independent-Bernoulli approximation, not a test statistic."
    ),
}


@dataclass(frozen=True)
class VariantComparison:
    """Name a candidate and baseline PL variant for a paired comparison."""

    candidate: str
    baseline: str


@dataclass(frozen=True)
class PLComparisonSettings:
    """Hold validated comparison pairs and paired-bootstrap parameters."""

    comparisons: tuple[VariantComparison, ...]
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence: float

    def __post_init__(self) -> None:
        """Reject ambiguous comparison requests and invalid bootstrap settings."""
        if not self.comparisons:
            raise ValueError("at least one variant comparison is required")
        pairs: set[tuple[str, str]] = set()
        for comparison in self.comparisons:
            if not isinstance(comparison, VariantComparison):
                raise ValueError("comparisons must contain VariantComparison values")
            if not comparison.candidate or not comparison.baseline:
                raise ValueError("comparison variants must be nonempty strings")
            if comparison.candidate == comparison.baseline:
                raise ValueError("comparison candidate and baseline must differ")
            pair = (comparison.candidate, comparison.baseline)
            if pair in pairs:
                raise ValueError("comparison pairs must be unique")
            pairs.add(pair)
        if (
            isinstance(self.bootstrap_resamples, bool)
            or not isinstance(self.bootstrap_resamples, int)
            or self.bootstrap_resamples < 1
        ):
            raise ValueError("bootstrap_resamples must be a positive integer")
        if isinstance(self.bootstrap_seed, bool) or not isinstance(self.bootstrap_seed, int):
            raise ValueError("bootstrap_seed must be an integer")
        if isinstance(self.bootstrap_confidence, bool):
            raise ValueError("bootstrap_confidence must be between zero and one")
        confidence = float(self.bootstrap_confidence)
        if not np.isfinite(confidence) or not 0.0 < confidence < 1.0:
            raise ValueError("bootstrap_confidence must be between zero and one")


@dataclass(frozen=True)
class NormalizedVariantPredictions:
    """Hold validated prediction rows in canonical variant/test-year/race order."""

    name: str
    row_test_years: IntArray
    row_race_ids: tuple[str, ...]
    race_test_years: IntArray
    race_ids: tuple[str, ...]
    horse_ids: tuple[str, ...]
    finish_positions: IntArray
    in_jra_flat_graded_stakes: BoolArray
    layout: RaceLayout
    marginals: MarginalProbabilities
    metrics: RaceProbabilityMetrics
    metrics_by_test_year: Mapping[int, RaceProbabilityMetrics]


@dataclass(frozen=True)
class NormalizedPredictions:
    """Hold comparable variants and their common test-year sequence."""

    variants: Mapping[str, NormalizedVariantPredictions]
    test_years: tuple[int, ...]


def normalize_pl_predictions(predictions: pa.Table) -> NormalizedPredictions:
    """Validate, recompute, and canonically order saved PL prediction rows.

    Rows are paired by ``(test_year, race_id, horse_id)`` rather than their
    source order. The function rejects duplicate keys, variant-label drift,
    fold temperatures that are not constant, and stored probabilities that do
    not reproduce from score and temperature.
    """
    _validate_prediction_schema(predictions)
    variant_names = _variant_names(predictions)
    variants = {
        name: _normalize_variant(predictions.filter(pc.equal(predictions["variant"], name)), name)
        for name in variant_names
    }
    reference = variants[variant_names[0]]
    for name in variant_names[1:]:
        _validate_variant_alignment(reference, variants[name])
    return NormalizedPredictions(
        variants=variants,
        test_years=tuple(sorted({int(year) for year in reference.race_test_years})),
    )


def build_pl_comparison_report(
    normalized: NormalizedPredictions,
    settings: PLComparisonSettings,
    segments: ResidualSegmentAssignments,
) -> dict[str, object]:
    """Return the comparison-report body for normalized prediction rows.

    The returned body is JSON-compatible and deliberately excludes I/O-bound
    provenance and artifact identity fields, which the CLI boundary owns.
    """
    _validate_comparison_variants(settings.comparisons, normalized.variants)
    masks, unavailable = _validated_segment_assignments(segments, normalized)

    variant_reports = {
        name: {
            "all_test_races": _variant_scope_report(
                variant, np.ones(variant.layout.race_count, dtype=np.bool_)
            ),
            JRA_FLAT_GRADED_STAKES_V1: _variant_scope_report(
                variant, variant.in_jra_flat_graded_stakes
            ),
        }
        for name, variant in normalized.variants.items()
    }
    comparisons = [
        _comparison_report(
            normalized.variants[comparison.candidate],
            normalized.variants[comparison.baseline],
            comparison,
            settings,
        )
        for comparison in settings.comparisons
    ]
    segment_reports: dict[str, object] = {
        "definition_version": PL_RESIDUAL_SEGMENTS_V1,
        "residual_definition": dict(_RESIDUAL_DEFINITION),
    }
    for name, definition in RESIDUAL_SEGMENT_DEFINITIONS.items():
        if name in unavailable:
            segment_reports[name] = {
                "definition": definition,
                "available": False,
                "reason": unavailable[name],
            }
            continue
        mask = masks[name]
        segment_reports[name] = {
            "definition": definition,
            "available": True,
            "variants": {
                variant_name: _residuals(variant, mask)
                for variant_name, variant in normalized.variants.items()
            },
        }
    return {
        "test_years": list(normalized.test_years),
        "variants": variant_reports,
        "comparisons": comparisons,
        "segments": segment_reports,
    }


def _validate_prediction_schema(predictions: pa.Table) -> None:
    """Reject tables that cannot be an evaluation prediction artifact."""
    if predictions.num_rows == 0:
        raise ValueError("predictions must not be empty")
    for name, expected_type in _REQUIRED_PREDICTION_TYPES.items():
        if name not in predictions.schema.names:
            raise ValueError(f"predictions is missing required column {name!r}")
        field = predictions.schema.field(name)
        if not field.type.equals(expected_type):
            raise ValueError(f"predictions column {name!r} has an unexpected type")
        if predictions[name].null_count:
            raise ValueError(f"predictions column {name!r} must not contain nulls")


def _variant_names(predictions: pa.Table) -> tuple[str, ...]:
    """Return the sorted nonempty names in a validated variant column."""
    values = pc.unique(predictions["variant"]).to_pylist()
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise ValueError("prediction variants must be nonempty strings")
    return tuple(sorted(cast(list[str], values)))


def _normalize_variant(predictions: pa.Table, name: str) -> NormalizedVariantPredictions:
    """Return one variant in its canonical key order after validation."""
    ordered = predictions.sort_by(
        [("test_year", "ascending"), ("race_id", "ascending"), ("horse_id", "ascending")]
    )
    payload = ordered.select(list(_REQUIRED_PREDICTION_TYPES)).to_pydict()
    test_years = _int_values(payload, "test_year", positive=True)
    race_ids = _string_values(payload, "race_id")
    horse_ids = _string_values(payload, "horse_id")
    finish_positions = _int_values(payload, "finish_position", positive=True)
    scores = _finite_float_values(payload, "score")
    temperatures = _positive_float_values(payload, "temperature")
    graded_rows = _bool_values(payload, "in_jra_flat_graded_stakes")
    stored_marginals = MarginalProbabilities(
        win=_probability_values(payload, "p_win"),
        top2=_probability_values(payload, "p_top2"),
        top3=_probability_values(payload, "p_top3"),
    )
    if np.any(stored_marginals.win > stored_marginals.top2) or np.any(
        stored_marginals.top2 > stored_marginals.top3
    ):
        raise ValueError("saved marginal probabilities must increase from win through top-three")

    race_starts = _race_starts(test_years, race_ids, horse_ids)
    group_sizes = np.diff(np.append(race_starts, len(test_years))).astype(np.int64)
    layout = RaceLayout.from_group_sizes(group_sizes.tolist())
    race_test_years = test_years[race_starts]
    race_id_values = tuple(race_ids[index] for index in race_starts)
    race_flags = _race_flags(graded_rows, race_starts)
    temperatures_by_year = _temperatures_by_year(test_years, temperatures)
    marginals, metrics, by_year = _recompute_values(
        scores,
        finish_positions,
        layout,
        race_test_years,
        temperatures_by_year,
    )
    _validate_stored_marginals(stored_marginals, marginals)
    return NormalizedVariantPredictions(
        name=name,
        row_test_years=test_years,
        row_race_ids=race_ids,
        race_test_years=race_test_years,
        race_ids=race_id_values,
        horse_ids=tuple(horse_ids),
        finish_positions=finish_positions,
        in_jra_flat_graded_stakes=race_flags,
        layout=layout,
        marginals=marginals,
        metrics=metrics,
        metrics_by_test_year=by_year,
    )


def _int_values(payload: Mapping[str, object], name: str, *, positive: bool) -> IntArray:
    """Return an integer prediction column after validating its values."""
    values = _column_values(payload, name)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError(f"predictions column {name!r} must contain integers")
    result = np.asarray(values, dtype=np.int64)
    if positive and np.any(result <= 0):
        raise ValueError(f"predictions column {name!r} must contain positive integers")
    return result


def _string_values(payload: Mapping[str, object], name: str) -> tuple[str, ...]:
    """Return a nonempty string prediction column."""
    values = _column_values(payload, name)
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"predictions column {name!r} must contain nonempty strings")
    return tuple(cast(str, value) for value in values)


def _finite_float_values(payload: Mapping[str, object], name: str) -> FloatArray:
    """Return a finite floating-point prediction column."""
    try:
        result = np.asarray(_column_values(payload, name), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"predictions column {name!r} must contain numbers") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"predictions column {name!r} must contain finite values")
    return result


def _positive_float_values(payload: Mapping[str, object], name: str) -> FloatArray:
    """Return a strictly positive floating-point prediction column."""
    result = _finite_float_values(payload, name)
    if np.any(result <= 0.0):
        raise ValueError(f"predictions column {name!r} must contain positive values")
    return result


def _probability_values(payload: Mapping[str, object], name: str) -> FloatArray:
    """Return a probability column within the persisted tolerance."""
    result = _finite_float_values(payload, name)
    if np.any((result < -_PROBABILITY_TOLERANCE) | (result > 1.0 + _PROBABILITY_TOLERANCE)):
        raise ValueError(f"predictions column {name!r} must contain probabilities")
    return result


def _bool_values(payload: Mapping[str, object], name: str) -> BoolArray:
    """Return a boolean prediction column."""
    values = _column_values(payload, name)
    if any(not isinstance(value, bool) for value in values):
        raise ValueError(f"predictions column {name!r} must contain booleans")
    return np.asarray(values, dtype=np.bool_)


def _column_values(payload: Mapping[str, object], name: str) -> list[object]:
    """Return one dynamic Arrow column as a checked Python list."""
    values = payload[name]
    if not isinstance(values, list):
        raise ValueError(f"predictions column {name!r} must be a list")
    return values


def _race_starts(
    test_years: IntArray, race_ids: Sequence[str], horse_ids: Sequence[str]
) -> IntArray:
    """Return starts of unique race keys and reject duplicate horse keys."""
    starts = [0]
    for index in range(1, len(test_years)):
        same_race = (
            test_years[index] == test_years[index - 1] and race_ids[index] == race_ids[index - 1]
        )
        if same_race:
            if horse_ids[index] == horse_ids[index - 1]:
                raise ValueError("predictions contain duplicate variant/test-year/race/horse keys")
            continue
        starts.append(index)
    return np.asarray(starts, dtype=np.int64)


def _race_flags(values: BoolArray, race_starts: IntArray) -> BoolArray:
    """Return the race-level subset flag after enforcing within-race agreement."""
    stops = np.append(race_starts[1:], len(values))
    result = np.empty(len(race_starts), dtype=np.bool_)
    for index, (start, stop) in enumerate(zip(race_starts, stops, strict=True)):
        flag = values[start]
        if np.any(values[start:stop] != flag):
            raise ValueError("in_jra_flat_graded_stakes must agree within each race")
        result[index] = flag
    return result


def _temperatures_by_year(test_years: IntArray, temperatures: FloatArray) -> dict[int, float]:
    """Return one required temperature for every test year."""
    result: dict[int, float] = {}
    for year in np.unique(test_years):
        values = temperatures[test_years == year]
        if not np.all(values == values[0]):
            raise ValueError("temperature must be constant within each variant and test year")
        result[int(year)] = float(values[0])
    return result


def _recompute_values(
    scores: FloatArray,
    finish_positions: IntArray,
    layout: RaceLayout,
    race_test_years: IntArray,
    temperatures: Mapping[int, float],
) -> tuple[MarginalProbabilities, RaceProbabilityMetrics, dict[int, RaceProbabilityMetrics]]:
    """Recompute marginal probabilities and race metrics with yearly temperatures."""
    win = np.empty(layout.row_count, dtype=np.float64)
    top2 = np.empty(layout.row_count, dtype=np.float64)
    top3 = np.empty(layout.row_count, dtype=np.float64)
    by_year: dict[int, RaceProbabilityMetrics] = {}
    metrics: list[RaceProbabilityMetrics] = []
    race_offsets = layout.offsets
    for year in sorted(temperatures):
        race_indices = np.flatnonzero(race_test_years == year)
        if len(race_indices) == 0:
            continue
        first_race = int(race_indices[0])
        last_race = int(race_indices[-1]) + 1
        if not np.array_equal(race_indices, np.arange(first_race, last_race)):
            raise ValueError("test-year races must be contiguous after normalization")
        row_start = int(race_offsets[first_race])
        row_stop = int(race_offsets[last_race])
        yearly_layout = RaceLayout.from_group_sizes(layout.group_sizes[first_race:last_race])
        temperature = temperatures[year]
        yearly_marginals = top3_marginal_probabilities(
            scores[row_start:row_stop], yearly_layout, temperature=temperature
        )
        yearly_metrics = race_probability_metrics(
            scores[row_start:row_stop],
            finish_positions[row_start:row_stop],
            yearly_layout,
            temperature=temperature,
        )
        win[row_start:row_stop] = yearly_marginals.win
        top2[row_start:row_stop] = yearly_marginals.top2
        top3[row_start:row_stop] = yearly_marginals.top3
        by_year[year] = yearly_metrics
        metrics.append(yearly_metrics)
    return (
        MarginalProbabilities(win=win, top2=top2, top3=top3),
        _concatenate_metrics(metrics),
        by_year,
    )


def _validate_stored_marginals(
    stored: MarginalProbabilities,
    recomputed: MarginalProbabilities,
) -> None:
    """Reject stored probability columns that do not match the PL calculation."""
    for name in ("win", "top2", "top3"):
        if not np.allclose(
            getattr(stored, name),
            getattr(recomputed, name),
            rtol=0.0,
            atol=_PROBABILITY_TOLERANCE,
        ):
            raise ValueError(f"saved p_{name} does not match score and temperature")


def _validate_variant_alignment(
    reference: NormalizedVariantPredictions,
    candidate: NormalizedVariantPredictions,
) -> None:
    """Reject variants whose key set or shared labels differ from the reference."""
    if (
        reference.layout.group_sizes != candidate.layout.group_sizes
        or not np.array_equal(reference.race_test_years, candidate.race_test_years)
        or reference.race_ids != candidate.race_ids
        or reference.horse_ids != candidate.horse_ids
    ):
        raise ValueError("variants must contain the same test-year/race/horse keys")
    if not np.array_equal(reference.finish_positions, candidate.finish_positions):
        raise ValueError("variants must agree on finish_position")
    if not np.array_equal(reference.in_jra_flat_graded_stakes, candidate.in_jra_flat_graded_stakes):
        raise ValueError("variants must agree on in_jra_flat_graded_stakes")


def _validate_comparison_variants(
    comparisons: Sequence[VariantComparison],
    variants: Mapping[str, NormalizedVariantPredictions],
) -> None:
    """Reject comparison names absent from the saved predictions."""
    available = set(variants)
    for comparison in comparisons:
        missing = {comparison.candidate, comparison.baseline} - available
        if missing:
            raise ValueError(
                f"comparison variants are absent from predictions: {sorted(missing)!r}"
            )


def _validated_segment_assignments(
    assignments: ResidualSegmentAssignments,
    normalized: NormalizedPredictions,
) -> tuple[dict[str, BoolArray], dict[str, str]]:
    """Validate segment masks against the canonical shared horse-row order."""
    reference = next(iter(normalized.variants.values()))
    masks = assignments.member_masks
    unavailable = assignments.unavailable
    known = set(RESIDUAL_SEGMENT_DEFINITIONS)
    if set(masks) | set(unavailable) != known or set(masks) & set(unavailable):
        raise ValueError("segment assignments must cover every fixed segment exactly once")
    result: dict[str, BoolArray] = {}
    for name, mask in masks.items():
        values = np.asarray(mask)
        if (
            values.dtype != np.bool_
            or values.ndim != 1
            or len(values) != reference.layout.row_count
        ):
            raise ValueError("segment masks must be boolean arrays matching prediction rows")
        result[name] = values
    if any(not isinstance(reason, str) or not reason for reason in unavailable.values()):
        raise ValueError("unavailable segment reasons must be nonempty strings")
    return result, dict(unavailable)


def _variant_scope_report(
    variant: NormalizedVariantPredictions,
    race_mask: BoolArray,
) -> dict[str, object]:
    """Return pooled and per-test-year metric means for a race subset."""
    return {
        "pooled": _metric_summary(variant.metrics, race_mask),
        "by_test_year": {
            str(year): _metric_summary(
                variant.metrics_by_test_year[year],
                race_mask[variant.race_test_years == year],
            )
            for year in sorted(variant.metrics_by_test_year)
        },
    }


def _comparison_report(
    candidate: NormalizedVariantPredictions,
    baseline: NormalizedVariantPredictions,
    comparison: VariantComparison,
    settings: PLComparisonSettings,
) -> dict[str, object]:
    """Return paired-comparison reports for all races and graded stakes."""
    all_races = np.ones(candidate.layout.race_count, dtype=np.bool_)
    return {
        "candidate": comparison.candidate,
        "baseline": comparison.baseline,
        "all_test_races": _comparison_scope_report(candidate, baseline, all_races, settings),
        JRA_FLAT_GRADED_STAKES_V1: _comparison_scope_report(
            candidate,
            baseline,
            candidate.in_jra_flat_graded_stakes,
            settings,
        ),
    }


def _comparison_scope_report(
    candidate: NormalizedVariantPredictions,
    baseline: NormalizedVariantPredictions,
    race_mask: BoolArray,
    settings: PLComparisonSettings,
) -> dict[str, object]:
    """Return pooled and yearly bootstrap comparisons for one race subset."""
    return {
        "pooled": _paired_metrics(candidate.metrics, baseline.metrics, race_mask, settings),
        "by_test_year": {
            str(year): _paired_metrics(
                candidate.metrics_by_test_year[year],
                baseline.metrics_by_test_year[year],
                race_mask[candidate.race_test_years == year],
                settings,
            )
            for year in sorted(candidate.metrics_by_test_year)
        },
    }


def _metric_summary(metrics: RaceProbabilityMetrics, mask: BoolArray) -> dict[str, object] | None:
    """Return race-equally weighted metric means, or null for an empty subset."""
    if not np.any(mask):
        return None
    return {
        "race_count": int(mask.sum()),
        **{name: float(np.mean(getattr(metrics, name)[mask])) for name in _LOSS_METRICS},
        **{
            f"stage{index + 1}_nll": float(np.mean(metrics.stage_nll[mask, index]))
            for index in range(3)
        },
    }


def _paired_metrics(
    candidate: RaceProbabilityMetrics,
    baseline: RaceProbabilityMetrics,
    mask: BoolArray,
    settings: PLComparisonSettings,
) -> dict[str, object] | None:
    """Return the named paired-bootstrap comparison for every report metric."""
    if not np.any(mask):
        return None
    values: dict[str, object] = {"race_count": int(mask.sum())}
    for name in _LOSS_METRICS:
        values[name] = _paired_metric(
            getattr(candidate, name)[mask],
            getattr(baseline, name)[mask],
            settings,
        )
    for index in range(3):
        values[f"stage{index + 1}_nll"] = _paired_metric(
            candidate.stage_nll[mask, index],
            baseline.stage_nll[mask, index],
            settings,
        )
    return values


def _paired_metric(
    candidate: FloatArray,
    baseline: FloatArray,
    settings: PLComparisonSettings,
) -> dict[str, object]:
    """Return one report-shaped paired-bootstrap comparison."""
    result = paired_bootstrap_comparison(
        candidate,
        baseline,
        resamples=settings.bootstrap_resamples,
        seed=settings.bootstrap_seed,
        confidence=settings.bootstrap_confidence,
    )
    conclusion: Literal["candidate_better", "baseline_better", "inconclusive"]
    if result.conclusion == "model_better":
        conclusion = "candidate_better"
    elif result.conclusion == "market_better":
        conclusion = "baseline_better"
    else:
        conclusion = "inconclusive"
    return {
        "candidate_mean": result.model_mean,
        "baseline_mean": result.market_mean,
        "mean_difference": result.mean_difference,
        "confidence_interval_lower": result.confidence_interval_lower,
        "confidence_interval_upper": result.confidence_interval_upper,
        "conclusion": conclusion,
    }


def _residuals(variant: NormalizedVariantPredictions, mask: BoolArray) -> dict[str, object]:
    """Return win and top-three residual summaries for one horse segment."""
    return {
        "horses": int(mask.sum()),
        "win": _residual(variant.marginals.win[mask], variant.finish_positions[mask] == 1),
        "top3": _residual(variant.marginals.top3[mask], variant.finish_positions[mask] <= 3),
    }


def _residual(probabilities: FloatArray, outcomes: BoolArray) -> dict[str, float | int | None]:
    """Return one independent-Bernoulli standardized residual approximation."""
    actual = int(outcomes.sum())
    expected = float(probabilities.sum())
    variance = float(np.sum(probabilities * (1.0 - probabilities)))
    zero_tolerance = _RESIDUAL_ZERO_TOLERANCE * len(probabilities)
    if expected <= zero_tolerance:
        expected = 0.0
    if variance <= zero_tolerance:
        variance = 0.0
    ratio = None if expected == 0.0 else actual / expected
    z = None if variance == 0.0 else (actual - expected) / float(np.sqrt(variance))
    return {"actual": actual, "expected": expected, "ratio": ratio, "z": z}


def _concatenate_metrics(values: Sequence[RaceProbabilityMetrics]) -> RaceProbabilityMetrics:
    """Concatenate per-year race metrics in canonical test-year order."""
    return RaceProbabilityMetrics(
        **{
            name: np.concatenate([getattr(value, name) for value in values])
            for name in (*_LOSS_METRICS, "stage_nll")
        }
    )


__all__ = [
    "NormalizedPredictions",
    "NormalizedVariantPredictions",
    "PLComparisonSettings",
    "VariantComparison",
    "build_pl_comparison_report",
    "normalize_pl_predictions",
]
