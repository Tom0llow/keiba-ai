"""Tests for expanding yearly folds and label-use purge boundaries."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from models.dataset.race_arrays import RaceArrays
from models.evaluation.yearly_folds import plan_final_fit, plan_yearly_folds


def test_yearly_folds_purge_labels_at_or_after_the_next_split_freeze() -> None:
    arrays = _yearly_arrays()

    (plan,) = plan_yearly_folds(arrays, train_start_year=2020, test_years=[2023])
    fold = plan.materialize(arrays)

    assert fold.train.race_ids == ("race-2020",)
    assert fold.valid.race_ids == ("race-2022-keep",)
    assert fold.test.race_ids == ("race-2023",)
    assert fold.audit.purged_train_races == 1
    assert fold.audit.purged_valid_races == 1
    assert fold.audit.valid_first_freeze_at == _utc(2022, 1, 1)
    assert fold.audit.test_first_freeze_at == _utc(2023, 1, 1)
    assert fold.audit.train_max_label_usable_after < fold.audit.valid_first_freeze_at
    assert fold.audit.valid_max_label_usable_after < fold.audit.test_first_freeze_at


def test_plans_hold_indexes_and_materialize_to_the_same_folds() -> None:
    arrays = _yearly_arrays()

    (plan,) = plan_yearly_folds(arrays, train_start_year=2020, test_years=[2023])
    materialized = plan.materialize(arrays)

    assert (plan.train_races, plan.valid_races, plan.test_races) == ((0,), (2,), (4,))
    assert materialized.audit == plan.audit
    assert materialized.train.race_ids == ("race-2020",)
    assert materialized.valid.race_ids == ("race-2022-keep",)
    assert materialized.test.race_ids == ("race-2023",)
    np.testing.assert_array_equal(materialized.train.features, arrays.features[:3])


def test_yearly_folds_reject_invalid_years_and_empty_splits() -> None:
    arrays = _yearly_arrays()

    with pytest.raises(ValueError, match="strictly increasing"):
        plan_yearly_folds(arrays, train_start_year=2020, test_years=[2023, 2023])
    with pytest.raises(ValueError, match="not present"):
        plan_yearly_folds(arrays, train_start_year=2020, test_years=[2024])
    with pytest.raises(ValueError, match="at most"):
        plan_yearly_folds(arrays, train_start_year=2022, test_years=[2023])
    with pytest.raises(ValueError, match="train_start_year 2019 is not present"):
        plan_yearly_folds(arrays, train_start_year=2019, test_years=[2023])
    with pytest.raises(ValueError, match="train after label purge"):
        plan_yearly_folds(arrays.subset([1, 2, 3, 4]), train_start_year=2021, test_years=[2023])


def test_final_fit_purges_train_labels_at_the_valid_freeze_and_keeps_every_valid_race() -> None:
    arrays = _yearly_arrays()

    plan = plan_final_fit(arrays, train_start_year=2020, valid_year=2022)
    fit = plan.materialize(arrays)

    assert fit.train.race_ids == ("race-2020",)
    # No test year exists, so the valid race whose label is usable later is kept.
    assert fit.valid.race_ids == ("race-2022-keep", "race-2022-purged")
    assert (plan.train_races, plan.valid_races) == ((0,), (2, 3))
    assert fit.audit.purged_train_races == 1
    assert fit.audit.valid_first_freeze_at == _utc(2022, 1, 1)
    assert fit.audit.train_max_label_usable_after == _utc(2021, 12, 31)
    assert fit.audit.valid_max_label_usable_after == _utc(2023, 1, 1)
    assert fit.audit.label_usable_through == _utc(2023, 1, 1)
    assert (fit.train_start_year, fit.valid_year) == (2020, 2022)


def test_final_fit_through_the_last_year_uses_every_earlier_year_for_training() -> None:
    arrays = _yearly_arrays()

    fit = plan_final_fit(arrays, train_start_year=2020, valid_year=2023).materialize(arrays)

    # The 2022 race whose label is usable at the 2023 freeze is purged from train.
    assert fit.train.race_ids == ("race-2020", "race-2021-purged", "race-2022-keep")
    assert fit.valid.race_ids == ("race-2023",)
    assert fit.audit.label_usable_through == _utc(2023, 12, 1)


def test_final_fit_rejects_invalid_years_and_empty_splits() -> None:
    arrays = _yearly_arrays()

    with pytest.raises(ValueError, match="valid_year 2024 is not present"):
        plan_final_fit(arrays, train_start_year=2020, valid_year=2024)
    with pytest.raises(ValueError, match="train_start_year 2019 is not present"):
        plan_final_fit(arrays, train_start_year=2019, valid_year=2022)
    with pytest.raises(ValueError, match="at most valid_year - 1"):
        plan_final_fit(arrays, train_start_year=2022, valid_year=2022)
    with pytest.raises(ValueError, match="integer years"):
        plan_final_fit(arrays, train_start_year=2020, valid_year=True)
    with pytest.raises(ValueError, match="train after label purge"):
        plan_final_fit(arrays.subset([1, 2, 3]), train_start_year=2021, valid_year=2022)


def _yearly_arrays() -> RaceArrays:
    race_ids = (
        "race-2020",
        "race-2021-purged",
        "race-2022-keep",
        "race-2022-purged",
        "race-2023",
    )
    freeze_at = (
        _utc(2020, 1, 1),
        _utc(2021, 1, 1),
        _utc(2022, 1, 1),
        _utc(2022, 6, 1),
        _utc(2023, 1, 1),
    )
    labels = (
        _utc(2021, 12, 31),
        _utc(2022, 1, 1),
        _utc(2022, 12, 1),
        _utc(2023, 1, 1),
        _utc(2023, 12, 1),
    )
    row_count = len(race_ids) * 3
    return RaceArrays(
        race_ids=race_ids,
        freeze_at=freeze_at,
        label_usable_after=labels,
        years=np.array([2020, 2021, 2022, 2022, 2023], dtype=np.int64),
        group_sizes=np.full(len(race_ids), 3, dtype=np.int64),
        horse_ids=tuple(f"horse-{index}" for index in range(row_count)),
        features=np.arange(row_count, dtype=np.float64).reshape(row_count, 1),
        feature_names=("feature",),
        finish_positions=np.tile(np.array([1, 2, 3], dtype=np.int64), len(race_ids)),
        market_odds=np.full(row_count, 2.0, dtype=np.float64),
    )


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)
