"""Tests for cumulative archiving of transient JVLinkToSQLite odds tables."""

import sqlite3
from datetime import date
from pathlib import Path

from data.race_key import RaceKey
from data.retriever.odds_archive import OddsArchive


def _seed_realtime_tables(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE RT_O1_ODDS_TANFUKUWAKU (race_id TEXT, HappyoTime TEXT, Odds TEXT)"
        )
        connection.execute(
            "CREATE TABLE RT_O2_ODDS_UMAREN (race_id TEXT, HappyoTime TEXT, Odds TEXT)"
        )
        connection.execute("INSERT INTO RT_O1_ODDS_TANFUKUWAKU VALUES ('r1', '101000', '25')")
        connection.execute("INSERT INTO RT_O2_ODDS_UMAREN VALUES ('r1', '101000', '80')")


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]


def test_archive_preserves_schema_and_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _seed_realtime_tables(database)
    archive = OddsArchive(database)

    assert archive.archive() == 2
    assert archive.archive() == 0

    with sqlite3.connect(database) as connection:
        o1_columns = _columns(connection, "ARCHIVE_O1_ODDS_TANFUKUWAKU")
        o2_columns = _columns(connection, "ARCHIVE_O2_ODDS_UMAREN")
        o1_count = connection.execute("SELECT COUNT(*) FROM ARCHIVE_O1_ODDS_TANFUKUWAKU").fetchone()
        o2_count = connection.execute("SELECT COUNT(*) FROM ARCHIVE_O2_ODDS_UMAREN").fetchone()

    assert o1_columns == ["race_id", "HappyoTime", "Odds"]
    assert o2_columns == ["race_id", "HappyoTime", "Odds"]
    assert o1_count == (1,)
    assert o2_count == (1,)


def test_archive_accumulates_rows_after_realtime_table_replacement(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _seed_realtime_tables(database)
    archive = OddsArchive(database)
    archive.archive()

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM RT_O1_ODDS_TANFUKUWAKU")
        connection.execute("DELETE FROM RT_O2_ODDS_UMAREN")
        connection.execute("INSERT INTO RT_O1_ODDS_TANFUKUWAKU VALUES ('r1', '102000', '22')")
        connection.execute("INSERT INTO RT_O2_ODDS_UMAREN VALUES ('r1', '102000', '75')")

    assert archive.archive() == 2
    with sqlite3.connect(database) as connection:
        o1_times = connection.execute(
            "SELECT HappyoTime FROM ARCHIVE_O1_ODDS_TANFUKUWAKU ORDER BY HappyoTime"
        ).fetchall()
        o2_times = connection.execute(
            "SELECT HappyoTime FROM ARCHIVE_O2_ODDS_UMAREN ORDER BY HappyoTime"
        ).fetchall()

    assert o1_times == [("101000",), ("102000",)]
    assert o2_times == [("101000",), ("102000",)]


def test_archive_request_classifies_valid_empty_realtime_tables_as_no_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "race.db"
    with sqlite3.connect(database) as connection:
        for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
            connection.execute(
                f"CREATE TABLE {table} ("
                "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,"
                "idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT)"
            )

    key = RaceKey(date(2008, 1, 27), "01", "01", "08", "01")
    results = OddsArchive(database).archive_request(key, frozenset({"0B41", "0B42"}))

    assert {spec: result.reason for spec, result in results.items()} == {
        "0B41": "jvopen_no_data",
        "0B42": "jvopen_no_data",
    }
    assert not any(result.acquired for result in results.values())
