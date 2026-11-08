"""Tests for race-day capture archives and the capture log on real SQLite files."""

import sqlite3
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from configuration.data_paths import DataPaths
from data.storage.snapshot_builder import SnapshotBuilder
from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import JVLinkExecutionResult
from jra_van_retriever.acquisition.odds_archive import CaptureResult, OddsArchive
from jra_van_retriever.workflows.race_day_odds_plan import classify_capture

KEY = RaceKey(date(2026, 11, 15), "05", "05", "04", "11")
OTHER = RaceKey(date(2026, 11, 15), "05", "05", "04", "12")
SPECS = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"})
KEYS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
PARENTS = {
    "0B31": "RT_O1_ODDS_TANFUKUWAKU",
    "0B32": "RT_O2_ODDS_UMAREN",
    "0B33": "RT_O3_ODDS_WIDE",
    "0B34": "RT_O4_ODDS_UMATAN",
    "0B35": "RT_O5_ODDS_SANREN",
    "0B36": "RT_O6_ODDS_SANRENTAN",
}
CHILDREN = {
    "0B35": ("RT_O5_OddsSanrenInfo", "OddsSanrenInfo"),
    "0B36": ("RT_O6_OddsSanrentanInfo", "OddsSanrentanInfo"),
}
ARCHIVES = {
    "0B31": "ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU",
    "0B32": "ARCHIVE_CAPTURE_O2_ODDS_UMAREN",
    "0B33": "ARCHIVE_CAPTURE_O3_ODDS_WIDE",
    "0B34": "ARCHIVE_CAPTURE_O4_ODDS_UMATAN",
    "0B35": "ARCHIVE_CAPTURE_O5_ODDS_SANREN",
    "0B36": "ARCHIVE_CAPTURE_O6_ODDS_SANRENTAN",
}
CHILD_ARCHIVES = {
    "0B35": "ARCHIVE_CAPTURE_O5_OddsSanrenInfo",
    "0B36": "ARCHIVE_CAPTURE_O6_OddsSanrentanInfo",
}
JST = timezone(timedelta(hours=9))
SCHEDULED = datetime(2026, 11, 15, 15, 40, tzinfo=JST)
PLANNED = SCHEDULED - timedelta(minutes=5)
COMPLETED = datetime(2026, 11, 15, 6, 35, 3, tzinfo=UTC)


def _values(key: RaceKey) -> tuple[str, ...]:
    return (
        f"{key.race_date:%Y}",
        f"{key.race_date:%m%d}",
        key.jyo_code,
        key.kaiji,
        key.nichiji,
        key.race_number,
    )


def _create_staging(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        parent_columns = ", ".join(
            f'"{name}" TEXT'
            for name in ("headRecordSpec", "headDataKubun", "headMakeDate", *KEYS, "HappyoTime")
        )
        for table in PARENTS.values():
            connection.execute(f'CREATE TABLE "{table}" ({parent_columns}, "Odds" TEXT)')
        for table, prefix in CHILDREN.values():
            child_columns = ", ".join(
                f'"{name}" TEXT'
                for name in (*KEYS, f"{prefix}Idx", f"{prefix}Kumi", f"{prefix}Odds")
            )
            connection.execute(f'CREATE TABLE "{table}" ({child_columns})')


def _stage(
    database: Path,
    *,
    happyo: str = "11151535",
    kubun: str = "1",
    odds: str = "0123",
    key: RaceKey = KEY,
    child_key: RaceKey | None = None,
    specs: frozenset[str] = SPECS,
    parent_rows: int = 1,
    child_odds: str | None = None,
    child_rows: tuple[str, ...] = ("010203", "010204"),
) -> None:
    with sqlite3.connect(database) as connection:
        for spec in sorted(specs):
            table = PARENTS[spec]
            connection.execute(f'DELETE FROM "{table}"')
            for index in range(parent_rows):
                connection.execute(
                    f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    ("O", kubun, "20261115", *_values(key), happyo, f"{odds}{index}"),
                )
            if spec in CHILDREN:
                child, _ = CHILDREN[spec]
                connection.execute(f'DELETE FROM "{child}"')
                for index, kumi in enumerate(child_rows):
                    connection.execute(
                        f'INSERT INTO "{child}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (
                            *_values(child_key or key),
                            f"{index:03d}",
                            kumi,
                            f"{child_odds or odds}{index}",
                        ),
                    )


def _begin(archive: OddsArchive, capture_id: str, specs: frozenset[str] = SPECS) -> None:
    archive.begin_capture(
        capture_id,
        KEY,
        specs,
        scheduled_start_at=SCHEDULED,
        offset_minutes=5,
        planned_at=PLANNED,
    )


def _finish(
    archive: OddsArchive,
    capture_id: str,
    tmp_path: Path,
    execution: JVLinkExecutionResult | None,
    specs: frozenset[str] = SPECS,
) -> dict[str, CaptureResult]:
    return archive.finish_capture(
        capture_id,
        KEY,
        specs,
        execution,
        completed_at=COMPLETED,
        quarantine_directory=tmp_path / "quarantine",
        quarantine_label=capture_id,
        classifier=classify_capture,
    )


def _ok(
    no_data: frozenset[str] = frozenset(), fatal: frozenset[str] = frozenset()
) -> JVLinkExecutionResult:
    return JVLinkExecutionResult(
        {},
        no_data_specs=no_data,
        fatal_specs=fatal,
        api_results={spec: ("JVRTOpen", 0) for spec in SPECS},
        process_returncode=0,
    )


def _count(database: Path, table: str) -> int:
    with sqlite3.connect(database) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists is None:
            return 0
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _log(database: Path, capture_id: str) -> dict[str, dict[str, str | None]]:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            'SELECT * FROM "ARCHIVE_CAPTURE_LOG" WHERE capture_id = ?', (capture_id,)
        ).fetchall()
    return {str(row["data_spec"]): dict(row) for row in rows}


def _schema(database: Path, table: str) -> list[tuple[str, str]]:
    with sqlite3.connect(database) as connection:
        return [
            (str(row[1]), str(row[2]))
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        ]


def test_capture_archives_every_spec_into_separate_tables_and_logs(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    _stage(database)
    archive = OddsArchive(database)

    _begin(archive, "c1")
    assert {row["status"] for row in _log(database, "c1").values()} == {"running"}
    results = _finish(archive, "c1", tmp_path, _ok())

    assert {spec: result.status for spec, result in results.items()} == dict.fromkeys(
        sorted(SPECS), "archived"
    )
    for spec, table in ARCHIVES.items():
        assert _count(database, table) == 1
        assert _schema(database, table) == _schema(database, PARENTS[spec])
    for spec, table in CHILD_ARCHIVES.items():
        child, _ = CHILDREN[spec]
        assert _count(database, table) == 2
        assert _schema(database, table) == [
            (name, "TEXT") for name, _ in _schema(database, child)
        ] + [("headDataKubun", "TEXT"), ("HappyoTime", "TEXT")]
        assert results[spec].child_observed_rows == 2
        assert results[spec].child_inserted_rows == 2
    assert _count(database, "ARCHIVE_O1_ODDS_TANFUKUWAKU") == 0
    assert _count(database, "ARCHIVE_O2_ODDS_UMAREN") == 0
    for table in (*PARENTS.values(), *(child for child, _ in CHILDREN.values())):
        assert _count(database, table) == 0

    log = _log(database, "c1")
    assert set(log) == SPECS
    assert set(_schema(database, "ARCHIVE_CAPTURE_LOG")) == {
        (name, "TEXT") for name, _ in _schema(database, "ARCHIVE_CAPTURE_LOG")
    }
    row = log["0B36"]
    assert row["status"] == "archived"
    assert row["scheduled_start_at"] == SCHEDULED.isoformat()
    assert row["offset_minutes"] == "5"
    assert row["planned_at"] == PLANNED.astimezone(UTC).isoformat()
    assert row["completed_at"] == COMPLETED.isoformat()
    assert row["api_name"] == "JVRTOpen"
    assert row["api_returncode"] == "0"
    assert row["process_returncode"] == "0"
    assert (row["headDataKubun"], row["HappyoTime"]) == ("1", "11151535")
    assert (row["observed_rows"], row["inserted_rows"]) == ("1", "1")
    assert (row["child_observed_rows"], row["child_inserted_rows"]) == ("2", "2")


def test_repeated_capture_is_idempotent_and_new_happyo_rows_are_kept(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    for capture_id in ("c1", "c2"):
        _stage(database)
        _begin(archive, capture_id)
        _finish(archive, capture_id, tmp_path, _ok())

    second = _log(database, "c2")["0B36"]
    assert (second["observed_rows"], second["inserted_rows"]) == ("1", "0")
    assert (second["child_observed_rows"], second["child_inserted_rows"]) == ("2", "0")
    assert _count(database, "ARCHIVE_CAPTURE_O3_ODDS_WIDE") == 1

    _stage(database, happyo="11151538", odds="0150")
    _begin(archive, "c3")
    results = _finish(archive, "c3", tmp_path, _ok())

    assert results["0B36"].status == "archived"
    assert _count(database, "ARCHIVE_CAPTURE_O3_ODDS_WIDE") == 2
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            'SELECT "OddsSanrentanInfoKumi", "HappyoTime" '
            'FROM "ARCHIVE_CAPTURE_O6_OddsSanrentanInfo" ORDER BY 2, 1'
        ).fetchall()
    assert rows == [
        ("010203", "11151535"),
        ("010204", "11151535"),
        ("010203", "11151538"),
        ("010204", "11151538"),
    ]


@pytest.mark.parametrize("spec", ["0B33", "0B34", "0B35", "0B36"])
def test_same_happyo_with_different_rows_is_rejected_and_quarantined(
    tmp_path: Path, spec: str
) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database)
    _begin(archive, "c1")
    _finish(archive, "c1", tmp_path, _ok())
    before = {
        table: _count(database, table)
        for table in (ARCHIVES[spec], CHILD_ARCHIVES.get(spec, ARCHIVES[spec]))
    }

    _stage(database, odds="0999", specs=frozenset({spec}))
    _begin(archive, "c2", frozenset({spec}))
    results = _finish(archive, "c2", tmp_path, _ok(), frozenset({spec}))

    assert (results[spec].status, results[spec].reason) == ("failed", "happyo_conflict")
    assert {table: _count(database, table) for table in before} == before
    row = _log(database, "c2")[spec]
    assert row["status"] == "failed"
    assert row["reason"] is not None
    assert row["reason"].startswith("happyo_conflict: quarantined")
    assert list((tmp_path / "quarantine").glob("c2-*.db"))
    assert _count(database, PARENTS[spec]) == 0


def test_invalid_or_empty_staging_fails_only_the_affected_spec(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database, specs=frozenset({"0B31"}))
    _stage(database, specs=frozenset({"0B32"}), key=OTHER)
    _stage(database, specs=frozenset({"0B34"}), parent_rows=2)
    _stage(database, specs=frozenset({"0B35"}), child_key=OTHER)
    _stage(database, specs=frozenset({"0B36"}))
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE "ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU" ("unexpected" TEXT)')

    _begin(archive, "c1")
    results = _finish(archive, "c1", tmp_path, _ok(fatal=frozenset({"0B36"})))

    assert {spec: (result.status, result.reason) for spec, result in results.items()} == {
        "0B31": ("failed", "archive_schema_mismatch"),
        "0B32": ("failed", "staging_race_mismatch"),
        "0B33": ("failed", "empty_response_unverified"),
        "0B34": ("failed", "staging_multiple_rows"),
        "0B35": ("failed", "child_race_mismatch"),
        "0B36": ("failed", "jvlink_error"),
    }
    for spec in ("0B32", "0B34", "0B35", "0B36"):
        assert _count(database, ARCHIVES[spec]) == 0
    assert _count(database, ARCHIVES["0B31"]) == 0
    assert _schema(database, ARCHIVES["0B31"]) == [("unexpected", "TEXT")]
    assert _log(database, "c1")["0B32"]["observed_rows"] == "0"
    assert _log(database, "c1")["0B34"]["observed_rows"] == "2"
    for spec in ("0B31", "0B32", "0B34", "0B35", "0B36"):
        assert _log(database, "c1")[spec]["reason"] is not None
        assert str(_log(database, "c1")[spec]["reason"]).count("quarantined") == 1
    assert _log(database, "c1")["0B33"]["reason"] == "empty_response_unverified"


def test_empty_staging_with_provider_evidence_is_no_data(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database, specs=SPECS - {"0B33"})

    _begin(archive, "c1")
    results = _finish(archive, "c1", tmp_path, _ok(no_data=frozenset({"0B33"})))

    assert (results["0B33"].status, results["0B33"].reason) == ("no_data", "jvopen_no_data")
    assert results["0B31"].status == "archived"
    assert _log(database, "c1")["0B33"]["observed_rows"] == "0"


def test_capture_log_and_archives_are_readable_by_complete_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "raw" / "race.db"
    database.parent.mkdir()
    _create_staging(database)
    _stage(database)
    archive = OddsArchive(database)
    _begin(archive, "c1")
    _finish(archive, "c1", tmp_path, _ok())
    archive.record_skipped_capture(
        "c2",
        KEY,
        SPECS,
        scheduled_start_at=SCHEDULED,
        offset_minutes=2,
        planned_at=PLANNED,
    )

    tables = SnapshotBuilder(
        DataPaths(database, tmp_path / "processed", tmp_path / "runtime")
    ).rebuild()

    assert tables["ARCHIVE_CAPTURE_LOG"] == 12
    assert tables["ARCHIVE_CAPTURE_O6_OddsSanrentanInfo"] == 2
    assert tables["ARCHIVE_CAPTURE_O3_ODDS_WIDE"] == 1


@pytest.mark.parametrize("spec", ["0B35", "0B36"])
def test_child_only_difference_under_the_same_happyo_is_a_conflict(
    tmp_path: Path, spec: str
) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database)
    _begin(archive, "c1")
    _finish(archive, "c1", tmp_path, _ok())

    _stage(database, child_odds="0777", specs=frozenset({spec}))
    _begin(archive, "c2", frozenset({spec}))
    results = _finish(archive, "c2", tmp_path, _ok(), frozenset({spec}))

    assert (results[spec].status, results[spec].reason) == ("failed", "happyo_conflict")
    assert _count(database, CHILD_ARCHIVES[spec]) == 2
    assert _count(database, ARCHIVES[spec]) == 1


def test_children_added_to_an_archived_parent_version_are_a_conflict(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    spec = frozenset({"0B36"})
    _stage(database, specs=spec, child_rows=())
    _begin(archive, "c1", spec)
    first = _finish(archive, "c1", tmp_path, _ok(), spec)
    assert (first["0B36"].status, first["0B36"].child_observed_rows) == ("archived", 0)

    _stage(database, specs=spec)
    _begin(archive, "c2", spec)
    second = _finish(archive, "c2", tmp_path, _ok(), spec)

    assert (second["0B36"].status, second["0B36"].reason) == ("failed", "happyo_conflict")
    assert _count(database, CHILD_ARCHIVES["0B36"]) == 0


def test_orphan_child_rows_are_quarantined_even_with_no_data_evidence(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database, specs=frozenset({"0B35"}))
    with sqlite3.connect(database) as connection:
        connection.execute('DELETE FROM "RT_O5_ODDS_SANREN"')

    spec = frozenset({"0B35"})
    _begin(archive, "c1", spec)
    results = _finish(archive, "c1", tmp_path, _ok(no_data=spec), spec)

    assert (results["0B35"].status, results["0B35"].reason) == ("failed", "orphan_child_rows")
    assert results["0B35"].child_observed_rows == 2
    assert str(_log(database, "c1")["0B35"]["reason"]).startswith("orphan_child_rows: quarantined")
    assert _count(database, "RT_O5_OddsSanrenInfo") == 0
    assert list((tmp_path / "quarantine").glob("c1-0B35-*.db"))


def test_one_failed_spec_does_not_block_the_others_in_the_same_capture(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database, specs=SPECS - {"0B32"})
    _stage(database, specs=frozenset({"0B32"}), key=OTHER)

    _begin(archive, "c1")
    results = _finish(archive, "c1", tmp_path, _ok())

    assert (results["0B32"].status, results["0B32"].reason) == ("failed", "staging_race_mismatch")
    assert _count(database, ARCHIVES["0B32"]) == 0
    for spec in SPECS - {"0B32"}:
        assert results[spec].status == "archived"
        assert _count(database, ARCHIVES[spec]) == 1
    assert _count(database, CHILD_ARCHIVES["0B36"]) == 2


def test_deduplication_ignores_archived_rows_of_other_races(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    spec = frozenset({"0B33"})
    _stage(database, specs=spec, key=OTHER)
    archive.begin_capture(
        "c0", OTHER, spec, scheduled_start_at=SCHEDULED, offset_minutes=5, planned_at=PLANNED
    )
    archive.finish_capture(
        "c0",
        OTHER,
        spec,
        _ok(),
        completed_at=COMPLETED,
        quarantine_directory=tmp_path / "quarantine",
        quarantine_label="c0",
        classifier=classify_capture,
    )
    for capture_id in ("c1", "c2"):
        _stage(database, specs=spec)
        _begin(archive, capture_id, spec)
        _finish(archive, capture_id, tmp_path, _ok(), spec)

    assert _count(database, ARCHIVES["0B33"]) == 2
    assert _log(database, "c1")["0B33"]["inserted_rows"] == "1"
    assert _log(database, "c2")["0B33"]["inserted_rows"] == "0"


def test_child_rows_are_quarantined_when_the_parent_staging_table_is_missing(
    tmp_path: Path,
) -> None:
    database = tmp_path / "race.db"
    _create_staging(database)
    archive = OddsArchive(database)
    _stage(database, specs=frozenset({"0B35"}))
    with sqlite3.connect(database) as connection:
        connection.execute('DROP TABLE "RT_O5_ODDS_SANREN"')

    spec = frozenset({"0B35"})
    _begin(archive, "c1", spec)
    results = _finish(archive, "c1", tmp_path, _ok(), spec)

    assert (results["0B35"].status, results["0B35"].reason) == (
        "failed",
        "staging_table_missing",
    )
    assert str(_log(database, "c1")["0B35"]["reason"]).startswith(
        "staging_table_missing: quarantined"
    )
    assert _count(database, "RT_O5_OddsSanrenInfo") == 0
    quarantined = list((tmp_path / "quarantine").glob("c1-0B35-*.db"))
    assert len(quarantined) == 1
    with sqlite3.connect(quarantined[0]) as connection:
        assert connection.execute('SELECT COUNT(*) FROM "RT_O5_OddsSanrenInfo"').fetchone()[0] == 2
