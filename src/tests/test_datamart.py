"""Tests for ordered datamart joins of intermediate feature tables."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import make_datamart as datamart_api
from features.contracts.rows import FeatureTableRow
from features.odds_ratio import OddsRatioInput, build_odds_ratio
from features.previous_race_result import PreviousRaceResultInput, build_previous_race_result
from features.tables.build import build_feature_table
from features.tables.parquet import write_feature_table
from make_datamart import builder as builder_api
from make_datamart.builder import (
    join_feature_tables,
    make_datamart,
)
from make_datamart.tables.parquet import read_datamart, write_datamart

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)


def _base_table() -> pa.Table:
    return build_previous_race_result(
        [
            PreviousRaceResultInput("race-2", "horse-2", FREEZE_AT, AVAILABLE_AT, 4),
            PreviousRaceResultInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2),
        ]
    )


def _odds_table() -> pa.Table:
    return build_odds_ratio(
        [OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0)]
    )


def test_datamart_reads_parquet_and_preserves_base_order(tmp_path: Path) -> None:
    base_path = tmp_path / "previous.parquet"
    odds_path = tmp_path / "odds.parquet"
    write_feature_table(_base_table(), base_path)
    write_feature_table(_odds_table(), odds_path)

    datamart = make_datamart([base_path, odds_path])

    assert list(
        zip(
            datamart["race_id"].to_pylist(),
            datamart["horse_id"].to_pylist(),
            strict=True,
        )
    ) == [("race-2", "horse-2"), ("race-1", "horse-1")]
    assert datamart["previous_race_finish_position"].to_pylist() == [4, 2]
    assert datamart["odds_ratio"].to_pylist() == [None, 0.5]
    assert datamart["odds_ratio__available_at"].to_pylist() == [
        None,
        AVAILABLE_AT,
    ]


def test_datamart_rejects_extra_key() -> None:
    extra = build_odds_ratio(
        [
            OddsRatioInput("race-2", "horse-2", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0),
            OddsRatioInput("race-3", "horse-3", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0),
        ]
    )

    with pytest.raises(ValueError, match="extra key"):
        join_feature_tables([_base_table(), extra])


def test_datamart_rejects_freeze_at_mismatch_for_same_key() -> None:
    mismatched = build_odds_ratio(
        [
            OddsRatioInput(
                "race-1",
                "horse-1",
                FREEZE_AT + timedelta(minutes=1),
                AVAILABLE_AT,
                2.0,
                4.0,
            )
        ]
    )

    with pytest.raises(ValueError, match="freeze_at mismatch"):
        join_feature_tables([_base_table(), mismatched])


def test_datamart_rejects_duplicate_feature_name() -> None:
    with pytest.raises(ValueError, match="duplicate feature name"):
        join_feature_tables([_base_table(), _base_table()])


@pytest.mark.parametrize("first_column", ["past_value", "second_feature__available_at"])
def test_datamart_rejects_value_and_availability_column_collisions(first_column: str) -> None:
    names = ("first_feature", "second_feature")
    tables = [
        build_feature_table(
            name,
            [FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {column: 1})],
            column_types={column: pa.int64()},
            registered_names=names,
        )
        for name, column in zip(names, (first_column, "past_value"), strict=True)
    ]

    with pytest.raises(ValueError, match="feature column collision"):
        join_feature_tables(tables, registered_names=names)


def test_datamart_rejects_incomplete_saved_schema(tmp_path: Path) -> None:
    table = join_feature_tables([_base_table(), _odds_table()])
    invalid = table.drop(["odds_ratio"])

    with pytest.raises(ValueError, match="columns"):
        write_datamart(invalid, tmp_path / "invalid.parquet")


def test_datamart_rejects_non_finite_odds_ratio_at_save_boundaries(
    tmp_path: Path,
) -> None:
    table = join_feature_tables([_base_table(), _odds_table()])
    invalid = table.set_column(
        table.schema.get_field_index("odds_ratio"),
        "odds_ratio",
        pa.array([None, float("inf")], type=pa.float64()),
    )

    with pytest.raises(ValueError, match="odds_ratio must be finite"):
        write_datamart(invalid, tmp_path / "invalid.parquet")

    invalid_path = tmp_path / "invalid-read.parquet"
    pq.write_table(invalid, invalid_path)
    with pytest.raises(ValueError, match="odds_ratio must be finite"):
        read_datamart(invalid_path)


def test_datamart_round_trips_through_parquet(tmp_path: Path) -> None:
    previous_path = tmp_path / "previous.parquet"
    odds_path = tmp_path / "odds.parquet"
    write_feature_table(_base_table(), previous_path)
    write_feature_table(_odds_table(), odds_path)

    table = make_datamart([previous_path, odds_path])
    datamart_path = tmp_path / "datamart.parquet"
    write_datamart(table, datamart_path)

    assert read_datamart(datamart_path).equals(table, check_metadata=True)


@pytest.mark.parametrize(
    ("build", "make", "join", "write", "read"),
    [
        pytest.param(
            datamart_api.build_datamart,
            datamart_api.make_datamart,
            datamart_api.join_feature_tables,
            datamart_api.write_datamart,
            datamart_api.read_datamart,
            id="package",
        ),
        pytest.param(
            builder_api.build_datamart,
            builder_api.make_datamart,
            builder_api.join_feature_tables,
            builder_api.write_datamart,
            builder_api.read_datamart,
            id="builder",
        ),
    ],
)
def test_existing_public_datamart_functions_preserve_round_trip(
    tmp_path: Path,
    build: Callable[[Sequence[str | Path]], pa.Table],
    make: Callable[[Sequence[str | Path]], pa.Table],
    join: Callable[[Sequence[pa.Table]], pa.Table],
    write: Callable[[pa.Table, str | Path], None],
    read: Callable[[str | Path], pa.Table],
) -> None:
    tables = [_base_table(), _odds_table()]
    paths = [tmp_path / "previous.parquet", tmp_path / "odds.parquet"]
    for table, path in zip(tables, paths, strict=True):
        write_feature_table(table, path)
    expected = join(tables)

    assert build(paths).equals(expected, check_metadata=True)
    assert make(paths).equals(expected, check_metadata=True)
    destination = tmp_path / "datamart.parquet"
    write(expected, destination)
    assert read_datamart(destination).equals(expected, check_metadata=True)
    assert read(destination).equals(expected, check_metadata=True)

    canonical_destination = tmp_path / "canonical.parquet"
    write_datamart(expected, canonical_destination)
    assert read(canonical_destination).equals(expected, check_metadata=True)
