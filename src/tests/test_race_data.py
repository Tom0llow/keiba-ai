"""Tests for the configured SQLite-to-Parquet data boundary."""

import sqlite3
from pathlib import Path

import pyarrow as pa
import pytest

from data.race_data import DataPaths, RaceDataLoader, convert_all_tables

pytestmark = pytest.mark.integration


def _create_source(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            'CREATE TABLE "NL_RA_RACE" '
            "(RaceKey TEXT, RaceDate TEXT, ObservedAt DATETIME, Note TEXT)"
        )
        db.executemany(
            'INSERT INTO "NL_RA_RACE" VALUES (?, ?, ?, ?)',
            [
                (" 001 ", "00000000", "0000-00-00", None),
                ("002", "20261001", "2026-10-01 12:00:00", "  "),
                ("003", "", None, "競走"),
            ],
        )
        db.execute('CREATE TABLE "NL_UM_UMA" (HorseKey TEXT)')


def test_convert_and_load_preserves_rows_columns_and_empty_tables(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    _create_source(source)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "data.toml"
    config_path.write_text(
        '[paths]\nraw_db = "../raw.db"\nprocessed_dir = "../processed"\n', encoding="utf-8"
    )

    paths = DataPaths.from_toml(config_path)
    assert paths == DataPaths(source, tmp_path / "processed")
    assert convert_all_tables(paths) == {"NL_RA_RACE": 3, "NL_UM_UMA": 0}

    loader = RaceDataLoader(paths)
    assert loader.list_tables() == ["NL_RA_RACE", "NL_UM_UMA"]
    race = loader.read_table("NL_RA_RACE")
    assert race.column_names == ["RaceKey", "RaceDate", "ObservedAt", "Note"]
    assert race.schema.types == [pa.string(), pa.string(), pa.string(), pa.string()]
    assert race.to_pylist() == [
        {"RaceKey": " 001 ", "RaceDate": "00000000", "ObservedAt": "0000-00-00", "Note": None},
        {
            "RaceKey": "002",
            "RaceDate": "20261001",
            "ObservedAt": "2026-10-01 12:00:00",
            "Note": "  ",
        },
        {"RaceKey": "003", "RaceDate": "", "ObservedAt": None, "Note": "競走"},
    ]
    assert [batch.num_rows for batch in loader.iter_batches("NL_RA_RACE", batch_size=2)] == [2, 1]
    assert loader.read_table("NL_UM_UMA").num_rows == 0
    assert loader.read_table("NL_UM_UMA").column_names == ["HorseKey"]


def test_convert_wide_table_keeps_every_column(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    column_names = [f"Field{index}" for index in range(932)]
    with sqlite3.connect(source) as db:
        db.execute(f"CREATE TABLE Wide ({', '.join(f'{name} TEXT' for name in column_names)})")
        db.execute(
            f"INSERT INTO Wide VALUES ({', '.join('?' for _ in column_names)})",
            [f"value-{index}" for index in range(len(column_names))],
        )

    paths = DataPaths(source, tmp_path / "processed")
    assert convert_all_tables(paths) == {"Wide": 1}
    table = RaceDataLoader(paths).read_table("Wide")
    assert table.column_names == column_names
    assert table.num_columns == 932
    assert table.column("Field931").to_pylist() == ["value-931"]


def test_convert_reads_every_row_across_multiple_batches(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    total_rows = 65_537
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE ManyRows (Value TEXT)")
        db.executemany(
            "INSERT INTO ManyRows VALUES (?)", ((str(index),) for index in range(total_rows))
        )

    paths = DataPaths(source, tmp_path / "processed")
    assert convert_all_tables(paths) == {"ManyRows": total_rows}
    table = RaceDataLoader(paths).read_table("ManyRows")
    assert table.num_rows == total_rows
    assert table.column("Value")[0].as_py() == "0"
    assert table.column("Value")[-1].as_py() == str(total_rows - 1)


def test_convert_orders_by_internal_rowid_when_column_shadows_name(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE Shadowed (RowID TEXT, Value TEXT)")
        db.executemany(
            "INSERT INTO Shadowed VALUES (?, ?)",
            [("2", "first"), ("1", "second")],
        )

    paths = DataPaths(source, tmp_path / "processed")
    assert convert_all_tables(paths) == {"Shadowed": 2}
    assert RaceDataLoader(paths).read_table("Shadowed").column("Value").to_pylist() == [
        "first",
        "second",
    ]


def test_convert_includes_user_table_starting_with_sqlite(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sqliteData (Value TEXT)")
        db.execute("INSERT INTO sqliteData VALUES (?)", ("kept",))

    paths = DataPaths(source, tmp_path / "processed")
    assert convert_all_tables(paths) == {"sqliteData": 1}
    assert RaceDataLoader(paths).read_table("sqliteData").column("Value").to_pylist() == ["kept"]


def test_convert_refuses_to_replace_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    _create_source(source)
    processed = tmp_path / "processed"
    processed.mkdir()
    sentinel = processed / "keep.txt"
    sentinel.write_text("owned", encoding="utf-8")

    with pytest.raises(FileExistsError):
        convert_all_tables(DataPaths(source, processed))

    assert sentinel.read_text(encoding="utf-8") == "owned"


def test_bad_sqlite_scalar_removes_staging_and_publishes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE "A_Good" (Value TEXT)')
        db.execute('INSERT INTO "A_Good" VALUES (?)', ("okay",))
        db.execute('CREATE TABLE "B_Bad" (Value TEXT)')
        db.execute('INSERT INTO "B_Bad" VALUES (?)', (b"\x00",))

    processed = tmp_path / "processed"
    with pytest.raises(TypeError, match=r"B_Bad\.Value"):
        convert_all_tables(DataPaths(source, processed))

    assert not processed.exists()
    assert list(tmp_path.glob(".processed.tmp-*")) == []


def test_table_name_validation_blocks_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "raw.db"
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE "invalid/name" (Value TEXT)')

    processed = tmp_path / "processed"
    with pytest.raises(ValueError, match="invalid table name"):
        convert_all_tables(DataPaths(source, processed))
    with pytest.raises(ValueError, match="invalid table name"):
        RaceDataLoader(DataPaths(source, processed)).read_table("../raw")

    assert not processed.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "config must contain a"),
        ("[paths]\nraw_db = 42\nprocessed_dir = 'processed'\n", "raw_db must be"),
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, content: str, message: str) -> None:
    config = tmp_path / "data.toml"
    config.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        DataPaths.from_toml(config)
