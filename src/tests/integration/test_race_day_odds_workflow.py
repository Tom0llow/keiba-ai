"""Tests for the race-day odds capture loop with fake JV-Link and clock boundaries."""

import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from domain.race_key import RaceKey
from jra_van_retriever.acquisition import odds_archive
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.config.profiles import (
    HistoricalOddsBatch,
    JVLinkProfile,
    RaceDayOddsProfile,
)
from jra_van_retriever.progress.raw_observation import read_raw_snapshot
from jra_van_retriever.workflows.race_day_odds import RaceDayOddsRetriever

RACE_DATE = date(2026, 11, 15)
SPECS = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"})
KEYS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
PARENTS = (
    "RT_O1_ODDS_TANFUKUWAKU",
    "RT_O2_ODDS_UMAREN",
    "RT_O3_ODDS_WIDE",
    "RT_O4_ODDS_UMATAN",
    "RT_O5_ODDS_SANREN",
    "RT_O6_ODDS_SANRENTAN",
)
CHILDREN = (
    ("RT_O5_OddsSanrenInfo", "OddsSanrenInfo"),
    ("RT_O6_OddsSanrentanInfo", "OddsSanrentanInfo"),
)
# 15:00 and 15:30 JST starts are 06:00 and 06:30 UTC.
STARTS = {"11": "1500", "12": "1530"}


class FakeClock:
    """Advance only when the workflow sleeps or the runner executes."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


class FakeRunner:
    """Write one race's staging rows the way JVLinkToSQLite would."""

    def __init__(self, database: Path, clock: FakeClock) -> None:
        self.database = database
        self.clock = clock
        self.calls: list[str] = []
        self.observed_running: list[set[str]] = []
        self.observed_staging: list[int] = []
        self.fail_calls: set[int] = set()
        self.assert_not_running = Mock()

    def execute(self, setting: Path, *, skip_last_modified_update: bool = False) -> object:
        assert skip_last_modified_update is True
        assert setting.name == "race-day-odds.xml"
        call = len(self.calls)
        race = _race_numbers_by_order[call]
        self.calls.append(race)
        with sqlite3.connect(self.database) as connection:
            self.observed_running.append(
                {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT status FROM ARCHIVE_CAPTURE_LOG WHERE started_at IS NOT NULL "
                        "AND completed_at IS NULL"
                    )
                }
            )
            self.observed_staging.append(
                sum(
                    int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    for table in PARENTS
                )
            )
        _stage(self.database, race, f"1115{self.clock.now.astimezone(UTC):%H%M}")
        self.clock.now += timedelta(seconds=2)
        if call in self.fail_calls:
            raise JVLinkToSQLiteError("JV-Link failed", returncode=1)
        return JVLinkExecutionResult({}, process_returncode=0)


_race_numbers_by_order: list[str] = []


def _create_raw(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE NL_RA_RACE ("
            + ", ".join(f'"{name}" TEXT' for name in (*KEYS, "headDataKubun", "HassoTime"))
            + ")"
        )
        for race, hasso in STARTS.items():
            connection.execute(
                "INSERT INTO NL_RA_RACE VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("2026", "1115", "05", "05", "04", race, "2", hasso),
            )
        parent_columns = ", ".join(
            f'"{name}" TEXT' for name in ("headRecordSpec", "headDataKubun", *KEYS, "HappyoTime")
        )
        for table in PARENTS:
            connection.execute(f'CREATE TABLE "{table}" ({parent_columns})')
        for table, prefix in CHILDREN:
            columns = ", ".join(f'"{name}" TEXT' for name in (*KEYS, f"{prefix}Kumi"))
            connection.execute(f'CREATE TABLE "{table}" ({columns})')


def _stage(database: Path, race: str, happyo: str) -> None:
    values = ("2026", "1115", "05", "05", "04", race)
    with sqlite3.connect(database) as connection:
        for table in PARENTS:
            connection.execute(f'DELETE FROM "{table}"')
            connection.execute(
                f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                ("O", "1", *values, happyo),
            )
        for table, _ in CHILDREN:
            connection.execute(f'DELETE FROM "{table}"')
            connection.execute(
                f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?)', (*values, "010203")
            )


def _profile(offsets: tuple[int, ...] = (10, 2)) -> RaceDayOddsProfile:
    return RaceDayOddsProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=SPECS,
        offsets_minutes=offsets,
        late_tolerance_seconds=60,
    )


def _retriever(
    tmp_path: Path, start: datetime, offsets: tuple[int, ...] = (10, 2)
) -> tuple[RaceDayOddsRetriever, FakeRunner, FakeClock, Mock, Path]:
    database = tmp_path / "race.db"
    if not database.exists():
        _create_raw(database)
    clock = FakeClock(start)
    runner = FakeRunner(database, clock)
    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    retriever = RaceDayOddsRetriever(
        runner,  # type: ignore[arg-type]
        builder,
        OddsArchive(database),
        _profile(offsets),
        database,
        tmp_path / "runtime" / "historical-odds-progress.db",
        tmp_path / "runtime",
        clock=clock,
        sleeper=clock.sleep,
    )
    return retriever, runner, clock, builder, database


def _statuses(database: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(database) as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                "SELECT idRaceNum, offset_minutes, status FROM ARCHIVE_CAPTURE_LOG "
                "WHERE data_spec = '0B31' ORDER BY planned_at, idRaceNum"
            )
        ]


@pytest.fixture(autouse=True)
def _race_order() -> None:
    _race_numbers_by_order[:] = ["11", "11", "12", "12"]


def test_captures_wait_for_each_planned_time_and_run_in_order(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, clock, builder, database = _retriever(tmp_path, start)

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    assert _statuses(database) == [
        ("11", "10", "archived"),
        ("11", "2", "archived"),
        ("12", "10", "archived"),
        ("12", "2", "archived"),
    ]
    assert clock.sleeps[0] == pytest.approx(50 * 60)
    assert [call.kwargs["race_key"].race_number for call in builder.build.call_args_list] == [
        "11",
        "11",
        "12",
        "12",
    ]
    assert builder.build.call_args_list[0].args[0].realtime_data_specs == SPECS
    assert runner.observed_running == [{"running"}] * 4
    assert runner.observed_staging == [0, 0, 0, 0]
    assert result.summary == {
        "archived": 24,
        "no_data": 0,
        "failed": 0,
        "skipped_late": 0,
        "interrupted": 0,
    }
    assert not result.failed
    runner.assert_not_running.assert_called_once_with()
    with sqlite3.connect(database) as connection:
        first = connection.execute(
            "SELECT planned_at, started_at, completed_at FROM ARCHIVE_CAPTURE_LOG "
            "WHERE idRaceNum = '11' AND offset_minutes = '10' AND data_spec = '0B31'"
        ).fetchone()
    # The fake clock sleeps exactly to 05:50 UTC and the fake runner takes 2 seconds.
    assert first == (
        "2026-11-15T05:50:00+00:00",
        "2026-11-15T05:50:00+00:00",
        "2026-11-15T05:50:02+00:00",
    )


def test_restart_does_not_rerun_or_relog_finished_captures(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, _, _, _, database = _retriever(tmp_path, start)
    retriever.retrieve(RACE_DATE)
    with sqlite3.connect(database) as connection:
        before = connection.execute("SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG").fetchone()[0]

    _race_numbers_by_order[:] = []
    restarted, rerun, _, _, _ = _retriever(tmp_path, datetime(2026, 11, 15, 7, 0, tzinfo=UTC))
    result = restarted.retrieve(RACE_DATE)

    assert rerun.calls == []
    assert result.captures == ()
    with sqlite3.connect(database) as connection:
        after = connection.execute("SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG").fetchone()[0]
    assert after == before == 24


def test_hot_rollback_journal_does_not_block_locks_or_recovery(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_raw(database)
    child = (
        "import os, sqlite3, sys\n"
        "con = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
        "con.execute('PRAGMA cache_size=1')\n"
        "con.execute('BEGIN')\n"
        "con.executemany('INSERT INTO NL_RA_RACE (idRaceNum) VALUES (?)',"
        " [('x' * 500,) for _ in range(20000)])\n"
        "os._exit(0)\n"
    )
    subprocess.run([sys.executable, "-I", "-c", child, str(database)], check=True)
    assert database.with_name("race.db-journal").exists()
    ledger = tmp_path / "runtime" / "historical-odds-progress.db"

    with AcquisitionLock(database, ledger):
        pass

    assert not database.with_name("race.db-journal").exists()
    assert OddsArchive(database).running_capture_specs() == frozenset()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM NL_RA_RACE").fetchone()[0] == 2


def test_late_captures_are_skipped_without_running_jvlink(tmp_path: Path) -> None:
    _race_numbers_by_order[:] = ["11", "12", "12"]
    # Race 11 minus 10 minutes is 05:50 UTC; 05:51:01 exceeds the 60 second tolerance.
    start = datetime(2026, 11, 15, 5, 51, 1, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start)

    result = retriever.retrieve(RACE_DATE)

    assert _statuses(database)[0] == ("11", "10", "skipped_late")
    assert runner.calls == ["11", "12", "12"]
    assert result.summary["skipped_late"] == 6
    assert not result.failed


def test_jvlink_failure_is_recorded_and_later_captures_continue(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start)
    runner.fail_calls = {0}

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    assert _statuses(database)[0] == ("11", "10", "failed")
    assert _statuses(database)[1:] == [
        ("11", "2", "archived"),
        ("12", "10", "archived"),
        ("12", "2", "archived"),
    ]
    with sqlite3.connect(database) as connection:
        reason = connection.execute(
            "SELECT reason FROM ARCHIVE_CAPTURE_LOG WHERE status = 'failed' AND data_spec='0B36'"
        ).fetchone()[0]
    assert str(reason).startswith("jvlink_error: quarantined")
    assert result.summary["failed"] == 6
    assert result.failed


def test_persistence_failure_after_begin_stops_and_recovery_releases_the_lock(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start)
    archive = retriever._archive
    original = archive.finish_capture
    archive.finish_capture = Mock(side_effect=sqlite3.OperationalError("disk I/O error"))  # type: ignore[method-assign]

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11"]
    assert result.failed
    assert {status for _, _, status in _statuses(database)} == {"running"}
    with sqlite3.connect(database) as connection:
        staged = connection.execute('SELECT COUNT(*) FROM "RT_O6_ODDS_SANRENTAN"').fetchone()[0]
    assert staged == 1
    ledger = tmp_path / "runtime" / "historical-odds-progress.db"
    for allow_unresolved in (False, True):
        with (
            pytest.raises(AcquisitionBlocked, match="race-day odds capture"),
            AcquisitionLock(database, ledger, allow_unresolved=allow_unresolved),
        ):
            pytest.fail("unresolved capture accepted")

    archive.finish_capture = original  # type: ignore[method-assign]
    _race_numbers_by_order[:] = ["12", "12"]
    recovered, rerun, _, _, _ = _retriever(tmp_path, datetime(2026, 11, 15, 6, 0, tzinfo=UTC))
    second = recovered.retrieve(RACE_DATE)

    assert second.summary["interrupted"] == 6
    with sqlite3.connect(database) as connection:
        reason = connection.execute(
            "SELECT reason FROM ARCHIVE_CAPTURE_LOG WHERE status = 'interrupted' LIMIT 1"
        ).fetchone()[0]
    assert str(reason).startswith("recovery_quarantined: [")
    assert str(reason).endswith("; interrupted_recovery")
    assert list((tmp_path / "runtime" / "race-day-odds-quarantine").glob("startup-recovery-*.db"))
    assert rerun.calls == ["12", "12"]
    with AcquisitionLock(database, ledger):
        pass


def test_preexisting_staging_is_quarantined_before_reset(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start, offsets=(2,))
    _race_numbers_by_order[:] = ["11", "12"]
    _stage(database, "09", "11081540")

    retriever.retrieve(RACE_DATE)

    assert runner.observed_staging == [0, 0]
    quarantined = list(
        (tmp_path / "runtime" / "race-day-odds-quarantine").glob("*-pre-request-*.db")
    )
    assert len(quarantined) == 1
    with sqlite3.connect(quarantined[0]) as connection:
        race = connection.execute('SELECT idRaceNum FROM "RT_O3_ODDS_WIDE"').fetchone()[0]
    assert race == "09"
    with sqlite3.connect(database) as connection:
        reason = connection.execute(
            "SELECT reason FROM ARCHIVE_CAPTURE_LOG WHERE idRaceNum = '11' AND data_spec = '0B31'"
        ).fetchone()[0]
    assert str(reason).startswith("preexisting_staging: [")
    assert '"RT_O3_ODDS_WIDE": {"rows": 1' in str(reason)
    assert str(reason).endswith("; capture_archive_committed")


def test_race_day_only_captures_never_mark_historical_odds_as_archived(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, _, _, _, database = _retriever(tmp_path, start)

    retriever.retrieve(RACE_DATE)

    with sqlite3.connect(database) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "ARCHIVE_O1_ODDS_TANFUKUWAKU" not in tables
    assert "ARCHIVE_O2_ODDS_UMAREN" not in tables
    assert "ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU" in tables
    historical = JVLinkProfile(
        False,
        False,
        True,
        frozenset(),
        frozenset(),
        frozenset({"0B41", "0B42"}),
        race_start_date=date(2026, 1, 4),
    )
    snapshot = read_raw_snapshot(
        database, historical, HistoricalOddsBatch(2026, 2026, 1), date(2026, 11, 30)
    )
    assert len(snapshot.races) == 2
    assert snapshot.counts == {}


def test_recovery_keeps_staging_when_jvlink_may_still_be_running(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start)
    archive = retriever._archive
    archive.begin_capture(
        "stale",
        RaceKey(RACE_DATE, "05", "05", "04", "11"),
        SPECS,
        scheduled_start_at=datetime(2026, 11, 15, 6, 0, tzinfo=UTC),
        offset_minutes=10,
        planned_at=datetime(2026, 11, 15, 5, 50, tzinfo=UTC),
    )
    _stage(database, "11", "11151450")
    runner.assert_not_running.side_effect = AcquisitionBlocked("JVLinkToSQLite is running")

    with pytest.raises(AcquisitionBlocked, match="running"):
        retriever.retrieve(RACE_DATE)

    assert runner.calls == []
    assert {status for _, _, status in _statuses(database)} == {"running"}
    with sqlite3.connect(database) as connection:
        staged = connection.execute('SELECT COUNT(*) FROM "RT_O3_ODDS_WIDE"').fetchone()[0]
    assert staged == 1
    assert not (tmp_path / "runtime" / "race-day-odds-quarantine").exists()


def test_fail_closed_report_keeps_specs_that_were_already_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, _, _ = _retriever(tmp_path, start)
    original = odds_archive._reset_capture_spec

    def fail_on_0b33(connection: sqlite3.Connection, spec: str) -> None:
        if spec == "0B33":
            raise sqlite3.OperationalError("disk I/O error")
        original(connection, spec)

    monkeypatch.setattr(odds_archive, "_reset_capture_spec", fail_on_0b33)

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11"]
    report = result.captures[0].results
    assert {spec: report[spec].status for spec in ("0B31", "0B32")} == {
        "0B31": "archived",
        "0B32": "archived",
    }
    assert {report[spec].reason for spec in ("0B33", "0B34", "0B35", "0B36")} == {
        "capture_incomplete"
    }
    assert result.summary["archived"] == 2
    assert result.summary["failed"] == 4


def test_existing_historical_archives_are_left_unchanged(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, _, _, _, database = _retriever(tmp_path, start)
    with sqlite3.connect(database) as connection:
        for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN"):
            connection.execute(f'CREATE TABLE "{table}" (race TEXT, HappyoTime TEXT, Odds TEXT)')
            connection.execute(f'INSERT INTO "{table}" VALUES (?, ?, ?)', ("r", "1", "2"))

    def snapshot() -> list[list[tuple[str, ...]]]:
        with sqlite3.connect(database) as connection:
            return [
                [tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
                for table in ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN")
            ]

    before = snapshot()
    retriever.retrieve(RACE_DATE)

    assert snapshot() == before == [[("r", "1", "2")], [("r", "1", "2")]]
