"""Tests for NumPy race arrays and reference datamart conversion."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pyarrow as pa
import pytest

from models.dataset.race_arrays import RaceArrays
from models.serialization.race_arrays import race_arrays_from_reference_tables


def test_race_arrays_validate_invariants_and_return_race_and_column_subsets() -> None:
    arrays = _arrays()

    subset = arrays.subset([1])
    columns = arrays.columns(["feature_b"])

    assert subset.race_ids == ("race-2",)
    assert subset.horse_ids == ("horse-4", "horse-5", "horse-6", "horse-7")
    assert subset.features.tolist() == arrays.features[3:].tolist()
    assert subset.finish_positions.tolist() == [1, 2, 3, 4]
    np.testing.assert_array_equal(subset.market_odds, arrays.market_odds[3:])
    assert subset.freeze_at == (arrays.freeze_at[1],)
    assert subset.label_usable_after == (arrays.label_usable_after[1],)
    assert subset.years.tolist() == [2025]
    assert subset.group_sizes.tolist() == [4]
    reordered = arrays.subset([1, 0])
    assert reordered.race_ids == ("race-2", "race-1")
    assert reordered.horse_ids[4:] == ("horse-1", "horse-2", "horse-3")
    assert reordered.features[4:].tolist() == arrays.features[:3].tolist()
    assert columns.feature_names == ("feature_b",)
    assert columns.features.tolist() == [[1.0], [3.0], [5.0], [7.0], [9.0], [11.0], [13.0]]
    assert not arrays.features.flags.writeable
    with pytest.raises(ValueError, match="unique"):
        arrays.subset([0, 0])
    with pytest.raises(ValueError, match="unknown"):
        arrays.columns(["missing"])


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"features": np.ones((7, 2), dtype=np.float32)}, "float64"),
        ({"group_sizes": np.array([2, 4], dtype=np.int64)}, "at least 3"),
        (
            {"finish_positions": np.array([1, 1, 3, 1, 2, 3, 4], dtype=np.int64)},
            "permutation",
        ),
        (
            {"freeze_at": (datetime(2025, 1, 1), datetime(2025, 2, 1, tzinfo=UTC))},
            "UTC-aware",
        ),
    ],
)
def test_race_arrays_reject_invalid_shapes_types_and_positions(
    replacement: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_arrays(), **replacement)


def test_reference_tables_are_stably_sorted_and_converted_to_race_arrays() -> None:
    rows, races = _reference_tables()

    arrays = race_arrays_from_reference_tables(
        rows,
        races,
        feature_columns=["feature_a"],
        market_column="market_win_odds",
    )

    assert arrays.race_ids == ("race-b", "race-a")
    assert arrays.horse_ids == (
        "horse-b1",
        "horse-b2",
        "horse-b3",
        "horse-a1",
        "horse-a2",
        "horse-a3",
    )
    assert arrays.group_sizes.tolist() == [3, 3]
    assert arrays.years.tolist() == [2025, 2026]
    assert arrays.feature_names == ("feature_a",)
    assert np.isnan(arrays.features[0, 0])
    assert np.isnan(arrays.market_odds[1])
    assert arrays.finish_positions.tolist() == [1, 2, 3, 1, 2, 3]


def test_races_sharing_a_freeze_time_are_ordered_by_race_id_then_horse_id() -> None:
    rows, races = _reference_tables()
    shared_freeze = races.column("freeze_at")[1]
    shared_start = races.column("scheduled_start_at")[1]
    rows = rows.set_column(
        rows.schema.get_field_index("freeze_at"),
        "freeze_at",
        pa.array([shared_freeze.as_py()] * rows.num_rows, type=pa.timestamp("us", tz="UTC")),
    ).set_column(
        rows.schema.get_field_index("scheduled_start_at"),
        "scheduled_start_at",
        pa.array([shared_start.as_py()] * rows.num_rows, type=pa.timestamp("us", tz="UTC")),
    )
    races = races.set_column(
        races.schema.get_field_index("freeze_at"),
        "freeze_at",
        pa.array([shared_freeze.as_py()] * 2, type=pa.timestamp("us", tz="UTC")),
    ).set_column(
        races.schema.get_field_index("scheduled_start_at"),
        "scheduled_start_at",
        pa.array([shared_start.as_py()] * 2, type=pa.timestamp("us", tz="UTC")),
    )

    arrays = race_arrays_from_reference_tables(
        rows, races, feature_columns=["feature_a"], market_column="market_win_odds"
    )

    assert arrays.race_ids == ("race-a", "race-b")
    assert arrays.horse_ids == (
        "horse-a1",
        "horse-a2",
        "horse-a3",
        "horse-b1",
        "horse-b2",
        "horse-b3",
    )
    assert arrays.finish_positions.tolist() == [1, 2, 3, 1, 2, 3]
    assert arrays.features[:3, 0].tolist() == [1.0, 2.0, 3.0]


def test_market_column_can_also_be_a_model_feature() -> None:
    rows, races = _reference_tables()

    arrays = race_arrays_from_reference_tables(
        rows,
        races,
        feature_columns=["feature_a", "market_win_odds"],
        market_column="market_win_odds",
    )

    assert arrays.feature_names == ("feature_a", "market_win_odds")
    np.testing.assert_array_equal(arrays.features[:, 1], arrays.market_odds)


def test_reference_table_conversion_rejects_contract_violations() -> None:
    rows, races = _reference_tables()

    with pytest.raises(ValueError, match="duplicates"):
        race_arrays_from_reference_tables(
            rows,
            races,
            feature_columns=["feature_a", "feature_a"],
            market_column="market_win_odds",
        )
    with pytest.raises(ValueError, match="missing required column"):
        race_arrays_from_reference_tables(
            rows.drop(["feature_a"]),
            races,
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )

    wrong_type = rows.set_column(
        rows.schema.get_field_index("feature_a"),
        "feature_a",
        pa.array(["x"] * rows.num_rows, type=pa.string()),
    )
    with pytest.raises(ValueError, match="invalid type"):
        race_arrays_from_reference_tables(
            wrong_type,
            races,
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )

    with pytest.raises(ValueError, match="matching race"):
        race_arrays_from_reference_tables(
            rows,
            races.slice(0, 1),
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )

    invalid_positions = rows.set_column(
        rows.schema.get_field_index("finish_position"),
        "finish_position",
        pa.array([1, 2, 3, 1, 1, 3], type=pa.int64()),
    )
    with pytest.raises(ValueError, match="permutation"):
        race_arrays_from_reference_tables(
            invalid_positions,
            races,
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )

    shifted_freeze = races.set_column(
        races.schema.get_field_index("freeze_at"),
        "freeze_at",
        pa.array(
            [value + timedelta(seconds=1) for value in races.column("freeze_at").to_pylist()],
            type=pa.timestamp("us", tz="UTC"),
        ),
    )
    with pytest.raises(ValueError, match="timestamps differ"):
        race_arrays_from_reference_tables(
            rows,
            shifted_freeze,
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )

    wrong_size = races.set_column(
        races.schema.get_field_index("field_size"),
        "field_size",
        pa.array([3, 4], type=pa.int64()),
    )
    with pytest.raises(ValueError, match="field_size"):
        race_arrays_from_reference_tables(
            rows,
            wrong_size,
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )

    too_small = races.set_column(
        races.schema.get_field_index("field_size"),
        "field_size",
        pa.array([3, 2], type=pa.int64()),
    )
    with pytest.raises(ValueError, match="at least 3"):
        race_arrays_from_reference_tables(
            rows,
            too_small,
            feature_columns=["feature_a"],
            market_column="market_win_odds",
        )


def _arrays() -> RaceArrays:
    return RaceArrays(
        race_ids=("race-1", "race-2"),
        freeze_at=(_utc(2025, 1, 1), _utc(2025, 2, 1)),
        label_usable_after=(_utc(2025, 1, 8), _utc(2025, 2, 8)),
        years=np.array([2025, 2025], dtype=np.int64),
        group_sizes=np.array([3, 4], dtype=np.int64),
        horse_ids=("horse-1", "horse-2", "horse-3", "horse-4", "horse-5", "horse-6", "horse-7"),
        features=np.arange(14, dtype=np.float64).reshape(7, 2),
        feature_names=("feature_a", "feature_b"),
        finish_positions=np.array([1, 2, 3, 1, 2, 3, 4], dtype=np.int64),
        market_odds=np.array([2.0, 3.0, np.nan, 4.0, 5.0, 6.0, 7.0], dtype=np.float64),
    )


def _reference_tables() -> tuple[pa.Table, pa.Table]:
    scheduled_a = datetime(2025, 12, 31, 15, 0, tzinfo=UTC)
    scheduled_b = datetime(2025, 1, 1, 15, 0, tzinfo=UTC)
    freeze_a = scheduled_a - timedelta(minutes=5)
    freeze_b = scheduled_b - timedelta(minutes=5)
    rows = pa.table(
        {
            "race_id": pa.array(
                ["race-a", "race-a", "race-a", "race-b", "race-b", "race-b"], type=pa.string()
            ),
            "horse_id": pa.array(
                ["horse-a2", "horse-a1", "horse-a3", "horse-b3", "horse-b1", "horse-b2"],
                type=pa.string(),
            ),
            "scheduled_start_at": pa.array(
                [scheduled_a, scheduled_a, scheduled_a, scheduled_b, scheduled_b, scheduled_b],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "freeze_at": pa.array(
                [freeze_a, freeze_a, freeze_a, freeze_b, freeze_b, freeze_b],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "feature_a": pa.array([2.0, 1.0, 3.0, 3.0, None, 2.0], type=pa.float64()),
            "market_win_odds": pa.array([3.0, 2.0, 5.0, 6.0, 2.0, None], type=pa.float64()),
            "finish_position": pa.array([2, 1, 3, 3, 1, 2], type=pa.int64()),
        }
    )
    races = pa.table(
        {
            "race_id": pa.array(["race-a", "race-b"], type=pa.string()),
            "scheduled_start_at": pa.array(
                [scheduled_a, scheduled_b], type=pa.timestamp("us", tz="UTC")
            ),
            "freeze_at": pa.array([freeze_a, freeze_b], type=pa.timestamp("us", tz="UTC")),
            "field_size": pa.array([3, 3], type=pa.int64()),
            "label_usable_after": pa.array(
                [scheduled_a + timedelta(days=7), scheduled_b + timedelta(days=7)],
                type=pa.timestamp("us", tz="UTC"),
            ),
        }
    )
    return rows, races


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)
