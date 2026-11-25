"""Plan and classify race-day odds captures without performing I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import JVLinkExecutionResult
from jra_van_retriever.contracts.odds import RaceDayRaceRow
from jra_van_retriever.parsing.race_key import race_key_from_row

_JST = ZoneInfo("Asia/Tokyo")
_JRA_JYO_CODES = frozenset(f"{value:02d}" for value in range(1, 11))
_JVLINK_OPEN_APIS = frozenset({"JVOpen", "JVRTOpen"})
JVLINK_AGENT_DOWN_RETURNCODES = frozenset({-211, -303})


type CaptureKind = Literal["capture", "prediction"]
# A prediction fetch runs before a capture planned at the same instant (ADR-032 Amendment 2).
_KIND_RANK: dict[str, int] = {"prediction": 0, "capture": 1}


@dataclass(frozen=True)
class CapturePlan:
    """Represent one race and offset scheduled for capture.

    ``kind="prediction"`` fetches the 0B41/0B42 time series for race-day features.
    """

    race_key: RaceKey
    scheduled_start_at: datetime
    offset_minutes: int
    planned_at: datetime
    kind: CaptureKind = "capture"
    effective_start_at: datetime | None = None


@dataclass(frozen=True)
class CaptureClassification:
    """Represent the persisted status and reason for one DataSpec."""

    status: str
    reason: str


def plan_captures(
    rows: Iterable[RaceDayRaceRow],
    race_date: date,
    offsets_minutes: tuple[int, ...],
    *,
    prediction_offset_minutes: int | None = None,
) -> tuple[CapturePlan, ...]:
    """Return valid race-day captures in planned-time, kind and race-key order.

    With ``prediction_offset_minutes`` every race also gets one prediction fetch, which
    precedes any capture planned at the same instant.
    """
    _validate_offsets(offsets_minutes)
    captures: list[CapturePlan] = []
    for row in rows:
        year, month_day, jyo_code, kaiji, nichiji, race_number, head_data_kubun, hasso = row
        if jyo_code not in _JRA_JYO_CODES or head_data_kubun in {"0", "9"}:
            continue
        if not isinstance(hasso, str) or len(hasso) != 4 or not hasso.isdigit() or hasso == "0000":
            continue
        if (
            not isinstance(year, str)
            or not isinstance(month_day, str)
            or not isinstance(jyo_code, str)
            or not isinstance(kaiji, str)
            or not isinstance(nichiji, str)
            or not isinstance(race_number, str)
        ):
            raise ValueError("race-day odds row contains an invalid race key")
        race_key = race_key_from_row((year, month_day, jyo_code, kaiji, nichiji, race_number))
        if race_key.race_date != race_date:
            continue
        try:
            start_time = datetime.strptime(hasso, "%H%M").time()
        except ValueError:
            continue
        scheduled_start_at = datetime.combine(race_date, start_time, _JST)
        for offset_minutes in offsets_minutes:
            planned_at = (scheduled_start_at - timedelta(minutes=offset_minutes)).astimezone(UTC)
            captures.append(CapturePlan(race_key, scheduled_start_at, offset_minutes, planned_at))
        if prediction_offset_minutes is not None:
            planned_at = (
                scheduled_start_at - timedelta(minutes=prediction_offset_minutes)
            ).astimezone(UTC)
            captures.append(
                CapturePlan(
                    race_key,
                    scheduled_start_at,
                    prediction_offset_minutes,
                    planned_at,
                    "prediction",
                )
            )
    if not captures:
        raise ValueError(f"no eligible JRA races found for {race_date.isoformat()}")
    return tuple(
        sorted(
            captures,
            key=_plan_order,
        )
    )


def effective_starts(
    tc_rows: Iterable[Mapping[str, object]], card_starts: Mapping[str, datetime]
) -> dict[str, datetime]:
    """Return the currently announced start for each race that differs from its card.

    The newest ``HappyoTime`` wins.  Equal announcements use ``headMakeDate`` and then
    every value in the row as deterministic tie breakers, so accumulated TC rows remain
    reproducible even when the provider repeats an announcement.
    """
    return {
        race_id: start
        for race_id, (start, _) in _adopted_tc_rows(tc_rows, card_starts).items()
        if start != card_starts[race_id]
    }


def adopted_starts(
    tc_rows: Iterable[Mapping[str, object]], card_starts: Mapping[str, datetime]
) -> dict[str, dict[str, str]]:
    """Return the changed starts and their announcement time for audit logging."""
    return {
        race_id: {
            "effective_start_at": start.isoformat(),
            "HappyoTime": happyo_time,
        }
        for race_id, (start, happyo_time) in _adopted_tc_rows(tc_rows, card_starts).items()
        if start != card_starts[race_id]
    }


def earlier_start_races(
    tc_rows: Iterable[Mapping[str, object]], card_starts: Mapping[str, datetime]
) -> frozenset[str]:
    """Return races that were ever announced earlier than their card start.

    A later row that returns a race to its card start does not erase the safety signal.
    A deleted announcement (``headDataKubun`` "0") is not a change.
    """
    earlier: set[str] = set()
    for row in _active_tc_rows(tc_rows):
        race_id = _tc_race_id(row)
        if race_id is None or race_id not in card_starts:
            continue
        start = _tc_after_start(row)
        if start is not None and start < card_starts[race_id]:
            earlier.add(race_id)
    return frozenset(earlier)


def replan(
    plans: Iterable[CapturePlan], effective: Mapping[str, datetime]
) -> tuple[CapturePlan, ...]:
    """Move only unfinished odds captures to their current effective start time."""
    replanned: list[CapturePlan] = []
    for plan in plans:
        if plan.kind != "capture":
            # The prediction fetch always stays on the card schedule (ADR-049 decision 4).
            replanned.append(plan)
            continue
        effective_start = effective.get(plan.race_key.race_id)
        if effective_start is None or effective_start == plan.scheduled_start_at:
            # No change, or a change that returned to the card time: plan from the card.
            start, effective_start_at = plan.scheduled_start_at, None
        else:
            start, effective_start_at = effective_start, effective_start
        replanned.append(
            replace(
                plan,
                planned_at=(start - timedelta(minutes=plan.offset_minutes)).astimezone(UTC),
                effective_start_at=effective_start_at,
            )
        )
    return tuple(sorted(replanned, key=_plan_order))


def is_capture_late(
    planned_at: datetime, current_at: datetime, late_tolerance_seconds: int
) -> bool:
    """Return whether the current clock is strictly beyond the allowed delay."""
    if planned_at.tzinfo is None or current_at.tzinfo is None:
        raise ValueError("capture clocks must be timezone-aware")
    if type(late_tolerance_seconds) is not int or late_tolerance_seconds <= 0:
        raise ValueError("late_tolerance_seconds must be a positive integer")
    return current_at > planned_at + timedelta(seconds=late_tolerance_seconds)


def classify_capture(
    data_spec: str,
    execution: JVLinkExecutionResult | None,
    *,
    archived: bool,
    observed_rows: int,
    failure_reason: str | None = None,
) -> CaptureClassification:
    """Classify one capture without inferring no-data from an empty table alone."""
    if execution is not None and data_spec in execution.fatal_specs:
        return CaptureClassification("failed", "jvlink_error")
    if failure_reason is not None:
        return CaptureClassification("failed", failure_reason)
    if archived:
        return CaptureClassification("archived", "capture_archive_committed")
    if observed_rows == 0:
        if execution is not None and data_spec in execution.no_data_specs:
            return CaptureClassification("no_data", "jvopen_no_data")
        return CaptureClassification("failed", "empty_response_unverified")
    return CaptureClassification("failed", "archive_not_committed")


def jvlink_agent_down_results(execution: JVLinkExecutionResult) -> dict[str, tuple[str, int]]:
    """Return JV-Link Agent stop results in DataSpec order."""
    return {
        data_spec: (api, returncode)
        for data_spec, (api, returncode) in sorted(execution.api_results.items())
        if api in _JVLINK_OPEN_APIS and returncode in JVLINK_AGENT_DOWN_RETURNCODES
    }


def _adopted_tc_rows(
    tc_rows: Iterable[Mapping[str, object]], card_starts: Mapping[str, datetime]
) -> dict[str, tuple[datetime, str]]:
    latest: dict[str, tuple[tuple[str, str, tuple[str, ...]], datetime, str]] = {}
    for row in _active_tc_rows(tc_rows):
        race_id = _tc_race_id(row)
        happyo_time = _text(row, "HappyoTime")
        if (
            race_id is None
            or race_id not in card_starts
            or happyo_time is None
            or not _valid_happyo_time(happyo_time)
        ):
            continue
        start = _tc_after_start(row)
        if start is None:
            continue
        order = (
            happyo_time,
            _text(row, "headMakeDate") or "",
            tuple(_text(row, name) or "" for name in sorted(row)),
        )
        previous = latest.get(race_id)
        if previous is None or order > previous[0]:
            latest[race_id] = (order, start, happyo_time)
    return {race_id: (start, happyo_time) for race_id, (_, start, happyo_time) in latest.items()}


def _active_tc_rows(tc_rows: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Drop JV-Data deletion records and the announcements they withdraw.

    A TC record with ``headDataKubun`` "0" deletes the record of the same race and
    ``HappyoTime`` (a provider error); neither counts as a start-time change.
    """
    rows = list(tc_rows)
    deleted = {
        (_tc_race_id(row), _text(row, "HappyoTime"))
        for row in rows
        if _text(row, "headDataKubun") == "0"
    }
    return [
        row
        for row in rows
        if _text(row, "headDataKubun") != "0"
        and (_tc_race_id(row), _text(row, "HappyoTime")) not in deleted
    ]


def _tc_race_id(row: Mapping[str, object]) -> str | None:
    values = tuple(_text(row, column) for column in (*_race_key_columns(),))
    if any(value is None for value in values):
        return None
    return "".join(value for value in values if value is not None)


def _tc_after_start(row: Mapping[str, object]) -> datetime | None:
    """Return the announced start on the race's own date (not the announcement date)."""
    year = _text(row, "idYear")
    month_day = _text(row, "idMonthDay")
    hour = _text(row, "TCInfoAfterJi")
    minute = _text(row, "TCInfoAfterFun")
    if (
        year is None
        or month_day is None
        or hour is None
        or minute is None
        or not (len(year) == 4 and year.isdigit())
        or not (len(month_day) == 4 and month_day.isdigit())
        or not hour.isdigit()
        or not minute.isdigit()
    ):
        return None
    try:
        return datetime(
            int(year),
            int(month_day[:2]),
            int(month_day[2:]),
            int(hour),
            int(minute),
            tzinfo=_JST,
        )
    except ValueError:
        return None


def _valid_happyo_time(value: str | None) -> bool:
    return value is not None and len(value) == 8 and value.isdigit()


def _text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _race_key_columns() -> tuple[str, ...]:
    return ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")


def _plan_order(capture: CapturePlan) -> tuple[datetime, int, RaceKey]:
    return (capture.planned_at, _KIND_RANK[capture.kind], capture.race_key)


def _validate_offsets(offsets_minutes: tuple[int, ...]) -> None:
    if not offsets_minutes:
        raise ValueError("offsets_minutes must not be empty")
    if any(type(value) is not int or value <= 0 for value in offsets_minutes):
        raise ValueError("offsets_minutes must contain positive integers")
    if len(offsets_minutes) != len(set(offsets_minutes)):
        raise ValueError("offsets_minutes must not contain duplicates")
