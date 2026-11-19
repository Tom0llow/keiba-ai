"""Tests for the ADR-046 actual-purchase ledger format (synthetic ledgers only)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from models.betting.purchase_ledger import (
    LedgerError,
    Purchase,
    append_entries,
    new_ledger,
    parse_bet,
    parse_ledger,
    required_confirmed_since,
)

JST = ZoneInfo("Asia/Tokyo")
T0 = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
RACE_A = "2026111505050811"
RACE_B = "2026111508050811"
HEADER = b'{"format": "purchase_ledger", "format_version": 1, "kind": "header"}\n'


def _line(**fields: object) -> bytes:
    return (json.dumps(fields, sort_keys=True) + "\n").encode("ascii")


def _purchase_line(
    race_id: str = RACE_A,
    bet_type: str = "place",
    selection: str = "07",
    stake_yen: object = 1_000,
    recorded_at: str = T0.isoformat(),
) -> bytes:
    return _line(
        kind="purchase",
        race_id=race_id,
        bet_type=bet_type,
        selection=selection,
        stake_yen=stake_yen,
        recorded_at=recorded_at,
    )


def _confirmation_line(at: datetime = T0) -> bytes:
    return _line(kind="confirmation", recorded_at=at.isoformat())


def _purchase(race_id: str = RACE_A, stake_yen: int = 1_000, at: datetime = T0) -> Purchase:
    return Purchase(race_id, "place", "07", stake_yen, at)


def test_parse_ledger_sums_race_and_race_date_year_spending_over_every_bet_type() -> None:
    data = (
        HEADER
        + _purchase_line(RACE_A, "win", "03", 500)
        + _purchase_line(RACE_A, "trifecta", "03-01-02", 1_200)
        + _purchase_line(RACE_B, "bracket_quinella", "03-03", 300)
        + _purchase_line("2025122806050811", "place", "01", 9_900)
        + _confirmation_line(T0 + timedelta(minutes=1))
    )

    ledger = parse_ledger(data)

    assert ledger.sha256 == hashlib.sha256(data).hexdigest()
    assert ledger.race_spent_yen(RACE_A) == 1_700
    assert ledger.race_spent_yen(RACE_B) == 300
    assert ledger.race_spent_yen("2026111509050811") == 0
    # The year total includes the race's own spending; another year is not counted.
    assert ledger.annual_spent_yen(2026) == 2_000
    assert ledger.annual_spent_yen(2025) == 9_900
    assert ledger.latest_confirmation == T0 + timedelta(minutes=1)


def test_an_empty_ledger_has_no_spending_and_no_confirmation() -> None:
    ledger = parse_ledger(new_ledger())

    assert new_ledger() == HEADER
    assert ledger.purchases == ()
    assert ledger.latest_confirmation is None
    assert ledger.annual_spent_yen(2026) == 0


def test_the_same_bet_may_be_recorded_twice() -> None:
    data = HEADER + _purchase_line() + _purchase_line() + _confirmation_line()

    assert parse_ledger(data).race_spent_yen(RACE_A) == 2_000


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty file"),
        pytest.param(HEADER[:-1], id="no final newline"),
        pytest.param(HEADER + _confirmation_line()[:-1], id="incomplete last line"),
        pytest.param(HEADER + b"\n" + _confirmation_line(), id="blank line"),
        pytest.param(HEADER.replace(b"\n", b"\r\n"), id="carriage return"),
        pytest.param(b"\xef\xbb\xbf" + HEADER, id="byte order mark"),
        pytest.param(_confirmation_line(), id="missing header"),
        pytest.param(HEADER + HEADER, id="second header"),
        pytest.param(
            b'{"format": "purchase_ledger", "format_version": 2, "kind": "header"}\n',
            id="unknown version",
        ),
        pytest.param(
            b'{"format": "purchase_ledger", "format_version": true, "kind": "header"}\n',
            id="boolean version",
        ),
        pytest.param(HEADER + _line(kind="refund", recorded_at=T0.isoformat()), id="unknown kind"),
        pytest.param(
            HEADER + _line(kind="confirmation", recorded_at=T0.isoformat(), note="x"),
            id="extra key",
        ),
        pytest.param(HEADER + _line(kind="confirmation"), id="missing key"),
        pytest.param(
            HEADER + _purchase_line().replace(b"}", b', "x": 1}'), id="purchase extra key"
        ),
        pytest.param(
            HEADER + _purchase_line().replace(b'"selection": "07", ', b""),
            id="purchase missing key",
        ),
        pytest.param(HEADER + b"[]\n", id="not an object"),
        pytest.param(HEADER + _purchase_line(race_id="202611150505081"), id="short race id"),
        pytest.param(HEADER + _purchase_line(race_id="2026113105050811"), id="unreal date"),
        pytest.param(HEADER + _purchase_line(race_id="2026111511050811"), id="venue 11"),
        pytest.param(HEADER + _purchase_line(race_id="2026111505000811"), id="meeting 00"),
        pytest.param(HEADER + _purchase_line(race_id="2026111505050011"), id="day 00"),
        pytest.param(HEADER + _purchase_line(race_id="2026111505050813"), id="race 13"),
        pytest.param(HEADER + _purchase_line(race_id="2026111505050800"), id="race 00"),
        pytest.param(HEADER + _purchase_line(bet_type="bracket_exacta"), id="unknown bet type"),
        pytest.param(HEADER + _purchase_line(selection="7"), id="one-digit number"),
        pytest.param(HEADER + _purchase_line(selection="19"), id="horse 19"),
        pytest.param(HEADER + _purchase_line(selection="07-08"), id="two numbers for place"),
        pytest.param(
            HEADER + _purchase_line(bet_type="quinella", selection="08-07"), id="unordered quinella"
        ),
        pytest.param(
            HEADER + _purchase_line(bet_type="quinella_place", selection="07-07"),
            id="repeated wide",
        ),
        pytest.param(
            HEADER + _purchase_line(bet_type="bracket_quinella", selection="09-09"),
            id="bracket 09",
        ),
        pytest.param(
            HEADER + _purchase_line(bet_type="bracket_quinella", selection="04-03"),
            id="descending bracket",
        ),
        pytest.param(
            HEADER + _purchase_line(bet_type="exacta", selection="03-03"), id="repeated exacta"
        ),
        pytest.param(
            HEADER + _purchase_line(bet_type="trio", selection="01-03-02"), id="unordered trio"
        ),
        pytest.param(HEADER + _purchase_line(stake_yen=150), id="not a 100 multiple"),
        pytest.param(HEADER + _purchase_line(stake_yen=0), id="zero stake"),
        pytest.param(HEADER + _purchase_line(stake_yen=-100), id="negative stake"),
        pytest.param(HEADER + _purchase_line(stake_yen=True), id="boolean stake"),
        pytest.param(HEADER + _purchase_line(stake_yen=100.0), id="float stake"),
        pytest.param(
            HEADER + _purchase_line(recorded_at="2026-11-15T05:00:00"), id="naive recorded_at"
        ),
        pytest.param(
            HEADER + _confirmation_line(T0) + _confirmation_line(T0 - timedelta(seconds=1)),
            id="decreasing recorded_at",
        ),
    ],
)
def test_parse_ledger_rejects_each_broken_rule(data: bytes) -> None:
    with pytest.raises(LedgerError):
        parse_ledger(data)


def test_ordered_and_loose_selections_are_accepted() -> None:
    data = (
        HEADER
        + _purchase_line(bet_type="exacta", selection="08-02")
        + _purchase_line(bet_type="trifecta", selection="18-01-09")
        + _purchase_line(bet_type="bracket_quinella", selection="08-08")
        + _purchase_line(bet_type="trio", selection="01-02-18")
    )

    assert len(parse_ledger(data).purchases) == 4


def test_append_entries_adds_purchases_and_one_confirmation_without_changing_old_lines() -> None:
    first = append_entries(new_ledger(), [_purchase()], confirmed_at=T0)
    later = T0 + timedelta(hours=1)

    second = append_entries(first, [_purchase(RACE_B, 300, later)], confirmed_at=later)

    assert second.startswith(first)
    assert second.count(b"\n") == 5
    ledger = parse_ledger(second)
    assert [item.race_id for item in ledger.purchases] == [RACE_A, RACE_B]
    assert ledger.confirmations == (T0, later)


def test_append_entries_without_purchases_adds_only_a_confirmation() -> None:
    data = append_entries(new_ledger(), [], confirmed_at=T0)

    assert data == HEADER + _confirmation_line()


def test_append_entries_rejects_an_earlier_time_a_different_purchase_time_and_bad_ledgers() -> None:
    first = append_entries(new_ledger(), [], confirmed_at=T0)

    with pytest.raises(LedgerError, match="earlier"):
        append_entries(first, [], confirmed_at=T0 - timedelta(seconds=1))
    with pytest.raises(LedgerError, match="confirmed_at"):
        append_entries(first, [_purchase(at=T0)], confirmed_at=T0 + timedelta(seconds=1))
    with pytest.raises(LedgerError):
        append_entries(first[:-1], [], confirmed_at=T0)
    with pytest.raises(LedgerError, match="timezone"):
        append_entries(first, [], confirmed_at=datetime(2026, 11, 15, 6, 0))


@pytest.mark.parametrize(
    ("text", "bet_type", "selection", "stake"),
    [
        (f"{RACE_A}:win:01:100", "win", "01", 100),
        (f"{RACE_A}:place:18:1000", "place", "18", 1_000),
        (f"{RACE_A}:bracket_quinella:01-01:200", "bracket_quinella", "01-01", 200),
        (f"{RACE_A}:quinella:01-02:300", "quinella", "01-02", 300),
        (f"{RACE_A}:quinella_place:01-02:400", "quinella_place", "01-02", 400),
        (f"{RACE_A}:exacta:02-01:500", "exacta", "02-01", 500),
        (f"{RACE_A}:trio:01-02-03:600", "trio", "01-02-03", 600),
        (f"{RACE_A}:trifecta:03-01-02:700", "trifecta", "03-01-02", 700),
    ],
)
def test_parse_bet_reads_each_bet_type(
    text: str, bet_type: str, selection: str, stake: int
) -> None:
    purchase = parse_bet(text, recorded_at=T0)

    assert (purchase.race_id, purchase.bet_type, purchase.selection) == (
        RACE_A,
        bet_type,
        selection,
    )
    assert (purchase.stake_yen, purchase.recorded_at) == (stake, T0)


@pytest.mark.parametrize(
    "text",
    [
        f"{RACE_A}:win:01",
        f"{RACE_A}:win:01:100:1",
        f"{RACE_A}:win:01:1e3",
        f"{RACE_A}:win:01:+100",
        f"{RACE_A}:win:01: 100",
        f"{RACE_A}:win:01:150",
        f"{RACE_A}:win:01:0",
        f"{RACE_A}:show:01:100",
    ],
)
def test_parse_bet_rejects_malformed_text(text: str) -> None:
    with pytest.raises(LedgerError):
        parse_bet(text, recorded_at=T0)


def test_required_confirmed_since_uses_midnight_or_the_latest_earlier_sales_close() -> None:
    day = date(2026, 11, 15)
    midnight = datetime(2026, 11, 15, tzinfo=JST)
    close_1 = datetime(2026, 11, 15, 15, 38, tzinfo=JST)
    close_2 = datetime(2026, 11, 15, 6, 23, tzinfo=UTC)

    assert required_confirmed_since(day, []) == midnight
    assert required_confirmed_since(day, [close_1, close_2]) == close_1
    assert required_confirmed_since(day, [midnight - timedelta(hours=1)]) == midnight
    with pytest.raises(LedgerError):
        required_confirmed_since(day, [datetime(2026, 11, 15, 15, 0)])


@pytest.mark.parametrize(
    ("line", "message"),
    [
        pytest.param(
            _purchase_line().replace(b'"stake_yen": 1000', b'"stake_yen": 100, "stake_yen": 9900'),
            "duplicate key",
            id="duplicate stake",
        ),
        pytest.param(
            _purchase_line().replace(b'"stake_yen": 1000', b'"stake_yen": NaN'),
            "NaN is not allowed",
            id="NaN",
        ),
        pytest.param(
            _purchase_line().replace(b'"stake_yen": 1000', b'"stake_yen": Infinity'),
            "Infinity is not allowed",
            id="Infinity",
        ),
        pytest.param(b"[" * 100_000 + b"\n", "not strict JSON", id="deep nesting"),
        pytest.param(
            b'{"recorded_at": "' + T0.isoformat().encode() + b'", "kind": "confirmation"}\n',
            "sorted keys",
            id="unsorted keys",
        ),
        pytest.param(
            b'{"kind":"confirmation", "recorded_at": "' + T0.isoformat().encode() + b'"}\n',
            "sorted keys",
            id="other separators",
        ),
        pytest.param(b" " + _confirmation_line(), "sorted keys", id="leading space"),
        pytest.param(
            _purchase_line().replace(b'"stake_yen": 1000', b'"stake_yen": 1e3'),
            "default number and string forms",
            id="exponent number",
        ),
    ],
)
def test_parse_ledger_names_the_rule_a_line_breaks(line: bytes, message: str) -> None:
    with pytest.raises(LedgerError, match=message):
        parse_ledger(HEADER + line)
