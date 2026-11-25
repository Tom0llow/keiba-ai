"""Storage contracts for race-day start-time changes (ADR-049)."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from data.preprocessor.sqlite_to_arrow import sqlite_arrow_schema, sqlite_rows_to_arrow
from domain.race_key import RaceKey
from jra_van_retriever.acquisition import odds_archive
from jra_van_retriever.acquisition.acquisition_lock import (
    AcquisitionBlocked,
    check_unresolved_capture,
)
from jra_van_retriever.acquisition.jvlink_runner import JVLinkExecutionResult
from jra_van_retriever.acquisition.odds_archive import OddsArchive

RACE = RaceKey(date(2026, 11, 15), "05", "05", "04", "11")
START = datetime(2026, 11, 15, 6, 0, tzinfo=UTC)
NEW_COLUMNS = odds_archive._CAPTURE_LOG_COLUMNS
OLD_COLUMNS = NEW_COLUMNS[:-1]


def _schema(database: Path, table: str) -> list[tuple[str, str]]:
    with sqlite3.connect(database) as connection:
        return [
            (str(row[1]), str(row[2]))
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        ]


def _old_log(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ARCHIVE_CAPTURE_LOG ("
            + ", ".join(f'"{column}" TEXT' for column in OLD_COLUMNS)
            + ")"
        )
        connection.execute(
            "INSERT INTO ARCHIVE_CAPTURE_LOG ("
            + ", ".join(f'"{column}"' for column in OLD_COLUMNS)
            + ") VALUES ("
            + ", ".join("?" for _ in OLD_COLUMNS)
            + ")",
            tuple("archived" if column == "status" else "x" for column in OLD_COLUMNS),
        )


def _begin(archive: OddsArchive, capture_id: str, effective: datetime | None = None) -> None:
    archive.begin_capture(
        capture_id,
        RACE,
        frozenset({"0B31"}),
        scheduled_start_at=START,
        offset_minutes=5,
        planned_at=START,
        effective_start_at=effective,
    )


def test_the_24_column_log_gains_effective_start_at_once_and_keeps_old_rows(
    tmp_path: Path,
) -> None:
    assert len(OLD_COLUMNS) == 24
    assert NEW_COLUMNS[-1] == "effective_start_at"
    database = tmp_path / "race.db"
    _old_log(database)
    archive = OddsArchive(database)

    _begin(archive, "a")
    _begin(archive, "b", START.replace(minute=5))

    assert _schema(database, "ARCHIVE_CAPTURE_LOG") == [(column, "TEXT") for column in NEW_COLUMNS]
    fresh = tmp_path / "fresh.db"
    _begin(OddsArchive(fresh), "c")
    assert _schema(fresh, "ARCHIVE_CAPTURE_LOG") == _schema(database, "ARCHIVE_CAPTURE_LOG")
    with sqlite3.connect(database) as connection:
        values = connection.execute(
            "SELECT capture_id, effective_start_at FROM ARCHIVE_CAPTURE_LOG ORDER BY rowid"
        ).fetchall()
    assert values == [("x", None), ("a", None), ("b", "2026-11-15T06:05:00+00:00")]


def test_rollback_drops_only_the_new_column_and_keeps_every_row(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _old_log(database)
    _begin(OddsArchive(database), "a")
    assert sqlite3.sqlite_version_info >= (3, 35, 0)

    with sqlite3.connect(database) as connection:
        connection.execute('ALTER TABLE "ARCHIVE_CAPTURE_LOG" DROP COLUMN "effective_start_at"')

    assert _schema(database, "ARCHIVE_CAPTURE_LOG") == [(column, "TEXT") for column in OLD_COLUMNS]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG").fetchone()[0] == 2


def test_new_tables_and_the_25_column_log_convert_and_the_lock_sees_running(
    tmp_path: Path,
) -> None:
    database = tmp_path / "race.db"
    archive = OddsArchive(database)
    _begin(archive, "a")
    with sqlite3.connect(database) as connection:
        connection.execute(
            'CREATE TABLE RT_TC_INFO ("idYear" TEXT, "idMonthDay" TEXT, "HappyoTime" TEXT)'
        )
        connection.execute("INSERT INTO RT_TC_INFO VALUES ('2026', '1115', '11150820')")
    assert archive.archive_tc_info() == 1
    # Archiving the same response again adds nothing (full-row deduplication).
    assert archive.archive_tc_info() == 0
    archive.record_tc_check(
        "c1",
        race_date=RACE.race_date,
        time_point_at=START,
        started_at=START,
        completed_at=START,
        result="ok",
        reason="tc_rows_archived",
        execution=JVLinkExecutionResult({"0B14": 0}, api_results={"0B14": ("JVRTOpen", 0)}),
        tc_rows=1,
        earlier_start_races=frozenset(),
        adopted_starts="{}",
    )
    archive.reset_tc_staging()

    with sqlite3.connect(database) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "RT_TC_INFO" not in tables
        for table in ("ARCHIVE_CAPTURE_LOG", "ARCHIVE_TC_INFO", "ARCHIVE_TC_CHECK_LOG"):
            schema = sqlite_arrow_schema(table, _schema(database, table))
            rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
            assert len(rows) >= 1
            assert sqlite_rows_to_arrow(table, schema, rows).num_rows == len(rows)

    with pytest.raises(AcquisitionBlocked):
        check_unresolved_capture(database)


def test_the_tc_archive_and_check_log_reject_unexpected_schemas(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE ARCHIVE_TC_CHECK_LOG ("check_id" TEXT)')
        connection.execute('CREATE TABLE RT_TC_INFO ("idYear" INTEGER)')
    archive = OddsArchive(database)

    with pytest.raises(sqlite3.IntegrityError):
        archive.archive_tc_info()
    with pytest.raises(sqlite3.IntegrityError):
        archive.record_tc_check(
            "c1",
            race_date=RACE.race_date,
            time_point_at=START,
            started_at=None,
            completed_at=None,
            result="skipped",
            reason="no_time_before_time_point",
            execution=None,
            tc_rows=0,
            earlier_start_races=frozenset(),
            adopted_starts="{}",
        )


def test_a_full_snapshot_rebuild_publishes_the_new_tables(tmp_path: Path) -> None:
    from configuration.data_paths import DataPaths
    from data.loader.processed_data_loader import DataLoader
    from data.storage.snapshot_builder import DataPreprocesser

    paths = DataPaths(
        raw_db=tmp_path / "raw" / "race.db",
        processed_dir=tmp_path / "processed",
        jvlink_runtime_dir=tmp_path / "runtime",
    )
    paths.raw_db.parent.mkdir(parents=True)
    archive = OddsArchive(paths.raw_db)
    _begin(archive, "a", START.replace(minute=5))
    archive.interrupt_running_captures(START, "interrupted_recovery")
    with sqlite3.connect(paths.raw_db) as connection:
        connection.execute(
            'CREATE TABLE RT_TC_INFO ("idYear" TEXT, "idMonthDay" TEXT, "HappyoTime" TEXT)'
        )
        connection.execute("INSERT INTO RT_TC_INFO VALUES ('2026', '1115', '11150820')")
    archive.archive_tc_info()
    archive.reset_tc_staging()
    archive.record_tc_check(
        "c1",
        race_date=RACE.race_date,
        time_point_at=START,
        started_at=None,
        completed_at=None,
        result="skipped",
        reason="no_time_before_time_point",
        execution=None,
        tc_rows=0,
        earlier_start_races=frozenset(),
        adopted_starts="{}",
    )

    counts = DataPreprocesser(paths).rebuild()

    assert counts["ARCHIVE_TC_INFO"] == 1
    assert counts["ARCHIVE_TC_CHECK_LOG"] == 1
    assert counts["ARCHIVE_CAPTURE_LOG"] == 1
    log = DataLoader(paths).read_table("ARCHIVE_CAPTURE_LOG")
    assert log.column_names[-1] == "effective_start_at"
