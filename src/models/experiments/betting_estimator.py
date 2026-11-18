"""Fit the race-day betting estimator from a backtest's results (ADR-045). No I/O.

The target year follows the backtest's last test year. Its fits are ADR-044's fits for
that year, made by the backtest's own ``fit_year_estimators``: the place corrections
from every hit before the target year and the blend from every test year. Its method is
ADR-044 Decision 4 applied to the target year, using the flat results the backtest
report recorded for earlier years.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from models.artifacts.betting_estimator import (
    BettingEstimatorRecord,
    EstimatorSettings,
)
from models.betting.methods import METHODS, Method, select_method
from models.experiments.betting_backtest import (
    REPORT_FORMAT,
    REPORT_FORMAT_VERSION,
    BettingBacktestSettings,
    YearEstimators,
    fit_year_estimators,
    method_available,
    width_observations,
)
from models.serialization.betting_inputs import BlendTraining
from models.serialization.final_odds_observations import HitObservation


@dataclass(frozen=True)
class BacktestResults:
    """Hold each method's flat ``(receipt_yen, stake_yen)`` of every year it ran."""

    flat: Mapping[Method, Mapping[int, tuple[int, int]]]


def backtest_results(report: Mapping[str, object], test_years: Sequence[int]) -> BacktestResults:
    """Validate a backtest report's methods and selection and return its flat results.

    Raises:
        ValueError: If the format, a method's years, its flat totals or a recorded
            selection differ from what the report's own flat results give.
    """
    if (
        report.get("format") != REPORT_FORMAT
        or report.get("format_version") != REPORT_FORMAT_VERSION
    ):
        raise ValueError(
            f"backtest report must be {REPORT_FORMAT} format_version {REPORT_FORMAT_VERSION}"
        )
    methods = report.get("methods")
    if not isinstance(methods, dict) or set(methods) != set(METHODS):
        raise ValueError("backtest report methods differ from the four ADR-044 methods")
    flat: dict[Method, dict[int, tuple[int, int]]] = {}
    for method in METHODS:
        entry = methods[method]
        years = entry.get("years") if isinstance(entry, dict) else None
        if not isinstance(years, dict) or set(years) != {str(year) for year in test_years}:
            raise ValueError(f"backtest report {method} years differ from test_years")
        flat[method] = {}
        for year in test_years:
            item = years[str(year)]
            if not isinstance(item, dict) or not isinstance(item.get("available"), bool):
                raise ValueError(f"backtest report {method} {year} has no available flag")
            totals = item.get("flat")
            if not item["available"]:
                if totals is not None:
                    raise ValueError(f"backtest report {method} {year} is unavailable but flat")
                continue
            if not isinstance(totals, dict):
                raise ValueError(f"backtest report {method} {year} has no flat totals")
            flat[method][year] = (
                _amount(totals.get("receipt_yen"), "receipt_yen"),
                _amount(totals.get("stake_yen"), "stake_yen"),
            )
    selection = report.get("selection")
    if not isinstance(selection, dict) or set(selection) != {str(y) for y in test_years}:
        raise ValueError("backtest report selection years differ from test_years")
    for year in test_years:
        recorded = selection[str(year)]
        method, comparison = select_method(
            flat,
            test_years,
            year,
            available=frozenset(name for name in METHODS if year in flat[name]),
        )
        if (
            not isinstance(recorded, dict)
            or recorded.get("method") != method
            or recorded.get("comparison_years") != list(comparison)
        ):
            raise ValueError(f"backtest report selection of {year} differs from its flat results")
    return BacktestResults(flat)


def fit_betting_estimator(
    *,
    settings: BettingBacktestSettings,
    results: BacktestResults,
    hits: Sequence[HitObservation],
    graded_race_ids: frozenset[str],
    blend_training: BlendTraining,
    sources: Mapping[str, object],
    provenance: Mapping[str, object],
) -> tuple[BettingEstimatorRecord, YearEstimators]:
    """Fit the estimator for the year after the last test year and return its record.

    ``hits`` are ADR-042 ``place_mid`` and ``place_low`` hits; only those from
    ``train_start_year`` through the last test year are used. ``blend_training`` holds
    the PL evaluation's test-year races. Also returns the in-memory fits, which the
    caller compares with the written artifact.
    """
    target_year = settings.test_years[-1] + 1
    used = [hit for hit in hits if settings.train_start_year <= int(hit.race_id[:4]) < target_year]
    widths = width_observations(used)
    estimators = fit_year_estimators(
        target_year, settings, used, widths, blend_training, graded_race_ids
    )
    available = frozenset(method for method in METHODS if method_available(method, estimators))
    method, comparison = select_method(
        results.flat, settings.test_years, target_year, available=available
    )
    record = BettingEstimatorRecord(
        target_year=target_year,
        method=method,
        comparison_years=comparison,
        flat={name: {year: results.flat[name][year] for year in comparison} for name in METHODS},
        policy=settings.policy,
        settings=EstimatorSettings(
            train_start_year=settings.train_start_year,
            max_publication_age_seconds=settings.max_publication_age_seconds,
            place_mid_bands=settings.place_bands,
            quantiles=settings.quantiles,
            min_hits=settings.min_hits,
            graded_shrinkage_k=settings.graded_shrinkage_k,
            place_width_bands=settings.place_width_bands,
            blend_min_races=settings.blend_min_races,
            blend_tolerance=settings.blend_tolerance,
            blend_max_iterations=settings.blend_max_iterations,
        ),
        place_mid_hits=sum(hit.bet_type == "place_mid" for hit in used),
        width_observations=len(widths),
        mid=estimators.mid,
        width=estimators.width,
        blend=estimators.blend,
        blend_excluded=dict(estimators.blend_excluded),
        blend_fit_years=tuple(y for y in settings.test_years if y < target_year),
        sources=sources,
        provenance=provenance,
    )
    return record, estimators


def year_estimators(record: BettingEstimatorRecord) -> YearEstimators:
    """Return the fits of a (read) record in the backtest's form."""
    return YearEstimators(
        mid=record.mid,
        width=record.width,
        blend=record.blend,
        blend_excluded=record.blend_excluded,
    )


def require_same_estimates(
    expected: YearEstimators,
    record: BettingEstimatorRecord,
    hits: Sequence[HitObservation],
) -> None:
    """Require a read record to give exactly the fitted estimates.

    Every ``place_mid`` hit's freeze odds is estimated by both place corrections (the
    width correction at the hit's own width) and the blend coefficients are compared.
    The ``place_mid`` comparison covers the whole estimate with its quantiles; the width
    correction gives only the corrected odds, which is all a proposal uses.

    Raises:
        ValueError: If a ``place_mid`` estimate or quantile, a width-corrected odds or a
            blend coefficient differs.
    """
    if (record.blend.alpha, record.blend.beta) != (expected.blend.alpha, expected.blend.beta):
        raise ValueError("written blend coefficients differ from the fit")
    for hit in hits:
        if hit.bet_type != "place_mid":
            continue
        if record.mid.estimate(hit.freeze_odds) != expected.mid.estimate(hit.freeze_odds):
            raise ValueError("written place_mid correction differs from the fit")
    for observation in width_observations(hits):
        odds, width = observation.freeze_odds, observation.width
        if record.width.estimate(odds, width) != expected.width.estimate(odds, width):
            raise ValueError("written width correction differs from the fit")


def _amount(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"backtest report flat {name} must be a non-negative integer")
    return value


__all__ = [
    "BacktestResults",
    "backtest_results",
    "fit_betting_estimator",
    "require_same_estimates",
    "year_estimators",
]
