"""Fit hit-conditional final-odds corrections from freeze-time market odds.

The correction is deliberately limited to pure estimation under ADR-042.  It
maps a freeze-time odds value to the expected final odds conditional on that
combination winning; data loading, folds and report assembly belong elsewhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from math import ceil, exp, isfinite, log
from numbers import Real


@dataclass(frozen=True)
class CorrectionBand:
    """Describe one fitted odds band and the source bands it contains."""

    lower: float
    upper: float | None
    source_lowers: tuple[float, ...]
    hit_count: int
    mean_ratio: float | None
    mean_log_freeze_odds: float | None
    ratio_quantiles: tuple[float, ...] | None
    shrinkage_target: float | None = None
    shrinkage_k: int | None = None


@dataclass(frozen=True)
class FinalOddsEstimate:
    """Hold the corrected final-odds estimate for one freeze-time quote."""

    freeze_odds: float
    multiplier: float
    final_odds: float
    ratio_quantiles: tuple[float, ...]
    final_odds_quantiles: tuple[float, ...]


@dataclass(frozen=True)
class FinalOddsCorrection:
    """Represent a banded correction with log-odds interpolation knots."""

    band_edges: tuple[float, ...]
    quantile_levels: tuple[float, ...]
    bands: tuple[CorrectionBand, ...]
    _quantile_fallback: FinalOddsCorrection | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def estimate(self, freeze_odds: float) -> FinalOddsEstimate:
        """Return the expected final odds and empirical ratio interval for one quote."""
        odds = _positive_value(freeze_odds, "freeze_odds")
        if odds < self.band_edges[0]:
            raise ValueError("freeze_odds must not be below the first odds-band lower bound")
        multiplier = self._multiplier(odds)
        quantiles = self._quantiles(odds)
        return FinalOddsEstimate(
            freeze_odds=odds,
            multiplier=multiplier,
            final_odds=multiplier * odds,
            ratio_quantiles=quantiles,
            final_odds_quantiles=tuple(value * odds for value in quantiles),
        )

    def _multiplier(self, freeze_odds: float) -> float:
        if self._quantile_fallback is not None and self._band_is_empty(freeze_odds):
            return self._quantile_fallback._multiplier(freeze_odds)
        knots = tuple(
            (band.mean_log_freeze_odds, band.mean_ratio)
            for band in self.bands
            if band.mean_log_freeze_odds is not None and band.mean_ratio is not None
        )
        if not knots:
            if self._quantile_fallback is not None:
                return self._quantile_fallback._multiplier(freeze_odds)
            raise ValueError("correction has no fitted odds bands")
        target = log(freeze_odds)
        first_x, first_multiplier = knots[0]
        if target <= first_x:
            return first_multiplier
        last_x, last_multiplier = knots[-1]
        if target >= last_x:
            return last_multiplier
        for (left_x, left_multiplier), (right_x, right_multiplier) in pairwise(knots):
            if target <= right_x:
                proportion = (target - left_x) / (right_x - left_x)
                return left_multiplier + proportion * (right_multiplier - left_multiplier)
        raise AssertionError("the final interpolation knot must contain the target")

    def _band_is_empty(self, freeze_odds: float) -> bool:
        for band in self.bands:
            if freeze_odds >= band.lower and (band.upper is None or freeze_odds < band.upper):
                return band.mean_ratio is None
        return False

    def _quantiles(self, freeze_odds: float) -> tuple[float, ...]:
        for band in self.bands:
            if freeze_odds >= band.lower and (band.upper is None or freeze_odds < band.upper):
                if band.ratio_quantiles is not None:
                    return band.ratio_quantiles
                break
        if self._quantile_fallback is not None:
            return self._quantile_fallback._quantiles(freeze_odds)
        raise ValueError("correction has no empirical quantiles for freeze_odds")


@dataclass
class _RawBand:
    """Collect unmerged observations for an internal configured odds range."""

    source_lowers: list[float]
    values: list[tuple[float, float]]

    @property
    def hit_count(self) -> int:
        """Return the number of observed winning combinations in the band."""
        return len(self.values)


def validate_odds_bands(bands: Sequence[float]) -> tuple[float, ...]:
    """Return validated left-closed odds-band lower bounds.

    The final band is unbounded.  JRA decimal odds must therefore start at one
    or higher and every following lower bound must be strictly larger.
    """
    values = _finite_values(bands, "odds bands")
    if values[0] < 1.0:
        raise ValueError("odds bands must start at 1.0 or higher")
    if any(right <= left for left, right in pairwise(values)):
        raise ValueError("odds bands must be strictly increasing without duplicates")
    return values


def validate_quantiles(quantiles: Sequence[float]) -> tuple[float, ...]:
    """Return validated strictly increasing empirical-quantile levels."""
    values = _finite_values(quantiles, "quantiles")
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("quantiles must be between zero and one")
    if any(right <= left for left, right in pairwise(values)):
        raise ValueError("quantiles must be strictly increasing without duplicates")
    return values


def fit_all_correction(
    freeze_odds: Sequence[float],
    final_odds: Sequence[float],
    *,
    bands: Sequence[float],
    quantiles: Sequence[float],
    min_hits: int,
) -> FinalOddsCorrection:
    """Fit the all-races correction with undersized adjacent bands merged.

    Every observation is a winning combination.  The fitted multiplier is the
    arithmetic mean of ``final_odds / freeze_odds`` in each merged band.  The
    model interpolates those means linearly on the logarithm of freeze-time
    odds and uses the outer knot value beyond its observed range.
    """
    edges = validate_odds_bands(bands)
    levels = validate_quantiles(quantiles)
    _positive_integer(min_hits, "min_hits")
    observations = _observations(freeze_odds, final_odds, edges[0])
    raw_bands = _raw_bands(observations, edges)
    merged_bands = _merge_small_bands(raw_bands, min_hits)
    return FinalOddsCorrection(
        band_edges=edges,
        quantile_levels=levels,
        bands=tuple(_fit_band(raw_band, edges, levels) for raw_band in merged_bands),
    )


def fit_graded_correction(
    freeze_odds: Sequence[float],
    final_odds: Sequence[float],
    *,
    bands: Sequence[float],
    quantiles: Sequence[float],
    min_hits: int,
    shrinkage_k: int,
    all_correction: FinalOddsCorrection,
) -> FinalOddsCorrection:
    """Fit a graded-races correction shrunk toward an all-races correction.

    Each configured band remains separate.  Its multiplier is shrunk using
    ``(n * graded + k * all) / (n + k)`` at the band's observed mean log odds.
    Bands with fewer than ``min_hits`` retain the all-races empirical
    quantiles, as required by ADR-042.  Odds inside a band without graded
    hits use the all-races multiplier and quantiles; other odds interpolate
    between the knots of the bands that have graded hits.  An empty graded
    population therefore falls back entirely to the all-races correction.
    """
    edges = validate_odds_bands(bands)
    levels = validate_quantiles(quantiles)
    _positive_integer(min_hits, "min_hits")
    _nonnegative_integer(shrinkage_k, "shrinkage_k")
    if all_correction.band_edges != edges or all_correction.quantile_levels != levels:
        raise ValueError("all_correction must use the same odds bands and quantiles")
    observations = _observations(freeze_odds, final_odds, edges[0], allow_empty=True)
    fitted_bands: list[CorrectionBand] = []
    for raw_band in _raw_bands(observations, edges):
        lower, upper = _band_bounds(edges, raw_band.source_lowers[0])
        if not raw_band.values:
            fitted_bands.append(
                CorrectionBand(
                    lower=lower,
                    upper=upper,
                    source_lowers=tuple(raw_band.source_lowers),
                    hit_count=0,
                    mean_ratio=None,
                    mean_log_freeze_odds=None,
                    ratio_quantiles=None,
                    shrinkage_target=None,
                    shrinkage_k=shrinkage_k,
                )
            )
            continue
        ratios = [final / freeze for freeze, final in raw_band.values]
        mean_log_odds = sum(log(freeze) for freeze, _ in raw_band.values) / len(raw_band.values)
        graded_mean = sum(ratios) / len(ratios)
        target = all_correction._multiplier(exp(mean_log_odds))
        multiplier = (len(raw_band.values) * graded_mean + shrinkage_k * target) / (
            len(raw_band.values) + shrinkage_k
        )
        band_quantiles = (
            _empirical_quantiles(ratios, levels)
            if len(raw_band.values) >= min_hits
            else all_correction._quantiles(exp(mean_log_odds))
        )
        fitted_bands.append(
            CorrectionBand(
                lower=lower,
                upper=upper,
                source_lowers=tuple(raw_band.source_lowers),
                hit_count=len(raw_band.values),
                mean_ratio=multiplier,
                mean_log_freeze_odds=mean_log_odds,
                ratio_quantiles=band_quantiles,
                shrinkage_target=target,
                shrinkage_k=shrinkage_k,
            )
        )
    return FinalOddsCorrection(
        band_edges=edges,
        quantile_levels=levels,
        bands=tuple(fitted_bands),
        _quantile_fallback=all_correction,
    )


def _finite_values(values: Sequence[float], name: str) -> tuple[float, ...]:
    converted = tuple(_finite_value(value, name) for value in values)
    if not converted:
        raise ValueError(f"{name} must not be empty")
    return converted


def _finite_value(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must contain finite real numbers")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{name} must contain finite real numbers")
    return converted


def _positive_value(value: object, name: str) -> float:
    converted = _finite_value(value, name)
    if converted <= 0.0:
        raise ValueError(f"{name} must be positive")
    return converted


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _observations(
    freeze_odds: Sequence[float],
    final_odds: Sequence[float],
    minimum_odds: float,
    *,
    allow_empty: bool = False,
) -> tuple[tuple[float, float], ...]:
    if len(freeze_odds) != len(final_odds):
        raise ValueError("freeze_odds and final_odds must have the same length")
    if not freeze_odds and not allow_empty:
        raise ValueError("freeze_odds and final_odds must not be empty")
    observations: list[tuple[float, float]] = []
    for freeze, final in zip(freeze_odds, final_odds, strict=True):
        validated_freeze = _positive_value(freeze, "freeze_odds")
        if validated_freeze < minimum_odds:
            raise ValueError("freeze_odds must not be below the first odds-band lower bound")
        observations.append((validated_freeze, _positive_value(final, "final_odds")))
    return tuple(observations)


def _raw_bands(
    observations: Sequence[tuple[float, float]], edges: tuple[float, ...]
) -> list[_RawBand]:
    result = [_RawBand([edge], []) for edge in edges]
    for freeze, final in observations:
        index = _band_index(freeze, edges)
        result[index].values.append((freeze, final))
    return result


def _merge_small_bands(raw_bands: list[_RawBand], min_hits: int) -> list[_RawBand]:
    """Merge an undersized band into its lower neighbor, except at the start."""
    result = list(raw_bands)
    while len(result) > 1:
        small_index = next(
            (index for index, band in enumerate(result) if band.hit_count < min_hits),
            None,
        )
        if small_index is None:
            break
        target_index = 1 if small_index == 0 else small_index - 1
        left_index, right_index = sorted((small_index, target_index))
        left = result[left_index]
        right = result[right_index]
        merged = _RawBand(
            source_lowers=[*left.source_lowers, *right.source_lowers],
            values=[*left.values, *right.values],
        )
        result[left_index : right_index + 1] = [merged]
    return result


def _fit_band(
    raw_band: _RawBand,
    edges: tuple[float, ...],
    quantile_levels: tuple[float, ...],
) -> CorrectionBand:
    lower, upper = _band_bounds(edges, raw_band.source_lowers[0])
    if len(raw_band.source_lowers) > 1:
        _, upper = _band_bounds(edges, raw_band.source_lowers[-1])
    ratios = [final / freeze for freeze, final in raw_band.values]
    return CorrectionBand(
        lower=lower,
        upper=upper,
        source_lowers=tuple(raw_band.source_lowers),
        hit_count=len(raw_band.values),
        mean_ratio=sum(ratios) / len(ratios),
        mean_log_freeze_odds=sum(log(freeze) for freeze, _ in raw_band.values)
        / len(raw_band.values),
        ratio_quantiles=_empirical_quantiles(ratios, quantile_levels),
    )


def _band_index(freeze_odds: float, edges: tuple[float, ...]) -> int:
    for index in range(len(edges) - 1, 0, -1):
        if freeze_odds >= edges[index]:
            return index
    return 0


def _band_bounds(edges: tuple[float, ...], lower: float) -> tuple[float, float | None]:
    index = edges.index(lower)
    return lower, edges[index + 1] if index + 1 < len(edges) else None


def _empirical_quantiles(values: Sequence[float], levels: Sequence[float]) -> tuple[float, ...]:
    ordered = sorted(values)
    return tuple(ordered[max(ceil(level * len(ordered)) - 1, 0)] for level in levels)


__all__ = [
    "CorrectionBand",
    "FinalOddsCorrection",
    "FinalOddsEstimate",
    "fit_all_correction",
    "fit_graded_correction",
    "validate_odds_bands",
    "validate_quantiles",
]
