"""Correct ``place_mid`` odds separately for bands of the place-odds width (ADR-044).

The width of a freeze-time place quote is ``OddsHigh / OddsLow``. O1 place odds have a
0.1 resolution, so both bounds are compared as integer tenths and the width is an exact
fraction. Each width band gets ADR-042's graded ``place_mid`` correction, fitted only on
hits of that band; a band with fewer than ``min_hits`` hits is merged into its lower
neighbour (the lowest band into its upper neighbour). Standard library only; no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from models.market.final_odds_correction import (
    FinalOddsCorrection,
    fit_all_correction,
    fit_graded_correction,
)


@dataclass(frozen=True)
class PlaceWidthObservation:
    """Hold one ``place_mid`` hit with its freeze-time width."""

    race_id: str
    freeze_odds: float
    final_odds: float
    width: Fraction


@dataclass(frozen=True)
class PlaceWidthCorrection:
    """Hold one graded ``place_mid`` correction per (merged) width band."""

    width_edges: tuple[Fraction, ...]
    groups: tuple[tuple[int, ...], ...]
    corrections: tuple[FinalOddsCorrection, ...]
    hit_counts: tuple[int, ...]

    def estimate(self, freeze_odds: float, width: Fraction) -> float:
        """Return the corrected ``place_mid`` odds of a quote with this width."""
        band = width_band(width, self.width_edges)
        for group, correction in zip(self.groups, self.corrections, strict=True):
            if band in group:
                return correction.estimate(freeze_odds).final_odds
        raise AssertionError("every width band belongs to one group")


def odds_tenths(value: float) -> int:
    """Return decimal odds as an integer number of tenths."""
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("place odds must be positive and finite")
    return round(value * 10)


def recover_place_high(low: float, mid: float) -> float:
    """Return ``OddsHigh`` from ``OddsLow`` and ``mid = sqrt(OddsLow * OddsHigh)``."""
    odds_tenths(low)
    odds_tenths(mid)
    return round(mid * mid / low, 1)


def place_width(low: float, high: float) -> Fraction | None:
    """Return ``high / low`` exactly from tenths, or ``None`` when ``high < low``."""
    low_tenths = odds_tenths(low)
    high_tenths = odds_tenths(high)
    if high_tenths < low_tenths:
        return None
    return Fraction(high_tenths, low_tenths)


def validate_width_bands(bands: Sequence[float]) -> tuple[Fraction, ...]:
    """Return width-band lower bounds as fractions; they start at 1.0 and increase."""
    if not bands or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in bands
    ):
        raise ValueError("width bands must be a non-empty list of finite numbers")
    edges = tuple(Fraction(str(float(value))) for value in bands)
    if edges[0] != 1:
        raise ValueError("width bands must start at 1.0")
    if any(right <= left for left, right in pairwise(edges)):
        raise ValueError("width bands must be strictly increasing without duplicates")
    return edges


def width_band(width: Fraction, edges: Sequence[Fraction]) -> int:
    """Return the index of the left-closed band that contains ``width``."""
    if width < edges[0]:
        raise ValueError("width must not be below the first width band")
    return max(index for index, edge in enumerate(edges) if width >= edge)


def fit_place_width_correction(
    observations: Sequence[PlaceWidthObservation],
    *,
    width_bands: Sequence[float],
    place_bands: Sequence[float],
    quantiles: Sequence[float],
    min_hits: int,
    shrinkage_k: int,
    graded_race_ids: Collection[str],
) -> PlaceWidthCorrection:
    """Fit ADR-042's graded ``place_mid`` correction in every merged width band.

    Raises:
        ValueError: If there are no observations or a setting is invalid.
    """
    edges = validate_width_bands(width_bands)
    if not observations:
        raise ValueError("no place_mid training hits for the width correction")
    by_band: list[list[PlaceWidthObservation]] = [[] for _ in edges]
    for observation in observations:
        by_band[width_band(observation.width, edges)].append(observation)
    groups = _merged_groups([len(items) for items in by_band], min_hits)
    corrections: list[FinalOddsCorrection] = []
    counts: list[int] = []
    for group in groups:
        hits = [item for index in group for item in by_band[index]]
        all_correction = fit_all_correction(
            [item.freeze_odds for item in hits],
            [item.final_odds for item in hits],
            bands=place_bands,
            quantiles=quantiles,
            min_hits=min_hits,
        )
        graded = [item for item in hits if item.race_id in graded_race_ids]
        corrections.append(
            fit_graded_correction(
                [item.freeze_odds for item in graded],
                [item.final_odds for item in graded],
                bands=place_bands,
                quantiles=quantiles,
                min_hits=min_hits,
                shrinkage_k=shrinkage_k,
                all_correction=all_correction,
            )
        )
        counts.append(len(hits))
    return PlaceWidthCorrection(edges, groups, tuple(corrections), tuple(counts))


def _merged_groups(counts: Sequence[int], min_hits: int) -> tuple[tuple[int, ...], ...]:
    """Merge an undersized band into its lower neighbour, except at the start (ADR-042)."""
    if isinstance(min_hits, bool) or not isinstance(min_hits, int) or min_hits < 1:
        raise ValueError("min_hits must be a positive integer")
    groups: list[tuple[tuple[int, ...], int]] = [
        ((index,), count) for index, count in enumerate(counts)
    ]
    while len(groups) > 1:
        small = next((index for index, (_, count) in enumerate(groups) if count < min_hits), None)
        if small is None:
            break
        target = 1 if small == 0 else small - 1
        left, right = sorted((small, target))
        merged = (
            (*groups[left][0], *groups[right][0]),
            groups[left][1] + groups[right][1],
        )
        groups[left : right + 1] = [merged]
    return tuple(group for group, _ in groups)


__all__ = [
    "PlaceWidthCorrection",
    "PlaceWidthObservation",
    "fit_place_width_correction",
    "odds_tenths",
    "place_width",
    "recover_place_high",
    "validate_width_bands",
    "width_band",
]
