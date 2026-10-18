"""Tests for raw SQLite preprocessing and processed Parquet loading."""

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import date
from pathlib import Path

import pyarrow as pa
import pytest

from configuration.data_paths import DataPaths
from data.loader.processed_data_loader import DataLoader
from data.saver.write_parquet import write_parquet_batches
from data.storage import snapshot_builder
from data.storage.snapshot_builder import DataPreprocesser
from data.storage.snapshot_store import SnapshotStore
from domain.race_key import RaceKey


def _paths(tmp_path: Path) -> DataPaths:
    return DataPaths(
        raw_db=tmp_path / "raw" / "race.db",
        processed_dir=tmp_path / "processed",
        jvlink_runtime_dir=tmp_path / "runtime",
    )


def _create_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as database, database:
        database.execute("CREATE TABLE NL_RA_RACE (RaceKey TEXT, RaceDate TEXT, Note TEXT)")
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


def test_realtime_update_keeps_previous_version_when_second_export_fails(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _create_source(paths.raw_db)
    race_key = RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    preprocesser = DataPreprocesser(paths)
    preprocesser.update_race(race_key)
    race_root = paths.processed_dir / "realtime" / race_key.race_id
    current_before = (race_root / "CURRENT").read_text(encoding="utf-8")
    versions_before = set((race_root / "versions").iterdir())
    with closing(sqlite3.connect(paths.raw_db)) as database, database:
        database.execute("ALTER TABLE ARCHIVE_O2_ODDS_UMAREN ADD COLUMN Invalid INTEGER")

    with pytest.raises(ValueError, match="unsupported declared type"):
        preprocesser.update_race(race_key)

    assert (race_root / "CURRENT").read_text(encoding="utf-8") == current_before
    assert set((race_root / "versions").iterdir()) == versions_before
    loader = DataLoader(paths)
    for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
        assert loader.read_realtime_table(race_key, table).num_rows == 1


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


def test_batches_defer_snapshot_lookup_and_validate_size_first(tmp_path: Path) -> None:
    loader = DataLoader(_paths(tmp_path))
    batches = loader.iter_batches("NL_RA_RACE", batch_size=0)
    with pytest.raises(ValueError, match="batch_size must be positive"):
        next(batches)
    batches = loader.iter_batches("NL_RA_RACE")
    with pytest.raises(FileNotFoundError):
        next(batches)


def test_batches_observe_current_at_first_iteration(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _create_source(paths.raw_db)
    builder = DataPreprocesser(paths)
    builder.rebuild()
    batches = DataLoader(paths).iter_batches("NL_RA_RACE")
    with closing(sqlite3.connect(paths.raw_db)) as database, database:
        database.execute("INSERT INTO NL_RA_RACE VALUES ('003', '20261006', NULL)")
    builder.rebuild()
    assert sum(batch.num_rows for batch in batches) == 3


@pytest.mark.parametrize("realtime", [False, True])
def test_current_replacement_failure_keeps_readable_previous_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, realtime: bool
) -> None:
    paths = _paths(tmp_path)
    _create_source(paths.raw_db)
    race = RaceKey(date(2026, 10, 4), "05", "04", "08", "11") if realtime else None
    builder = DataPreprocesser(paths)
    publish = builder.rebuild if race is None else lambda: builder.update_race(race)
    publish()
    store = SnapshotStore(paths.processed_dir)
    current = store.current_snapshot(race)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("CURRENT replacement failed")

    monkeypatch.setattr("data.storage.snapshot_publisher.os.replace", fail_replace)
    with pytest.raises(OSError, match="CURRENT replacement failed"):
        publish()
    assert store.current_snapshot(race) == current
    loader = DataLoader(paths)
    table = (
        loader.read_table("NL_RA_RACE")
        if race is None
        else loader.read_realtime_table(race, "ARCHIVE_O1_ODDS_TANFUKUWAKU")
    )
    assert table.num_rows == (2 if race is None else 1)


def test_complete_snapshot_uses_one_read_transaction_across_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    paths.raw_db.parent.mkdir(parents=True)
    with closing(sqlite3.connect(paths.raw_db)) as database, database:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("CREATE TABLE FIRST_TABLE (value TEXT)")
        database.execute("CREATE TABLE SECOND_TABLE (value TEXT)")
        database.execute("INSERT INTO FIRST_TABLE VALUES ('before')")
        database.execute("INSERT INTO SECOND_TABLE VALUES ('before')")
    write_batches = write_parquet_batches

    def write_and_change_raw(path: Path, schema: pa.Schema, batches: Iterable[pa.Table]) -> int:
        count = write_batches(path, schema, batches)
        if path.stem == "FIRST_TABLE":
            with closing(sqlite3.connect(paths.raw_db)) as database, database:
                database.execute("UPDATE SECOND_TABLE SET value = 'after'")
        return count

    monkeypatch.setattr(snapshot_builder, "write_parquet_batches", write_and_change_raw)
    DataPreprocesser(paths).rebuild()
    assert DataLoader(paths).read_table("SECOND_TABLE")["value"].to_pylist() == ["before"]
    with closing(sqlite3.connect(paths.raw_db)) as database:
        assert database.execute("SELECT value FROM SECOND_TABLE").fetchone() == ("after",)


def test_sqlite_batches_preserve_empty_schema_nulls_and_leading_zeros(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.raw_db.parent.mkdir(parents=True)
    with closing(sqlite3.connect(paths.raw_db)) as database, database:
        database.execute("CREATE TABLE EMPTY_TABLE (value TEXT, stamp DATETIME)")
        database.execute("CREATE TABLE SOURCE_TABLE (rowid TEXT, value TEXT)")
        database.executemany(
            "INSERT INTO SOURCE_TABLE VALUES (?, ?)",
            ((f"{index:06}", None if index == 0 else "001") for index in range(65_537)),
        )
    assert DataPreprocesser(paths).rebuild() == {"EMPTY_TABLE": 0, "SOURCE_TABLE": 65_537}
    loader = DataLoader(paths)
    empty = loader.read_table("EMPTY_TABLE")
    assert empty.schema == pa.schema(
        [pa.field("value", pa.string()), pa.field("stamp", pa.string())]
    )
    source = loader.read_table("SOURCE_TABLE")
    assert source["rowid"][0].as_py() == "000000"
    assert source["rowid"][-1].as_py() == "065536"
    assert source["value"][0].as_py() is None
    assert source["value"][1].as_py() == "001"
