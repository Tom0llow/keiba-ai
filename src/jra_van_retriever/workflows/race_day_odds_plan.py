"""Plan and classify race-day odds captures without performing I/O."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import JVLinkExecutionResult
from jra_van_retriever.contracts.odds import RaceDayRaceRow
from jra_van_retriever.parsing.race_key import race_key_from_row

_JST = ZoneInfo("Asia/Tokyo")
_JRA_JYO_CODES = frozenset(f"{value:02d}" for value in range(1, 11))


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
            key=lambda capture: (capture.planned_at, _KIND_RANK[capture.kind], capture.race_key),
        )
    )


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


def _validate_offsets(offsets_minutes: tuple[int, ...]) -> None:
    if not offsets_minutes:
        raise ValueError("offsets_minutes must not be empty")
    if any(type(value) is not int or value <= 0 for value in offsets_minutes):
        raise ValueError("offsets_minutes must contain positive integers")
    if len(offsets_minutes) != len(set(offsets_minutes)):
        raise ValueError("offsets_minutes must not contain duplicates")
