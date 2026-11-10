"""Create leakage-audited expanding train, validation, and test folds by year."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray

from models.dataset.race_arrays import RaceArrays


@dataclass(frozen=True)
class LabelUseAudit:
    """Record exclusions and post-purge label-use boundaries for one fold."""

    valid_first_freeze_at: datetime
    test_first_freeze_at: datetime
    train_max_label_usable_after: datetime
    valid_max_label_usable_after: datetime
    purged_train_races: int
    purged_valid_races: int


@dataclass(frozen=True)
class YearlyFoldPlan:
    """Hold one audited fold as race indexes into the source arrays, without copies."""

    test_year: int
    train_races: tuple[int, ...]
    valid_races: tuple[int, ...]
    test_races: tuple[int, ...]
    audit: LabelUseAudit

    def materialize(self, arrays: RaceArrays) -> YearlyFold:
        """Copy this fold's races out of the arrays the plan was made from."""
        return YearlyFold(
            test_year=self.test_year,
            train=arrays.subset(self.train_races),
            valid=arrays.subset(self.valid_races),
            test=arrays.subset(self.test_races),
            audit=self.audit,
        )


@dataclass(frozen=True)
class YearlyFold:
    """Hold one expanding yearly split and its label-use audit."""

    test_year: int
    train: RaceArrays
    valid: RaceArrays
    test: RaceArrays
    audit: LabelUseAudit


def plan_yearly_folds(
    arrays: RaceArrays,
    *,
    train_start_year: int,
    test_years: Sequence[int],
) -> tuple[YearlyFoldPlan, ...]:
    """Validate and audit every expanding yearly fold using race indexes only.

    For each test year ``Y``, train contains years from ``train_start_year``
    through ``Y - 2``, valid contains ``Y - 1``, and test contains ``Y``.
    Train labels available at or after the first valid freeze, and valid labels
    available at or after the first test freeze, are excluded. Every fold is
    checked before any is materialized, so configuration errors surface first.

    Raises:
        ValueError: If years are invalid, a split is empty, or post-purge
            label-use boundaries are not strictly before the next split.
    """
    _validate_year(train_start_year, "train_start_year")
    selected_test_years = tuple(test_years)
    if not selected_test_years:
        raise ValueError("test_years must contain at least one year")
    for year in selected_test_years:
        _validate_year(year, "test_years")
    if any(left >= right for left, right in pairwise(selected_test_years)):
        raise ValueError("test_years must be strictly increasing")

    available_years = {int(year) for year in arrays.years}
    if train_start_year not in available_years:
        raise ValueError(f"train_start_year {train_start_year} is not present in the datamart")
    plans: list[YearlyFoldPlan] = []
    for test_year in selected_test_years:
        if test_year not in available_years:
            raise ValueError(f"test year {test_year} is not present in the datamart")
        if train_start_year > test_year - 2:
            raise ValueError("train_start_year must be at most test_year - 2")

        train_indices = _race_indices_between(arrays.years, train_start_year, test_year - 2)
        valid_indices = _race_indices_for_year(arrays.years, test_year - 1)
        test_indices = _race_indices_for_year(arrays.years, test_year)
        _require_nonempty_split(train_indices, "train")
        _require_nonempty_split(valid_indices, "valid")
        _require_nonempty_split(test_indices, "test")

        valid_first_freeze_at = min(arrays.freeze_at[index] for index in valid_indices)
        test_first_freeze_at = min(arrays.freeze_at[index] for index in test_indices)
        retained_train = tuple(
            index
            for index in train_indices
            if arrays.label_usable_after[index] < valid_first_freeze_at
        )
        retained_valid = tuple(
            index
            for index in valid_indices
            if arrays.label_usable_after[index] < test_first_freeze_at
        )
        _require_nonempty_split(retained_train, "train after label purge")
        _require_nonempty_split(retained_valid, "valid after label purge")

        train_max_label_usable_after = max(arrays.label_usable_after[i] for i in retained_train)
        valid_max_label_usable_after = max(arrays.label_usable_after[i] for i in retained_valid)
        if train_max_label_usable_after >= valid_first_freeze_at:
            raise ValueError("train labels cross the valid freeze boundary")
        if max(train_max_label_usable_after, valid_max_label_usable_after) >= test_first_freeze_at:
            raise ValueError("train or valid labels cross the test freeze boundary")

        plans.append(
            YearlyFoldPlan(
                test_year=test_year,
                train_races=retained_train,
                valid_races=retained_valid,
                test_races=test_indices,
                audit=LabelUseAudit(
                    valid_first_freeze_at=valid_first_freeze_at,
                    test_first_freeze_at=test_first_freeze_at,
                    train_max_label_usable_after=train_max_label_usable_after,
                    valid_max_label_usable_after=valid_max_label_usable_after,
                    purged_train_races=len(train_indices) - len(retained_train),
                    purged_valid_races=len(valid_indices) - len(retained_valid),
                ),
            )
        )
    return tuple(plans)


def make_yearly_folds(
    arrays: RaceArrays,
    *,
    train_start_year: int,
    test_years: Sequence[int],
) -> tuple[YearlyFold, ...]:
    """Return every planned fold materialized; see ``plan_yearly_folds``.

    Long runs should materialize one plan at a time instead, because expanding
    train windows overlap and every fold holds its own copy.
    """
    return tuple(
        plan.materialize(arrays)
        for plan in plan_yearly_folds(
            arrays, train_start_year=train_start_year, test_years=test_years
        )
    )


def _validate_year(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must contain integer years")


def _race_indices_between(
    years: NDArray[np.int64], start_year: int, end_year: int
) -> tuple[int, ...]:
    return tuple(index for index, year in enumerate(years) if start_year <= year <= end_year)


def _race_indices_for_year(years: NDArray[np.int64], target_year: int) -> tuple[int, ...]:
    return tuple(index for index, year in enumerate(years) if year == target_year)


def _require_nonempty_split(indices: Sequence[int], name: str) -> None:
    if not indices:
        raise ValueError(f"{name} split must contain at least one race")


__all__ = [
    "LabelUseAudit",
    "YearlyFold",
    "YearlyFoldPlan",
    "make_yearly_folds",
    "plan_yearly_folds",
]
