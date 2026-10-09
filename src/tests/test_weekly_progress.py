"""Tests for isolated weekly progress bootstrap and reconciliation."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from data.race_key import RaceKey
from data.retriever.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.odds_archive import OddsArchive
from data.retriever.progress import ProgressLedger, RawSnapshot, read_raw_snapshot
from data.retriever.setting import HistoricalOddsBatch, JVLinkProfile
from data.retriever.weekly import WeeklyHistoricalOddsRetriever

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


def test_ledger_refuses_unsupported_schema_and_wrong_database(tmp_path: Path) -> None:
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        ProgressLedger(path, tmp_path / "other.db", PROFILE, BATCH).read()
    with sqlite3.connect(path) as database:
        database.execute("PRAGMA user_version=2")
    with pytest.raises(AcquisitionBlocked, match="schema version"):
        ledger.read()
    with pytest.raises(AcquisitionBlocked, match="schema version"):
        ledger.running_requests()


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
