"""Calculate hit-conditional final-odds metrics and race-level bootstrap intervals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, isfinite
from numbers import Real

import numpy as np

from models.market.final_odds_correction import validate_odds_bands


@dataclass(frozen=True)
class FinalOddsBandMetrics:
    """Hold the payout-ratio metrics for one configured freeze-odds band."""

    lower: float
    upper: float | None
    hits: int
    payout_ratio: float | None
    mean_payout_ratio: float | None


@dataclass(frozen=True)
class FinalOddsMetrics:
    """Hold summary metrics calculated over a collection of winning combinations."""

    hits: int
    payout_ratio: float | None
    mean_payout_ratio: float | None
    median_abs_error_pct: float | None
    within_10pct: float | None
    over_20pct: float | None
    mean_log_error: float | None
    interval_coverage: float | None
    bands: tuple[FinalOddsBandMetrics, ...]


@dataclass(frozen=True)
class BootstrapInterval:
    """Hold a point estimate and its percentile bootstrap confidence interval."""

    point_estimate: float | None
    confidence_interval_lower: float | None
    confidence_interval_upper: float | None


@dataclass(frozen=True)
class FinalOddsBootstrap:
    """Hold race-resampled intervals for the two ADR-042 selection metrics."""

    payout_ratio: BootstrapInterval
    mean_payout_ratio: BootstrapInterval


@dataclass(frozen=True)
class FinalOddsBootstrapDifference:
    """Hold paired left-minus-right race-resampled metric differences."""

    payout_ratio: BootstrapInterval
    mean_payout_ratio: BootstrapInterval


def final_odds_metrics(
    freeze_odds: Sequence[float],
    final_odds: Sequence[float],
    predicted_odds: Sequence[float],
    *,
    bands: Sequence[float],
    interval_lower: Sequence[float] | None = None,
    interval_upper: Sequence[float] | None = None,
) -> FinalOddsMetrics:
    """Return ADR-042 hit-conditional metrics and per-band payout summaries.

    ``interval_lower`` and ``interval_upper`` are final-odds bounds.  They are
    optional together, which lets the uncorrected ``none`` variant report no
    interval coverage.
    """
    edges = validate_odds_bands(bands)
    freeze, actual, predicted = _metric_values(freeze_odds, final_odds, predicted_odds, edges[0])
    lower, upper = _interval_values(interval_lower, interval_upper, len(actual))
    band_metrics = _band_metrics(freeze, actual, predicted, edges)
    if not len(actual):
        return FinalOddsMetrics(
            hits=0,
            payout_ratio=None,
            mean_payout_ratio=None,
            median_abs_error_pct=None,
            within_10pct=None,
            over_20pct=None,
            mean_log_error=None,
            interval_coverage=None,
            bands=band_metrics,
        )
    payout_ratios = actual / predicted
    errors = np.log(predicted / actual)
    interval_coverage = (
        float(np.mean((actual >= lower) & (actual <= upper)))
        if lower is not None and upper is not None
        else None
    )
    return FinalOddsMetrics(
        hits=len(actual),
        payout_ratio=float(actual.sum() / predicted.sum()),
        mean_payout_ratio=float(payout_ratios.mean()),
        median_abs_error_pct=float(exp(float(np.median(np.abs(errors)))) - 1.0) * 100.0,
        within_10pct=float(np.mean(np.abs(predicted / actual - 1.0) <= 0.10)),
        over_20pct=float(np.mean(np.abs(predicted / actual - 1.0) > 0.20)),
        mean_log_error=float(errors.mean()),
        interval_coverage=interval_coverage,
        bands=band_metrics,
    )


def bootstrap_final_odds_metrics(
    race_ids: Sequence[str],
    final_odds: Sequence[float],
    predicted_odds: Sequence[float],
    *,
    resamples: int,
    seed: int,
    confidence: float = 0.95,
) -> FinalOddsBootstrap:
    """Return deterministic race-level bootstrap intervals for the selection metrics."""
    races, actual, predicted = _bootstrap_values(race_ids, final_odds, predicted_odds)
    _bootstrap_settings(resamples, seed, confidence)
    if not len(actual):
        empty = BootstrapInterval(None, None, None)
        return FinalOddsBootstrap(empty, empty)
    grouped = _grouped_sums(races, actual, predicted)
    payout_values, mean_values = _bootstrap_metric_values(
        grouped,
        resamples=resamples,
        seed=seed,
    )
    point_payout, point_mean = _metric_point_estimates(grouped)
    return FinalOddsBootstrap(
        payout_ratio=_bootstrap_interval(point_payout, payout_values, confidence),
        mean_payout_ratio=_bootstrap_interval(point_mean, mean_values, confidence),
    )


def paired_bootstrap_final_odds_metrics(
    race_ids: Sequence[str],
    final_odds: Sequence[float],
    left_predicted_odds: Sequence[float],
    right_predicted_odds: Sequence[float],
    *,
    resamples: int,
    seed: int,
    confidence: float = 0.95,
) -> FinalOddsBootstrapDifference:
    """Return paired left-minus-right intervals using identical sampled races.

    Both predictions are evaluated against the exact same winning-combination
    collection.  Every resample draws races once and applies its multiplicity
    to both variants, preserving the required pairing.
    """
    races, actual, left = _bootstrap_values(race_ids, final_odds, left_predicted_odds)
    _, _, right = _bootstrap_values(race_ids, final_odds, right_predicted_odds)
    _bootstrap_settings(resamples, seed, confidence)
    if not len(actual):
        empty = BootstrapInterval(None, None, None)
        return FinalOddsBootstrapDifference(empty, empty)
    left_grouped = _grouped_sums(races, actual, left)
    right_grouped = _grouped_sums(races, actual, right)
    generator = np.random.default_rng(seed)
    payout_differences = np.empty(resamples, dtype=np.float64)
    mean_differences = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        counts = _resample_counts(generator, len(left_grouped.hit_counts))
        left_payout, left_mean = _weighted_metric_values(left_grouped, counts)
        right_payout, right_mean = _weighted_metric_values(right_grouped, counts)
        payout_differences[index] = left_payout - right_payout
        mean_differences[index] = left_mean - right_mean
    left_payout, left_mean = _metric_point_estimates(left_grouped)
    right_payout, right_mean = _metric_point_estimates(right_grouped)
    return FinalOddsBootstrapDifference(
        payout_ratio=_bootstrap_interval(
            left_payout - right_payout, payout_differences, confidence
        ),
        mean_payout_ratio=_bootstrap_interval(left_mean - right_mean, mean_differences, confidence),
    )


@dataclass(frozen=True)
class _GroupedSums:
    """Store enough per-race totals to resample metrics without row copies."""

    actual_sums: np.ndarray[tuple[int], np.dtype[np.float64]]
    predicted_sums: np.ndarray[tuple[int], np.dtype[np.float64]]
    payout_ratio_sums: np.ndarray[tuple[int], np.dtype[np.float64]]
    hit_counts: np.ndarray[tuple[int], np.dtype[np.int64]]


def _metric_values(
    freeze_odds: Sequence[float],
    final_odds: Sequence[float],
    predicted_odds: Sequence[float],
    minimum_odds: float,
) -> tuple[np.ndarray[tuple[int], np.dtype[np.float64]], ...]:
    if not (len(freeze_odds) == len(final_odds) == len(predicted_odds)):
        raise ValueError("freeze_odds, final_odds and predicted_odds must have the same length")
    freeze = _positive_array(freeze_odds, "freeze_odds")
    if np.any(freeze < minimum_odds):
        raise ValueError("freeze_odds must not be below the first odds-band lower bound")
    return (
        freeze,
        _positive_array(final_odds, "final_odds"),
        _positive_array(predicted_odds, "predicted_odds"),
    )


def _interval_values(
    interval_lower: Sequence[float] | None,
    interval_upper: Sequence[float] | None,
    expected_length: int,
) -> tuple[
    np.ndarray[tuple[int], np.dtype[np.float64]] | None,
    np.ndarray[tuple[int], np.dtype[np.float64]] | None,
]:
    if (interval_lower is None) != (interval_upper is None):
        raise ValueError("interval_lower and interval_upper must be provided together")
    if interval_lower is None or interval_upper is None:
        return None, None
    lower = _positive_array(interval_lower, "interval_lower")
    upper = _positive_array(interval_upper, "interval_upper")
    if len(lower) != expected_length or len(upper) != expected_length:
        raise ValueError("interval bounds must have the expected length")
    if np.any(lower > upper):
        raise ValueError("interval_lower must not exceed interval_upper")
    return lower, upper


def _positive_array(
    values: Sequence[float], name: str
) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    converted: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must contain finite positive real numbers")
        number = float(value)
        if not isfinite(number) or number <= 0.0:
            raise ValueError(f"{name} must contain finite positive real numbers")
        converted.append(number)
    return np.asarray(converted, dtype=np.float64)


def _band_metrics(
    freeze_odds: np.ndarray[tuple[int], np.dtype[np.float64]],
    final_odds: np.ndarray[tuple[int], np.dtype[np.float64]],
    predicted_odds: np.ndarray[tuple[int], np.dtype[np.float64]],
    edges: tuple[float, ...],
) -> tuple[FinalOddsBandMetrics, ...]:
    result: list[FinalOddsBandMetrics] = []
    for index, lower in enumerate(edges):
        upper = edges[index + 1] if index + 1 < len(edges) else None
        selected = freeze_odds >= lower
        if upper is not None:
            selected &= freeze_odds < upper
        count = int(selected.sum())
        if not count:
            result.append(FinalOddsBandMetrics(lower, upper, 0, None, None))
            continue
        selected_actual = final_odds[selected]
        selected_predicted = predicted_odds[selected]
        result.append(
            FinalOddsBandMetrics(
                lower=lower,
                upper=upper,
                hits=count,
                payout_ratio=float(selected_actual.sum() / selected_predicted.sum()),
                mean_payout_ratio=float((selected_actual / selected_predicted).mean()),
            )
        )
    return tuple(result)


def _bootstrap_values(
    race_ids: Sequence[str],
    final_odds: Sequence[float],
    predicted_odds: Sequence[float],
) -> tuple[
    tuple[str, ...],
    np.ndarray[tuple[int], np.dtype[np.float64]],
    np.ndarray[tuple[int], np.dtype[np.float64]],
]:
    if not (len(race_ids) == len(final_odds) == len(predicted_odds)):
        raise ValueError("race_ids, final_odds and predicted_odds must have the same length")
    validated_races: list[str] = []
    for race_id in race_ids:
        if not isinstance(race_id, str) or not race_id:
            raise ValueError("race_ids must contain non-empty strings")
        validated_races.append(race_id)
    return (
        tuple(validated_races),
        _positive_array(final_odds, "final_odds"),
        _positive_array(predicted_odds, "predicted_odds"),
    )


def _bootstrap_settings(resamples: int, seed: int, confidence: float) -> None:
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ValueError("resamples must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(confidence, bool) or not isinstance(confidence, Real):
        raise ValueError("confidence must be between zero and one")
    if not isfinite(float(confidence)) or not 0.0 < float(confidence) < 1.0:
        raise ValueError("confidence must be between zero and one")


def _grouped_sums(
    race_ids: Sequence[str],
    final_odds: np.ndarray[tuple[int], np.dtype[np.float64]],
    predicted_odds: np.ndarray[tuple[int], np.dtype[np.float64]],
) -> _GroupedSums:
    indices: dict[str, list[int]] = {}
    for index, race_id in enumerate(race_ids):
        indices.setdefault(race_id, []).append(index)
    actual_sums: list[float] = []
    predicted_sums: list[float] = []
    payout_ratio_sums: list[float] = []
    hit_counts: list[int] = []
    for race_indices in indices.values():
        selected_actual = final_odds[race_indices]
        selected_predicted = predicted_odds[race_indices]
        actual_sums.append(float(selected_actual.sum()))
        predicted_sums.append(float(selected_predicted.sum()))
        payout_ratio_sums.append(float((selected_actual / selected_predicted).sum()))
        hit_counts.append(len(race_indices))
    return _GroupedSums(
        actual_sums=np.asarray(actual_sums, dtype=np.float64),
        predicted_sums=np.asarray(predicted_sums, dtype=np.float64),
        payout_ratio_sums=np.asarray(payout_ratio_sums, dtype=np.float64),
        hit_counts=np.asarray(hit_counts, dtype=np.int64),
    )


def _bootstrap_metric_values(
    grouped: _GroupedSums,
    *,
    resamples: int,
    seed: int,
) -> tuple[
    np.ndarray[tuple[int], np.dtype[np.float64]], np.ndarray[tuple[int], np.dtype[np.float64]]
]:
    generator = np.random.default_rng(seed)
    payout_values = np.empty(resamples, dtype=np.float64)
    mean_values = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        counts = _resample_counts(generator, len(grouped.hit_counts))
        payout_values[index], mean_values[index] = _weighted_metric_values(grouped, counts)
    return payout_values, mean_values


def _resample_counts(
    generator: np.random.Generator, race_count: int
) -> np.ndarray[tuple[int], np.dtype[np.int64]]:
    selected = generator.integers(0, race_count, size=race_count)
    return np.bincount(selected, minlength=race_count).astype(np.int64)


def _weighted_metric_values(
    grouped: _GroupedSums,
    counts: np.ndarray[tuple[int], np.dtype[np.int64]],
) -> tuple[float, float]:
    actual_sum = float(np.dot(counts, grouped.actual_sums))
    predicted_sum = float(np.dot(counts, grouped.predicted_sums))
    ratio_sum = float(np.dot(counts, grouped.payout_ratio_sums))
    hit_count = int(np.dot(counts, grouped.hit_counts))
    return actual_sum / predicted_sum, ratio_sum / hit_count


def _metric_point_estimates(grouped: _GroupedSums) -> tuple[float, float]:
    counts = np.ones(len(grouped.hit_counts), dtype=np.int64)
    return _weighted_metric_values(grouped, counts)


def _bootstrap_interval(
    point_estimate: float,
    sampled_values: np.ndarray[tuple[int], np.dtype[np.float64]],
    confidence: float,
) -> BootstrapInterval:
    tail = (1.0 - confidence) / 2.0
    return BootstrapInterval(
        point_estimate=point_estimate,
        confidence_interval_lower=float(np.percentile(sampled_values, tail * 100.0)),
        confidence_interval_upper=float(np.percentile(sampled_values, (1.0 - tail) * 100.0)),
    )


__all__ = [
    "BootstrapInterval",
    "FinalOddsBandMetrics",
    "FinalOddsBootstrap",
    "FinalOddsBootstrapDifference",
    "FinalOddsMetrics",
    "bootstrap_final_odds_metrics",
    "final_odds_metrics",
    "paired_bootstrap_final_odds_metrics",
]
