"""Evaluate hit-conditional final-odds corrections in yearly expanding folds.

This module is the pure ADR-042 experiment layer.  Callers supply already
assembled race observations plus immutable snapshot and provenance values; no
filesystem, dataset, configuration or CLI access occurs here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from statistics import median
from typing import Literal, cast

from models.evaluation.final_odds_metrics import (
    BootstrapInterval,
    FinalOddsBootstrap,
    FinalOddsBootstrapDifference,
    FinalOddsMetrics,
    bootstrap_final_odds_metrics,
    final_odds_metrics,
    paired_bootstrap_final_odds_metrics,
)
from models.market.final_odds_correction import (
    FinalOddsCorrection,
    fit_all_correction,
    fit_graded_correction,
    validate_odds_bands,
    validate_quantiles,
)
from models.serialization.final_odds_observations import (
    BET_TYPES,
    BetType,
    HitObservation,
    RaceObservations,
)
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1

CorrectionVariant = Literal["all", "graded", "none"]

_CORRECTION_VARIANTS: tuple[CorrectionVariant, ...] = ("all", "graded", "none")
_PRIMARY_PERIOD = "all_test_years"
_EARLY_PERIOD = "2016_2020"


@dataclass(frozen=True)
class FinalOddsEvaluationSettings:
    """Hold the validated pure settings for a final-odds evaluation."""

    train_start_year: int
    test_years: tuple[int, ...]
    bands: Mapping[BetType, tuple[float, ...]]
    quantiles: tuple[float, ...]
    min_hits: int
    graded_shrinkage_k: int
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence: float

    def __post_init__(self) -> None:
        """Reject settings that cannot define an unambiguous yearly evaluation."""
        _positive_year(self.train_start_year, "train_start_year")
        if not self.test_years:
            raise ValueError("test_years must not be empty")
        if any(not _is_year(year) for year in self.test_years):
            raise ValueError("test_years must contain four-digit integer years")
        if any(year <= self.train_start_year for year in self.test_years):
            raise ValueError("every test year must be after train_start_year")
        if any(
            right <= left for left, right in zip(self.test_years, self.test_years[1:], strict=False)
        ):
            raise ValueError("test_years must be strictly increasing without duplicates")
        if set(self.bands) != set(BET_TYPES):
            raise ValueError(f"bands must have exactly these bet types: {BET_TYPES!r}")
        for bet_type in BET_TYPES:
            validate_odds_bands(self.bands[bet_type])
        validate_quantiles(self.quantiles)
        _positive_integer(self.min_hits, "min_hits")
        _nonnegative_integer(self.graded_shrinkage_k, "graded_shrinkage_k")
        _positive_integer(self.bootstrap_resamples, "bootstrap_resamples")
        _nonnegative_integer(self.bootstrap_seed, "bootstrap_seed")
        if (
            isinstance(self.bootstrap_confidence, bool)
            or not isinstance(self.bootstrap_confidence, Real)
            or not isfinite(float(self.bootstrap_confidence))
            or not 0.0 < float(self.bootstrap_confidence) < 1.0
        ):
            raise ValueError("bootstrap_confidence must be a finite number between zero and one")


@dataclass(frozen=True)
class FinalOddsRaceSubset:
    """Describe one named race subset and the source used to classify it."""

    race_ids: frozenset[str]
    definition: str
    source: Mapping[str, object]

    def __post_init__(self) -> None:
        """Reject non-serializable subset identities at the pure boundary."""
        if not isinstance(self.definition, str) or not self.definition:
            raise ValueError("race subset definition must be a nonempty string")
        if not isinstance(self.source, Mapping):
            raise ValueError("race subset source must be a mapping")
        if any(not isinstance(race_id, str) or not race_id for race_id in self.race_ids):
            raise ValueError("race subset race_ids must be nonempty strings")


@dataclass(frozen=True)
class FinalOddsSelection:
    """Record the Decision 6 result for one bet type."""

    selected_variant: CorrectionVariant | None
    reason: str
    all_compatible: bool
    graded_compatible: bool


@dataclass(frozen=True)
class FinalOddsEvaluation:
    """Hold the JSON-compatible report payload of one pure evaluation."""

    report: dict[str, object]


@dataclass
class _MetricRows:
    """Accumulate the aligned rows needed for one metrics calculation."""

    race_ids: list[str]
    freeze_odds: list[float]
    final_odds: list[float]
    predicted_odds: list[float]
    interval_lower: list[float] | None
    interval_upper: list[float] | None

    @classmethod
    def empty(cls, *, has_interval: bool) -> _MetricRows:
        """Return an empty collector for one correction variant."""
        return cls([], [], [], [], [] if has_interval else None, [] if has_interval else None)

    def append(
        self,
        observation: HitObservation,
        *,
        predicted_odds: float,
        interval_lower: float | None,
        interval_upper: float | None,
    ) -> None:
        """Append one aligned observation and its optional prediction interval."""
        if (interval_lower is None) != (interval_upper is None):
            raise ValueError("prediction interval bounds must be provided together")
        if self.interval_lower is None or self.interval_upper is None:
            if interval_lower is not None:
                raise ValueError("this metric collector does not accept prediction intervals")
        elif interval_lower is None or interval_upper is None:
            raise ValueError("this metric collector requires prediction intervals")
        self.race_ids.append(observation.race_id)
        self.freeze_odds.append(observation.freeze_odds)
        self.final_odds.append(observation.final_odds)
        self.predicted_odds.append(predicted_odds)
        if self.interval_lower is not None and self.interval_upper is not None:
            assert interval_lower is not None
            assert interval_upper is not None
            self.interval_lower.append(interval_lower)
            self.interval_upper.append(interval_upper)


type _MetricMatrix = dict[CorrectionVariant, dict[str, dict[BetType, _MetricRows]]]
type _BootstrapMatrix = dict[CorrectionVariant, dict[str, dict[BetType, FinalOddsBootstrap]]]


def evaluate_final_odds(
    race_observations: Sequence[RaceObservations],
    settings: FinalOddsEvaluationSettings,
    *,
    race_subsets: Mapping[str, FinalOddsRaceSubset],
    config: Mapping[str, object],
    snapshot: Mapping[str, object],
    provenance: Mapping[str, object],
) -> FinalOddsEvaluation:
    """Return the complete pure ADR-042 report for yearly expanding folds.

    Each fold fits both corrected variants only on hits whose race year is at
    least ``train_start_year`` and strictly earlier than the fold's test year.
    The test year's final payouts are used solely for metrics.  ``config``,
    ``snapshot`` and ``provenance`` are values prepared by the later CLI layer
    and are copied into the JSON payload without any I/O here.
    """
    races, race_years = _validate_race_observations(race_observations)
    subsets = _validate_race_subsets(race_subsets)
    _validate_report_values(config, "config")
    _validate_report_values(snapshot, "snapshot")
    _validate_report_values(provenance, "provenance")
    subset_names = ("all", *sorted(subsets))
    all_hits = tuple(hit for race in races for hit in race.hits)
    pooled = {
        _PRIMARY_PERIOD: _metric_matrix(subset_names),
        _EARLY_PERIOD: _metric_matrix(subset_names),
    }
    fold_reports: list[dict[str, object]] = []
    for test_year in settings.test_years:
        train_hits = tuple(
            hit
            for hit in all_hits
            if settings.train_start_year <= race_years[hit.race_id] < test_year
        )
        test_hits = tuple(hit for hit in all_hits if race_years[hit.race_id] == test_year)
        corrections = _fit_corrections(train_hits, settings, subsets)
        fold_rows = _metric_matrix(subset_names)
        _score_hits(
            test_hits,
            corrections,
            settings,
            subsets,
            fold_rows,
            pooled[_PRIMARY_PERIOD],
        )
        if 2016 <= test_year <= 2020:
            _score_hits(
                test_hits,
                corrections,
                settings,
                subsets,
                pooled[_EARLY_PERIOD],
            )
        fold_reports.append(
            {
                "test_year": test_year,
                "train_start_year": settings.train_start_year,
                "train_end_year": test_year - 1,
                "corrections": _corrections_payload(corrections),
                "metrics": _metrics_payload(fold_rows, settings),
            }
        )
    pooled_payload: dict[str, object] = {}
    pooled_bootstraps: dict[str, _BootstrapMatrix] = {}
    pooled_years = {
        _PRIMARY_PERIOD: sorted(settings.test_years),
        _EARLY_PERIOD: sorted(year for year in settings.test_years if 2016 <= year <= 2020),
    }
    for name, rows in pooled.items():
        payload, bootstraps = _pooled_payload(rows, settings)
        pooled_payload[name] = {"test_years": pooled_years[name], **payload}
        pooled_bootstraps[name] = bootstraps
    primary_bootstraps = pooled_bootstraps[_PRIMARY_PERIOD]
    selections = {
        bet_type: _selection_payload(
            select_final_odds_variant(
                primary_bootstraps["all"][JRA_FLAT_GRADED_STAKES_V1][bet_type],
                primary_bootstraps["graded"][JRA_FLAT_GRADED_STAKES_V1][bet_type],
            ),
            all_bootstrap=primary_bootstraps["all"][JRA_FLAT_GRADED_STAKES_V1][bet_type],
            graded_bootstrap=primary_bootstraps["graded"][JRA_FLAT_GRADED_STAKES_V1][bet_type],
        )
        for bet_type in BET_TYPES
    }
    return FinalOddsEvaluation(
        {
            "format": "final_odds_evaluation",
            "format_version": 1,
            "config": dict(config),
            "snapshot": dict(snapshot),
            "provenance": dict(provenance),
            "race_subsets": {
                name: {"definition": subset.definition, "source": dict(subset.source)}
                for name, subset in sorted(subsets.items())
            },
            "selection": selections,
            "counts": _counts_payload(races, race_years),
            "folds": fold_reports,
            "pooled": pooled_payload,
        }
    )


def select_final_odds_variant(
    all_bootstrap: FinalOddsBootstrap,
    graded_bootstrap: FinalOddsBootstrap,
) -> FinalOddsSelection:
    """Apply ADR-042 Decision 6 to one bet type's pooled bootstrap intervals."""
    all_compatible = _is_compatible(all_bootstrap)
    graded_compatible = _is_compatible(graded_bootstrap)
    if graded_compatible and not all_compatible:
        return FinalOddsSelection("graded", "graded_only_compatible", False, True)
    if all_compatible:
        reason = "both_compatible_select_all" if graded_compatible else "all_only_compatible"
        return FinalOddsSelection("all", reason, True, graded_compatible)
    return FinalOddsSelection(None, "neither_compatible", False, False)


def _fit_corrections(
    train_hits: Sequence[HitObservation],
    settings: FinalOddsEvaluationSettings,
    subsets: Mapping[str, FinalOddsRaceSubset],
) -> dict[CorrectionVariant, dict[BetType, FinalOddsCorrection | None]]:
    """Fit the two leakage-safe corrected variants for one yearly fold."""
    all_corrections: dict[BetType, FinalOddsCorrection] = {}
    graded_corrections: dict[BetType, FinalOddsCorrection] = {}
    graded_race_ids = subsets[JRA_FLAT_GRADED_STAKES_V1].race_ids
    for bet_type in BET_TYPES:
        all_hits = [hit for hit in train_hits if hit.bet_type == bet_type]
        if not all_hits:
            raise ValueError(f"no training hits for {bet_type!r}")
        bands = settings.bands[bet_type]
        all_correction = fit_all_correction(
            [hit.freeze_odds for hit in all_hits],
            [hit.final_odds for hit in all_hits],
            bands=bands,
            quantiles=settings.quantiles,
            min_hits=settings.min_hits,
        )
        graded_hits = [hit for hit in all_hits if hit.race_id in graded_race_ids]
        graded_corrections[bet_type] = fit_graded_correction(
            [hit.freeze_odds for hit in graded_hits],
            [hit.final_odds for hit in graded_hits],
            bands=bands,
            quantiles=settings.quantiles,
            min_hits=settings.min_hits,
            shrinkage_k=settings.graded_shrinkage_k,
            all_correction=all_correction,
        )
        all_corrections[bet_type] = all_correction
    return {
        "all": {bet_type: correction for bet_type, correction in all_corrections.items()},
        "graded": {bet_type: correction for bet_type, correction in graded_corrections.items()},
        "none": {bet_type: None for bet_type in BET_TYPES},
    }


def _score_hits(
    hits: Sequence[HitObservation],
    corrections: Mapping[CorrectionVariant, Mapping[BetType, FinalOddsCorrection | None]],
    settings: FinalOddsEvaluationSettings,
    subsets: Mapping[str, FinalOddsRaceSubset],
    *matrices: _MetricMatrix,
) -> None:
    """Score one test-year's hits into one or more aligned metric matrices."""
    for hit in hits:
        predictions = _predictions_for_hit(hit, corrections)
        names = ["all"]
        names.extend(name for name, subset in subsets.items() if hit.race_id in subset.race_ids)
        for variant, (predicted, lower, upper) in predictions.items():
            for name in names:
                for matrix in matrices:
                    matrix[variant][name][hit.bet_type].append(
                        hit,
                        predicted_odds=predicted,
                        interval_lower=lower,
                        interval_upper=upper,
                    )


def _predictions_for_hit(
    hit: HitObservation,
    corrections: Mapping[CorrectionVariant, Mapping[BetType, FinalOddsCorrection | None]],
) -> dict[CorrectionVariant, tuple[float, float | None, float | None]]:
    """Return all three predictions for one hit, including corrected intervals."""
    result: dict[CorrectionVariant, tuple[float, float | None, float | None]] = {
        "none": (hit.freeze_odds, None, None)
    }
    for variant in ("all", "graded"):
        correction = corrections[variant][hit.bet_type]
        if correction is None:
            raise AssertionError(f"{variant} correction must exist for every bet type")
        estimate = correction.estimate(hit.freeze_odds)
        result[variant] = (
            estimate.final_odds,
            estimate.final_odds_quantiles[0],
            estimate.final_odds_quantiles[-1],
        )
    return result


def _metric_matrix(subset_names: Sequence[str]) -> _MetricMatrix:
    """Return empty metric collectors for every required result combination."""
    return {
        variant: {
            subset_name: {
                bet_type: _MetricRows.empty(has_interval=variant != "none")
                for bet_type in BET_TYPES
            }
            for subset_name in subset_names
        }
        for variant in _CORRECTION_VARIANTS
    }


def _metrics_payload(
    rows: _MetricMatrix,
    settings: FinalOddsEvaluationSettings,
) -> dict[str, object]:
    """Return JSON-compatible metric summaries for a fold or pooled population."""
    return {
        variant: {
            subset_name: {
                bet_type: _final_metrics_payload(_final_metrics(values, settings.bands[bet_type]))
                for bet_type, values in by_bet.items()
            }
            for subset_name, by_bet in by_subset.items()
        }
        for variant, by_subset in rows.items()
    }


def _pooled_payload(
    rows: _MetricMatrix,
    settings: FinalOddsEvaluationSettings,
) -> tuple[dict[str, object], _BootstrapMatrix]:
    """Return pooled metrics, bootstrap intervals and paired differences."""
    metrics = _metrics_payload(rows, settings)
    bootstraps: _BootstrapMatrix = {
        variant: {
            subset_name: {
                bet_type: _bootstrap_metrics(values, settings)
                for bet_type, values in by_bet.items()
            }
            for subset_name, by_bet in by_subset.items()
        }
        for variant, by_subset in rows.items()
    }
    bootstrap_payload = {
        variant: {
            subset_name: {
                bet_type: _bootstrap_payload(values) for bet_type, values in by_bet.items()
            }
            for subset_name, by_bet in by_subset.items()
        }
        for variant, by_subset in bootstraps.items()
    }
    return (
        {
            "metrics": metrics,
            "bootstrap": bootstrap_payload,
            "differences": _differences_payload(rows, settings),
        },
        bootstraps,
    )


def _differences_payload(
    rows: _MetricMatrix,
    settings: FinalOddsEvaluationSettings,
) -> dict[str, object]:
    """Return the required paired corrected-variant comparisons."""
    pairs: tuple[tuple[str, CorrectionVariant, CorrectionVariant], ...] = (
        ("all_minus_none", "all", "none"),
        ("graded_minus_none", "graded", "none"),
        ("all_minus_graded", "all", "graded"),
    )
    result: dict[str, object] = {}
    for name, left_variant, right_variant in pairs:
        by_subset: dict[str, object] = {}
        for subset_name in rows[left_variant]:
            by_bet: dict[str, object] = {}
            for bet_type in BET_TYPES:
                left = rows[left_variant][subset_name][bet_type]
                right = rows[right_variant][subset_name][bet_type]
                by_bet[bet_type] = _difference_payload(_paired_difference(left, right, settings))
            by_subset[subset_name] = by_bet
        result[name] = by_subset
    return result


def _final_metrics(rows: _MetricRows, bands: Sequence[float]) -> FinalOddsMetrics:
    """Calculate one final-odds metric object from aligned collector rows."""
    return final_odds_metrics(
        rows.freeze_odds,
        rows.final_odds,
        rows.predicted_odds,
        bands=bands,
        interval_lower=rows.interval_lower,
        interval_upper=rows.interval_upper,
    )


def _bootstrap_metrics(
    rows: _MetricRows,
    settings: FinalOddsEvaluationSettings,
) -> FinalOddsBootstrap:
    """Return selection bootstrap intervals for one pooled metric collector."""
    return bootstrap_final_odds_metrics(
        rows.race_ids,
        rows.final_odds,
        rows.predicted_odds,
        resamples=settings.bootstrap_resamples,
        seed=settings.bootstrap_seed,
        confidence=settings.bootstrap_confidence,
    )


def _paired_difference(
    left: _MetricRows,
    right: _MetricRows,
    settings: FinalOddsEvaluationSettings,
) -> FinalOddsBootstrapDifference:
    """Return a paired bootstrap difference after verifying row alignment."""
    if left.race_ids != right.race_ids or left.final_odds != right.final_odds:
        raise AssertionError("paired correction metrics must use identical hit observations")
    return paired_bootstrap_final_odds_metrics(
        left.race_ids,
        left.final_odds,
        left.predicted_odds,
        right.predicted_odds,
        resamples=settings.bootstrap_resamples,
        seed=settings.bootstrap_seed,
        confidence=settings.bootstrap_confidence,
    )


def _corrections_payload(
    corrections: Mapping[CorrectionVariant, Mapping[BetType, FinalOddsCorrection | None]],
) -> dict[str, object]:
    """Return serializable fitted-band details, including merge and shrinkage data."""
    return {
        variant: {
            bet_type: (None if correction is None else _correction_payload(correction))
            for bet_type, correction in by_bet.items()
        }
        for variant, by_bet in corrections.items()
    }


def _correction_payload(correction: FinalOddsCorrection) -> dict[str, object]:
    """Return every persisted fitting value of one correction."""
    return {
        "band_edges": list(correction.band_edges),
        "quantile_levels": list(correction.quantile_levels),
        "bands": [
            {
                "lower": band.lower,
                "upper": band.upper,
                "source_lowers": list(band.source_lowers),
                "hit_count": band.hit_count,
                "mean_ratio": band.mean_ratio,
                "mean_log_freeze_odds": band.mean_log_freeze_odds,
                "ratio_quantiles": (
                    None if band.ratio_quantiles is None else list(band.ratio_quantiles)
                ),
                "shrinkage_target": band.shrinkage_target,
                "shrinkage_k": band.shrinkage_k,
            }
            for band in correction.bands
        ],
    }


def _final_metrics_payload(metrics: FinalOddsMetrics) -> dict[str, object]:
    """Return JSON-compatible summary and configured-band metric values."""
    return {
        "hits": metrics.hits,
        "payout_ratio": metrics.payout_ratio,
        "mean_payout_ratio": metrics.mean_payout_ratio,
        "median_abs_error_pct": metrics.median_abs_error_pct,
        "within_10pct": metrics.within_10pct,
        "over_20pct": metrics.over_20pct,
        "mean_log_error": metrics.mean_log_error,
        "interval_coverage": metrics.interval_coverage,
        "bands": [
            {
                "lower": band.lower,
                "upper": band.upper,
                "hits": band.hits,
                "payout_ratio": band.payout_ratio,
                "mean_payout_ratio": band.mean_payout_ratio,
            }
            for band in metrics.bands
        ],
    }


def _bootstrap_payload(bootstrap: FinalOddsBootstrap) -> dict[str, object]:
    """Return both Decision 6 bootstrap intervals as JSON-compatible values."""
    return {
        "payout_ratio": _interval_payload(bootstrap.payout_ratio),
        "mean_payout_ratio": _interval_payload(bootstrap.mean_payout_ratio),
    }


def _difference_payload(difference: FinalOddsBootstrapDifference) -> dict[str, object]:
    """Return both paired bootstrap-difference intervals as JSON-compatible values."""
    return {
        "payout_ratio": _interval_payload(difference.payout_ratio),
        "mean_payout_ratio": _interval_payload(difference.mean_payout_ratio),
    }


def _interval_payload(interval: BootstrapInterval) -> dict[str, float | None]:
    """Return a JSON-compatible percentile bootstrap interval."""
    return {
        "point_estimate": interval.point_estimate,
        "confidence_interval_lower": interval.confidence_interval_lower,
        "confidence_interval_upper": interval.confidence_interval_upper,
    }


def _selection_payload(
    selection: FinalOddsSelection,
    *,
    all_bootstrap: FinalOddsBootstrap,
    graded_bootstrap: FinalOddsBootstrap,
) -> dict[str, object]:
    """Return a selection decision together with its Decision 6 evidence."""
    return {
        "selected_variant": selection.selected_variant,
        "reason": selection.reason,
        "all_compatible": selection.all_compatible,
        "graded_compatible": selection.graded_compatible,
        "all": _bootstrap_payload(all_bootstrap),
        "graded": _bootstrap_payload(graded_bootstrap),
    }


def _is_compatible(bootstrap: FinalOddsBootstrap) -> bool:
    """Return whether both required confidence intervals contain one."""
    return _interval_contains_one(bootstrap.payout_ratio) and _interval_contains_one(
        bootstrap.mean_payout_ratio
    )


def _interval_contains_one(interval: BootstrapInterval) -> bool:
    """Return whether a nonempty interval includes the neutral value one."""
    return (
        interval.confidence_interval_lower is not None
        and interval.confidence_interval_upper is not None
        and interval.confidence_interval_lower <= 1.0 <= interval.confidence_interval_upper
    )


def _counts_payload(
    races: Sequence[RaceObservations],
    race_years: Mapping[str, int],
) -> dict[str, object]:
    """Return the report's non-I/O observation, hold and publication-age counts."""
    races_by_year: dict[int, int] = {}
    race_holds: dict[str, int] = {}
    table_holds: dict[str, dict[str, int]] = {"o1": {}, "o2": {}}
    hits: dict[BetType, int] = {bet_type: 0 for bet_type in BET_TYPES}
    exclusions: dict[BetType, dict[str, int]] = {bet_type: {} for bet_type in BET_TYPES}
    ages: dict[int, list[int]] = {}
    refund_races = 0
    for race in races:
        year = race_years[race.race_id]
        races_by_year[year] = races_by_year.get(year, 0) + 1
        if race.refund:
            refund_races += 1
        for hold in race.holds:
            target = race_holds if hold.scope == "race" else table_holds[hold.scope]
            target[hold.reason] = target.get(hold.reason, 0) + 1
        for hit in race.hits:
            hits[hit.bet_type] += 1
        for exclusion in race.exclusions:
            by_reason = exclusions[exclusion.bet_type]
            by_reason[exclusion.reason] = by_reason.get(exclusion.reason, 0) + 1
        ages.setdefault(year, []).extend(race.publication_ages.values())
    return {
        "races_by_year": {str(year): races_by_year[year] for year in sorted(races_by_year)},
        "race_holds_by_reason": dict(sorted(race_holds.items())),
        "table_holds_by_table_and_reason": {
            table: dict(sorted(by_reason.items())) for table, by_reason in table_holds.items()
        },
        "hits_by_bet_type": dict(hits),
        "exclusions_by_bet_type": {
            bet_type: dict(sorted(by_reason.items())) for bet_type, by_reason in exclusions.items()
        },
        "refund_races": refund_races,
        "publication_age_seconds_by_year": {
            str(year): _age_distribution(ages.get(year, [])) for year in sorted(races_by_year)
        },
    }


def _age_distribution(values: Sequence[int]) -> dict[str, object]:
    """Return minimum, median, maximum and 60-second-bin counts for ages."""
    if not values:
        return {"minimum": None, "median": None, "maximum": None, "bins_60_seconds": {}}
    bins: dict[str, int] = {}
    for value in values:
        lower = (value // 60) * 60
        name = f"{lower}-{lower + 59}"
        bins[name] = bins.get(name, 0) + 1
    return {
        "minimum": min(values),
        "median": median(values),
        "maximum": max(values),
        "bins_60_seconds": dict(
            sorted(bins.items(), key=lambda item: int(item[0].split("-", 1)[0]))
        ),
    }


def _validate_race_observations(
    race_observations: Sequence[RaceObservations],
) -> tuple[tuple[RaceObservations, ...], dict[str, int]]:
    """Return unique race observations and their validated four-digit years."""
    races = tuple(race_observations)
    years: dict[str, int] = {}
    for race in races:
        if race.race_id in years:
            raise ValueError(f"race observations contain duplicate race_id {race.race_id!r}")
        years[race.race_id] = _race_year(race.race_id)
        if any(hit.race_id != race.race_id for hit in race.hits):
            raise ValueError("hit observations must retain their enclosing race_id")
        if any(exclusion.race_id != race.race_id for exclusion in race.exclusions):
            raise ValueError("hit exclusions must retain their enclosing race_id")
        if any(hold.race_id != race.race_id for hold in race.holds):
            raise ValueError("race holds must retain their enclosing race_id")
    return races, years


def _validate_race_subsets(
    race_subsets: Mapping[str, FinalOddsRaceSubset],
) -> dict[str, FinalOddsRaceSubset]:
    """Return named subsets after requiring the fixed graded-stakes classification."""
    if not isinstance(race_subsets, Mapping):
        raise ValueError("race_subsets must be a mapping")
    if JRA_FLAT_GRADED_STAKES_V1 not in race_subsets:
        raise ValueError(f"race_subsets must contain {JRA_FLAT_GRADED_STAKES_V1!r}")
    result: dict[str, FinalOddsRaceSubset] = {}
    for name, subset in race_subsets.items():
        if not isinstance(name, str) or not name or name == "all":
            raise ValueError("race subset names must be nonempty strings other than 'all'")
        if not isinstance(subset, FinalOddsRaceSubset):
            raise ValueError("race_subsets values must be FinalOddsRaceSubset instances")
        result[name] = subset
    return result


def _validate_report_values(values: Mapping[str, object], name: str) -> None:
    """Validate that a report section arrives as a mapping from the outer boundary."""
    if not isinstance(values, Mapping):
        raise ValueError(f"{name} must be a mapping")


def _race_year(race_id: str) -> int:
    """Return the year encoded in one canonical 16-digit race identifier."""
    if not isinstance(race_id, str) or len(race_id) != 16 or not race_id.isdecimal():
        raise ValueError("race_id must be a 16-digit string")
    year = int(race_id[:4])
    _positive_year(year, "race_id year")
    return year


def _positive_year(value: object, name: str) -> int:
    """Return a valid four-digit integer year."""
    if not _is_year(value):
        raise ValueError(f"{name} must be a four-digit integer year")
    return cast(int, value)


def _is_year(value: object) -> bool:
    """Return whether a value is a non-boolean four-digit integer year."""
    return isinstance(value, int) and not isinstance(value, bool) and 1000 <= value <= 9999


def _positive_integer(value: object, name: str) -> int:
    """Return a positive integer setting or raise a descriptive validation error."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    """Return a nonnegative integer setting or raise a descriptive validation error."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


__all__ = [
    "CorrectionVariant",
    "FinalOddsEvaluation",
    "FinalOddsEvaluationSettings",
    "FinalOddsRaceSubset",
    "FinalOddsSelection",
    "evaluate_final_odds",
    "select_final_odds_variant",
]
