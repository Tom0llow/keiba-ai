"""Tests for isolated weekly progress bootstrap and reconciliation."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
    JVLinkToSQLiteRunner,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.config.profiles import HistoricalOddsBatch, JVLinkProfile
from jra_van_retriever.progress.ledger import (
    ProgressLedger,
    RawSnapshot,
    _legacy_policy_hash,
    read_raw_snapshot,
)
from jra_van_retriever.progress.raw_observation import read_confirmed_pairs
from jra_van_retriever.progress.state import SpecState, reconcile_states
from jra_van_retriever.workflows.historical_odds import WeeklyHistoricalOddsRetriever
from jra_van_retriever.workflows.historical_odds_plan import (
    plan_snapshot,
    races_for_year,
    select_year,
)

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
BATCH = HistoricalOddsBatch(2003, 2026, 1)


def _extension_ledger(
    tmp_path: Path, *, last_year: int = 2027
) -> tuple[ProgressLedger, ProgressLedger, RawSnapshot]:
    """Return a pre-extension ledger, its extended view, and matching schemas."""
    path = tmp_path / "progress.db"
    raw = tmp_path / "raw.db"
    snapshot = RawSnapshot((FRONTIER,), {}, {"0B41": "schema", "0B42": "schema"})
    ledger = ProgressLedger(path, raw, PROFILE, BATCH)
    ledger.bootstrap(snapshot, NOW)
    return (
        ledger,
        ProgressLedger(path, raw, PROFILE, HistoricalOddsBatch(2003, last_year, 1)),
        snapshot,
    )


def test_bootstrap_leaves_initial_archive_gaps_pending(tmp_path: Path) -> None:
    earlier = RaceKey(date(2003, 10, 4), "05", "04", "01", "01")
    later = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    snapshot = RawSnapshot((earlier, FRONTIER, later), {(FRONTIER.race_id, "0B41"): 2}, {})

    ledger.bootstrap(snapshot, NOW)
    states, _, _ = ledger.read()

    assert states[(earlier.race_id, "0B41")].state == "pending"
    assert states[(earlier.race_id, "0B42")].reason == "unrequested"
    assert states[(FRONTIER.race_id, "0B41")].state == "acquired"
    assert states[(FRONTIER.race_id, "0B42")].state == "pending"
    assert states[(later.race_id, "0B41")].state == "pending"
    assert all(publication == "pending" for publication in ledger.read()[1].values())
    assert not (tmp_path / "raw.db").exists()


def test_bootstrap_adopts_existing_archive_without_initial_gap_classification(
    tmp_path: Path,
) -> None:
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
    _, publications, _ = ledger.read()
    assert publications[2008] == "pending"


def test_legacy_frontier_ledger_is_migrated_without_losing_raw_state(tmp_path: Path) -> None:
    earlier = RaceKey(date(2003, 10, 4), "05", "04", "01", "01")
    snapshot = RawSnapshot((earlier, FRONTIER), {}, {"0B41": "schema"})
    path = tmp_path / "progress.db"
    ledger = ProgressLedger(path, tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(snapshot, NOW)

    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE metadata SET value=? WHERE key='policy_hash'",
            (_legacy_policy_hash(PROFILE, BATCH, FRONTIER),),
        )
        database.executemany(
            "INSERT INTO metadata (key,value) VALUES (?,?)",
            (
                ("frontier", str(FRONTIER)),
                ("bootstrap_reason", "user_accepted_existing_gaps"),
            ),
        )
        database.execute(
            "UPDATE race_specs SET state='provider_missing',reason='user_accepted_existing_gaps' "
            "WHERE race_id=? AND data_spec='0B41'",
            (earlier.race_id,),
        )
        database.execute("UPDATE years SET publication='baseline' WHERE year=2003")

    assert not ledger.extend_last_year(snapshot, NOW)
    assert ledger.migrate_legacy_frontier(snapshot, NOW)
    states, years, _ = ledger.read()

    assert states[(earlier.race_id, "0B41")].state == "pending"
    assert states[(earlier.race_id, "0B41")].reason == "unrequested"
    assert years[2003] == "pending"
    with sqlite3.connect(path) as database:
        metadata = dict(database.execute("SELECT key,value FROM metadata"))
    assert "frontier" not in metadata
    assert metadata["migration_reason"] == "remove_initial_gap_classification"
    assert not ledger.migrate_legacy_frontier(snapshot, NOW)


def test_last_year_extension_adds_pending_years_without_changing_state(tmp_path: Path) -> None:
    ledger, extended, snapshot = _extension_ledger(tmp_path)
    with sqlite3.connect(ledger.path) as database:
        database.execute("UPDATE years SET publication='published' WHERE year=2003")
        database.execute(
            "UPDATE race_specs SET state='failed',reason='jvlink_error',before_rows=1,"
            "after_rows=1,attempts=2 WHERE data_spec='0B41'"
        )
        database.execute(
            "UPDATE race_specs SET state='provider_missing',reason='provider_confirmed_missing',"
            "before_rows=2,after_rows=2,attempts=3 WHERE data_spec='0B42'"
        )
        database.execute(
            "INSERT INTO race_specs (race_id,data_spec,year,state,reason,before_rows,after_rows,"
            "attempts,updated_at) VALUES ('2008012606010708','0B41',2008,'acquired',"
            "'requested_archive_committed',4,4,1,?)",
            (NOW.isoformat(),),
        )
        before_metadata = dict(database.execute("SELECT key,value FROM metadata"))
        before_rows = database.execute(
            "SELECT race_id,data_spec,year,state,reason,last_run,attempts,before_rows,after_rows,"
            "requested_at,updated_at,returncode,api_name,api_returncode FROM race_specs"
        ).fetchall()
        before_years = database.execute(
            "SELECT year,publication,snapshot_id FROM years WHERE year<=2026 ORDER BY year"
        ).fetchall()

    assert extended.extend_last_year(snapshot, NOW)
    _, years, revision = extended.read()
    assert set(years) == set(range(2003, 2028))
    assert years[2027] == "pending"
    assert revision == int(before_metadata["state_revision"]) + 1
    with sqlite3.connect(ledger.path) as database:
        after_metadata = dict(database.execute("SELECT key,value FROM metadata"))
        after_rows = database.execute(
            "SELECT race_id,data_spec,year,state,reason,last_run,attempts,before_rows,after_rows,"
            "requested_at,updated_at,returncode,api_name,api_returncode FROM race_specs"
        ).fetchall()
        after_years = database.execute(
            "SELECT year,publication,snapshot_id FROM years WHERE year<=2026 ORDER BY year"
        ).fetchall()
    assert after_rows == before_rows
    assert after_years == before_years
    assert after_metadata == {
        **before_metadata,
        "policy_hash": extended.policy_hash,
        "state_revision": str(revision),
    }
    extended_bytes = ledger.path.read_bytes()
    assert not extended.extend_last_year(snapshot, NOW)
    assert ledger.path.read_bytes() == extended_bytes


def test_last_year_extension_accepts_multiple_years(tmp_path: Path) -> None:
    _, extended, snapshot = _extension_ledger(tmp_path, last_year=2028)

    assert extended.extend_last_year(snapshot, NOW)

    assert extended.read()[1][2027] == "pending"
    assert extended.read()[1][2028] == "pending"


@pytest.mark.parametrize(
    "change",
    [
        "lower_last_year",
        "first_year",
        "data_specs",
        "race_start_date",
        "year_gap",
    ],
)
def test_last_year_extension_refuses_other_policy_changes(tmp_path: Path, change: str) -> None:
    ledger, extended, snapshot = _extension_ledger(tmp_path)
    if change == "lower_last_year":
        extended = ProgressLedger(
            ledger.path, ledger.raw_db, PROFILE, HistoricalOddsBatch(2003, 2025, 1)
        )
    elif change == "first_year":
        extended = ProgressLedger(
            ledger.path, ledger.raw_db, PROFILE, HistoricalOddsBatch(2004, 2027, 1)
        )
    elif change == "data_specs":
        changed_profile = JVLinkProfile(
            False,
            False,
            True,
            frozenset(),
            frozenset(),
            frozenset({"0B41"}),
            race_start_date=date(2003, 10, 4),
        )
        extended = ProgressLedger(ledger.path, ledger.raw_db, changed_profile, extended.batch)
    elif change == "race_start_date":
        changed_profile = JVLinkProfile(
            False,
            False,
            True,
            frozenset(),
            frozenset(),
            PROFILE.realtime_data_specs,
            race_start_date=date(2003, 10, 5),
        )
        extended = ProgressLedger(ledger.path, ledger.raw_db, changed_profile, extended.batch)
    else:
        with sqlite3.connect(ledger.path) as database:
            database.execute("DELETE FROM years WHERE year=2010")
    before = ledger.path.read_bytes()

    assert not extended.extend_last_year(snapshot, NOW)
    assert ledger.path.read_bytes() == before
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        extended.read()
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        extended.read(preview_year_extension=True)


@pytest.mark.parametrize("last_year", [2027, 2028])
def test_read_preview_adds_extended_years_without_writing(tmp_path: Path, last_year: int) -> None:
    ledger, extended, _ = _extension_ledger(tmp_path, last_year=last_year)
    with sqlite3.connect(ledger.path) as database:
        database.execute("UPDATE years SET publication='published' WHERE year=2026")
    before = ledger.path.read_bytes()

    _, years, _ = extended.read(preview_year_extension=True)

    assert set(years) == set(range(2003, last_year + 1))
    assert years[2026] == "published"
    assert all(years[year] == "pending" for year in range(2027, last_year + 1))
    assert ledger.path.read_bytes() == before
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        extended.read()


def test_last_year_extension_rejects_wrong_raw_database(tmp_path: Path) -> None:
    ledger, _, snapshot = _extension_ledger(tmp_path)
    wrong_database = ProgressLedger(
        ledger.path,
        tmp_path / "other.db",
        PROFILE,
        HistoricalOddsBatch(2003, 2027, 1),
    )
    before = ledger.path.read_bytes()

    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        wrong_database.extend_last_year(snapshot, NOW)

    assert ledger.path.read_bytes() == before


@pytest.mark.parametrize("invalid", ["state", "counts", "schemas"])
def test_last_year_extension_rejects_invalid_ledger_without_writing(
    tmp_path: Path, invalid: str
) -> None:
    ledger, extended, snapshot = _extension_ledger(tmp_path)
    if invalid == "state":
        with sqlite3.connect(ledger.path) as database:
            database.execute("UPDATE race_specs SET state='provider_missing',reason='jvlink_error'")
    elif invalid == "counts":
        with sqlite3.connect(ledger.path) as database:
            database.execute("UPDATE race_specs SET before_rows=-1")
    else:
        snapshot = RawSnapshot(snapshot.races, snapshot.counts, {"0B41": "changed"})
    before = ledger.path.read_bytes()
    message = {
        "state": "unsupported or unresolved race/spec state",
        "counts": "invalid progress row counts",
        "schemas": "archive schema disappeared or changed",
    }[invalid]

    with pytest.raises(AcquisitionBlocked, match=message):
        extended.extend_last_year(snapshot, NOW)

    assert ledger.path.read_bytes() == before


@pytest.mark.parametrize("invalid", ["publication", "race_year"])
def test_year_extension_preview_and_migration_refuse_ledger_invalid_under_prior_policy(
    tmp_path: Path, invalid: str
) -> None:
    ledger, extended, snapshot = _extension_ledger(tmp_path)
    with sqlite3.connect(ledger.path) as database:
        if invalid == "publication":
            database.execute("UPDATE years SET publication='baseline' WHERE year=2010")
        else:
            database.execute(
                "INSERT INTO race_specs (race_id,data_spec,year,state,reason,updated_at) "
                "VALUES ('2027010906010101','0B41',2027,'pending','unrequested',?)",
                (NOW.isoformat(),),
            )
    before = ledger.path.read_bytes()
    message = {
        "publication": "invalid publication year states",
        "race_year": "progress ledger race lies outside the policy",
    }[invalid]

    with pytest.raises(AcquisitionBlocked, match=message):
        extended.read(preview_year_extension=True)
    with pytest.raises(AcquisitionBlocked, match=message):
        extended.extend_last_year(snapshot, NOW)

    assert ledger.path.read_bytes() == before


def test_external_archive_is_adopted_and_missing_state_recovers(tmp_path: Path) -> None:
    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((FRONTIER,), {}, {}), NOW)
    columns = (
        "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,"
        "idNichiji TEXT,idRaceNum TEXT,headDataKubun TEXT"
    )
    with sqlite3.connect(ledger.raw_db) as database:
        database.execute(f"CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE ARCHIVE_O2_ODDS_UMAREN ({columns})")
        database.execute(
            "INSERT INTO ARCHIVE_O1_ODDS_TANFUKUWAKU VALUES ('2008','0126','06','01','07','06','4')"
        )
        database.execute(
            "INSERT INTO ARCHIVE_O2_ODDS_UMAREN VALUES ('2008','0126','06','01','07','06','1')"
        )

    adopted = ledger.reconcile(
        RawSnapshot(
            (FRONTIER,),
            {(FRONTIER.race_id, "0B41"): 1, (FRONTIER.race_id, "0B42"): 1},
            {},
        ),
        NOW,
    )
    states, years, _ = ledger.read()

    assert adopted == {"0B41": 1, "0B42": 0}
    assert states[(FRONTIER.race_id, "0B41")].reason == "external_archive_observed"
    assert states[(FRONTIER.race_id, "0B41")].state == "acquired"
    assert states[(FRONTIER.race_id, "0B42")].state == "pending"
    assert years[2008] == "pending"
    assert ledger.reconcile(
        RawSnapshot(
            (FRONTIER,),
            {(FRONTIER.race_id, "0B41"): 1, (FRONTIER.race_id, "0B42"): 1},
            {},
        ),
        NOW,
    ) == {"0B41": 0, "0B42": 0}
    with pytest.raises(AcquisitionBlocked, match="disappeared"):
        ledger.reconcile(RawSnapshot((FRONTIER,), {}, {}), NOW)


def test_unconfirmed_archive_candidate_remains_pending_and_is_planned(tmp_path: Path) -> None:
    pair = (FRONTIER.race_id, "0B41")
    snapshot = RawSnapshot((FRONTIER,), {pair: 1}, {})

    states, changed_years, adopted = reconcile_states({}, snapshot, PROFILE.realtime_data_specs)

    assert states[pair].state == "pending"
    assert states[pair].reason == "new_candidate"
    assert changed_years == {2008}
    assert adopted == {"0B41": 0, "0B42": 0}
    assert (
        select_year(PROFILE.realtime_data_specs, states, snapshot.races, date(2026, 10, 5)) == 2008
    )
    assert races_for_year(PROFILE.realtime_data_specs, states, snapshot.races, 2008) == (FRONTIER,)

    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((), {}, {}), NOW)
    with sqlite3.connect(ledger.raw_db) as database:
        database.execute(
            "CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU "
            "(idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,"
            "idNichiji TEXT,idRaceNum TEXT,headDataKubun TEXT)"
        )
        database.execute(
            "INSERT INTO ARCHIVE_O1_ODDS_TANFUKUWAKU VALUES ('2008','0126','06','01','07','06','1')"
        )

    plan = plan_snapshot(snapshot, date(2026, 10, 5), PROFILE.realtime_data_specs, ledger)

    assert plan.adopted_races == {"0B41": 0, "0B42": 0}
    assert plan.year == 2008
    assert plan.requested_races == 1
    assert plan.requested_specs == 2


def test_confirmed_archive_candidate_is_adopted_and_unconfirmed_spec_is_planned(
    tmp_path: Path,
) -> None:
    pair = (FRONTIER.race_id, "0B41")
    snapshot = RawSnapshot((FRONTIER,), {pair: 1}, {})

    ledger = ProgressLedger(tmp_path / "progress.db", tmp_path / "raw.db", PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((), {}, {}), NOW)
    with sqlite3.connect(ledger.raw_db) as database:
        database.execute(
            "CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU "
            "(idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,"
            "idNichiji TEXT,idRaceNum TEXT,headDataKubun TEXT)"
        )
        database.execute(
            "INSERT INTO ARCHIVE_O1_ODDS_TANFUKUWAKU VALUES ('2008','0126','06','01','07','06','4')"
        )

    plan = plan_snapshot(snapshot, date(2026, 10, 5), PROFILE.realtime_data_specs, ledger)

    assert plan.adopted_races == {"0B41": 1, "0B42": 0}
    assert plan.requested_races == 1
    assert plan.requested_specs == 1


def test_confirmed_archive_adopts_new_candidate() -> None:
    pair = (FRONTIER.race_id, "0B41")
    snapshot = RawSnapshot((FRONTIER,), {pair: 1}, {}, frozenset({pair}))

    states, changed_years, adopted = reconcile_states({}, snapshot, frozenset({"0B41"}))

    assert states[pair].state == "acquired"
    assert states[pair].reason == "external_archive_observed"
    assert changed_years == {2008}
    assert adopted == {"0B41": 1}


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("pending", "unrequested"),
        ("failed", "jvlink_error"),
        ("provider_missing", "jvopen_no_data"),
    ],
)
def test_confirmed_archive_adopts_incomplete_state(state: str, reason: str) -> None:
    pair = (FRONTIER.race_id, "0B41")
    prior = SpecState(FRONTIER.race_id, "0B41", state, reason, 0, 0)
    snapshot = RawSnapshot((FRONTIER,), {pair: 1}, {}, frozenset({pair}))

    states, changed_years, adopted = reconcile_states({pair: prior}, snapshot, frozenset({"0B41"}))

    assert states[pair].state == "acquired"
    assert states[pair].reason == "external_archive_observed"
    assert changed_years == {2008}
    assert adopted == {"0B41": 1}


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("pending", "unrequested"),
        ("failed", "jvlink_error"),
        ("provider_missing", "jvopen_no_data"),
    ],
)
def test_unconfirmed_archive_keeps_incomplete_state(state: str, reason: str) -> None:
    pair = (FRONTIER.race_id, "0B41")
    prior = SpecState(FRONTIER.race_id, "0B41", state, reason, 0, 0)
    snapshot = RawSnapshot((FRONTIER,), {pair: 1}, {})

    states, changed_years, adopted = reconcile_states({pair: prior}, snapshot, frozenset({"0B41"}))

    assert states[pair] == prior
    assert changed_years == set()
    assert adopted == {"0B41": 0}


def test_unconfirmed_archive_keeps_acquired_state_without_updating_count() -> None:
    pair = (FRONTIER.race_id, "0B41")
    prior = SpecState(FRONTIER.race_id, "0B41", "acquired", "initial_archive_observed", 1, 1)
    snapshot = RawSnapshot((FRONTIER,), {pair: 2}, {})

    states, changed_years, adopted = reconcile_states({pair: prior}, snapshot, frozenset({"0B41"}))

    assert states[pair] == prior
    assert changed_years == set()
    assert adopted == {"0B41": 0}


def test_confirmed_archive_refreshes_acquired_state_when_count_increases() -> None:
    pair = (FRONTIER.race_id, "0B41")
    prior = SpecState(FRONTIER.race_id, "0B41", "acquired", "external_archive_observed", 1, 1)
    snapshot = RawSnapshot((FRONTIER,), {pair: 2}, {}, frozenset({pair}))

    states, changed_years, adopted = reconcile_states({pair: prior}, snapshot, frozenset({"0B41"}))

    assert states[pair] == SpecState(
        FRONTIER.race_id, "0B41", "acquired", "external_archive_observed", 2, 2
    )
    assert changed_years == {2008}
    assert adopted == {"0B41": 1}


def test_read_confirmed_pairs_and_snapshot_rejects_missing_column(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT"
    archive_columns = f"{columns},headDataKubun TEXT"
    archive_rows = [
        ("2008", "0127", "05", "02", "03", "01", "4"),
        ("2008", "0127", "01", "01", "08", "02", "1"),
        ("2008", "0127", "01", "01", "08", "03", "2"),
        ("2008", "0127", "01", "01", "08", "04", "9"),
    ]
    with sqlite3.connect(raw) as database:
        database.execute(f"CREATE TABLE NL_RA_RACE ({columns})")
        database.executemany(
            "INSERT INTO NL_RA_RACE VALUES (?,?,?,?,?,?)",
            [row[:6] for row in archive_rows] + [("2008", "0127", "01", "01", "08", "05")],
        )
        database.execute(f"CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU ({archive_columns})")
        database.execute(f"CREATE TABLE ARCHIVE_O2_ODDS_UMAREN ({archive_columns})")
        database.executemany(
            "INSERT INTO ARCHIVE_O1_ODDS_TANFUKUWAKU VALUES (?,?,?,?,?,?,?)", archive_rows
        )
        database.execute(
            "INSERT INTO ARCHIVE_O2_ODDS_UMAREN VALUES ('2008','0127','01','01','08','05','5')"
        )

    pairs = frozenset(
        {
            (RaceKey(date(2008, 1, 27), "05", "02", "03", "01").race_id, "0B41"),
            (RaceKey(date(2008, 1, 27), "01", "01", "08", "02").race_id, "0B41"),
            (RaceKey(date(2008, 1, 27), "01", "01", "08", "03").race_id, "0B41"),
            (RaceKey(date(2008, 1, 27), "01", "01", "08", "04").race_id, "0B41"),
            (RaceKey(date(2008, 1, 27), "01", "01", "08", "05").race_id, "0B42"),
        }
    )
    assert read_confirmed_pairs(raw, pairs) == {
        (RaceKey(date(2008, 1, 27), "05", "02", "03", "01").race_id, "0B41"),
        (RaceKey(date(2008, 1, 27), "01", "01", "08", "05").race_id, "0B42"),
    }
    assert read_confirmed_pairs(tmp_path / "missing.db", ()) == frozenset()

    missing_table = tmp_path / "missing-table.db"
    with sqlite3.connect(missing_table) as database:
        database.execute(f"CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU ({archive_columns})")
    assert read_confirmed_pairs(missing_table, {(FRONTIER.race_id, "0B42")}) == frozenset()

    missing_column = tmp_path / "missing-head-data-kubun.db"
    with sqlite3.connect(missing_column) as database:
        database.execute(f"CREATE TABLE NL_RA_RACE ({columns})")
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08','01')")
        database.execute(f"CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU ({columns})")

    with pytest.raises(AcquisitionBlocked, match="archive key schema is invalid"):
        read_raw_snapshot(missing_column, PROFILE, BATCH, date(2026, 10, 5))


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
        HistoricalOddsBatch(2003, 2025, 1),
    )
    with pytest.raises(AcquisitionBlocked, match="raw database or policy"):
        mismatched.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 0})

    missing = ProgressLedger(tmp_path / "missing.db", raw, PROFILE, BATCH)
    with pytest.raises(AcquisitionBlocked, match="existing ledger"):
        missing.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 0})
    assert not (tmp_path / "missing.db").exists()


def _raw_with_archive_rows(raw: Path, key: RaceKey, head_data_kubun: str) -> None:
    columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT"
    values = (
        f"{key.race_date:%Y}",
        f"{key.race_date:%m%d}",
        key.jyo_code,
        key.kaiji,
        key.nichiji,
        key.race_number,
    )
    with closing(sqlite3.connect(raw)) as database, database:
        database.execute(f"CREATE TABLE ARCHIVE_O1_ODDS_TANFUKUWAKU ({columns},headDataKubun TEXT)")
        database.execute(
            "INSERT INTO ARCHIVE_O1_ODDS_TANFUKUWAKU VALUES (?,?,?,?,?,?,?)",
            (*values, head_data_kubun),
        )


@pytest.mark.parametrize(("head_data_kubun", "accepted"), [("1", True), ("4", False)])
def test_confirm_provider_missing_accepts_only_unconfirmed_archive_rows(
    tmp_path: Path, head_data_kubun: str, accepted: bool
) -> None:
    key = RaceKey(date(2008, 1, 26), "06", "01", "07", "07")
    raw = tmp_path / "raw.db"
    _raw_with_archive_rows(raw, key, head_data_kubun)
    ledger = ProgressLedger(tmp_path / "progress.db", raw, PROFILE, BATCH)
    ledger.bootstrap(RawSnapshot((key,), {}, {}), NOW)
    ledger.start_run("run", 2008, date(2026, 10, 5), NOW, (key,), {})
    ledger.request("run", key, frozenset({"0B41"}), {"0B41": 1}, NOW)
    ledger.finish_request(
        key,
        {"0B41": ("failed", "empty_response_unverified", 0)},
        NOW,
        recovered=True,
    )

    if accepted:
        ledger.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 1})
        states, _, _ = ledger.read()
        assert states[(key.race_id, "0B41")].state == "provider_missing"
        assert states[(key.race_id, "0B41")].reason == "provider_confirmed_missing"
    else:
        with pytest.raises(AcquisitionBlocked, match="conflicts with archive rows"):
            ledger.confirm_provider_missing(key, frozenset({"0B41"}), NOW, {"0B41": 1})
        states, _, _ = ledger.read()
        assert states[(key.race_id, "0B41")].state == "failed"


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
            "UPDATE race_specs SET state='provider_missing',reason='jvopen_no_data' "
            "WHERE race_id=? AND data_spec='0B41'",
            (FRONTIER.race_id,),
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


def _create_year_extension_raw_database(raw: Path) -> None:
    """Create one acquired 2026 race and one pending 2027 race."""
    columns = (
        "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,"
        "idRaceNum TEXT,HappyoTime TEXT,headDataKubun TEXT"
    )
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,"
            "idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2026','1227','01','01','01','01')")
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2027','0109','01','01','01','01')")
        for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns})")
        for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns})")
            database.execute(
                f"INSERT INTO {table} VALUES ('2026','1227','01','01','01','01','120000','4')"
            )


def _bootstrap_year_extension_ledger(
    retriever: WeeklyHistoricalOddsRetriever, raw: Path
) -> ProgressLedger:
    """Create the 2026 ledger at the runtime path used by an extended retriever."""
    ledger = ProgressLedger(retriever.ledger_path, raw, PROFILE, BATCH)
    ledger.bootstrap(read_raw_snapshot(raw, PROFILE, BATCH, date(2027, 12, 31)), NOW)
    return ledger


def test_plan_only_previews_year_extension_without_writing(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    _create_year_extension_raw_database(raw)
    builder = Mock()
    retriever = WeeklyHistoricalOddsRetriever(
        Mock(),
        raw,
        builder,
        OddsArchive(raw),
        PROFILE,
        HistoricalOddsBatch(2003, 2027, 1),
        tmp_path / "runtime",
        clock=lambda: NOW,
    )
    ledger = _bootstrap_year_extension_ledger(retriever, raw)
    before = ledger.path.read_bytes()

    plan = retriever.run(plan_only=True, cutoff=date(2027, 12, 31), raw_only=True)

    assert plan.year == 2027
    assert plan.requested_races == 1
    assert ledger.path.read_bytes() == before


def test_plan_only_preview_returns_earlier_incomplete_year_first(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    _create_year_extension_raw_database(raw)
    with sqlite3.connect(raw) as database:
        database.execute("DELETE FROM ARCHIVE_O1_ODDS_TANFUKUWAKU")
        database.execute("DELETE FROM ARCHIVE_O2_ODDS_UMAREN")
    retriever = WeeklyHistoricalOddsRetriever(
        Mock(),
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        HistoricalOddsBatch(2003, 2027, 1),
        tmp_path / "runtime",
        clock=lambda: NOW,
    )
    ledger = _bootstrap_year_extension_ledger(retriever, raw)
    before = ledger.path.read_bytes()

    plan = retriever.run(plan_only=True, cutoff=date(2027, 12, 31), raw_only=True)

    assert plan.year == 2026
    assert plan.requested_races == 1
    assert ledger.path.read_bytes() == before


def test_weekly_run_extends_ledger_and_requests_new_year(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    _create_year_extension_raw_database(raw)

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, setting: Path, *, skip_last_modified_update: bool) -> None:
            self.calls += 1
            with sqlite3.connect(raw) as database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(
                        f"INSERT INTO {table} VALUES ('2027','0109','01','01','01','01','120000','4')"
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
        HistoricalOddsBatch(2003, 2027, 1),
        tmp_path / "runtime",
        clock=lambda: NOW,
    )
    _bootstrap_year_extension_ledger(retriever, raw)

    result = retriever.run(cutoff=date(2027, 12, 31), raw_only=True)

    assert result.year == 2027
    assert result.requested_races == 1
    assert runner.calls == 1
    states, years, _ = retriever.ledger.read()
    assert years[2027] == "pending"
    assert all(
        states[("2027010901010101", spec)].state == "acquired"
        for spec in PROFILE.realtime_data_specs
    )


def test_recovery_run_extends_ledger_before_recovering_running_request(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    _create_year_extension_raw_database(raw)

    class Runner:
        def __init__(self) -> None:
            self.recovery_checks = 0
            self.calls = 0

        def assert_not_running(self) -> None:
            self.recovery_checks += 1

        def execute(self, setting: Path, *, skip_last_modified_update: bool) -> None:
            self.calls += 1
            with sqlite3.connect(raw) as database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(
                        f"INSERT INTO {table} VALUES ('2027','0109','01','01','01','01','120000','4')"
                    )

    runner = Runner()
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, runner),
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        HistoricalOddsBatch(2003, 2027, 1),
        tmp_path / "runtime",
        clock=lambda: NOW,
    )
    ledger = _bootstrap_year_extension_ledger(retriever, raw)
    key = RaceKey(date(2026, 12, 27), "01", "01", "01", "01")
    with sqlite3.connect(ledger.path) as database:
        database.execute(
            "UPDATE race_specs SET state='pending',reason='unrequested' "
            "WHERE race_id=? AND data_spec='0B41'",
            (key.race_id,),
        )
    ledger.start_run("interrupted", 2026, date(2027, 12, 31), NOW, (key,), {})
    ledger.request("interrupted", key, frozenset({"0B41"}), {"0B41": 1}, NOW)

    result = retriever.run(recover=True, cutoff=date(2027, 12, 31), raw_only=True)

    assert result.status == "up_to_date"
    assert runner.recovery_checks == 1
    assert runner.calls == 1
    _, years, _ = retriever.ledger.read()
    assert years[2027] == "pending"
    with sqlite3.connect(retriever.ledger.path) as database:
        assert (
            database.execute("SELECT COUNT(*) FROM race_specs WHERE state='running'").fetchone()[0]
            == 0
        )


def test_confirm_provider_missing_extends_last_year(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    _create_year_extension_raw_database(raw)
    with sqlite3.connect(raw) as database:
        database.execute("DELETE FROM ARCHIVE_O1_ODDS_TANFUKUWAKU")
        database.execute("DELETE FROM ARCHIVE_O2_ODDS_UMAREN")
    confirmation_time = datetime(2027, 1, 2, 12, tzinfo=UTC)
    retriever = WeeklyHistoricalOddsRetriever(
        Mock(),
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        HistoricalOddsBatch(2003, 2027, 1),
        tmp_path / "runtime",
        clock=lambda: confirmation_time,
    )
    ledger = _bootstrap_year_extension_ledger(retriever, raw)
    key = RaceKey(date(2026, 12, 27), "01", "01", "01", "01")
    with sqlite3.connect(ledger.path) as database:
        database.execute(
            "UPDATE race_specs SET state='failed',reason='empty_response_unverified' "
            "WHERE race_id=? AND data_spec='0B41'",
            (key.race_id,),
        )

    assert retriever.confirm_provider_missing(key, frozenset({"0B41"})) == 1

    states, years, _ = retriever.ledger.read()
    assert years[2027] == "pending"
    assert states[(key.race_id, "0B41")].state == "provider_missing"


def test_publication_preparation_extends_last_year(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    _create_year_extension_raw_database(raw)
    retriever = WeeklyHistoricalOddsRetriever(
        Mock(),
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        HistoricalOddsBatch(2003, 2027, 1),
        tmp_path / "runtime",
        clock=lambda: NOW,
    )
    _bootstrap_year_extension_ledger(retriever, raw)

    retriever.prepare_publication(cutoff=date(2027, 12, 31))

    assert retriever.ledger.read()[1][2027] == "pending"


def test_weekly_run_retrieves_one_year_and_resumes_without_repeating(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08','01')")
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT,headDataKubun TEXT"
        database.execute(f"CREATE TABLE RT_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE RT_O2_ODDS_UMAREN ({columns})")
        database.execute(
            "INSERT INTO RT_O1_ODDS_TANFUKUWAKU VALUES ('2008','0127','01','01','08','01','110000','1')"
        )

    class Runner:
        def execute(self, setting: Path, *, skip_last_modified_update: bool) -> None:
            with sqlite3.connect(raw) as database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(
                        f"INSERT INTO {table} VALUES ('2008','0127','01','01','08','01','120000','4')"
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

    second = retriever.run(cutoff=date(2026, 10, 5), raw_only=True)
    assert second.status == "up_to_date"
    assert second.requested_races == 0
    assert retriever.publish_complete(lambda: "published") == "published"
    progress = json.loads(
        (tmp_path / "runtime" / "historical-odds-progress.json").read_text(encoding="utf-8")
    )
    assert progress["publication"] == "published"
    third = retriever.run(cutoff=date(2026, 10, 5))
    assert third.status == "up_to_date"
    assert 'phase = "idle"' in (tmp_path / "runtime" / "historical-odds-effective.toml").read_text(
        encoding="utf-8"
    )
    with sqlite3.connect(raw) as database:
        assert (
            database.execute("SELECT COUNT(*) FROM ARCHIVE_O1_ODDS_TANFUKUWAKU").fetchone()[0] == 1
        )
        assert database.execute("SELECT COUNT(*) FROM ARCHIVE_O2_ODDS_UMAREN").fetchone()[0] == 1


def test_weekly_run_backfills_race_with_only_unconfirmed_race_day_rows(tmp_path: Path) -> None:
    raw = tmp_path / "raw.db"
    race_key = "'2008','0127','01','01','08','01'"
    columns = (
        "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,"
        "HappyoTime TEXT,headDataKubun TEXT"
    )
    with closing(sqlite3.connect(raw)) as database, database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns})")

    class Runner:
        def execute(self, setting: Path, *, skip_last_modified_update: bool) -> None:
            with closing(sqlite3.connect(raw)) as database, database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(f"INSERT INTO {table} VALUES ({race_key},'115500','1')")
                    database.execute(f"INSERT INTO {table} VALUES ({race_key},'120000','4')")

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
    assert retriever.run(cutoff=date(2026, 10, 5), raw_only=True).status == "up_to_date"

    # A race-day prediction capture stored the freeze-time series before historical-odds saw the race.
    with closing(sqlite3.connect(raw)) as database, database:
        database.execute(f"INSERT INTO NL_RA_RACE VALUES ({race_key})")
        for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns})")
            database.execute(f"INSERT INTO {table} VALUES ({race_key},'115500','1')")

    result = retriever.run(cutoff=date(2026, 10, 5), raw_only=True)

    assert result.adopted_races == {"0B41": 0, "0B42": 0}
    assert result.requested_races == 1
    assert result.requested_specs == 2
    assert result.new_rows == {"0B41": 1, "0B42": 1}
    states, _, _ = retriever.ledger.read()
    for spec in ("0B41", "0B42"):
        state = states[("2008012701010801", spec)]
        assert (state.state, state.reason) == ("acquired", "requested_archive_committed")
        assert (state.before_rows, state.after_rows) == (1, 2)
    with closing(sqlite3.connect(raw)) as database:
        assert database.execute(
            "SELECT HappyoTime, headDataKubun FROM ARCHIVE_O1_ODDS_TANFUKUWAKU ORDER BY HappyoTime"
        ).fetchall() == [("115500", "1"), ("120000", "4")]


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
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT,headDataKubun TEXT"
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
                        f"INSERT INTO {table} VALUES ('2008','0127','01','01','08','02','120000','4')"
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
    assert result.new_races == {"0B41": 1, "0B42": 1}
    assert result.new_provider_missing == {"0B41": 1, "0B42": 1}
    with sqlite3.connect(tmp_path / "runtime" / "historical-odds-progress.db") as database:
        rows = database.execute(
            "SELECT race_id,state,reason,returncode,api_name,api_returncode "
            "FROM race_specs ORDER BY race_id,data_spec"
        ).fetchall()
        publication = database.execute("SELECT publication FROM years WHERE year=2008").fetchone()[
            0
        ]
    assert set(rows) == {
        ("2008012701010801", "provider_missing", "jvopen_no_data", None, "JVOpen", -1),
        ("2008012701010802", "acquired", "requested_archive_committed", None, "JVOpen", 0),
    }
    assert publication == "pending"
    with sqlite3.connect(raw) as database:
        assert database.execute("SELECT COUNT(*) FROM RT_O1_ODDS_TANFUKUWAKU").fetchone()[0] == 0
        assert database.execute("SELECT COUNT(*) FROM RT_O2_ODDS_UMAREN").fetchone()[0] == 0


def test_weekly_run_reports_current_year_as_up_to_date_after_complete_request(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw.db"
    with sqlite3.connect(raw) as database:
        database.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT)"
        )
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2026','1004','01','01','01','01')")
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT,headDataKubun TEXT"
        database.execute(f"CREATE TABLE RT_O1_ODDS_TANFUKUWAKU ({columns})")
        database.execute(f"CREATE TABLE RT_O2_ODDS_UMAREN ({columns})")

    class Runner:
        def execute(
            self, setting: Path, *, skip_last_modified_update: bool
        ) -> JVLinkExecutionResult:
            with sqlite3.connect(raw) as database:
                for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                    database.execute(
                        f"INSERT INTO {table} VALUES ('2026','1004','01','01','01','01','120000','4')"
                    )
            return JVLinkExecutionResult(
                {"0B41": 0, "0B42": 0},
                api_results={"0B41": ("JVOpen", 0), "0B42": ("JVOpen", 0)},
                open_returncodes={"0B41": 0, "0B42": 0},
            )

    batch = HistoricalOddsBatch(
        2026,
        2026,
        1,
    )
    profile = JVLinkProfile(
        False,
        False,
        True,
        frozenset(),
        frozenset(),
        frozenset({"0B41", "0B42"}),
        race_start_date=date(2026, 1, 1),
    )
    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    retriever = WeeklyHistoricalOddsRetriever(
        cast(JVLinkToSQLiteRunner, Runner()),
        raw,
        builder,
        OddsArchive(raw),
        profile,
        batch,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )

    result = retriever.run(cutoff=date(2026, 10, 5))

    assert result.status == "up_to_date"
    assert result.year == 2026
    assert result.pending_after == 0


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
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT,headDataKubun TEXT"
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
        columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT,HappyoTime TEXT,headDataKubun TEXT"
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


def _retriever_with_staging_rows(
    tmp_path: Path, execution: JVLinkExecutionResult
) -> tuple[WeeklyHistoricalOddsRetriever, Mock]:
    raw = tmp_path / "raw.db"
    columns = "idYear TEXT,idMonthDay TEXT,idJyoCD TEXT,idKaiji TEXT,idNichiji TEXT,idRaceNum TEXT"
    with closing(sqlite3.connect(raw)) as database, database:
        database.execute(f"CREATE TABLE NL_RA_RACE ({columns})")
        database.execute("INSERT INTO NL_RA_RACE VALUES ('2008','0127','01','01','08','01')")
        for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
            database.execute(f"CREATE TABLE {table} ({columns},HappyoTime TEXT,headDataKubun TEXT)")

    def execute(setting: Path, *, skip_last_modified_update: bool) -> JVLinkExecutionResult:
        with closing(sqlite3.connect(raw, timeout=0)) as database, database:
            database.execute("BEGIN EXCLUSIVE")
            for table in ("RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"):
                database.execute(
                    f"INSERT INTO {table} VALUES ('2008','0127','01','01','08','01','120000','4')"
                )
        return execution

    runner = Mock(spec=JVLinkToSQLiteRunner)
    runner.execute.side_effect = execute
    retriever = WeeklyHistoricalOddsRetriever(
        runner,
        raw,
        Mock(),
        OddsArchive(raw),
        PROFILE,
        BATCH,
        tmp_path / "runtime",
        clock=lambda: NOW,
    )
    return retriever, runner


def test_weekly_run_counts_acquired_and_fatal_specs_separately(tmp_path: Path) -> None:
    execution = JVLinkExecutionResult(
        {"0B41": 0, "0B42": -504},
        fatal_specs=frozenset({"0B42"}),
        api_results={"0B41": ("JVRTOpen", 0), "0B42": ("JVRTOpen", -504)},
        fatal_returncodes={"0B42": -504},
        process_returncode=0,
    )
    retriever, runner = _retriever_with_staging_rows(tmp_path, execution)

    result = retriever.run(cutoff=date(2026, 10, 5))

    runner.execute.assert_called_once()
    assert result.status == "failed"
    assert result.requested_specs == 2
    assert result.failed_specs == 1
    assert result.new_rows == {"0B41": 1, "0B42": 0}
    assert result.new_races == {"0B41": 1, "0B42": 0}
    assert result.new_provider_missing == {"0B41": 0, "0B42": 0}
    states, _, _ = retriever.ledger.read()
    assert states[("2008012701010801", "0B41")].state == "acquired"
    assert states[("2008012701010801", "0B42")].reason == "jvlink_error"
    with closing(sqlite3.connect(retriever.ledger_path)) as database:
        rows = database.execute(
            "SELECT data_spec,returncode,api_name,api_returncode FROM race_specs ORDER BY data_spec"
        ).fetchall()
    assert rows == [("0B41", 0, "JVRTOpen", 0), ("0B42", 0, "JVRTOpen", -504)]


def test_weekly_run_resumes_from_committed_ledger_after_report_write_failure(
    tmp_path: Path,
) -> None:
    retriever, runner = _retriever_with_staging_rows(tmp_path, JVLinkExecutionResult({}))
    with (
        patch(
            "jra_van_retriever.progress.output.atomic_write", side_effect=OSError("report failed")
        ),
        pytest.raises(OSError, match="report failed"),
    ):
        retriever.run(cutoff=date(2026, 10, 5), raw_only=True)

    states, _, revision = retriever.ledger.read()
    assert all(state.state == "acquired" for state in states.values())
    with closing(sqlite3.connect(retriever.ledger_path)) as database:
        assert database.execute("SELECT status FROM runs").fetchall() == [("completed",)]

    result = retriever.run(cutoff=date(2026, 10, 5), raw_only=True)

    assert result.status == "up_to_date"
    runner.execute.assert_called_once()
    progress = json.loads(
        (tmp_path / "runtime" / "historical-odds-progress.json").read_text(encoding="utf-8")
    )
    assert progress["state_revision"] >= revision
    assert progress["status"] == "up_to_date"
