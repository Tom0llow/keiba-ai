"""Tests for the pure start-time-change rules of race-day-odds (ADR-049)."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from domain.race_key import RaceKey
from jra_van_retriever.workflows.race_day_odds_plan import (
    CapturePlan,
    adopted_starts,
    earlier_start_races,
    effective_starts,
    replan,
)

JST = ZoneInfo("Asia/Tokyo")
RACE = RaceKey(date(2026, 11, 15), "05", "05", "04", "11")
OTHER = RaceKey(date(2026, 11, 15), "05", "05", "04", "12")
CARD = datetime(2026, 11, 15, 15, 0, tzinfo=JST)
CARDS = {RACE.race_id: CARD, OTHER.race_id: CARD + timedelta(minutes=35)}


def _row(
    race: RaceKey, after: str, happyo: str, *, make: str = "20261115", before: str = "1500"
) -> dict[str, object]:
    return {
        "headRecordSpec": "TC",
        "headDataKubun": "1",
        "headMakeDate": make,
        "idYear": f"{race.race_date:%Y}",
        "idMonthDay": f"{race.race_date:%m%d}",
        "idJyoCD": race.jyo_code,
        "idKaiji": race.kaiji,
        "idNichiji": race.nichiji,
        "idRaceNum": race.race_number,
        "HappyoTime": happyo,
        "TCInfoAfterJi": after[:2],
        "TCInfoAfterFun": after[2:],
        "TCInfoBeforeJi": before[:2],
        "TCInfoBeforeFun": before[2:],
    }


def _plan(race: RaceKey, offset: int, kind: str = "capture") -> CapturePlan:
    start = CARDS[race.race_id]
    return CapturePlan(
        race,
        start,
        offset,
        (start - timedelta(minutes=offset)).astimezone(UTC),
        kind,  # type: ignore[arg-type]
    )


def test_the_newest_announcement_wins_and_a_return_to_the_card_is_no_change() -> None:
    rows = [_row(RACE, "1505", "11151000"), _row(RACE, "1501", "11150820")]
    assert effective_starts(rows, CARDS) == {RACE.race_id: CARD + timedelta(minutes=5)}

    reverted = [*rows, _row(RACE, "1500", "11151200", before="1505")]
    assert effective_starts(reverted, CARDS) == {}
    assert adopted_starts(reverted, CARDS) == {}


def test_the_start_uses_the_race_date_not_the_announcement_date() -> None:
    # Announced the evening before the race day.
    rows = [_row(RACE, "1501", "11141900", make="20261114")]
    assert effective_starts(rows, CARDS) == {
        RACE.race_id: datetime(2026, 11, 15, 15, 1, tzinfo=JST)
    }


def test_equal_announcement_times_are_ordered_deterministically() -> None:
    first = _row(RACE, "1501", "11150820", make="20261115")
    second = _row(RACE, "1505", "11150820", make="20261115")
    expected = effective_starts([first, second], CARDS)
    assert effective_starts([second, first], CARDS) == expected
    later_make = _row(RACE, "1502", "11150820", make="20261116")
    assert effective_starts([later_make, first, second], CARDS) == {
        RACE.race_id: CARD + timedelta(minutes=2)
    }


def test_any_accumulated_earlier_start_is_detected_even_after_a_revert() -> None:
    rows = [_row(RACE, "1455", "11151000"), _row(RACE, "1500", "11151000", before="1455")]
    assert earlier_start_races(rows, CARDS) == frozenset({RACE.race_id})
    assert earlier_start_races([_row(RACE, "1501", "11150820")], CARDS) == frozenset()


def test_rows_for_unknown_races_or_malformed_values_are_ignored() -> None:
    unknown = _row(RaceKey(date(2026, 11, 15), "06", "05", "04", "01"), "1001", "11150820")
    malformed = {**_row(RACE, "1501", "11150820"), "TCInfoAfterJi": "xx"}
    assert effective_starts([unknown, malformed], CARDS) == {}
    assert earlier_start_races([unknown, malformed], CARDS) == frozenset()


def test_adopted_starts_record_the_effective_start_and_announcement() -> None:
    rows = [_row(RACE, "1501", "11150820")]
    assert adopted_starts(rows, CARDS) == {
        RACE.race_id: {
            "effective_start_at": "2026-11-15T15:01:00+09:00",
            "HappyoTime": "11150820",
        }
    }


def test_replan_moves_only_captures_and_restores_them_on_a_revert() -> None:
    capture = _plan(RACE, 5)
    prediction = _plan(RACE, 5, "prediction")
    other = _plan(OTHER, 30)
    later = {RACE.race_id: CARD + timedelta(minutes=5)}

    moved = replan([capture, prediction, other], later)

    moved_capture = next(plan for plan in moved if plan.kind == "capture" and plan.race_key == RACE)
    moved_prediction = next(plan for plan in moved if plan.kind == "prediction")
    assert moved_capture.planned_at == (
        CARD + timedelta(minutes=5) - timedelta(minutes=5)
    ).astimezone(UTC)
    assert moved_capture.effective_start_at == CARD + timedelta(minutes=5)
    assert moved_capture.scheduled_start_at == CARD
    assert moved_prediction == prediction
    assert next(plan for plan in moved if plan.race_key == OTHER) == other

    restored = replan(moved, {})
    restored_capture = next(
        plan for plan in restored if plan.kind == "capture" and plan.race_key == RACE
    )
    assert restored_capture == capture


def test_replan_also_moves_captures_for_an_earlier_start_and_keeps_the_order() -> None:
    first = _plan(RACE, 30)
    second = _plan(OTHER, 30)
    # A large delay of the first race moves its capture after the second race's capture.
    replanned = replan([first, second], {RACE.race_id: CARD + timedelta(minutes=50)})
    assert [plan.race_key for plan in replanned] == [OTHER, RACE]

    earlier = replan([first], {RACE.race_id: CARD - timedelta(minutes=5)})
    assert earlier[0].planned_at == (CARD - timedelta(minutes=35)).astimezone(UTC)
    assert earlier[0].effective_start_at == CARD - timedelta(minutes=5)


def test_a_deletion_record_withdraws_the_announcement_it_deletes() -> None:
    delay = _row(RACE, "1510", "11151000")
    earlier = _row(RACE, "1455", "11151100")
    deletions = [
        {**delay, "headDataKubun": "0"},
        {**earlier, "headDataKubun": "0"},
    ]

    assert effective_starts([delay, earlier, *deletions], CARDS) == {}
    assert earlier_start_races([delay, earlier, *deletions], CARDS) == frozenset()
    # Only the deleted announcement is withdrawn; another announcement still counts.
    later = _row(RACE, "1505", "11151200")
    assert effective_starts([delay, later, deletions[0]], CARDS) == {
        RACE.race_id: CARD + timedelta(minutes=5)
    }
