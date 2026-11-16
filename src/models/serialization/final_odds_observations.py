"""Build hit-conditional final-odds observations from fixed-snapshot rows (ADR-042).

Everything here is pure: callers pass projected nullable-string rows and receive,
for one race, the winning combinations' freeze-time odds and final odds
(``NL_HR_PAY`` payout divided by 100), plus counted holds and exclusions.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast

from make_features.real_market import (
    JST,
    KEY_COLUMNS,
    canonical_hash,
    latest_o1,
    publication,
    win_quotes,
)
from make_features.reference_raw import (
    MARKET_O1_COLUMNS,
    MARKET_O2_COLUMNS,
    identifier,
    race_identity,
    scheduled_start,
)
from make_features.reference_rules import REFERENCE_BASES
from make_features.reference_snapshot import decimal_odds

BetType = Literal["win", "place_low", "place_mid", "quinella"]
HoldScope = Literal["race", "o1", "o2"]

BET_TYPES: tuple[BetType, ...] = ("win", "place_low", "place_mid", "quinella")
O1_BET_TYPES: tuple[BetType, ...] = ("win", "place_low", "place_mid")
O2_BET_TYPES: tuple[BetType, ...] = ("quinella",)

RA_TABLE = "NL_RA_RACE"
HR_TABLE = "NL_HR_PAY"
O1_TABLE = "ARCHIVE_O1_ODDS_TANFUKUWAKU"
O2_TABLE = "ARCHIVE_O2_ODDS_UMAREN"

RA_COLUMNS = (*KEY_COLUMNS, "headDataKubun", "headMakeDate", "HassoTime", "GradeCD", "TrackCD")
SCAN_COLUMNS = (*KEY_COLUMNS, "headDataKubun", "HappyoTime")
O1_COLUMNS = MARKET_O1_COLUMNS
O2_COLUMNS = MARKET_O2_COLUMNS
_FLAG_INDICES = range(9)
_REFUND_HORSE_INDICES = range(28)
_SPECIAL_FLAGS = ("TokubaraiFlag", "FuseirituFlag")
HR_COLUMNS = (
    *KEY_COLUMNS,
    "headDataKubun",
    "headMakeDate",
    "SyussoTosu",
    *(f"HenkanUma{i}" for i in _REFUND_HORSE_INDICES),
    *(f"{name}{i}" for name in (*_SPECIAL_FLAGS, "HenkanFlag") for i in _FLAG_INDICES),
    *(f"PayTansyo{i}{suffix}" for i in range(3) for suffix in ("Umaban", "Pay")),
    *(f"PayFukusyo{i}{suffix}" for i in range(5) for suffix in ("Umaban", "Pay")),
    *(f"PayUmaren{i}{suffix}" for i in range(3) for suffix in ("Kumi", "Pay")),
)

# latest_o1 reports these three cases only through its ValueError message.
_PUBLICATION_HOLDS = (
    ("no intermediate O1 publication at or before freeze", "no_publication"),
    ("conflicting intermediate O1 rows at the same publication", "conflicting_publication"),
    ("requires a valid HappyoTime", "invalid_publication"),
)


class ObservationHold(ValueError):
    """A race or one of its market tables cannot provide observations."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class HitObservation:
    """One winning combination with its freeze-time base odds and final odds."""

    race_id: str
    bet_type: BetType
    combination: str
    freeze_odds: float
    final_odds: float
    publication_age_seconds: int


@dataclass(frozen=True)
class HitExclusion:
    """A paid combination that is not used, with a counted reason."""

    race_id: str
    bet_type: BetType
    combination: str
    reason: str


@dataclass(frozen=True)
class RaceHold:
    """A held race (``scope="race"``) or a held market table of one race."""

    race_id: str
    scope: HoldScope
    reason: str
    detail: str


@dataclass(frozen=True)
class RaceObservations:
    """All observations, exclusions and holds of one race."""

    race_id: str
    hits: tuple[HitObservation, ...]
    exclusions: tuple[HitExclusion, ...]
    holds: tuple[RaceHold, ...]
    refund: bool
    publication_ages: Mapping[str, int]


def race_freeze(race_id: str, ra_rows: Sequence[Mapping[str, object]]) -> datetime:
    """Return the freeze of one race from its stored ``NL_RA_RACE`` schedule.

    Identical rows count once. The freeze is the stored scheduled start minus the
    repository's fixed reference offset (ADR-041).

    Raises:
        ObservationHold: If the race row is missing, ambiguous, cancelled or
            deleted, has an invalid ``HassoTime``, or its freeze falls on another
            JST date than the date in the race ID.
    """
    unique = {canonical_hash(dict(row)): row for row in ra_rows if race_identity(row) == race_id}
    if not unique:
        raise ObservationHold("no_race_row", race_id)
    if len(unique) != 1:
        raise ObservationHold("ambiguous_race_row", race_id)
    (row,) = unique.values()
    kubun = row.get("headDataKubun")
    if kubun == "9":
        raise ObservationHold("cancelled_race", race_id)
    if kubun == "0":
        raise ObservationHold("deleted_race", race_id)
    try:
        start = scheduled_start(row)
    except ValueError as exc:
        raise ObservationHold("invalid_schedule", str(exc)) from exc
    offset = REFERENCE_BASES["freeze_offset_seconds"]
    if not isinstance(offset, int):
        raise TypeError("REFERENCE_BASES freeze_offset_seconds must be an integer")
    freeze = start - timedelta(seconds=offset)
    if freeze.astimezone(JST).strftime("%Y%m%d") != race_id[:8]:
        raise ObservationHold("freeze_on_other_date", race_id)
    return freeze


def select_publication_pairs(
    rows: Sequence[Mapping[str, object]], freezes: Mapping[str, datetime]
) -> frozenset[tuple[str, str | None]]:
    """Select the ``(race_id, HappyoTime)`` pairs whose full rows decide ``latest_o1``.

    ``rows`` are scan rows (race key, ``headDataKubun`` and ``HappyoTime``). For each
    race in ``freezes`` the result holds the latest intermediate time at or before
    freeze, every such time that has two or more rows (so conflicts stay visible)
    and every invalid ``HappyoTime`` (which ``latest_o1`` rejects). Applying
    ``latest_o1`` to the selected full rows therefore gives the same choice or
    error as applying it to all rows. Rows of other races, other kinds and
    incomplete keys are ignored, as ``latest_o1`` ignores them.

    Raises:
        ValueError: If a ``HappyoTime`` is neither a string nor null.
    """
    latest: dict[str, tuple[datetime, str]] = {}
    counts: dict[tuple[str, str], int] = {}
    selected: set[tuple[str, str | None]] = set()
    for row in rows:
        if row.get("headDataKubun") != "1":
            continue
        try:
            race_id = race_identity(row)
        except ValueError:
            continue
        freeze = freezes.get(race_id)
        if freeze is None:
            continue
        value = row.get("HappyoTime")
        if value is not None and not isinstance(value, str):
            raise ValueError("HappyoTime must be a nullable string")
        try:
            at = publication(row)
        except ValueError:
            selected.add((race_id, value))
            continue
        if at > freeze:
            continue
        clock = cast(str, value)
        counts[(race_id, clock)] = counts.get((race_id, clock), 0) + 1
        if race_id not in latest or at > latest[race_id][0]:
            latest[race_id] = (at, clock)
    selected.update((race_id, clock) for race_id, (_, clock) in latest.items())
    selected.update(pair for pair, count in counts.items() if count > 1)
    return frozenset(selected)


def build_race_observations(
    race_id: str,
    *,
    ra_rows: Sequence[Mapping[str, object]],
    o1_rows: Sequence[Mapping[str, object]],
    o2_rows: Sequence[Mapping[str, object]],
    hr_rows: Sequence[Mapping[str, object]],
    max_publication_age_seconds: int,
) -> RaceObservations:
    """Build one race's hit observations under ADR-042 Decisions 2 and 3.

    A race-scope hold drops every bet type. A held O1 drops win and place; a held
    O2 drops quinella. Within a kept table, a winning combination without a
    freeze quote, or a bet type with a dead heat, becomes a counted exclusion.

    Raises:
        ValueError: If a payout row has a malformed horse number, combination or
            payout amount, or the maximum publication age is not positive.
    """
    if type(max_publication_age_seconds) is not int or max_publication_age_seconds < 1:
        raise ValueError("max_publication_age_seconds must be a positive integer")
    try:
        freeze = race_freeze(race_id, ra_rows)
        payouts = race_payouts(race_id, hr_rows)
    except ObservationHold as hold:
        return RaceObservations(
            race_id, (), (), (RaceHold(race_id, "race", hold.reason, hold.detail),), False, {}
        )
    holds: list[RaceHold] = []
    hits: list[HitObservation] = []
    exclusions: list[HitExclusion] = []
    ages: dict[str, int] = {}
    tables: tuple[tuple[HoldScope, Sequence[Mapping[str, object]], tuple[BetType, ...]], ...] = (
        ("o1", o1_rows, O1_BET_TYPES),
        ("o2", o2_rows, O2_BET_TYPES),
    )
    for scope, rows, bet_types in tables:
        try:
            row, age = freeze_row(race_id, rows, freeze)
            ages[scope] = age
            if age > max_publication_age_seconds:
                raise ObservationHold("stale_publication", f"{race_id}: {age} seconds old")
            quotes = o1_quotes(row) if scope == "o1" else _o2_quotes(row)
        except ObservationHold as hold:
            holds.append(RaceHold(race_id, scope, hold.reason, hold.detail))
            continue
        for bet_type in bet_types:
            paid = payouts.paid[bet_type]
            dead_heat = len(paid) > payouts.expected[bet_type]
            for combination, final_odds in paid:
                if dead_heat:
                    exclusions.append(HitExclusion(race_id, bet_type, combination, "dead_heat"))
                    continue
                base, reason = quotes[bet_type].get(combination, (None, "no_freeze_quote"))
                if base is None:
                    exclusions.append(
                        HitExclusion(race_id, bet_type, combination, reason or "unquoted")
                    )
                    continue
                hits.append(HitObservation(race_id, bet_type, combination, base, final_odds, age))
    return RaceObservations(
        race_id, tuple(hits), tuple(exclusions), tuple(holds), payouts.refund, ages
    )


@dataclass(frozen=True)
class RacePayouts:
    """Hold one race's finalized payouts, normal payout counts and refunded horses.

    ``paid`` maps each bet type to ``(combination, payout / 100)`` pairs. ``expected`` is
    the normal number of payouts (the place count follows the horses at the start of
    sales). ``refunded_horse_numbers`` are the two-digit horse numbers with a refund.
    """

    race_id: str
    paid: Mapping[BetType, tuple[tuple[str, float], ...]]
    expected: Mapping[BetType, int]
    refund: bool
    refunded_horse_numbers: tuple[str, ...]


def freeze_row(
    race_id: str, rows: Sequence[Mapping[str, object]], freeze: datetime
) -> tuple[Mapping[str, object], int]:
    """Return the freeze-time row by ``latest_o1`` and its age at freeze in seconds."""
    try:
        row = latest_o1(
            [dict(r) for r in rows], {"race_id": race_id, "freeze_at": freeze.isoformat()}
        )
    except ValueError as exc:
        message = str(exc)
        for fragment, reason in _PUBLICATION_HOLDS:
            if fragment in message:
                raise ObservationHold(reason, message) from exc
        raise
    return row, int((freeze - publication(row)).total_seconds())


QuoteTable = dict[str, tuple[float | None, str | None]]


def o1_quotes(row: Mapping[str, object]) -> Mapping[BetType, QuoteTable]:
    """Return every horse's win, ``place_low`` and ``place_mid`` quote of one O1 row.

    A missing quote maps to ``(None, reason)``. ``place_mid`` is ``sqrt(OddsLow * OddsHigh)``.

    Raises:
        ObservationHold: ``invalid_quote`` when a horse number or an odds encoding is invalid.
    """
    try:
        win: QuoteTable = {horse: (odds, reason) for horse, odds, reason in win_quotes(row)}
        low: QuoteTable = {}
        mid: QuoteTable = {}
        for i in range(28):
            horse = identifier(row, f"OddsFukusyoInfo{i}Umaban")
            if horse is None:
                continue
            if re.fullmatch(r"[0-9]{2}", horse) is None or horse in low:
                raise ValueError("O1 place quotes require unique valid horse numbers")
            lower = decimal_odds(row.get(f"OddsFukusyoInfo{i}OddsLow"), digits=4)
            upper = decimal_odds(row.get(f"OddsFukusyoInfo{i}OddsHigh"), digits=4)
            low[horse] = (lower, None if lower is not None else "unquoted")
            if lower is None:
                mid[horse] = (None, "unquoted")
            elif upper is None:
                mid[horse] = (None, "unquoted_high")
            else:
                mid[horse] = (math.sqrt(lower * upper), None)
    except ValueError as exc:
        raise ObservationHold("invalid_quote", str(exc)) from exc
    return {"win": win, "place_low": low, "place_mid": mid}


def _o2_quotes(row: Mapping[str, object]) -> Mapping[BetType, QuoteTable]:
    pairs: QuoteTable = {}
    try:
        for i in range(153):
            code = identifier(row, f"OddsUmarenInfo{i}Kumi")
            if code is None:
                continue
            if re.fullmatch(r"[0-9]{4}", code) is None or code[:2] >= code[2:] or code in pairs:
                raise ValueError("O2 requires unique ordered quinella combinations")
            odds = decimal_odds(row.get(f"OddsUmarenInfo{i}Odds"), digits=6)
            pairs[code] = (odds, None if odds is not None else "unquoted")
    except ValueError as exc:
        raise ObservationHold("invalid_quote", str(exc)) from exc
    return {"quinella": pairs}


def race_payouts(race_id: str, rows: Sequence[Mapping[str, object]]) -> RacePayouts:
    """Return finalized payouts and refunded horse numbers for one race.

    ``HenkanUma{i} == "1"`` represents the one-based horse number ``i + 1``.
    Special payouts and unestablished races are held because their payout layout
    has no verified settlement rule.

    Raises:
        ObservationHold: ``no_payout_row``, ``ambiguous_payout_row``, ``payout_not_final``,
            ``special_payout`` or ``unestablished``.
        ValueError: If ``SyussoTosu``, a ``HenkanUma`` flag or a payout column is malformed.
    """
    unique = {canonical_hash(dict(row)): row for row in rows if race_identity(row) == race_id}
    if not unique:
        raise ObservationHold("no_payout_row", race_id)
    if len(unique) != 1:
        raise ObservationHold("ambiguous_payout_row", race_id)
    (row,) = unique.values()
    if row.get("headDataKubun") != "2":
        raise ObservationHold("payout_not_final", f"{race_id}: {row.get('headDataKubun')!r}")
    for name, reason in (("TokubaraiFlag", "special_payout"), ("FuseirituFlag", "unestablished")):
        if any(_flag(row, f"{name}{i}") for i in _FLAG_INDICES):
            raise ObservationHold(reason, race_id)
    refund = any(_flag(row, f"HenkanFlag{i}") for i in _FLAG_INDICES)
    refunded_horse_numbers = _refunded_horse_numbers(row)
    horses_at_sale = _starters(row) + len(refunded_horse_numbers)
    win = _horse_payouts(row, "PayTansyo", 3)
    place = _horse_payouts(row, "PayFukusyo", 5)
    quinella = _pair_payouts(row)
    places = 3 if horses_at_sale >= 8 else 2 if horses_at_sale >= 5 else 0
    return RacePayouts(
        race_id=race_id,
        paid={"win": win, "place_low": place, "place_mid": place, "quinella": quinella},
        expected={"win": 1, "place_low": places, "place_mid": places, "quinella": 1},
        refund=refund,
        refunded_horse_numbers=refunded_horse_numbers,
    )


def _flag(row: Mapping[str, object], name: str) -> bool:
    value = row.get(name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a nullable string")
    return value not in (None, "", "0")


def _starters(row: Mapping[str, object]) -> int:
    value = row.get("SyussoTosu")
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{2}", value) is None:
        raise ValueError("NL_HR_PAY requires a two-digit SyussoTosu")
    return int(value)


def _refunded_horse_numbers(row: Mapping[str, object]) -> tuple[str, ...]:
    """Return horses withdrawn after sales opened, which still set the place count."""
    numbers: list[str] = []
    for i in _REFUND_HORSE_INDICES:
        value = row.get(f"HenkanUma{i}")
        if value not in ("0", "1"):
            raise ValueError(f"NL_HR_PAY requires HenkanUma{i} to be 0 or 1")
        if value == "1":
            numbers.append(f"{i + 1:02d}")
    return tuple(numbers)


def _horse_payouts(
    row: Mapping[str, object], prefix: str, slots: int
) -> tuple[tuple[str, float], ...]:
    paid: list[tuple[str, float]] = []
    for i in range(slots):
        horse = row.get(f"{prefix}{i}Umaban")
        amount = row.get(f"{prefix}{i}Pay")
        if _empty(horse, "00"):
            if not _empty(amount, "000000000"):
                raise ValueError(f"{prefix}{i}: payout without a horse number")
            continue
        if not isinstance(horse, str) or re.fullmatch(r"[0-9]{2}", horse) is None:
            raise ValueError(f"{prefix}{i}: invalid horse number")
        if not 1 <= int(horse) <= 28 or any(horse == seen for seen, _ in paid):
            raise ValueError(f"{prefix}{i}: invalid or duplicate horse number")
        paid.append((horse, _payout_odds(amount, f"{prefix}{i}Pay")))
    return tuple(paid)


def _pair_payouts(row: Mapping[str, object]) -> tuple[tuple[str, float], ...]:
    paid: list[tuple[str, float]] = []
    for i in range(3):
        code = row.get(f"PayUmaren{i}Kumi")
        amount = row.get(f"PayUmaren{i}Pay")
        if _empty(code, "0000"):
            if not _empty(amount, "000000000"):
                raise ValueError(f"PayUmaren{i}: payout without a combination")
            continue
        if (
            not isinstance(code, str)
            or re.fullmatch(r"[0-9]{4}", code) is None
            or not 1 <= int(code[:2]) < int(code[2:]) <= 28
            or any(code == seen for seen, _ in paid)
        ):
            raise ValueError(f"PayUmaren{i}: invalid or duplicate combination")
        paid.append((code, _payout_odds(amount, f"PayUmaren{i}Pay")))
    return tuple(paid)


def _empty(value: object, zero: str) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in ("", zero))


def _payout_odds(value: object, name: str) -> float:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{9}", value) is None or int(value) < 1:
        raise ValueError(f"{name}: payout must be a positive nine-digit amount")
    return int(value) / 100


__all__ = [
    "BET_TYPES",
    "HR_COLUMNS",
    "HR_TABLE",
    "O1_BET_TYPES",
    "O1_COLUMNS",
    "O1_TABLE",
    "O2_BET_TYPES",
    "O2_COLUMNS",
    "O2_TABLE",
    "RA_COLUMNS",
    "RA_TABLE",
    "SCAN_COLUMNS",
    "BetType",
    "HitExclusion",
    "HitObservation",
    "HoldScope",
    "ObservationHold",
    "RaceHold",
    "RaceObservations",
    "RacePayouts",
    "build_race_observations",
    "freeze_row",
    "o1_quotes",
    "race_freeze",
    "race_payouts",
    "select_publication_pairs",
]
