"""Tests for the race-day 0B41/0B42 prediction fetch (ADR-032 Amendment 2, ADR-037)."""

import sqlite3
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkProfile, RaceDayOddsProfile
from jra_van_retriever.workflows.race_day_odds import (
    RaceDayOddsRetriever,
    RaceDayOddsSetupError,
)
from jra_van_retriever.workflows.race_day_odds_plan import classify_capture

RACE_DATE = date(2026, 11, 15)
CAPTURE_SPECS = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"})
PREDICTION_SPECS = frozenset({"0B41", "0B42"})
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
# 15:00 and 15:30 JST starts are 06:00 and 06:30 UTC; freeze is five minutes earlier.
STARTS = {"11": "1500", "12": "1530"}


class FakeClock:
    """Advance only when the workflow sleeps or the runner executes."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeRunner:
    """Write the staging rows that JVLinkToSQLite writes for the setting's race."""

    def __init__(self, database: Path, clock: FakeClock) -> None:
        self.database = database
        self.clock = clock
        self.calls: list[tuple[str, str]] = []
        self.staging_before: list[int] = []
        self.fail: set[tuple[str, str]] = set()
        self.foreign_row: set[tuple[str, str]] = set()
        self.empty: dict[tuple[str, str], frozenset[str]] = {}
        self.assert_not_running = Mock()

    def execute(self, setting: Path, *, skip_last_modified_update: bool = False) -> object:
        assert skip_last_modified_update is True
        kind = "prediction" if setting.name == "race-day-prediction.xml" else "capture"
        race = next(
            spec.findtext("JVRaceKey/RaceNum") or ""
            for spec in ET.parse(setting).getroot().iter("JVDataSpecSetting")
            if spec.findtext("IsEnabled") == "true"
        )
        self.calls.append((race, kind))
        self.staging_before.append(_staging_rows(self.database))
        if (race, kind) in self.empty:
            self.clock.now += timedelta(seconds=2)
            return JVLinkExecutionResult(
                {}, no_data_specs=self.empty[(race, kind)], process_returncode=0
            )
        if kind == "prediction":
            _stage_series(self.database, race, foreign=(race, kind) in self.foreign_row)
        else:
            _stage_capture(self.database, race)
        self.clock.now += timedelta(seconds=2)
        if (race, kind) in self.fail:
            raise JVLinkToSQLiteError("JV-Link failed", returncode=1)
        return JVLinkExecutionResult({}, process_returncode=0)


def _key(race: str) -> tuple[str, ...]:
    return ("2026", "1115", "05", "05", "04", race)


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
                (*_key(race), "2", hasso),
            )
        columns = ", ".join(
            f'"{name}" TEXT' for name in ("headRecordSpec", "headDataKubun", *KEYS, "HappyoTime")
        )
        for table in PARENTS:
            connection.execute(f'CREATE TABLE "{table}" ({columns})')
        for table, prefix in CHILDREN:
            child = ", ".join(f'"{name}" TEXT' for name in (*KEYS, f"{prefix}Kumi"))
            connection.execute(f'CREATE TABLE "{table}" ({child})')


def _series_times(race: str) -> list[str]:
    """Return the five-minute 0B41 grid up to six minutes before the start (ADR-037)."""
    start = datetime.strptime(f"2026{STARTS[race]}", "%Y%H%M")
    return [f"1115{start - timedelta(minutes=minutes):%H%M}" for minutes in (16, 11, 6)]


def _stage_series(database: Path, race: str, *, foreign: bool = False) -> None:
    with sqlite3.connect(database) as connection:
        for table, record in (("RT_O1_ODDS_TANFUKUWAKU", "O1"), ("RT_O2_ODDS_UMAREN", "O2")):
            for happyo in _series_times(race):
                connection.execute(
                    f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (record, "1", *_key(race), happyo),
                )
            if foreign:
                connection.execute(
                    f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (record, "1", *_key("09"), "11151400"),
                )


def _stage_capture(database: Path, race: str) -> None:
    with sqlite3.connect(database) as connection:
        for table in PARENTS:
            connection.execute(
                f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                ("O", "1", *_key(race), "11151455"),
            )
        for table, _ in CHILDREN:
            connection.execute(
                f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?)', (*_key(race), "010203")
            )


def _staging_rows(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        return sum(
            int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in (*PARENTS, *(table for table, _ in CHILDREN))
        )


def _write_seed(path: Path, specs: frozenset[str]) -> None:
    key = (
        "<JVRaceKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate><JyoCD>01</JyoCD>"
        "<Kaiji>01</Kaiji><Nichiji>01</Nichiji><RaceNum>01</RaceNum></JVRaceKey>"
    )
    realtime = "".join(
        f"<JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>{spec}</DataSpec>{key}"
        "</JVDataSpecSetting>"
        for spec in sorted(specs)
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


def _profiles(
    offsets: tuple[int, ...] = (5, 2), prediction_offset: int | None = 5
) -> tuple[RaceDayOddsProfile, JVLinkProfile]:
    common = {
        "normal_update": False,
        "setup_update": False,
        "realtime_update": True,
        "normal_data_specs": frozenset(),
        "setup_data_specs": frozenset(),
    }
    capture = RaceDayOddsProfile(
        **common,  # type: ignore[arg-type]
        realtime_data_specs=CAPTURE_SPECS,
        offsets_minutes=offsets,
        late_tolerance_seconds=60,
        prediction_offset_minutes=prediction_offset,
    )
    return capture, JVLinkProfile(**common, realtime_data_specs=PREDICTION_SPECS)  # type: ignore[arg-type]


def _retriever(
    tmp_path: Path,
    start: datetime,
    *,
    offsets: tuple[int, ...] = (5, 2),
    seed_specs: frozenset[str] = CAPTURE_SPECS | PREDICTION_SPECS,
) -> tuple[RaceDayOddsRetriever, FakeRunner, FakeClock, Path]:
    database = tmp_path / "race.db"
    if not database.exists():
        _create_raw(database)
    clock = FakeClock(start)
    runner = FakeRunner(database, clock)
    seed = tmp_path / "seed.xml"
    _write_seed(seed, seed_specs)
    capture, prediction = _profiles(offsets)
    retriever = RaceDayOddsRetriever(
        runner,  # type: ignore[arg-type]
        JVLinkSettingBuilder(seed),
        OddsArchive(database),
        capture,
        database,
        tmp_path / "runtime" / "historical-odds-progress.db",
        tmp_path / "runtime",
        clock=clock,
        sleeper=clock.sleep,
        prediction_profile=prediction,
    )
    return retriever, runner, clock, database


class Publisher:
    """Record each published race, the staging it saw, and whether the lock was held."""

    def __init__(self, tmp_path: Path, database: Path) -> None:
        self.tmp_path = tmp_path
        self.database = database
        self.races: list[str] = []
        self.locked: list[bool] = []
        self.staging: list[int] = []
        self.errors: list[BaseException] = []

    def __call__(self, race_key: RaceKey) -> None:
        self.races.append(race_key.race_number)
        self.staging.append(_staging_rows(self.database))
        lock = AcquisitionLock(
            self.database, self.tmp_path / "runtime" / "historical-odds-progress.db"
        )
        try:
            with lock:
                self.locked.append(False)
        except AcquisitionBlocked:
            self.locked.append(True)
        if self.errors:
            raise self.errors.pop(0)


def _log(database: Path, *, specs: frozenset[str] = PREDICTION_SPECS) -> list[tuple[object, ...]]:
    placeholders = ", ".join("?" for _ in specs)
    with sqlite3.connect(database) as connection:
        return list(
            connection.execute(
                "SELECT idRaceNum, data_spec, offset_minutes, status, reason, headDataKubun, "
                "HappyoTime, observed_rows, inserted_rows, planned_at, started_at "
                f"FROM ARCHIVE_CAPTURE_LOG WHERE data_spec IN ({placeholders}) "
                "ORDER BY planned_at, idRaceNum, data_spec",
                sorted(specs),
            )
        )


def _archived(database: Path, table: str, race: str) -> int:
    with sqlite3.connect(database) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if exists is None:
            return 0
        return int(
            connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE idRaceNum = ?', (race,)
            ).fetchone()[0]
        )


def test_prediction_fetch_runs_first_at_freeze_archives_the_series_and_publishes(
    tmp_path: Path,
) -> None:
    retriever, runner, _, database = _retriever(tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC))
    publisher = Publisher(tmp_path, database)

    result = retriever.retrieve(RACE_DATE, publisher=publisher)

    assert runner.calls == [
        ("11", "prediction"),
        ("11", "capture"),
        ("11", "capture"),
        ("12", "prediction"),
        ("12", "capture"),
        ("12", "capture"),
    ]
    # Staging is empty before each run and after each prediction fetch.
    assert runner.staging_before == [0] * 6
    assert publisher.races == ["11", "12"]
    assert publisher.locked == [True, True]
    assert publisher.staging == [0, 0]
    assert not result.failed
    # Once at startup recovery, then before each prediction fetch.
    assert runner.assert_not_running.call_count == 3
    for race in ("11", "12"):
        assert _archived(database, "ARCHIVE_O1_ODDS_TANFUKUWAKU", race) == 3
        assert _archived(database, "ARCHIVE_O2_ODDS_UMAREN", race) == 3
        # Both captures stage the same publication, so the capture archive keeps one row.
        assert _archived(database, "ARCHIVE_CAPTURE_O1_ODDS_TANFUKUWAKU", race) == 1
    assert _log(database)[:2] == [
        (
            "11",
            spec,
            "5",
            "archived",
            "capture_archive_committed",
            "1",
            "11151454",
            "3",
            "3",
            "2026-11-15T05:55:00+00:00",
            "2026-11-15T05:55:00+00:00",
        )
        for spec in ("0B41", "0B42")
    ]


def test_a_repeated_series_is_deduplicated_as_full_rows(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_raw(database)
    archive = OddsArchive(database)
    key = RaceKey(RACE_DATE, "05", "05", "04", "11")
    inserted = []
    for capture_id in ("a" * 32, "b" * 32):
        archive.begin_capture(
            capture_id,
            key,
            PREDICTION_SPECS,
            scheduled_start_at=datetime(2026, 11, 15, 15, 0, tzinfo=UTC),
            offset_minutes=5,
            planned_at=datetime(2026, 11, 15, 5, 55, tzinfo=UTC),
        )
        _stage_series(database, "11")
        results = archive.finish_capture(
            capture_id,
            key,
            PREDICTION_SPECS,
            JVLinkExecutionResult({}, process_returncode=0),
            completed_at=datetime(2026, 11, 15, 5, 56, tzinfo=UTC),
            quarantine_directory=tmp_path / "quarantine",
            quarantine_label=capture_id,
            classifier=classify_capture,
        )
        inserted.append(results["0B41"].inserted_rows)
    assert inserted == [3, 0]
    assert _archived(database, "ARCHIVE_O1_ODDS_TANFUKUWAKU", "11") == 3


def test_a_failed_or_foreign_prediction_fetch_archives_nothing_and_is_still_published(
    tmp_path: Path,
) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC), offsets=(2,)
    )
    runner.fail.add(("11", "prediction"))
    runner.foreign_row.add(("12", "prediction"))
    publisher = Publisher(tmp_path, database)

    result = retriever.retrieve(RACE_DATE, publisher=publisher)

    assert runner.calls == [
        ("11", "prediction"),
        ("11", "capture"),
        ("12", "prediction"),
        ("12", "capture"),
    ]
    assert publisher.races == ["11", "12"]
    statuses = {(row[0], row[1]): (str(row[3]), str(row[4])) for row in _log(database)}
    assert statuses[("11", "0B41")][0] == "failed"
    assert statuses[("11", "0B41")][1].startswith("jvlink_error")
    assert statuses[("12", "0B41")][0] == "failed"
    assert statuses[("12", "0B41")][1].startswith("staging_race_mismatch")
    for race in ("11", "12"):
        assert _archived(database, "ARCHIVE_O1_ODDS_TANFUKUWAKU", race) == 0
    assert _staging_rows(database) == 0
    assert list((tmp_path / "runtime" / "race-day-odds-quarantine").glob("*.db"))
    assert result.failed


@pytest.mark.parametrize(
    ("evidence", "status", "reason"),
    [
        (PREDICTION_SPECS, "no_data", "jvopen_no_data"),
        (frozenset(), "failed", "empty_response_unverified"),
    ],
)
def test_an_empty_prediction_fetch_is_classified_by_its_jvopen_evidence(
    tmp_path: Path, evidence: frozenset[str], status: str, reason: str
) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC), offsets=(2,)
    )
    runner.empty[("11", "prediction")] = evidence
    publisher = Publisher(tmp_path, database)

    retriever.retrieve(RACE_DATE, publisher=publisher)

    rows = {(row[0], row[1]): (row[3], row[4]) for row in _log(database)}
    assert rows[("11", "0B41")] == (status, reason)
    assert rows[("11", "0B42")] == (status, reason)
    assert _archived(database, "ARCHIVE_O1_ODDS_TANFUKUWAKU", "11") == 0
    assert publisher.races == ["11", "12"]


def test_a_running_jvlink_process_skips_the_prediction_fetch_without_recording_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC), offsets=(2,)
    )
    # Startup recovery passes; the first prediction fetch then sees a running process.
    runner.assert_not_running.side_effect = [
        None,
        JVLinkToSQLiteError("JVLinkToSQLite is running"),
        None,
    ]
    publisher = Publisher(tmp_path, database)

    result = retriever.retrieve(RACE_DATE, publisher=publisher)

    assert runner.calls == [("11", "capture"), ("12", "prediction"), ("12", "capture")]
    assert publisher.races == ["12"]
    assert {row[0] for row in _log(database)} == {"12"}
    assert result.failed
    assert "JVLinkToSQLite is running" in capsys.readouterr().err


@pytest.mark.parametrize("error", [ValueError("bad table"), TypeError("bad value")])
def test_a_publication_failure_is_recorded_and_the_day_continues(
    tmp_path: Path, error: BaseException, capsys: pytest.CaptureFixture[str]
) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC), offsets=(2,)
    )
    publisher = Publisher(tmp_path, database)
    publisher.errors.append(error)

    retriever.retrieve(RACE_DATE, publisher=publisher)

    assert len(runner.calls) == 4
    assert publisher.races == ["11", "12"]
    rows = {(row[0], row[1]): (row[3], row[4]) for row in _log(database)}
    assert rows[("11", "0B41")] == (
        "archived",
        f"capture_archive_committed; publish_failed: {error}",
    )
    assert rows[("12", "0B41")] == ("archived", "capture_archive_committed")
    assert f"publish_failed: {error}" in capsys.readouterr().err


def test_a_late_prediction_fetch_is_skipped_and_still_published(tmp_path: Path) -> None:
    # 05:57 is two minutes after race 11's freeze, beyond the 60-second tolerance.
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 57, tzinfo=UTC), offsets=(2,)
    )
    publisher = Publisher(tmp_path, database)

    retriever.retrieve(RACE_DATE, publisher=publisher)

    assert ("11", "prediction") not in runner.calls
    assert publisher.races == ["11", "12"]
    rows = {(row[0], row[1]): row[3] for row in _log(database)}
    assert rows[("11", "0B41")] == "skipped_late"
    assert rows[("12", "0B41")] == "archived"


@pytest.mark.parametrize(
    ("finished", "expected"),
    [
        (CAPTURE_SPECS, [("11", "prediction"), ("12", "prediction"), ("12", "capture")]),
        (PREDICTION_SPECS, [("11", "capture"), ("12", "prediction"), ("12", "capture")]),
    ],
)
def test_a_restart_keeps_predictions_and_captures_at_one_offset_apart(
    tmp_path: Path, finished: frozenset[str], expected: list[tuple[str, str]]
) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC), offsets=(5,)
    )
    OddsArchive(database).record_skipped_capture(
        "f" * 32,
        RaceKey(RACE_DATE, "05", "05", "04", "11"),
        finished,
        scheduled_start_at=datetime(2026, 11, 15, 15, 0, tzinfo=UTC),
        offset_minutes=5,
        planned_at=datetime(2026, 11, 15, 5, 55, tzinfo=UTC),
    )

    retriever.retrieve(RACE_DATE, publisher=Publisher(tmp_path, database))

    assert runner.calls == expected


def test_recovery_quarantines_running_prediction_and_capture_rows_once(tmp_path: Path) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 7, 0, tzinfo=UTC), offsets=(2,)
    )
    archive = OddsArchive(database)
    key = RaceKey(RACE_DATE, "05", "05", "04", "11")
    for capture_id, specs in (("p" * 32, PREDICTION_SPECS), ("c" * 32, CAPTURE_SPECS)):
        archive.begin_capture(
            capture_id,
            key,
            specs,
            scheduled_start_at=datetime(2026, 11, 15, 15, 0, tzinfo=UTC),
            offset_minutes=5,
            planned_at=datetime(2026, 11, 15, 5, 55, tzinfo=UTC),
        )
    _stage_series(database, "11")

    assert retriever.recover() == 8

    assert _staging_rows(database) == 0
    rows = _log(database, specs=PREDICTION_SPECS | CAPTURE_SPECS)
    assert {row[3] for row in rows} == {"interrupted"}
    (quarantine,) = (tmp_path / "runtime" / "race-day-odds-quarantine").glob("*.db")
    with sqlite3.connect(quarantine) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master")]
    # RT_O1/RT_O2 are shared by 0B31/0B32 and 0B41/0B42 but preserved once.
    assert len(tables) == len(set(tables))
    assert {"RT_O1_ODDS_TANFUKUWAKU", "RT_O2_ODDS_UMAREN"} <= set(tables)
    assert runner.calls == []


def test_an_invalid_prediction_setting_stops_before_anything_is_recorded(tmp_path: Path) -> None:
    retriever, runner, _, database = _retriever(
        tmp_path, datetime(2026, 11, 15, 5, 0, tzinfo=UTC), seed_specs=CAPTURE_SPECS
    )

    with pytest.raises(RaceDayOddsSetupError):
        retriever.retrieve(RACE_DATE, publisher=Publisher(tmp_path, database))

    assert runner.calls == []
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'ARCHIVE_CAPTURE_LOG'"
            ).fetchone()
            is None
        )


def test_a_prediction_offset_requires_an_exact_0b41_0b42_profile(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    capture, prediction = _profiles()
    arguments = (
        Mock(),
        Mock(),
        OddsArchive(database),
        capture,
        database,
        tmp_path / "ledger.db",
        tmp_path,
    )
    with pytest.raises(ValueError, match="realtime-history profile"):
        RaceDayOddsRetriever(*arguments)
    wrong = JVLinkProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=frozenset({"0B41", "0B31"}),
    )
    with pytest.raises(ValueError, match="exactly 0B41 and 0B42"):
        RaceDayOddsRetriever(*arguments, prediction_profile=wrong)
    RaceDayOddsRetriever(*arguments, prediction_profile=prediction)
