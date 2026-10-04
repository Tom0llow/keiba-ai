"""Tests for cumulative archiving of transient JVLinkToSQLite odds tables."""

import sqlite3
from pathlib import Path

from data.retriever.odds_archive import OddsArchive


def _seed_realtime_tables(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE RT_O1_ODDS_TANFUKUWAKU (race_id TEXT, HappyoTime TEXT, Odds TEXT)"
        )
        connection.execute(
            "CREATE TABLE RT_O2_ODDS_UMAREN (race_id TEXT, HappyoTime TEXT, Odds TEXT)"
        )
        connection.execute(
            "INSERT INTO RT_O1_ODDS_TANFUKUWAKU VALUES ('r1', '101000', '25')"
        )
        connection.execute(
            "INSERT INTO RT_O2_ODDS_UMAREN VALUES ('r1', '101000', '80')"
        )


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]


def test_archive_preserves_schema_and_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _seed_realtime_tables(database)
    archive = OddsArchive(database)

    assert archive.archive() == 2
    assert archive.archive() == 0

    with sqlite3.connect(database) as connection:
        assert _columns(connection, "ARCHIVE_O1_ODDS_TANFUKUWAKU") == [
            "race_id",
            "HappyoTime",
            "Odds",
        ]
        assert _columns(connection, "ARCHIVE_O2_ODDS_UMAREN") == [
            "race_id",
            "HappyoTime",
            "Odds",
        ]
        assert connection.execute(
            "SELECT COUNT(*) FROM ARCHIVE_O1_ODDS_TANFUKUWAKU"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM ARCHIVE_O2_ODDS_UMAREN"
        ).fetchone() == (1,)


def test_archive_accumulates_rows_after_realtime_table_replacement(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _seed_realtime_tables(database)
    archive = OddsArchive(database)
    archive.archive()

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM RT_O1_ODDS_TANFUKUWAKU")
        connection.execute("DELETE FROM RT_O2_ODDS_UMAREN")
        connection.execute(
            "INSERT INTO RT_O1_ODDS_TANFUKUWAKU VALUES ('r1', '102000', '22')"
        )
        connection.execute(
            "INSERT INTO RT_O2_ODDS_UMAREN VALUES ('r1', '102000', '75')"
        )

    assert archive.archive() == 2
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT HappyoTime FROM ARCHIVE_O1_ODDS_TANFUKUWAKU ORDER BY HappyoTime"
        ).fetchall() == [("101000",), ("102000",)]
        assert connection.execute(
            "SELECT HappyoTime FROM ARCHIVE_O2_ODDS_UMAREN ORDER BY HappyoTime"
        ).fetchall() == [("101000",), ("102000",)]
