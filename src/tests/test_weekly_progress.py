"""Tests for isolated weekly progress bootstrap and reconciliation."""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from data.race_key import RaceKey
from data.retriever.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from data.retriever.jvlinktosqlite import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
    JVLinkToSQLiteRunner,
)
from data.retriever.odds_archive import OddsArchive
from data.retriever.progress import ProgressLedger, RawSnapshot, read_raw_snapshot
from data.retriever.setting import HistoricalOddsBatch, JVLinkProfile
from data.retriever.weekly import WeeklyBatchResult, WeeklyHistoricalOddsRetriever

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
FRONTIER = RaceKey(date(2008, 1, 26), "06", "01", "07", "06")
PROFILE = JVLinkProfile(
    False,
    False,
    True,
    frozenset(),
    frozenset(),
    frozenset({"0B41", "0B42"}),
    race_start_date=date(2003, 10, 4),
)
BATCH = HistoricalOddsBatch(2003, 2026, 1, FRONTIER)


def test_bootstrap_accepts_initial_gaps_only_through_complete_frontier(tmp_path: Path) -> None:
    earlier = RaceKey(date(2003, 10, 4), "05", "04", "01", "01")
    later = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    snapshot = RawSnapshot((earlier, FRONTIER, later), {(FRONTIER.race_id, "0B41"): 2}, {})

    ledger.bootstrap(snapshot, NOW)
    states, _, _ = ledger.read()

    assert states[(earlier.race_id, "0B41")].state == "provider_missing"
    assert states[(earlier.race_id, "0B42")].reason == "user_accepted_existing_gaps"
    assert states[(FRONTIER.race_id, "0B41")].state == "acquired"
    assert states[(FRONTIER.race_id, "0B42")].state == "provider_missing"
    assert states[(later.race_id, "0B41")].state == "pending"
    assert not (tmp_path / "raw.db").exists()


def test_bootstrap_adopts_existing_archive_after_frontier(tmp_path: Path) -> None:
    later = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(
        RawSnapshot((later,), {(later.race_id, "0B41"): 3}, {"0B41": "schema"}),
        NOW,
    )

    states, _, _ = ledger.read()
    assert states[(later.race_id, "0B41")].state == "acquired"
    assert states[(later.race_id, "0B41")].reason == "initial_archive_observed"
    assert states[(later.race_id, "0B42")].state == "pending"


def test_external_archive_is_adopted_and_missing_state_recovers(tmp_path: Path) -> None:
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)

    adopted = ledger.reconcile(RawSnapshot((FRONTIER,), {(FRONTIER.race_id, "0B41"): 3}, {}), NOW)
    states, years, _ = ledger.read()

    assert adopted == {"0B41": 1, "0B42": 0}
    assert states[(FRONTIER.race_id, "0B41")].reason == "external_archive_observed"
    assert states[(FRONTIER.race_id, "0B41")].state == "acquired"
    assert years[2008] == "pending"
    assert ledger.reconcile(RawSnapshot((FRONTIER,), {(FRONTIER.race_id, "0B41"): 3}, {}), NOW) == {
        "0B41": 0,
        "0B42": 0,
    }
    with pytest.raises(AcquisitionBlocked, match="disappeared"):
        ledger.reconcile(RawSnapshot((FRONTIER,), {}, {}), NOW)


def test_prepare_publication_reconciles_external_archive_after_published_year(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0126','06','01','07','06')")
        columns = (
            "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT"
        )
        for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns})")

    snapshot = read_raw_snapshot(raw, PROFILE, BATCH, date(2026, 10, 5))
    ledger = ProgressLedger(
        tmp_path / "runtime" / "historical-odds-progress.db", raw, PROFILE, BATCH
    )
    ledger.bootstrap(snapshot, NOW)
    ledger.publication(2008, "published")
    with sqlite3.connect(raw) as database:
        for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
            database.execute(f"INSERT INTO {table} VALUES ('2008','0126','06','01','07','06')")

    builder = Mock()
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, Mock()),
        raw,
        builder,
        OddsArchive(raw),
        PROFILE,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    plan = retriever.prepare_publication(cutoff=date(2026, 10, 5))

    assert plan.year == 2008
    assert plan.requested_specs == 0
    _, publications, _ = retriever.ledger.read()
    assert publications[2008] == "pending"

    with sqlite3.connect(raw) as database:
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0126','06','01','07','07')")
    with AcquisitionLock(raw, retriever.ledger_path) as lock:
        lock.bind()
        with pytest.raises(AcquisitionBlocked, match="incomplete"):
            retriever.verify_publication_locked(retriever.ledger, 2008)


def test_prepare_publication_requires_existing_progress_ledger(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, Mock()),
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    with pytest.raises(AcquisitionBlocked, match="existing progress ledger"):
        retriever.prepare_publication(cutoff=date(2026, 10, 5))


def test_publication_summary_preserves_retrieval_metrics(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0126','06','01','07','06')")
        columns = (
            "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT"
        )
        for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns})")
    snapshot = read_raw_snapshot(raw, PROFILE, BATCH, date(2026, 10, 5))
    runtime = tmp_path / "runtime"
    ledger = ProgressLedger(runtime / "historical-odds-progress.db", raw, PROFILE, BATCH)
    ledger.bootstrap(snapshot, NOW)
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, Mock()),
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        BATCH,
        runtime,
        clock=lambda: NOW,
    )
    runtime.mkdir(exist_ok=True)
    (runtime / "historical-odds-progress.json").write_text(
        '{"year": 2008, "run_id": "run", "requested_specs": 4, "new_rows": {"0B41": 2}}\n',
        encoding="utf-8",
    )

    retriever._write_summary(
        WeeklyBatchResult("completed", 2008, None, 0, 0, 0, 0, {}, False, {}),
        ledger,
        publication_state="published",
    )

    payload = json.loads((runtime / "historical-odds-progress.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "run"
    assert payload["requested_specs"] == 4
    assert payload["new_rows"] == {"0B41": 2}
    assert payload["publication"] == "published"


def test_new_past_candidate_is_pending_instead_of_provider_missing(tmp_path: Path) -> None:
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    new = RaceKey(date(2003, 10, 4), "01", "01", "01", "01")

    ledger.reconcile(RawSnapshot((new, FRONTIER), {}, {}), NOW)

    states, years, _ = ledger.read()
    assert states[(new.race_id, "0B42")].state == "pending"
    assert years[2003] == "pending"


def test_lock_rejects_running_and_conflicting_runtime_and_releases_os_lock(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    path = tmp_path / "progress.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    key = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    with AcquisitionLock(raw, path) as lock:
        lock.bind()
        with pytest.raises(AcquisitionBlocked, match="holds"), AcquisitionLock(raw, path):
            pytest.fail("second lock acquired")
    with AcquisitionLock(raw, path):
        pass
    with (
        pytest.raises(AcquisitionBlocked, match="another ledger"),
        AcquisitionLock(raw, tmp_path / "different.db"),
    ):
        pytest.fail("conflicting ledger acquired")
    ledger.start_run("test", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("test", key, frozenset({"0B41"}), {"0B41": 0}, NOW)
    with pytest.raises(AcquisitionBlocked, match="running"), AcquisitionLock(raw, path):
        pytest.fail("unresolved request accepted")


def test_explicit_recovery_releases_unresolved_request(tmp_path: Path) -> None:
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    key = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    ledger.start_run("run", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("run", key, frozenset({"0B41"}), {"0B41": 0}, NOW)

    assert ledger.running_requests() == (("run", key, frozenset({"0B41"})),)
    ledger.recover_running(key, frozenset({"0B41"}), NOW)

    states, _, _ = ledger.read()
    assert states[(key.race_id, "0B41")].state == "failed"
    assert states[(key.race_id, "0B41")].reason == "recovered_unconfirmed"


def test_recovery_recognizes_archive_committed_before_ledger_update(tmp_path: Path) -> None:
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    key = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    ledger.start_run("run", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("run", key, frozenset({"0B41"}), {"0B41": 0}, NOW)

    ledger.recover_running(key, frozenset({"0B41"}), NOW, {"0B41": 2})

    states, years, _ = ledger.read()
    assert states[(key.race_id, "0B41")].state == "acquired"
    assert states[(key.race_id, "0B41")].reason == "recovered_archive_commit"
    assert states[(key.race_id, "0B41")].after_rows == 2
    assert years[2008] == "pending"


def test_confirm_provider_missing_promotes_only_empty_response_failures(
    tmp_path: Path,
) -> None:
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    key = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    ledger.start_run("run", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("run", key, frozenset({"0B41"}), {"0B41": 0}, NOW)
    ledger.finish_request(
        key,
        {"0B41": ("failed", "empty_response_unverified", 0)},
        NOW,
        recovered=True,
    )

    ledger.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 0})

    states, years, _ = ledger.read()
    assert states[(key.race_id, "0B41")].state == "provider_missing"
    assert states[(key.race_id, "0B41")].reason == "provider_confirmed_missing"
    assert years[2008] == "pending"


def test_confirm_provider_missing_requires_owned_initialized_ledger(tmp_path: Path) -> None:
    key = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    ledger.start_run("run", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("run", key, frozenset({"0B41"}), {"0B41": 0}, NOW)
    ledger.finish_request(
        key,
        {"0B41": ("failed", "empty_response_unverified", 0)},
        NOW,
        recovered=True,
    )

    mismatched = ProgressLedger(
        path,
        raw,
        PROFILE,
        HistoricalOddsBatch(2003, 2025, 1, FRONTIER),
    )
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        mismatched.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 0})

    missing = ProgressLedger(tmp_path / "missing.db", raw, PROFILE, BATCH)
    with pytest.raises(AcquisitionBlocked, match="existing ledger"):
        missing.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 0})
    assert not (tmp_path / "missing.db").exists()


def test_ledger_refuses_unsupported_schema_and_wrong_database(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    key = RaceKey(date(2008, 1, 27), "01", "01", "08", "01")
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        ProgressLedger(path, tmp_path / "other.db", PROFILE, BATCH).read()
    with sqlite3.connect(path) as database:
        database.execute("PRAGMA user_version=2")
    with pytest.raises(AcquisitionBlocked, match="schema version"):
        ledger.read()
    with pytest.raises(AcquisitionBlocked, match="schema version"):
        ledger.running_requests()


def test_ledger_rejects_unknown_state_reason_pairs(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    with sqlite3.connect(path) as database:
        database.execute("UPDATE race_specs SET state='provider_missing',reason='jvlink_error'")

    with pytest.raises(AcquisitionBlocked, match="unsupported or unresolved"):
        ledger.read()


def test_ledger_rejects_provider_missing_without_jvopen_no_data_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE race_specs SET state='provider_missing',reason='jvopen_no_data',"
            "api_name='JVOpen',api_returncode=0"
        )

    with pytest.raises(AcquisitionBlocked, match="lacks JVOpen"):
        ledger.read()


def test_ledger_rejects_non_integer_api_return_code(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    with sqlite3.connect(path) as database:
        database.execute("UPDATE race_specs SET api_name='JVOpen',api_returncode='bad'")

    with pytest.raises(AcquisitionBlocked, match="invalid API return code"):
        ledger.read()


def test_request_clears_previous_api_observation(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    key = RaceKey(date(2008, 1, 27), "06", "01", "07", "06")
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    ledger.start_run("first", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("first", key, frozenset({"0B41"}), {"0B41": 0}, NOW)
    ledger.finish_request(
        key,
        {"0B41": ("failed", "jvlink_error", 0)},
        NOW,
        recovered=True,
        api_results={"0B41": ("JVOpen", -504)},
    )

    ledger.start_run("second", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("second", key, frozenset({"0B41"}), {"0B41": 0}, NOW)

    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT api_name,api_returncode FROM race_specs WHERE race_id=? AND data_spec='0B41'",
            (key.race_id,),
        ).fetchone() == (None, None)


def test_legacy_v1_ledger_adds_api_columns_without_changing_process_code(
    tmp_path: Path,
) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    key = RaceKey(date(2008, 1, 27), "01", "01", "08", "01")
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    with sqlite3.connect(path) as database:
        database.execute("ALTER TABLE race_specs DROP COLUMN api_name")
        database.execute("ALTER TABLE race_specs DROP COLUMN api_returncode")
        database.execute("UPDATE race_specs SET returncode=7")

    ledger.start_run("run", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("run", key, frozenset({"0B41"}), {"0B41": 0}, NOW)

    with sqlite3.connect(path) as database:
        columns = {row[1] for row in database.execute("PRAGMA table_info(race_specs)")}
        assert {"api_name", "api_returncode"} <= columns
        assert (
            database.execute(
                "SELECT returncode FROM race_specs WHERE race_id=? AND data_spec='0B42'",
                (key.race_id,),
            ).fetchone()[0]
            == 7
        )


def test_legacy_provider_missing_reason_is_migrated_without_api_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE race_specs SET reason='jvopen_no_data' WHERE state='provider_missing'"
        )
        database.execute("ALTER TABLE race_specs DROP COLUMN api_name")
        database.execute("ALTER TABLE race_specs DROP COLUMN api_returncode")

    ledger.read()
    ledger.publication(2008, "failed")

    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT state,reason,api_name,api_returncode FROM race_specs "
            "WHERE state='provider_missing'"
        ).fetchone() == ("provider_missing", "legacy_provider_missing", None, None)


def test_snapshot_includes_all_ten_venues_and_closes_reader(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.executemany(
            "INSERT INTO NL_RA_RACE VALUES ('2008','0127',?,'01','08','01')",
            [(f"{venue:02d}",) for venue in range(1, 11)],
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0127','A4','01','08','01')")

    snapshot = read_raw_snapshot(raw, PROFILE, BATCH, date(2026, 10, 5))

    assert {key.jyo_code for key in snapshot.races} == {f"{venue:02d}" for venue in range(1, 11)}
    with sqlite3.connect(raw, timeout=0) as database:
        database.execute("BEGIN EXCLUSIVE")
        database.rollback()


def test_weekly_run_retrieves_one_year_and_resumes_without_repeating(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08','01')")
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT"
        database.execute(f"CREATE TABLE RT_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE RT_O2_ODDS_UMAREN ({columns})")
        database.execute(
            "INSERT INTO RT_O1_ODDS_TANFUKUWAKU VALUES ('2008','0127','01','01','08','01','110000')"
        )

    class Runner:
        def execute(self, setting: Path, *, skip_last_modified_update: bool) -> None:
            with sqlite3.connect(raw) as database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(
                        f"INSERT INTO {table} VALUES ('2008','0127','01','01','08','01','120000')"
                    )

    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    profile = JVLinkProfile(
        False,
        False,
        True,
        frozenset(),
        frozenset(),
        frozenset({"0B41", "0B42"}),
        race_start_date=date(2003, 10, 4),
    )
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, Runner()),
        raw,
        builder,
        OddsArchive(raw),
        profile,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    plan = retriever.run(plan_only=True, cutoff=date(2026, 10, 5))
    assert plan.year == 2008
    assert plan.requested_races == 1
    assert plan.requested_specs == 2
    assert not (tmp_path / "runtime").exists()

    first = retriever.run(cutoff=date(2026, 10, 5))
    assert first.status == "completed"
    assert first.year == 2008
    assert first.requested_races == 1
    assert first.requested_specs == 2
    assert first.new_rows == {"0B41": 1, "0B42": 1}
    quarantine = next((tmp_path / "runtime" / "historical-odds-recovery").glob("*.db"))
    with sqlite3.connect(quarantine) as database:
        assert (
            database.execute("SELECT HappyoTime FROM RT_O1_ODDS_TANFUKUWAKU").fetchone()[0]
            == "110000"
        )

    retriever.mark_published(2008)
    second = retriever.run(cutoff=date(2026, 10, 5))
    assert second.status == "up_to_date"
    assert second.requested_races == 0
    with sqlite3.connect(raw) as database:
        assert (
            database.execute("SELECT COUNT(*) FROM ARCHIVE_O1_ODDS_TANFUKUWAKU").fetchone()[0] == 1
        )
        assert database.execute("SELECT COUNT(*) FROM ARCHIVE_O2_ODDS_UMAREN").fetchone()[0] == 1


def test_weekly_run_continues_after_no_data_response_and_marks_provider_missing(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.executemany(
            "INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08',?)",
            [("01",), ("02",)],
        )
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT"
        database.execute(f"CREATE TABLE RT_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE RT_O2_ODDS_UMAREN ({columns})")

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def execute(
            self, setting: Path, *, skip_last_modified_update: bool
        ) -> JVLinkExecutionResult:
            self.calls += 1
            if self.calls == 1:
                return JVLinkExecutionResult(
                    {"0B41": -1, "0B42": -1},
                    frozenset({"0B41", "0B42"}),
                    api_results={
                        "0B41": ("JVOpen", -1),
                        "0B42": ("JVOpen", -1),
                    },
                    open_returncodes={"0B41": -1, "0B42": -1},
                )
            with sqlite3.connect(raw) as database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(
                        f"INSERT INTO {table} VALUES ('2008','0127','01','01','08','02','120000')"
                    )
            return JVLinkExecutionResult(
                {"0B41": 0, "0B42": 0},
                api_results={"0B41": ("JVOpen", 0), "0B42": ("JVOpen", 0)},
                open_returncodes={"0B41": 0, "0B42": 0},
            )

    runner = Runner()
    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, runner),
        raw,
        builder,
        OddsArchive(raw),
        PROFILE,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    result = retriever.run(cutoff=date(2026, 10, 5))

    assert runner.calls == 2
    assert result.status == "completed"
    assert result.requested_races == 2
    assert result.requested_specs == 4
    assert result.failed_specs == 0
    assert result.pending_after == 0
    with sqlite3.connect(tmp_path / "runtime" / "historical-odds-progress.db") as database:
        rows = database.execute(
            "SELECT race_id,state,reason,returncode,api_name,api_returncode "
            "FROM race_specs ORDER BY race_id,data_spec"
        ).fetchall()
    assert set(rows) == {
        ("2008012701010801", "provider_missing", "jvopen_no_data", None, "JVOpen", -1),
        ("2008012701010802", "acquired", "requested_archive_committed", None, "JVOpen", 0),
    }


@pytest.mark.parametrize(
    ("execution", "expected_reason"),
    [
        (
            JVLinkExecutionResult(
                {"0B41": -504, "0B42": -504},
                fatal_specs=frozenset({"0B41", "0B42"}),
                fatal_returncodes={"0B41": -504, "0B42": -504},
                api_results={"0B41": ("JVOpen", -504), "0B42": ("JVOpen", -504)},
            ),
            "jvlink_error",
        ),
        (
            JVLinkExecutionResult({"0B41": -504, "0B42": -504}),
            "empty_response_unverified",
        ),
    ],
)
def test_weekly_run_does_not_promote_empty_table_without_no_data_code(
    tmp_path: Path,
    execution: JVLinkExecutionResult,
    expected_reason: str,
) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08','01')")
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT"
        database.execute(f"CREATE TABLE RT_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE RT_O2_ODDS_UMAREN ({columns})")

    class Runner:
        def execute(
            self, setting: Path, *, skip_last_modified_update: bool
        ) -> JVLinkExecutionResult:
            return execution

    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, Runner()),
        raw,
        builder,
        OddsArchive(raw),
        PROFILE,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    result = retriever.run(cutoff=date(2026, 10, 5))

    assert result.status == "failed"
    assert result.failed_specs == 2
    with sqlite3.connect(tmp_path / "runtime" / "historical-odds-progress.db") as database:
        rows = database.execute(
            "SELECT state,reason,returncode,api_name,api_returncode "
            "FROM race_specs ORDER BY data_spec"
        ).fetchall()
    if expected_reason == "jvlink_error":
        assert rows == [
            ("failed", expected_reason, None, "JVOpen", -504),
            ("failed", expected_reason, None, "JVOpen", -504),
        ]
    else:
        assert rows == [
            ("failed", expected_reason, None, None, None),
            ("failed", expected_reason, None, None, None),
        ]


def test_weekly_run_stops_after_jvlink_error_without_requesting_next_race(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.executemany(
            "INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08',?)",
            [("01",), ("02",)],
        )
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT"
        database.execute(f"CREATE TABLE RT_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE RT_O2_ODDS_UMAREN ({columns})")

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, setting: Path, *, skip_last_modified_update: bool) -> None:
            self.calls += 1
            raise JVLinkToSQLiteError("JV-Link failed", returncode=1)

    runner = Runner()
    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, runner),
        raw,
        builder,
        OddsArchive(raw),
        PROFILE,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    result = retriever.run(cutoff=date(2026, 10, 5))

    assert runner.calls == 1
    assert result.status == "failed"
    assert result.requested_races == 1
    assert result.requested_specs == 2
    assert result.failed_specs == 2
    assert result.pending_after == 4
