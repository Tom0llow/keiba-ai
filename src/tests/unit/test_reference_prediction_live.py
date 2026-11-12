"""Tests for the race-day feature loop and its fetch selection, without I/O (ADR-037)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.reference_datamart import (
    FetchLookup,
    LiveOutcome,
    ReadyFetch,
    _FetchFinder,
    find_prediction_fetch,
    run_live_races,
)
from data.loader.race_version import RaceVersion
from models.serialization.reference_datamart import TargetSchedule

LOG = "ARCHIVE_CAPTURE_LOG"
START = datetime(2027, 1, 3, 6, 0, tzinfo=UTC)
FREEZE = START - timedelta(minutes=5)
SCHEDULE = TargetSchedule("2027010301010109", START, FREEZE)


def _log_row(
    spec: str,
    *,
    capture: str = "a" * 32,
    status: str = "archived",
    started: datetime = FREEZE,
    scheduled: datetime = START,
    reason: str = "capture_archive_committed",
) -> dict[str, object]:
    return {
        "capture_id": capture,
        "data_spec": spec,
        "scheduled_start_at": scheduled.astimezone(UTC).isoformat(),
        "started_at": started.isoformat(),
        "status": status,
        "reason": reason,
    }


def _version(*rows: dict[str, object]) -> RaceVersion:
    return RaceVersion("b" * 32, {LOG: list(rows)}, {})


def _fetch(**changes: object) -> tuple[dict[str, object], dict[str, object]]:
    return _log_row("0B41", **changes), _log_row("0B42", **changes)  # type: ignore[arg-type]


def test_a_complete_fetch_at_freeze_is_ready() -> None:
    lookup = find_prediction_fetch(_version(*_fetch(), _log_row("0B31")), SCHEDULE)

    assert lookup.kind == "ready"
    assert lookup.ready is not None
    assert lookup.ready.capture_id == "a" * 32
    assert lookup.ready.started_at == FREEZE


@pytest.mark.parametrize(
    ("rows", "kind", "reason"),
    [
        ((), "pending", None),
        (_fetch(started=FREEZE - timedelta(seconds=1)), "pending", None),
        (_fetch(scheduled=START + timedelta(minutes=1)), "pending", None),
        ((_log_row("0B41"),), "pending", None),
        ((_log_row("0B41"), _log_row("0B42", status="running")), "pending", None),
        (
            (_log_row("0B41"), _log_row("0B42", status="failed", reason="jvlink_error")),
            "terminal",
            "race_day_fetch_failed: jvlink_error",
        ),
        (
            _fetch(status="skipped_late", reason="late_tolerance_exceeded"),
            "terminal",
            "race_day_fetch_skipped_late: late_tolerance_exceeded",
        ),
        (
            (*_fetch(), *_fetch(capture="c" * 32, started=FREEZE + timedelta(seconds=9))),
            "terminal",
            "ambiguous_race_day_fetch",
        ),
    ],
)
def test_fetch_selection_waits_rejects_or_reports(
    rows: tuple[dict[str, object], ...], kind: str, reason: str | None
) -> None:
    lookup = find_prediction_fetch(_version(*rows), SCHEDULE)

    assert (lookup.kind, lookup.reason) == (kind, reason)


def test_no_version_or_no_log_table_is_pending() -> None:
    assert find_prediction_fetch(None, SCHEDULE).kind == "pending"
    assert find_prediction_fetch(RaceVersion("b" * 32, {}, {}), SCHEDULE).kind == "pending"


def test_a_successful_fetch_wins_over_an_earlier_failed_one() -> None:
    failed = _fetch(capture="0" * 32, status="failed", reason="jvlink_error")

    assert find_prediction_fetch(_version(*failed, *_fetch()), SCHEDULE).kind == "ready"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


def _schedule(number: str, start: datetime) -> TargetSchedule:
    return TargetSchedule(f"202701030101010{number}", start, start - timedelta(minutes=5))


def _run(
    clock: Clock,
    schedules: list[TargetSchedule],
    lookups: dict[str, list[FetchLookup]],
) -> tuple[list[LiveOutcome], list[tuple[str, datetime]]]:
    seen: list[tuple[str, datetime]] = []
    completed: list[tuple[str, datetime]] = []

    def find(schedule: TargetSchedule) -> FetchLookup:
        seen.append((schedule.race_id, clock.now))
        queue = lookups[schedule.race_id]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def complete(schedule: TargetSchedule, fetch: ReadyFetch) -> LiveOutcome:
        completed.append((schedule.race_id, clock.now))
        return LiveOutcome(schedule.race_id, "published", None, None, "out", "f" * 64, 4)

    reported: list[LiveOutcome] = []
    outcomes = run_live_races(
        schedules,
        now=clock,
        sleep=clock.sleep,
        poll_seconds=5,
        deadline_seconds=150,
        find_fetch=find,
        complete=complete,
        report=reported.append,
    )
    assert outcomes == reported
    return outcomes, completed


READY = FetchLookup("ready", ready=ReadyFetch(_version(), "a" * 32, FREEZE))
PENDING = FetchLookup("pending")


def test_each_race_waits_for_its_freeze_and_polls_until_its_fetch_is_published() -> None:
    first, second = _schedule("9", START), _schedule("8", START + timedelta(minutes=30))
    clock = Clock(START - timedelta(minutes=20))

    outcomes, completed = _run(
        clock,
        [second, first],
        {first.race_id: [PENDING, PENDING, READY], second.race_id: [READY]},
    )

    assert [outcome.race_id for outcome in outcomes] == [first.race_id, second.race_id]
    assert completed == [
        (first.race_id, first.freeze_at + timedelta(seconds=10)),
        (second.race_id, second.freeze_at),
    ]
    # Sleep to the first freeze, poll twice, then sleep to the second freeze.
    assert clock.sleeps[:3] == [5, 5, 5]
    assert sum(clock.sleeps) == (second.freeze_at - (START - timedelta(minutes=20))).seconds


def test_a_terminal_fetch_is_held_at_once_and_a_missing_one_at_the_deadline() -> None:
    failed, missing = _schedule("9", START), _schedule("8", START + timedelta(minutes=1))
    clock = Clock(failed.freeze_at)
    terminal = FetchLookup("terminal", reason="race_day_fetch_failed: jvlink_error")

    outcomes, completed = _run(
        clock, [failed, missing], {failed.race_id: [terminal], missing.race_id: [PENDING]}
    )

    assert completed == []
    assert [(o.race_id, o.status, o.stage, o.reason) for o in outcomes] == [
        (failed.race_id, "held", "target_pre_freeze", "race_day_fetch_failed: jvlink_error"),
        (missing.race_id, "held", "target_pre_freeze", "race_day_fetch_not_published"),
    ]
    assert clock.now > missing.freeze_at + timedelta(seconds=150)
    assert clock.now <= missing.freeze_at + timedelta(seconds=155)


def test_a_late_race_is_looked_up_once_then_held_unless_its_fetch_is_published() -> None:
    late = _schedule("9", START)
    clock = Clock(late.freeze_at + timedelta(seconds=151))

    outcomes, completed = _run(clock, [late], {late.race_id: [PENDING]})

    assert completed == []
    assert [(o.status, o.reason) for o in outcomes] == [("held", "race_day_fetch_not_published")]
    assert clock.sleeps == []


@pytest.mark.parametrize("late", [181, 600])
def test_a_fetch_first_seen_after_sales_close_is_held_without_calculating(late: int) -> None:
    race = _schedule("9", START)
    # A late start or restart sees an existing fetch only after sales close.
    clock = Clock(race.freeze_at + timedelta(seconds=late))

    outcomes, completed = _run(clock, [race], {race.race_id: [READY]})

    assert completed == []
    assert [(o.status, o.reason) for o in outcomes] == [("held", "race_day_sales_closed")]


def test_sales_close_is_judged_when_each_race_is_seen_not_at_the_start_of_the_pass() -> None:
    first = _schedule("9", START)
    second = _schedule("8", START + timedelta(seconds=1))
    # Both races are due in one pass at the first race's freeze + 179 s. Calculating the
    # first takes 3 s, so the second is seen at its freeze + 181 s, after sales close.
    clock = Clock(first.freeze_at + timedelta(seconds=179))

    def complete(schedule: TargetSchedule, fetch: ReadyFetch) -> LiveOutcome:
        clock.now += timedelta(seconds=3)
        return LiveOutcome(schedule.race_id, "published", None, None, "out", "f" * 64, 4)

    outcomes = run_live_races(
        [first, second],
        now=clock,
        sleep=clock.sleep,
        poll_seconds=5,
        deadline_seconds=180,
        find_fetch=lambda schedule: READY,
        complete=complete,
        report=lambda outcome: None,
    )

    assert [(o.race_id, o.status, o.reason) for o in outcomes] == [
        (first.race_id, "published", None),
        (second.race_id, "held", "race_day_sales_closed"),
    ]


def test_a_fetch_published_before_the_deadline_is_used_when_polled_after_it() -> None:
    race = _schedule("9", START)
    # The fetch appeared at freeze + 148 s; the poll that sees it runs at freeze + 152 s.
    clock = Clock(race.freeze_at + timedelta(seconds=152))

    outcomes, completed = _run(clock, [race], {race.race_id: [READY]})

    assert completed == [(race.race_id, race.freeze_at + timedelta(seconds=152))]
    assert [o.status for o in outcomes] == ["published"]


def test_outcome_lines_are_sorted_json_with_nulls() -> None:
    line = LiveOutcome("2027010301010109", "held", "target_pre_freeze", "x", None, None, 0)

    assert json.loads(line.as_json()) == {
        "manifest_sha256": None,
        "output": None,
        "race_id": "2027010301010109",
        "reason": "x",
        "rows": 0,
        "stage": "target_pre_freeze",
        "status": "held",
    }
    assert line.as_json().index('"manifest_sha256"') < line.as_json().index('"race_id"')


def test_an_unreadable_current_pointer_is_retried_at_the_next_poll(tmp_path: Path) -> None:
    # On Windows CURRENT can be briefly unreadable while race-day-odds replaces it.
    with patch(
        "cli.reference_datamart.current_race_version_id",
        side_effect=PermissionError("[WinError 32] in use"),
    ):
        lookup = _FetchFinder(tmp_path).find(SCHEDULE)

    assert lookup.kind == "pending"
