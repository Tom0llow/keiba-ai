"""Tests for the race-day odds capture loop with fake JV-Link and clock boundaries."""

import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
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
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import (
    HistoricalOddsBatch,
    JVLinkProfile,
    RaceDayOddsProfile,
)
from jra_van_retriever.progress.raw_observation import read_raw_snapshot
from jra_van_retriever.workflows.race_day_odds import (
    RaceDayOddsRetriever,
    RaceDayOddsSetupError,
)

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
        self.failure_message = "JV-Link failed"
        self.failure_returncode: int | None = 1
        self.failure_api_results: dict[str, tuple[str, int]] = {}
        self.normal_api_results: dict[str, tuple[str, int]] = {}
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
            raise JVLinkToSQLiteError(
                self.failure_message,
                returncode=self.failure_returncode,
                api_results=self.failure_api_results,
            )
        return JVLinkExecutionResult(
            {},
            fatal_specs=frozenset(self.normal_api_results),
            api_results=self.normal_api_results,
            process_returncode=0,
        )


_race_numbers_by_order: list[str] = []


class FakeTCRunner:
    """Answer each 0B14 time-change check; by default JV-Link reports no data."""

    def __init__(self, database: Path, clock: FakeClock) -> None:
        self.database = database
        self.clock = clock
        self.calls: list[datetime] = []
        # Seconds each check takes on the fake clock.
        self.duration_seconds = 0
        # Each call pops the next response: a list of TC rows, "no_data", or an exception.
        self.responses: list[object] = []

    def execute(self, setting: Path, *, skip_last_modified_update: bool = False) -> object:
        assert skip_last_modified_update is True
        assert setting.name == "race-day-tc.xml"
        self.calls.append(self.clock.now)
        self.clock.now += timedelta(seconds=self.duration_seconds)
        response = self.responses.pop(0) if self.responses else "no_data"
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, tuple):
            # Write the TC rows, then fail the way a timed-out JVLinkToSQLite run does.
            rows, error = response
            self._write(rows)
            raise error
        if response == "no_data":
            return JVLinkExecutionResult(
                {"0B14": -1},
                no_data_specs=frozenset({"0B14"}),
                api_results={"0B14": ("JVRTOpen", -1)},
                process_returncode=0,
            )
        if isinstance(response, JVLinkExecutionResult):
            return response
        assert isinstance(response, list)
        self._write(response)
        return JVLinkExecutionResult(
            {"0B14": 0}, api_results={"0B14": ("JVRTOpen", 0)}, process_returncode=0
        )

    def _write(self, response: list[dict[str, str]]) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS RT_TC_INFO ("
                + ", ".join(f'"{name}" TEXT' for name in TC_COLUMNS)
                + ")"
            )
            for row in response:
                connection.execute(
                    "INSERT INTO RT_TC_INFO VALUES (" + ", ".join("?" for _ in TC_COLUMNS) + ")",
                    tuple(row[name] for name in TC_COLUMNS),
                )


TC_COLUMNS = (
    "headRecordSpec",
    "headDataKubun",
    "headMakeDate",
    "idYear",
    "idMonthDay",
    "idJyoCD",
    "idKaiji",
    "idNichiji",
    "idRaceNum",
    "HappyoTime",
    "TCInfoAfterJi",
    "TCInfoAfterFun",
    "TCInfoBeforeJi",
    "TCInfoBeforeFun",
)


def _tc_row(
    race: str, before: str, after: str, happyo: str, make: str = "20261115"
) -> dict[str, str]:
    return {
        "headRecordSpec": "TC",
        "headDataKubun": "1",
        "headMakeDate": make,
        "idYear": "2026",
        "idMonthDay": "1115",
        "idJyoCD": "05",
        "idKaiji": "05",
        "idNichiji": "04",
        "idRaceNum": race,
        "HappyoTime": happyo,
        "TCInfoAfterJi": after[:2],
        "TCInfoAfterFun": after[2:],
        "TCInfoBeforeJi": before[:2],
        "TCInfoBeforeFun": before[2:],
    }


class _RoutingBuilder:
    """Send the 0B14 date-key build straight to the real builder.

    The capture/prediction builds keep going through the recorded Mock, so existing
    assertions about those builds are unchanged.
    """

    def __init__(self, recorded: Mock, real: JVLinkSettingBuilder) -> None:
        self.recorded = recorded
        self.real = real
        self.date_builds = 0

    def build(self, profile: object, destination: Path, **kwargs: object) -> Path:
        if "race_date" in kwargs:
            self.date_builds += 1
            return self.real.build(profile, destination, **kwargs)  # type: ignore[arg-type]
        return cast(Path, self.recorded.build(profile, destination, **kwargs))


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


def _profile(offsets: tuple[int, ...] = (10, 2), lead: int = 40) -> RaceDayOddsProfile:
    return RaceDayOddsProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=SPECS,
        offsets_minutes=offsets,
        late_tolerance_seconds=60,
        tc_check_lead_seconds=lead,
    )


def _retriever(
    tmp_path: Path, start: datetime, offsets: tuple[int, ...] = (10, 2), lead: int = 40
) -> tuple[RaceDayOddsRetriever, FakeRunner, FakeClock, Mock, Path]:
    database = tmp_path / "race.db"
    if not database.exists():
        _create_raw(database)
    clock = FakeClock(start)
    runner = FakeRunner(database, clock)
    seed = tmp_path / "seed.xml"
    if not seed.exists():
        _write_seed(seed)
    real_builder = JVLinkSettingBuilder(seed)
    builder = Mock()
    builder.observed_log_rows = []

    def build(profile: RaceDayOddsProfile, destination: Path, **kwargs: object) -> Path:
        builder.observed_log_rows.append(_log_rows(database))
        return real_builder.build(profile, destination, **kwargs)  # type: ignore[arg-type]

    builder.build.side_effect = build
    tc_runner = FakeTCRunner(database, clock)
    builder.tc_runner = tc_runner
    retriever = RaceDayOddsRetriever(
        runner,  # type: ignore[arg-type]
        _RoutingBuilder(builder, real_builder),  # type: ignore[arg-type]
        OddsArchive(database),
        _profile(offsets, lead),
        database,
        tmp_path / "runtime" / "historical-odds-progress.db",
        tmp_path / "runtime",
        clock=clock,
        sleeper=clock.sleep,
        tc_runner=tc_runner,  # type: ignore[arg-type]
    )
    return retriever, runner, clock, builder, database


def _write_seed(path: Path, *, race_key: bool = True) -> None:
    key = (
        "<JVRaceKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate><JyoCD>01</JyoCD>"
        "<Kaiji>01</Kaiji><Nichiji>01</Nichiji><RaceNum>01</RaceNum></JVRaceKey>"
        if race_key
        else ""
    )
    realtime = "".join(
        f"<JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>{spec}</DataSpec>{key}"
        "</JVDataSpecSetting>"
        for spec in sorted(SPECS)
    ) + (
        "<JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>0B14</DataSpec>"
        "<JVKaisaiDateKey><KaisaiDate>2026-03-02T00:00:00+09:00</KaisaiDate></JVKaisaiDateKey>"
        "</JVDataSpecSetting>"
    )
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><JVLinkToSQLiteSetting><Details>'
        "<JVNormalUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>"
        "</DataSpecSettings></JVNormalUpdateSetting>"
        "<JVSetupDataUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>"
        "</DataSpecSettings></JVSetupDataUpdateSetting>"
        "<JVRealTimeDataUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>"
        f"{realtime}</DataSpecSettings></JVRealTimeDataUpdateSetting>"
        "</Details></JVLinkToSQLiteSetting>",
        encoding="utf-8",
    )


def _log_rows(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        if (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ARCHIVE_CAPTURE_LOG'"
            ).fetchone()
            is None
        ):
            return 0
        return int(connection.execute("SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG").fetchone()[0])


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
    # The 0B14 check runs 40 s (tc_check_lead_seconds) before the first time point.
    assert clock.sleeps[0] == pytest.approx(50 * 60 - 40)
    assert clock.sleeps[1] == pytest.approx(40)
    assert builder.tc_runner.calls[0] == start + timedelta(minutes=50) - timedelta(seconds=40)
    # The first build is the startup check; each capture then builds before it is logged.
    assert [call.kwargs["race_key"].race_number for call in builder.build.call_args_list] == [
        "11",
        "11",
        "11",
        "12",
        "12",
    ]
    assert builder.observed_log_rows == [0, 0, 6, 12, 18]
    assert builder.build.call_args_list[0].args[0].realtime_data_specs == SPECS
    assert runner.observed_running == [{"running"}] * 4
    assert runner.observed_staging == [0, 0, 0, 0]
    assert result.summary == {
        "archived": 24,
        "no_data": 0,
        "failed": 0,
        "held": 0,
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


@pytest.mark.parametrize(
    ("message", "process_returncode"),
    [
        ("JV-Link failed", 1),
        ("JVLinkToSQLite timed out after 120 seconds", None),
    ],
    ids=["process_failure", "timeout"],
)
def test_jvlink_failure_is_recorded_and_later_captures_continue(
    tmp_path: Path, message: str, process_returncode: int | None
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start)
    runner.fail_calls = {0}
    runner.failure_message = message
    runner.failure_returncode = process_returncode

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
        running = connection.execute(
            "SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG WHERE status = 'running'"
        ).fetchone()[0]
        returncode = connection.execute(
            "SELECT process_returncode FROM ARCHIVE_CAPTURE_LOG "
            "WHERE status = 'failed' AND data_spec = '0B36'"
        ).fetchone()[0]
    assert str(reason).startswith("jvlink_error: quarantined")
    assert running == 0
    # The capture log stores every column as TEXT.
    assert returncode == (None if process_returncode is None else str(process_returncode))
    assert result.summary["failed"] == 6
    assert result.failed
    assert result.stop_reason is None


@pytest.mark.parametrize(
    ("failure", "failure_returncode", "api_results", "expected_failed", "stop_reason"),
    [
        (
            False,
            None,
            {"0B31": ("JVOpen", -303)},
            1,
            "JV-Link returned 0B31 JVOpen -303; the JVLinkAgent service may have stopped; "
            "remaining captures were not run",
        ),
        (
            True,
            1,
            {"0B32": ("JVOpen", -211)},
            6,
            "JV-Link returned 0B32 JVOpen -211; the JVLinkAgent service may have stopped; "
            "remaining captures were not run",
        ),
        (
            True,
            None,
            {spec: ("JVOpen", -303) for spec in ("0B34", "0B33", "0B32", "0B31")},
            6,
            "JV-Link returned 0B31 JVOpen -303, 0B32 JVOpen -303, 0B33 JVOpen -303, "
            "0B34 JVOpen -303; the JVLinkAgent service may have stopped; "
            "remaining captures were not run",
        ),
    ],
    ids=["execution_result", "execution_error", "execution_timeout"],
)
def test_jvlink_agent_down_stops_after_recording_the_current_capture(
    tmp_path: Path,
    failure: bool,
    failure_returncode: int | None,
    api_results: dict[str, tuple[str, int]],
    expected_failed: int,
    stop_reason: str,
) -> None:
    retriever, runner, _, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    )
    if failure:
        runner.fail_calls = {0}
        runner.failure_returncode = failure_returncode
        if failure_returncode is None:
            runner.failure_message = "JVLinkToSQLite timed out after 120.0 seconds"
        runner.failure_api_results = api_results
    else:
        runner.normal_api_results = api_results

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11"]
    assert len(result.captures) == 1
    assert result.summary["failed"] == expected_failed
    assert result.stop_reason == stop_reason
    assert _statuses(database) == [("11", "10", "failed")]
    with sqlite3.connect(database) as connection:
        failed_reasons = list(
            connection.execute("SELECT reason FROM ARCHIVE_CAPTURE_LOG WHERE status = 'failed'")
        )
        running = connection.execute(
            "SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG WHERE status = 'running'"
        ).fetchone()[0]
    assert failed_reasons
    assert all(str(reason[0]).startswith("jvlink_error") for reason in failed_reasons)
    assert running == 0


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
    assert result.stop_reason is None
    assert {status for _, _, status in _statuses(database)} == {"running"}
    with sqlite3.connect(database) as connection:
        staged = connection.execute('SELECT COUNT(*) FROM "RT_O6_ODDS_SANRENTAN"').fetchone()[0]
    assert staged == 1
    ledger = tmp_path / "runtime" / "historical-odds-progress.db"
    for allow_unresolved in (False, True):
        with (
            pytest.raises(
                AcquisitionBlocked,
                match=(
                    r"unresolved race-day odds capture; "
                    r"run --retrieve --mode=race-day-odds --recover first"
                ),
            ),
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


@pytest.mark.parametrize("seed_state", ["malformed", "missing_race_key", "missing_file"])
def test_invalid_setting_stops_before_any_capture_is_recorded(
    tmp_path: Path, seed_state: str
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, clock, _, database = _retriever(tmp_path, start)
    seed = tmp_path / "seed.xml"
    if seed_state == "malformed":
        seed.write_text("<JVLinkToSQLiteSetting><Details>", encoding="utf-8")
    elif seed_state == "missing_race_key":
        _write_seed(seed, race_key=False)
    else:
        seed.unlink()

    with pytest.raises(RaceDayOddsSetupError, match="execution setting is invalid"):
        retriever.retrieve(RACE_DATE)

    assert runner.calls == []
    assert clock.sleeps == []
    assert _log_rows(database) == 0


@pytest.mark.parametrize(
    "error",
    [ValueError("setting is missing data specs: 0B36"), ET.ParseError("not well-formed")],
    ids=["value_error", "parse_error"],
)
def test_setting_error_during_the_day_records_nothing_and_later_captures_continue(
    tmp_path: Path, error: Exception
) -> None:
    _race_numbers_by_order[:] = ["11", "12", "12"]
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, builder, database = _retriever(tmp_path, start)
    build = builder.build.side_effect

    def fail_second_capture(
        profile: RaceDayOddsProfile, destination: Path, **kwargs: object
    ) -> Path:
        # Call 0 is the startup check, call 1 the first capture, call 2 the second.
        if builder.build.call_count == 3:
            raise error
        return build(profile, destination, **kwargs)  # type: ignore[no-any-return]

    builder.build.side_effect = fail_second_capture

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "12", "12"]
    assert _statuses(database) == [
        ("11", "10", "archived"),
        ("12", "10", "archived"),
        ("12", "2", "archived"),
    ]
    assert OddsArchive(database).running_capture_specs() == frozenset()
    failed = result.captures[1]
    assert (failed.race_key.race_number, failed.offset_minutes) == ("11", 2)
    assert {(item.status, item.reason) for item in failed.results.values()} == {
        ("failed", "capture_not_recorded")
    }
    assert result.summary["failed"] == 6
    assert result.summary["archived"] == 18


def test_recover_only_marks_unfinished_captures_interrupted_without_capturing(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, _, _, _, database = _retriever(tmp_path, start)
    archive = retriever._archive
    archive.finish_capture = Mock(side_effect=sqlite3.OperationalError("disk I/O error"))  # type: ignore[method-assign]
    retriever.retrieve(RACE_DATE)
    assert {status for _, _, status in _statuses(database)} == {"running"}

    recovering, runner, clock, builder, _ = _retriever(
        tmp_path, datetime(2026, 11, 15, 9, 0, tzinfo=UTC)
    )

    assert recovering.recover() == 6
    assert recovering.recover() == 0
    assert runner.calls == []
    assert clock.sleeps == []
    builder.build.assert_not_called()
    runner.assert_not_running.assert_called()
    assert {status for _, _, status in _statuses(database)} == {"interrupted"}
    with sqlite3.connect(database) as connection:
        staged = connection.execute('SELECT COUNT(*) FROM "RT_O6_ODDS_SANRENTAN"').fetchone()[0]
    assert staged == 0
    ledger = tmp_path / "runtime" / "historical-odds-progress.db"
    with AcquisitionLock(database, ledger):
        pass


def _tc_checks(database: Path) -> list[tuple[str, str, str, str]]:
    with sqlite3.connect(database) as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in connection.execute(
                "SELECT time_point_at, result, tc_rows, adopted_starts FROM ARCHIVE_TC_CHECK_LOG "
                "ORDER BY rowid"
            )
        ]


def _table_exists(database: Path, table: str) -> bool:
    with sqlite3.connect(database) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            is not None
        )


def test_a_delay_replans_unfinished_captures_in_time_order_and_records_the_check(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, builder, database = _retriever(tmp_path, start)
    # Race 11 is delayed 15:00 -> 15:25, so its captures move behind race 12's first one.
    builder.tc_runner.responses = [[_tc_row("11", "1500", "1525", "11151449")]]
    _race_numbers_by_order[:] = ["11", "12", "11", "12"]

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "12", "11", "12"]
    assert result.summary["archived"] == 24
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT idRaceNum, offset_minutes, scheduled_start_at, planned_at, effective_start_at "
            "FROM ARCHIVE_CAPTURE_LOG WHERE data_spec = '0B31' ORDER BY planned_at"
        ).fetchall()
        archived_tc = connection.execute("SELECT COUNT(*) FROM ARCHIVE_TC_INFO").fetchone()[0]
    assert rows == [
        (
            "11",
            "10",
            "2026-11-15T15:00:00+09:00",
            "2026-11-15T06:15:00+00:00",
            "2026-11-15T15:25:00+09:00",
        ),
        ("12", "10", "2026-11-15T15:30:00+09:00", "2026-11-15T06:20:00+00:00", None),
        (
            "11",
            "2",
            "2026-11-15T15:00:00+09:00",
            "2026-11-15T06:23:00+00:00",
            "2026-11-15T15:25:00+09:00",
        ),
        ("12", "2", "2026-11-15T15:30:00+09:00", "2026-11-15T06:28:00+00:00", None),
    ]
    assert archived_tc == 1
    checks = _tc_checks(database)
    assert checks[0][:3] == ("2026-11-15T05:50:00+00:00", "ok", "1")
    assert '"2026111505050411"' in checks[0][3]
    assert "15:25:00+09:00" in checks[0][3]
    # Each later check is a no-data response; every check is made 40 s before its time point.
    assert all(check[1] == "no_data" for check in checks[1:])
    assert builder.tc_runner.calls[0] == datetime(2026, 11, 15, 5, 49, 20, tzinfo=UTC)
    # The 0B14 response tables never stay in the raw database.
    assert not _table_exists(database, "RT_TC_INFO")


def test_a_stale_tc_response_from_an_earlier_run_is_not_read_as_this_one(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, builder, database = _retriever(tmp_path, start)
    # The first check answers with race 12's one-minute delay only.
    builder.tc_runner.responses = [[_tc_row("12", "1530", "1531", "11150820")]]
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE RT_TC_INFO (" + ", ".join(f'"{name}" TEXT' for name in TC_COLUMNS) + ")"
        )
        row = _tc_row("11", "1500", "1525", "11151449")
        connection.execute(
            "INSERT INTO RT_TC_INFO VALUES (" + ", ".join("?" for _ in TC_COLUMNS) + ")",
            tuple(row[name] for name in TC_COLUMNS),
        )

    retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    with sqlite3.connect(database) as connection:
        moved = connection.execute(
            "SELECT DISTINCT idRaceNum FROM ARCHIVE_CAPTURE_LOG "
            "WHERE effective_start_at IS NOT NULL"
        ).fetchall()
        archived = connection.execute("SELECT idRaceNum FROM ARCHIVE_TC_INFO").fetchall()
    # The leftover race 11 row was never read as this response.
    assert moved == [("12",)]
    assert archived == [("12",)]
    assert _tc_checks(database)[0][1:3] == ("ok", "1")
    assert not _table_exists(database, "RT_TC_INFO")


def test_a_check_with_no_time_left_is_skipped_and_never_delays_the_capture(
    tmp_path: Path,
) -> None:
    # Start inside the first time point's 40 s lead window.
    start = datetime(2026, 11, 15, 5, 49, 50, tzinfo=UTC)
    retriever, runner, clock, builder, database = _retriever(tmp_path, start)

    retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    checks = _tc_checks(database)
    assert checks[0][:2] == ("2026-11-15T05:50:00+00:00", "skipped")
    assert all(check[1] == "no_data" for check in checks[1:])
    assert clock.sleeps[0] == pytest.approx(10)
    assert builder.tc_runner.calls
    assert builder.tc_runner.calls[0] > start


def test_a_failed_check_keeps_the_plan_and_an_agent_stop_stops_the_day(tmp_path: Path) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, builder, database = _retriever(tmp_path, start)
    builder.tc_runner.responses = [JVLinkToSQLiteError("boom", returncode=1)]

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    assert result.stop_reason is None
    assert _tc_checks(database)[0][1] == "failed"

    stopped = tmp_path / "stopped"
    stopped.mkdir()
    retriever, runner, _, builder, database = _retriever(stopped, start)
    builder.tc_runner.responses = [
        JVLinkExecutionResult(
            {"0B14": -303},
            fatal_specs=frozenset({"0B14"}),
            api_results={"0B14": ("JVRTOpen", -303)},
            process_returncode=1,
        )
    ]

    result = retriever.retrieve(RACE_DATE)

    assert runner.calls == []
    assert result.stop_reason is not None
    assert "0B14 JVRTOpen -303" in result.stop_reason
    assert _tc_checks(database)[0][1] == "agent_down"


def test_a_restart_restores_the_accumulated_changes_before_the_first_check(
    tmp_path: Path,
) -> None:
    # Started inside the first time point's lead window, so the first check is skipped
    # and only the startup restore can move race 11's first capture.
    start = datetime(2026, 11, 15, 5, 49, 50, tzinfo=UTC)
    retriever, runner, _, _, database = _retriever(tmp_path, start)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ARCHIVE_TC_INFO ("
            + ", ".join(f'"{name}" TEXT' for name in TC_COLUMNS)
            + ")"
        )
        row = _tc_row("11", "1500", "1505", "11150820")
        connection.execute(
            "INSERT INTO ARCHIVE_TC_INFO VALUES (" + ", ".join("?" for _ in TC_COLUMNS) + ")",
            tuple(row[name] for name in TC_COLUMNS),
        )

    retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    with sqlite3.connect(database) as connection:
        planned = connection.execute(
            "SELECT planned_at, status FROM ARCHIVE_CAPTURE_LOG WHERE idRaceNum = '11' "
            "AND data_spec = '0B31' ORDER BY planned_at"
        ).fetchall()
    assert planned == [
        ("2026-11-15T05:55:00+00:00", "archived"),
        ("2026-11-15T06:03:00+00:00", "archived"),
    ]


def test_tc_rows_left_by_a_failed_check_are_not_counted_by_the_next_check(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
    retriever, runner, _, builder, database = _retriever(tmp_path, start)
    builder.tc_runner.responses = [
        ([_tc_row("11", "1500", "1525", "11151449")], JVLinkToSQLiteError("timed out")),
    ]

    retriever.retrieve(RACE_DATE)

    assert runner.calls == ["11", "11", "12", "12"]
    checks = _tc_checks(database)
    assert [check[1] for check in checks] == ["failed", "no_data", "no_data", "no_data"]
    with sqlite3.connect(database) as connection:
        moved = connection.execute(
            "SELECT COUNT(*) FROM ARCHIVE_CAPTURE_LOG WHERE effective_start_at IS NOT NULL"
        ).fetchone()[0]
    assert moved == 0
    assert not _table_exists(database, "RT_TC_INFO")
    assert not _table_exists(database, "ARCHIVE_TC_INFO")


def test_a_skipped_check_does_not_skip_a_later_time_point_that_can_still_be_checked(
    tmp_path: Path,
) -> None:
    # With a 90 s lead, race 11's 10- and 9-minute points (05:50, 05:51) share a window.
    start = datetime(2026, 11, 15, 5, 49, tzinfo=UTC)
    retriever, _, _, builder, database = _retriever(tmp_path, start, offsets=(10, 9), lead=90)

    retriever.retrieve(RACE_DATE)

    results = {check[0]: check[1] for check in _tc_checks(database)}
    # 05:50 had no time left, but 05:51's check (05:49:30) still ran before 05:50's capture.
    assert results["2026-11-15T05:50:00+00:00"] == "skipped"
    assert results["2026-11-15T05:51:00+00:00"] == "no_data"
    assert builder.tc_runner.calls[0] == datetime(2026, 11, 15, 5, 49, 30, tzinfo=UTC)


def test_a_later_check_that_could_overrun_never_delays_the_next_capture(tmp_path: Path) -> None:
    # Lead 70 s: 05:51's check would start at 05:49:50 and could last 20 s, past 05:50.
    start = datetime(2026, 11, 15, 5, 48, 55, tzinfo=UTC)
    retriever, _, _, builder, database = _retriever(tmp_path, start, offsets=(10, 9), lead=70)
    builder.tc_runner.duration_seconds = 20

    retriever.retrieve(RACE_DATE)

    with sqlite3.connect(database) as connection:
        started = connection.execute(
            "SELECT started_at FROM ARCHIVE_CAPTURE_LOG WHERE idRaceNum = '11' "
            "AND offset_minutes = '10' AND data_spec = '0B31'"
        ).fetchone()[0]
    assert started == "2026-11-15T05:50:00+00:00"
    assert all(
        call >= datetime(2026, 11, 15, 5, 50, tzinfo=UTC) for call in builder.tc_runner.calls
    )
