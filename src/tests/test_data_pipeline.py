"""Tests for raw SQLite preprocessing and processed Parquet loading."""

import sqlite3
from datetime import date
from pathlib import Path

import pyarrow as pa
import pytest

from data.config import DataPaths
from data.data_loader import DataLoader
from data.data_preprocesser import DataPreprocesser
from data.race_key import RaceKey


def _paths(tmp_path: Path) -> DataPaths:
    return DataPaths(
        raw_db=tmp_path / "raw" / "race.db",
        processed_dir=tmp_path / "processed",
        jvlink_runtime_dir=tmp_path / "runtime",
    )


def _create_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (RaceKey TEXT, RaceDate TEXT, Note TEXT)"
        )
        database.executemany(
            "INSERT INTO NL_RA_RACE VALUES (?, ?, ?)",
            [("001", "20261004", None), ("002", "20261005", "race")],
        )
        columns = (
            "idYear TEXT, idMonthDay TEXT, idJyoCD TEXT, idKaiji TEXT, "
            "idNichiji TEXT, idRaceNum TEXT, HappyoTime TEXT, Odds TEXT"
        )
        database.execute(f"CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE ARCHIVE_O2_ODDS_UMAREN ({columns})")
        rows = [
            ("2026", "1004", "05", "04", "08", "11", "150000", "25"),
            ("2026", "1004", "05", "04", "08", "12", "150000", "30"),
        ]
        database.executemany(
            "INSERT INTO ARCHIVE_O1_ODDS_TANFUKUWAKU VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        database.executemany(
            "INSERT INTO ARCHIVE_O2_ODDS_UMAREN VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def test_rebuild_publishes_snapshot_and_loader_reads_only_parquet(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _create_source(paths.raw_db)

    counts = DataPreprocesser(paths).rebuild()
    assert counts["NL_RA_RACE"] == 2

    loader = DataLoader(paths)
    assert "NL_RA_RACE" in loader.list_tables()
    table = loader.read_table("NL_RA_RACE")
    assert table.schema.types == [pa.string(), pa.string(), pa.string()]
    assert table.to_pylist() == [
        {"RaceKey": "001", "RaceDate": "20261004", "Note": None},
        {"RaceKey": "002", "RaceDate": "20261005", "Note": "race"},
    ]

    paths.raw_db.unlink()
    assert loader.read_table("NL_RA_RACE").num_rows == 2


def test_rebuild_keeps_previous_snapshot_when_export_fails(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _create_source(paths.raw_db)
    preprocesser = DataPreprocesser(paths)
    preprocesser.rebuild()
    current_before = (paths.processed_dir / "CURRENT").read_text(encoding="utf-8")

    with sqlite3.connect(paths.raw_db) as database:
        database.execute("CREATE TABLE BAD_TABLE (Value INTEGER)")
        database.execute("INSERT INTO BAD_TABLE VALUES (1)")

    with pytest.raises(ValueError, match="unsupported declared type"):
        preprocesser.rebuild()

    assert (paths.processed_dir / "CURRENT").read_text(encoding="utf-8") == current_before
    assert DataLoader(paths).read_table("NL_RA_RACE").num_rows == 2


def test_realtime_update_publishes_only_target_race_parquet(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _create_source(paths.raw_db)
    race_key = RaceKey(date(2026, 10, 4), "05", "04", "08", "11")

    counts = DataPreprocesser(paths).update_race(race_key)

    assert counts == {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 1,
        "ARCHIVE_O2_ODDS_UMAREN": 1,
    }
    loader = DataLoader(paths)
    o1 = loader.read_realtime_table(race_key, "ARCHIVE_O1_ODDS_TANFUKUWAKU")
    o2 = loader.read_realtime_table(race_key, "ARCHIVE_O2_ODDS_UMAREN")
    assert o1.num_rows == 1
    assert o2.num_rows == 1
    assert o1.column("idRaceNum").to_pylist() == ["11"]
    assert o2.column("idRaceNum").to_pylist() == ["11"]


def test_data_paths_resolve_all_shared_locations(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = config_dir / "data.toml"
    config.write_text(
        "[paths]\n"
        'raw_db = "../raw/race.db"\n'
        'processed_dir = "../processed"\n'
        'jvlink_runtime_dir = "../runtime/jvlink"\n',
        encoding="utf-8",
    )

    assert DataPaths.from_toml(config) == DataPaths(
        tmp_path / "raw" / "race.db",
        tmp_path / "processed",
        tmp_path / "runtime" / "jvlink",
    )
