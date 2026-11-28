"""Classify horses into the fixed PL residual-analysis segments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type BoolArray = npt.NDArray[np.bool_]
type FloatArray = npt.NDArray[np.float64]

PL_RESIDUAL_SEGMENTS_V1 = "pl_residual_segments_v1"

_SIGNED_GAP_SEGMENTS = frozenset({"prior_win_margin_ge_0_3s", "prior_2to5_within_0_1s"})
_SEGMENTS = (
    ("all_horses", "All horses in the evaluated test races."),
    (
        "dirt_le1400_inner",
        "Dirt (TrackCD 23 or 24), distance at most 1400 m, and horse number at most field size / 3.",
    ),
    (
        "dirt_le1400_outer",
        "Dirt (TrackCD 23 or 24), distance at most 1400 m, and horse number greater than 2 * field size / 3.",
    ),
    (
        "dirt_gt1400_inner",
        "Dirt (TrackCD 23 or 24), distance over 1400 m, and horse number at most field size / 3.",
    ),
    (
        "dirt_gt1400_outer",
        "Dirt (TrackCD 23 or 24), distance over 1400 m, and horse number greater than 2 * field size / 3.",
    ),
    (
        "turf_inner",
        "Turf (TrackCD 10 through 22) and horse number at most field size / 3.",
    ),
    (
        "turf_outer",
        "Turf (TrackCD 10 through 22) and horse number greater than 2 * field size / 3.",
    ),
    ("age_2", "Horse age is 2."),
    ("age_3", "Horse age is 3."),
    ("age_4", "Horse age is 4."),
    ("age_5", "Horse age is 5."),
    ("age_6", "Horse age is 6."),
    ("age_7_plus", "Horse age is at least 7."),
    (
        "prior_win_margin_ge_0_3s",
        "Previous finish was first and previous signed gap was at most -0.25 seconds.",
    ),
    (
        "prior_2to5_within_0_1s",
        "Previous finish was second through fifth and previous signed gap was at most 0.1 seconds.",
    ),
)

RESIDUAL_SEGMENT_DEFINITIONS = dict(_SEGMENTS)
_SIGNED_GAP_UNAVAILABLE_REASON = "past_racing_ability__past_signed_gap_sec_lag1 is unavailable"


@dataclass(frozen=True)
class ResidualSegmentAssignments:
    """Hold membership masks and unavailable segments for one horse-row order."""

    member_masks: dict[str, BoolArray]
    unavailable: dict[str, str]


def assign_residual_segments(
    track_codes: Sequence[str | None],
    distances_m: npt.ArrayLike,
    horse_numbers: npt.ArrayLike,
    field_sizes: npt.ArrayLike,
    ages: npt.ArrayLike,
    prior_finish_positions: npt.ArrayLike,
    prior_signed_gap_seconds: npt.ArrayLike | None,
) -> ResidualSegmentAssignments:
    """Return fixed PL residual-segment memberships for horse rows.

    Missing previous-race values do not belong to previous-race segments. When
    the signed-gap column is unavailable entirely, only its two dependent
    segments are marked unavailable; all other segment masks remain usable.

    Raises:
        ValueError: If inputs have inconsistent lengths or invalid field, age,
            horse-number, or distance values.
    """
    row_count = len(track_codes)
    tracks = _track_codes(track_codes)
    distances = _finite_values(distances_m, "distances_m", row_count, positive=True)
    numbers = _whole_number_values(horse_numbers, "horse_numbers", row_count, positive=True)
    sizes = _whole_number_values(field_sizes, "field_sizes", row_count, positive=True)
    age_values = _whole_number_values(ages, "ages", row_count, positive=True, allow_nan=True)
    prior_positions = _whole_number_values(
        prior_finish_positions,
        "prior_finish_positions",
        row_count,
        positive=True,
        allow_nan=True,
    )
    if np.any(numbers > sizes):
        raise ValueError("horse_numbers must not exceed field_sizes")

    inner = numbers <= sizes / 3.0
    outer = numbers > 2.0 * sizes / 3.0
    dirt = np.isin(tracks, ("23", "24"))
    turf = np.isin(tracks, tuple(f"{code:02d}" for code in range(10, 23)))
    masks: dict[str, BoolArray] = {
        "all_horses": np.ones(row_count, dtype=np.bool_),
        "dirt_le1400_inner": dirt & (distances <= 1400.0) & inner,
        "dirt_le1400_outer": dirt & (distances <= 1400.0) & outer,
        "dirt_gt1400_inner": dirt & (distances > 1400.0) & inner,
        "dirt_gt1400_outer": dirt & (distances > 1400.0) & outer,
        "turf_inner": turf & inner,
        "turf_outer": turf & outer,
        "age_2": age_values == 2.0,
        "age_3": age_values == 3.0,
        "age_4": age_values == 4.0,
        "age_5": age_values == 5.0,
        "age_6": age_values == 6.0,
        "age_7_plus": age_values >= 7.0,
    }
    if prior_signed_gap_seconds is None:
        return ResidualSegmentAssignments(
            member_masks=masks,
            unavailable={name: _SIGNED_GAP_UNAVAILABLE_REASON for name in _SIGNED_GAP_SEGMENTS},
        )

    signed_gaps = _finite_or_nan_values(
        prior_signed_gap_seconds,
        "prior_signed_gap_seconds",
        row_count,
    )
    masks["prior_win_margin_ge_0_3s"] = (prior_positions == 1.0) & (signed_gaps <= -0.25)
    masks["prior_2to5_within_0_1s"] = (
        (prior_positions >= 2.0) & (prior_positions <= 5.0) & (signed_gaps <= 0.1)
    )
    return ResidualSegmentAssignments(member_masks=masks, unavailable={})


def _track_codes(values: Sequence[str | None]) -> npt.NDArray[np.str_]:
    """Return nullable source track codes as string values."""
    result: list[str] = []
    for value in values:
        if value is None:
            result.append("")
        elif isinstance(value, str):
            result.append(value)
        else:
            raise ValueError("track_codes must contain strings or null")
    return np.asarray(result, dtype=str)


def _finite_values(
    values: npt.ArrayLike,
    name: str,
    expected_length: int,
    *,
    positive: bool,
) -> FloatArray:
    """Return finite numeric values with an optional positive-value requirement."""
    result = _numeric_values(values, name, expected_length)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain finite values")
    if positive and np.any(result <= 0.0):
        raise ValueError(f"{name} must contain positive values")
    return result


def _whole_number_values(
    values: npt.ArrayLike,
    name: str,
    expected_length: int,
    *,
    positive: bool,
    allow_nan: bool = False,
) -> FloatArray:
    """Return integer-valued numeric inputs, optionally preserving missing values."""
    result = _numeric_values(values, name, expected_length)
    valid = ~np.isnan(result) if allow_nan else np.ones(len(result), dtype=np.bool_)
    if np.any(np.isinf(result)) or (not allow_nan and np.any(np.isnan(result))):
        raise ValueError(f"{name} must contain finite values")
    if np.any(result[valid] != np.floor(result[valid])):
        raise ValueError(f"{name} must contain whole numbers")
    if positive and np.any(result[valid] <= 0.0):
        raise ValueError(f"{name} must contain positive values")
    return result


def _finite_or_nan_values(
    values: npt.ArrayLike,
    name: str,
    expected_length: int,
) -> FloatArray:
    """Return finite numeric values while allowing missing values."""
    result = _numeric_values(values, name, expected_length)
    if np.any(np.isinf(result)):
        raise ValueError(f"{name} must contain finite values or null")
    return result


def _numeric_values(values: npt.ArrayLike, name: str, expected_length: int) -> FloatArray:
    """Return a one-dimensional numeric array with the expected length."""
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a one-dimensional numeric array") from exc
    if result.ndim != 1 or len(result) != expected_length:
        raise ValueError(f"{name} must be a one-dimensional array with the expected length")
    return result


__all__ = [
    "PL_RESIDUAL_SEGMENTS_V1",
    "RESIDUAL_SEGMENT_DEFINITIONS",
    "ResidualSegmentAssignments",
    "assign_residual_segments",
]
