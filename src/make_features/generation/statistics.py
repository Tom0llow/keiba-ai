"""Share explicit window statistics without dropping missing observations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import sqrt

from make_features.contracts.types import FeatureScalar


def mean(values: Sequence[float | None]) -> float | None:
    """Return the mean only when the nonempty selected window is fully measured."""
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None) / len(values)


def std(values: Sequence[float | None]) -> float | None:
    """Return population standard deviation; a single value has unknown spread."""
    average = mean(values)
    if average is None or len(values) < 2:
        return None
    return sqrt(sum((value - average) ** 2 for value in values if value is not None) / len(values))


def relative(position: int, size: int) -> float | None:
    """Normalize a one-based rank, leaving singleton denominators missing."""
    return (position - 1) / (size - 1) if size > 1 else None


def summaries(
    values: Sequence[float | None], times: Sequence[datetime], cutoff: datetime, half_life: float
) -> dict[str, FeatureScalar]:
    """Calculate complete-window mean/max/std/EWMA and an elapsed-day OLS slope."""
    average = mean(values)
    result: dict[str, FeatureScalar] = {
        "mean": average,
        "max": None,
        "std": std(values),
        "ewma": None,
        "trend": None,
        "count": len(values),
        "valid_count": sum(value is not None for value in values),
    }
    if average is None:
        return result
    measured = [value for value in values if value is not None]
    result["max"] = max(measured)
    days = [(cutoff - time).total_seconds() / 86400 for time in times]
    weights = [2 ** (-age / half_life) for age in days]
    # Rescale from the youngest observation to avoid underflow for ancient windows.
    if not sum(weights):
        youngest = min(days)
        weights = [2 ** (-(age - youngest) / half_life) for age in days]
    result["ewma"] = sum(w * x for w, x in zip(weights, measured, strict=True)) / sum(weights)
    if len(values) > 1:
        day_mean = sum(days) / len(days)
        denominator = sum((day - day_mean) ** 2 for day in days)
        if denominator:
            result["trend"] = (
                sum(
                    (day_mean - day) * (value - average)
                    for day, value in zip(days, measured, strict=True)
                )
                / denominator
            )
    return result


def rates(finishes: Sequence[int], minimum_count: int) -> dict[str, FeatureScalar]:
    """Retain actual counts and unsmoothed rates, including small-sample status."""
    n = len(finishes)
    return {
        "start_count": n,
        "win_rate": sum(f == 1 for f in finishes) / n if n else None,
        "top3_rate": sum(f <= 3 for f in finishes) / n if n else None,
        "small_sample": n < minimum_count,
    }


def relative_values(
    values: Sequence[float | None], index: int, *, higher: bool, partial: bool
) -> dict[str, FeatureScalar]:
    """Compare the frozen field using competition ranks and an explicit direction."""
    known = [x for x in values if x is not None]
    own = values[index]
    result: dict[str, FeatureScalar] = {
        "rank": None,
        "mean_diff": None,
        "leader_gap": None,
        "zscore": None,
        "known_count": len(known),
        "field_size": len(values),
    }
    if own is None or (not partial and len(known) != len(values)):
        return result
    average = sum(known) / len(known)
    deviation = std(known)
    result.update(
        rank=float(1 + sum(x > own if higher else x < own for x in known)),
        mean_diff=own - average,
        leader_gap=max(known) - own if higher else own - min(known),
        zscore=(own - average) / deviation if deviation else None,
    )
    return result
