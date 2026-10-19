"""Tests for ordered datamart joins of intermediate feature tables."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

import make_datamart as datamart_api
from main import app
from make_datamart import builder as builder_api
from make_datamart.builder import join_feature_tables
from make_datamart.tables import parquet as parquet_api
from make_datamart.tables.parquet import make_datamart, read_datamart, write_datamart
from make_features.catalog.loader import load_feature_definitions
from make_features.contracts.rows import FeatureTableRow
from make_features.odds_ratio import OddsRatioInput, build_odds_ratio
from make_features.previous_race_result import PreviousRaceResultInput, build_previous_race_result
from make_features.tables.build import build_feature_table
from make_features.tables.parquet import write_feature_table

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)


AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)


def test_datamart_cli_builds_ordered_validated_parquet(tmp_path: Path) -> None:
    first, second, output = (
        tmp_path / name for name in ("first.parquet", "second.parquet", "out.parquet")
    )
    write_feature_table(_base_table(), first)
    write_feature_table(_odds_table(), second)
    result = CliRunner().invoke(
        app,
        [
            "datamart",
            "build",
            "--input",
            str(first),
            "--input",
            str(second),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert result.stdout == "datamart saved: 2 rows\n"
    assert result.stderr == ""
    assert read_datamart(output).equals(
        join_feature_tables([_base_table(), _odds_table()]), check_metadata=True
    )


@pytest.mark.parametrize("invalid_contents", [None, b"not parquet"])
def test_datamart_cli_reports_input_errors_without_publishing(
    tmp_path: Path, invalid_contents: bytes | None
) -> None:
    source, output = tmp_path / "input.parquet", tmp_path / "out.parquet"
    if invalid_contents is not None:
        source.write_bytes(invalid_contents)
    result = CliRunner().invoke(
        app, ["datamart", "build", "--input", str(source), "--output", str(output)]
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "cannot build datamart:" in result.stderr
    assert not output.exists()


def test_datamart_cli_rejects_incompatible_join_before_writing(tmp_path: Path) -> None:
    first, second, output = (
        tmp_path / name for name in ("first.parquet", "second.parquet", "out.parquet")
    )
    write_feature_table(_base_table(), first)
    write_feature_table(_base_table(), second)
    result = CliRunner().invoke(
        app,
        [
            "datamart",
            "build",
            "--input",
            str(first),
            "--input",
            str(second),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 1
    assert "duplicate feature name" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("custom_catalog", [False, True])
def test_datamart_cli_uses_declared_feature_names(tmp_path: Path, custom_catalog: bool) -> None:
    config = tmp_path / "features.toml" if custom_catalog else Path("configs/features.toml")
    if custom_catalog:
        config.write_text(
            '[[features]]\nid = "CUSTOM"\nname = "custom_feature"\n', encoding="utf-8"
        )
    names = tuple(definition.name for definition in load_feature_definitions(config))
    table = build_feature_table(
        names[0],
        [FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {"value": 2.0})],
        column_types={"value": pa.float64()},
        registered_names=names,
    )
    source, output = tmp_path / "input.parquet", tmp_path / "output.parquet"
    write_feature_table(table, source, registered_names=names)
    result = CliRunner().invoke(
        app,
        [
            "datamart",
            "build",
            "--input",
            str(source),
            "--output",
            str(output),
            "--features-config",
            str(config),
        ],
    )
    assert result.exit_code == 0
    assert read_datamart(output, registered_names=names).equals(
        join_feature_tables([table], registered_names=names), check_metadata=True
    )


def test_datamart_cli_rejects_unregistered_feature(tmp_path: Path) -> None:
    names = ("unregistered_feature",)
    table = build_feature_table(
        names[0],
        [FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {"value": 2.0})],
        column_types={"value": pa.float64()},
        registered_names=names,
    )
    source, output = tmp_path / "input.parquet", tmp_path / "output.parquet"
    write_feature_table(table, source, registered_names=names)
    result = CliRunner().invoke(
        app, ["datamart", "build", "--input", str(source), "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "unsupported feature_name: 'unregistered_feature'" in result.stderr
    assert not output.exists()


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
            parquet_api.build_datamart,
            parquet_api.make_datamart,
            builder_api.join_feature_tables,
            parquet_api.write_datamart,
            parquet_api.read_datamart,
            id="owning-modules",
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
