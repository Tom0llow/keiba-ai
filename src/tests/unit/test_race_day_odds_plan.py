"""Tests for pure race-day odds capture planning and classification."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import JVLinkExecutionResult
from jra_van_retriever.config.profiles import RaceDayOddsProfile
from jra_van_retriever.config.validation import validate_race_day_odds_profile
from jra_van_retriever.workflows.race_day_odds_plan import (
    classify_capture,
    is_capture_late,
    plan_captures,
)

RACE_DATE = date(2026, 11, 15)
SPECS = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"})


def _row(
    jyo: str, race: str, hasso: str | None, kubun: str | None = "2", month_day: str = "1115"
) -> tuple[str | None, ...]:
    return ("2026", month_day, jyo, "05", "03", race, kubun, hasso)


def _profile(**changes: object) -> RaceDayOddsProfile:
    profile = RaceDayOddsProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=SPECS,
        offsets_minutes=(30, 10, 5, 2),
        late_tolerance_seconds=60,
    )
    return replace(profile, **changes)  # type: ignore[arg-type]


def test_plan_captures_orders_offsets_by_planned_time_then_race_key() -> None:
    rows = [
        _row("08", "11", "1540"),
        _row("05", "11", "1540"),
        _row("05", "10", "1505"),
    ]

    plans = plan_captures(rows, RACE_DATE, (10, 2))  # type: ignore[arg-type]

    jst = timedelta(hours=9)
    assert [(plan.race_key.race_id, plan.offset_minutes) for plan in plans] == [
        ("2026111505050310", 10),
        ("2026111505050310", 2),
        ("2026111505050311", 10),
        ("2026111508050311", 10),
        ("2026111505050311", 2),
        ("2026111508050311", 2),
    ]
    first = plans[0]
    assert first.scheduled_start_at.utcoffset() == jst
    assert first.scheduled_start_at.replace(tzinfo=None) == datetime(2026, 11, 15, 15, 5)
    assert first.planned_at == datetime(2026, 11, 15, 5, 55, tzinfo=UTC)
    assert all(plan.planned_at.tzinfo is UTC for plan in plans)


@pytest.mark.parametrize(
    "row",
    [
        _row("43", "11", "1540"),
        _row("05", "11", "1540", kubun="0"),
        _row("05", "11", "1540", kubun="9"),
        _row("05", "11", "0000"),
        _row("05", "11", None),
        _row("05", "11", "15:4"),
        _row("05", "11", "2575"),
        _row("05", "11", "1540", month_day="1116"),
    ],
)
def test_plan_captures_skips_ineligible_rows(row: tuple[str | None, ...]) -> None:
    eligible = _row("05", "12", "1625")

    plans = plan_captures([row, eligible], RACE_DATE, (5,))  # type: ignore[list-item]

    assert [plan.race_key for plan in plans] == [
        RaceKey(RACE_DATE, "05", "05", "03", "12"),
    ]


def test_plan_captures_rejects_a_day_without_eligible_races() -> None:
    with pytest.raises(ValueError, match="no eligible JRA races"):
        plan_captures([_row("05", "11", "0000")], RACE_DATE, (5,))  # type: ignore[list-item]


@pytest.mark.parametrize("offsets", [(), (0,), (-5,), (5, 5)])
def test_plan_captures_rejects_invalid_offsets(offsets: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="offsets_minutes"):
        plan_captures([_row("05", "11", "1540")], RACE_DATE, offsets)  # type: ignore[list-item]


def test_capture_lateness_uses_a_strict_tolerance_boundary() -> None:
    planned = datetime(2026, 11, 15, 6, 0, tzinfo=UTC)

    assert not is_capture_late(planned, planned + timedelta(seconds=60), 60)
    assert is_capture_late(planned, planned + timedelta(seconds=61), 60)
    assert not is_capture_late(planned, planned - timedelta(seconds=30), 60)
    with pytest.raises(ValueError, match="timezone-aware"):
        is_capture_late(planned.replace(tzinfo=None), planned, 60)


def test_classification_follows_the_existing_provider_evidence_rules() -> None:
    execution = JVLinkExecutionResult(
        {},
        no_data_specs=frozenset({"0B33"}),
        fatal_specs=frozenset({"0B35"}),
    )

    assert classify_capture("0B35", execution, archived=True, observed_rows=1).status == "failed"
    assert classify_capture("0B35", execution, archived=True, observed_rows=1).reason == (
        "jvlink_error"
    )
    assert classify_capture("0B31", execution, archived=True, observed_rows=1).status == (
        "archived"
    )
    no_data = classify_capture("0B33", execution, archived=False, observed_rows=0)
    assert (no_data.status, no_data.reason) == ("no_data", "jvopen_no_data")
    unverified = classify_capture("0B34", execution, archived=False, observed_rows=0)
    assert (unverified.status, unverified.reason) == ("failed", "empty_response_unverified")
    rejected = classify_capture(
        "0B36", execution, archived=False, observed_rows=2, failure_reason="staging_multiple_rows"
    )
    assert (rejected.status, rejected.reason) == ("failed", "staging_multiple_rows")
    missing = classify_capture("0B33", None, archived=False, observed_rows=0)
    assert missing.reason == "empty_response_unverified"


def test_race_day_profile_validation_accepts_the_repository_shape() -> None:
    validate_race_day_odds_profile(_profile())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"normal_update": True}, "only realtime"),
        ({"realtime_update": False}, "only realtime"),
        ({"setup_data_specs": frozenset({"RACE"})}, "must be empty"),
        ({"realtime_data_specs": SPECS - {"0B36"}}, "exactly 0B31 through 0B36"),
        ({"realtime_data_specs": SPECS | {"0B41"}}, "exactly 0B31 through 0B36"),
        ({"offsets_minutes": ()}, "must not be empty"),
        ({"offsets_minutes": (5, 0)}, "positive integers"),
        ({"offsets_minutes": (5, 5)}, "duplicates"),
        ({"late_tolerance_seconds": 0}, "late_tolerance_seconds"),
    ],
)
def test_race_day_profile_validation_rejects_invalid_values(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_race_day_odds_profile(_profile(**changes))
