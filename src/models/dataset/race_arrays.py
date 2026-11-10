"""Hold validated NumPy arrays grouped into complete races."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Integral

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass(frozen=True)
class RaceArrays:
    """Hold race-level metadata and horse-level numeric model inputs.

    Race-level fields have one value per group in ``group_sizes``. Horse-level
    fields have one value per row, ordered in contiguous race groups. Datetime
    values are UTC-aware, feature and market nulls are represented by NaN.
    The instance takes ownership of the NumPy arrays it receives and makes
    them read-only; copying full-period arrays would double their memory use.
    """

    race_ids: tuple[str, ...]
    freeze_at: tuple[datetime, ...]
    label_usable_after: tuple[datetime, ...]
    years: IntArray
    group_sizes: IntArray
    horse_ids: tuple[str, ...]
    features: FloatArray
    feature_names: tuple[str, ...]
    finish_positions: IntArray
    market_odds: FloatArray

    def __post_init__(self) -> None:
        """Validate race-contiguous array invariants."""
        race_count = len(self.race_ids)
        if race_count == 0:
            raise ValueError("race arrays must contain at least one race")
        if len(set(self.race_ids)) != race_count or any(
            not isinstance(race_id, str) or not race_id for race_id in self.race_ids
        ):
            raise ValueError("race_ids must be nonempty and unique strings")
        if len(self.freeze_at) != race_count or len(self.label_usable_after) != race_count:
            raise ValueError("race metadata lengths must match race_ids")
        _validate_utc_datetimes(self.freeze_at, "freeze_at")
        _validate_utc_datetimes(self.label_usable_after, "label_usable_after")
        _validate_int_array(self.years, "years", (race_count,))
        _validate_int_array(self.group_sizes, "group_sizes", (race_count,))
        if np.any(self.years < 1):
            raise ValueError("years must be positive")
        if np.any(self.group_sizes < 3):
            raise ValueError("group_sizes must be at least 3")

        row_count = int(self.group_sizes.sum())
        if len(self.horse_ids) != row_count or any(
            not isinstance(horse_id, str) or not horse_id for horse_id in self.horse_ids
        ):
            raise ValueError("horse_ids must be nonempty strings for every row")
        _validate_float_array(self.features, "features", (row_count, None))
        if len(self.feature_names) != self.features.shape[1]:
            raise ValueError("feature_names must match the feature matrix columns")
        if len(set(self.feature_names)) != len(self.feature_names) or any(
            not isinstance(name, str) or not name for name in self.feature_names
        ):
            raise ValueError("feature_names must be unique nonempty strings")
        _validate_int_array(self.finish_positions, "finish_positions", (row_count,))
        _validate_float_array(self.market_odds, "market_odds", (row_count,))

        offsets = _group_offsets(self.group_sizes)
        for race_index, group_size in enumerate(self.group_sizes):
            start = int(offsets[race_index])
            stop = start + int(group_size)
            positions = np.sort(self.finish_positions[start:stop])
            expected = np.arange(1, int(group_size) + 1, dtype=np.int64)
            if not np.array_equal(positions, expected):
                raise ValueError("finish_positions must be a 1..n permutation in every race")
            if len(set(self.horse_ids[start:stop])) != int(group_size):
                raise ValueError("horse_ids must be unique within every race")

        for array in (
            self.years,
            self.group_sizes,
            self.features,
            self.finish_positions,
            self.market_odds,
        ):
            array.setflags(write=False)

    def subset(self, race_indices: Sequence[int]) -> RaceArrays:
        """Return the specified complete races in the supplied order.

        Args:
            race_indices: Zero-based, unique race indexes to retain.

        Raises:
            ValueError: If indexes are invalid, duplicated, or empty.
        """
        indices = tuple(_validate_race_index(index, len(self.race_ids)) for index in race_indices)
        if not indices:
            raise ValueError("race subset must contain at least one race")
        if len(set(indices)) != len(indices):
            raise ValueError("race subset indexes must be unique")

        offsets = _group_offsets(self.group_sizes)
        row_indices = np.concatenate(
            [
                np.arange(
                    int(offsets[race_index]),
                    int(offsets[race_index + 1]),
                    dtype=np.int64,
                )
                for race_index in indices
            ]
        )
        return RaceArrays(
            race_ids=tuple(self.race_ids[index] for index in indices),
            freeze_at=tuple(self.freeze_at[index] for index in indices),
            label_usable_after=tuple(self.label_usable_after[index] for index in indices),
            years=self.years[list(indices)].copy(),
            group_sizes=self.group_sizes[list(indices)].copy(),
            horse_ids=tuple(self.horse_ids[index] for index in row_indices),
            features=self.features[row_indices].copy(),
            feature_names=self.feature_names,
            finish_positions=self.finish_positions[row_indices].copy(),
            market_odds=self.market_odds[row_indices].copy(),
        )

    def columns(self, names: Sequence[str]) -> RaceArrays:
        """Return an array set restricted to the requested feature columns.

        Args:
            names: Ordered feature names to retain.

        Raises:
            ValueError: If names are duplicated or absent from this array set.
        """
        selected = tuple(names)
        if len(set(selected)) != len(selected):
            raise ValueError("feature column names must be unique")
        unknown = [name for name in selected if name not in self.feature_names]
        if unknown:
            raise ValueError(f"unknown feature columns: {unknown!r}")
        indexes = [self.feature_names.index(name) for name in selected]
        return RaceArrays(
            race_ids=self.race_ids,
            freeze_at=self.freeze_at,
            label_usable_after=self.label_usable_after,
            years=self.years.copy(),
            group_sizes=self.group_sizes.copy(),
            horse_ids=self.horse_ids,
            features=self.features[:, indexes].copy(),
            feature_names=selected,
            finish_positions=self.finish_positions.copy(),
            market_odds=self.market_odds.copy(),
        )


def _validate_utc_datetimes(values: Sequence[datetime], name: str) -> None:
    for value in values:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise ValueError(f"{name} must contain UTC-aware datetimes")


def _validate_int_array(array: object, name: str, shape: tuple[int, ...]) -> None:
    if not isinstance(array, np.ndarray) or array.dtype != np.int64 or array.shape != shape:
        raise ValueError(f"{name} must be an int64 array with shape {shape!r}")


def _validate_float_array(
    array: object,
    name: str,
    shape: tuple[int | None, ...],
) -> None:
    if not isinstance(array, np.ndarray) or array.dtype != np.float64 or array.ndim != len(shape):
        raise ValueError(f"{name} must be a float64 array with {len(shape)} dimensions")
    if any(
        expected is not None and array.shape[index] != expected
        for index, expected in enumerate(shape)
    ):
        raise ValueError(f"{name} has an invalid shape")
    if np.any(np.isinf(array)):
        raise ValueError(f"{name} must not contain infinite values")


def _group_offsets(group_sizes: IntArray) -> IntArray:
    return np.concatenate((np.array([0], dtype=np.int64), np.cumsum(group_sizes, dtype=np.int64)))


def _validate_race_index(index: int, race_count: int) -> int:
    if isinstance(index, bool) or not isinstance(index, Integral):
        raise ValueError("race subset indexes must be integers")
    normalized = int(index)
    if normalized < 0 or normalized >= race_count:
        raise ValueError("race subset index is out of range")
    return normalized


__all__ = ["RaceArrays"]
