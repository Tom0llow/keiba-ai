"""Parse, check and extend the actual-purchase ledger of ADR-046 without I/O.

The ledger is ASCII JSON Lines. Its first line is a header; each later line is a
purchase a person actually made or a confirmation that every purchase up to its
time is recorded. Race and calendar-year spending are sums of recorded stakes;
the year is the race date's year, and every bet type and race counts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from itertools import pairwise
from typing import Final, Literal, cast
from zoneinfo import ZoneInfo

LEDGER_FORMAT: Final = "purchase_ledger"
LEDGER_FORMAT_VERSION: Final = 1
BET_TYPES: Final = (
    "win",
    "place",
    "bracket_quinella",
    "quinella",
    "quinella_place",
    "exacta",
    "trio",
    "trifecta",
)
LedgerBetType = Literal[
    "win",
    "place",
    "bracket_quinella",
    "quinella",
    "quinella_place",
    "exacta",
    "trio",
    "trifecta",
]
JST = ZoneInfo("Asia/Tokyo")
_UNIT_YEN = 100
_HEADER_KEYS = frozenset({"format", "format_version", "kind"})
_PURCHASE_KEYS = frozenset({"kind", "race_id", "bet_type", "selection", "stake_yen", "recorded_at"})
_CONFIRMATION_KEYS = frozenset({"kind", "recorded_at"})
# Number count, highest number, and the order rule of each bet type's selection.
_SELECTION_RULES: Final[
    dict[str, tuple[int, int, Literal["one", "strict", "loose", "ordered"]]]
] = {
    "win": (1, 18, "one"),
    "place": (1, 18, "one"),
    "bracket_quinella": (2, 8, "loose"),
    "quinella": (2, 18, "strict"),
    "quinella_place": (2, 18, "strict"),
    "exacta": (2, 18, "ordered"),
    "trio": (3, 18, "strict"),
    "trifecta": (3, 18, "ordered"),
}


class LedgerError(ValueError):
    """A ledger, ledger line or purchase input that breaks the ADR-046 format."""


@dataclass(frozen=True)
class Purchase:
    """One recorded actual purchase."""

    race_id: str
    bet_type: LedgerBetType
    selection: str
    stake_yen: int
    recorded_at: datetime

    def __post_init__(self) -> None:
        _race_id(self.race_id)
        if self.bet_type not in BET_TYPES:
            raise LedgerError(f"bet_type must be one of {', '.join(BET_TYPES)}")
        _selection(self.bet_type, self.selection)
        stake = self.stake_yen
        if isinstance(stake, bool) or not isinstance(stake, int) or stake <= 0:
            raise LedgerError("stake_yen must be a positive integer")
        if stake % _UNIT_YEN:
            raise LedgerError("stake_yen must be a multiple of 100 yen")
        _aware(self.recorded_at)

    @property
    def race_year(self) -> int:
        """Return the calendar year of the race date."""
        return int(self.race_id[:4])


@dataclass(frozen=True)
class PurchaseLedger:
    """A checked ledger: its bytes' SHA-256, purchases and confirmation times."""

    sha256: str
    purchases: tuple[Purchase, ...]
    confirmations: tuple[datetime, ...]

    def race_spent_yen(self, race_id: str) -> int:
        """Return the recorded stakes of one race."""
        return sum(item.stake_yen for item in self.purchases if item.race_id == race_id)

    def annual_spent_yen(self, year: int) -> int:
        """Return the recorded stakes of every race dated in ``year``."""
        return sum(item.stake_yen for item in self.purchases if item.race_year == year)

    @property
    def latest_confirmation(self) -> datetime | None:
        """Return the last confirmation time, or None when nothing was confirmed."""
        return self.confirmations[-1] if self.confirmations else None


def new_ledger() -> bytes:
    """Return the bytes of an empty ledger (its header line only)."""
    return _line(
        {"format": LEDGER_FORMAT, "format_version": LEDGER_FORMAT_VERSION, "kind": "header"}
    )


def parse_ledger(data: bytes) -> PurchaseLedger:
    """Check ledger bytes strictly and return their purchases and confirmations.

    Raises:
        LedgerError: If the bytes break any rule of the ADR-046 format.
    """
    if not data:
        raise LedgerError("the ledger is empty")
    if not data.endswith(b"\n"):
        raise LedgerError("the ledger's last line is incomplete")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise LedgerError("the ledger must be ASCII") from exc
    if "\r" in text:
        raise LedgerError("the ledger must use LF line endings")
    lines = text[:-1].split("\n")
    header = _object(lines[0], 1)
    if set(header) != _HEADER_KEYS or header.get("kind") != "header":
        raise LedgerError("line 1 must be the ledger header")
    if (
        header["format"] != LEDGER_FORMAT
        or type(header["format_version"]) is not int
        or header["format_version"] != LEDGER_FORMAT_VERSION
    ):
        raise LedgerError("the ledger is not purchase_ledger format_version 1")
    purchases: list[Purchase] = []
    confirmations: list[datetime] = []
    previous: datetime | None = None
    for number, line in enumerate(lines[1:], start=2):
        entry = _object(line, number)
        kind = entry.get("kind")
        if kind == "purchase":
            if set(entry) != _PURCHASE_KEYS:
                raise LedgerError(f"line {number}: a purchase has exactly {sorted(_PURCHASE_KEYS)}")
            recorded_at = _clock(entry["recorded_at"], number)
            try:
                purchase = Purchase(
                    race_id=cast(str, entry["race_id"]),
                    bet_type=cast(LedgerBetType, entry["bet_type"]),
                    selection=cast(str, entry["selection"]),
                    stake_yen=cast(int, entry["stake_yen"]),
                    recorded_at=recorded_at,
                )
            except LedgerError as exc:
                raise LedgerError(f"line {number}: {exc}") from exc
            purchases.append(purchase)
        elif kind == "confirmation":
            if set(entry) != _CONFIRMATION_KEYS:
                raise LedgerError(
                    f"line {number}: a confirmation has exactly {sorted(_CONFIRMATION_KEYS)}"
                )
            recorded_at = _clock(entry["recorded_at"], number)
            confirmations.append(recorded_at)
        else:
            raise LedgerError(f"line {number}: kind must be purchase or confirmation")
        if previous is not None and recorded_at < previous:
            raise LedgerError(f"line {number}: recorded_at must not decrease")
        previous = recorded_at
    return PurchaseLedger(
        sha256=hashlib.sha256(data).hexdigest(),
        purchases=tuple(purchases),
        confirmations=tuple(confirmations),
    )


def append_entries(data: bytes, purchases: Sequence[Purchase], *, confirmed_at: datetime) -> bytes:
    """Return ``data`` with each purchase line and one closing confirmation line.

    Raises:
        LedgerError: If ``data`` is not a valid ledger, ``confirmed_at`` is naive or
            earlier than the ledger's last time, or a purchase's ``recorded_at``
            differs from ``confirmed_at``.
    """
    ledger = parse_ledger(data)
    _aware(confirmed_at)
    last = max(
        (*(item.recorded_at for item in ledger.purchases), *ledger.confirmations),
        default=None,
    )
    if last is not None and confirmed_at < last:
        raise LedgerError("confirmed_at is earlier than the ledger's last entry")
    lines = [data]
    for purchase in purchases:
        if purchase.recorded_at != confirmed_at:
            raise LedgerError("every purchase must be recorded at confirmed_at")
        lines.append(
            _line(
                {
                    "kind": "purchase",
                    "race_id": purchase.race_id,
                    "bet_type": purchase.bet_type,
                    "selection": purchase.selection,
                    "stake_yen": purchase.stake_yen,
                    "recorded_at": _iso(purchase.recorded_at),
                }
            )
        )
    lines.append(_line({"kind": "confirmation", "recorded_at": _iso(confirmed_at)}))
    result = b"".join(lines)
    parse_ledger(result)
    return result


def parse_bet(text: str, *, recorded_at: datetime) -> Purchase:
    """Parse ``<race_id>:<bet_type>:<selection>:<stake_yen>`` into a purchase.

    Raises:
        LedgerError: If the text does not have four fields or a field is invalid.
    """
    fields = text.split(":")
    if len(fields) != 4:
        raise LedgerError("a bet must be <race_id>:<bet_type>:<selection>:<stake_yen>")
    race_id, bet_type, selection, stake = fields
    if not stake.isascii() or not stake.isdigit():
        raise LedgerError("stake_yen must be written in decimal digits")
    return Purchase(
        race_id=race_id,
        bet_type=cast(LedgerBetType, bet_type),
        selection=selection,
        stake_yen=int(stake),
        recorded_at=recorded_at,
    )


def required_confirmed_since(race_day: date, earlier_sales_closes: Iterable[datetime]) -> datetime:
    """Return the time a race's latest confirmation must reach.

    It is the latest sales close among the day's earlier-starting graded races, or
    the race day's midnight (JST) when that is later or there is none.

    Raises:
        LedgerError: If a sales close is naive.
    """
    since = datetime.combine(race_day, time(0), tzinfo=JST)
    for close in earlier_sales_closes:
        _aware(close)
        since = max(since, close)
    return since


def _race_id(value: object) -> None:
    if not isinstance(value, str) or len(value) != 16 or not value.isascii() or not value.isdigit():
        raise LedgerError("race_id must be 16 digits")
    try:
        datetime.strptime(value[:8], "%Y%m%d")
    except ValueError as exc:
        raise LedgerError("race_id must start with a real YYYYMMDD date") from exc
    venue, kaiji, nichiji, race = (int(value[i : i + 2]) for i in (8, 10, 12, 14))
    if not 1 <= venue <= 10:
        raise LedgerError("race_id venue must be 01 to 10")
    if kaiji < 1 or nichiji < 1:
        raise LedgerError("race_id meeting and day must be 01 or more")
    if not 1 <= race <= 12:
        raise LedgerError("race_id race number must be 01 to 12")


def _selection(bet_type: str, value: object) -> None:
    count, highest, order = _SELECTION_RULES[bet_type]
    if not isinstance(value, str):
        raise LedgerError("selection must be a string")
    parts = value.split("-")
    if len(parts) != count or any(
        len(part) != 2 or not part.isascii() or not part.isdigit() for part in parts
    ):
        raise LedgerError(f"{bet_type} selection must be {count} two-digit numbers joined by '-'")
    numbers = [int(part) for part in parts]
    if any(not 1 <= number <= highest for number in numbers):
        raise LedgerError(f"{bet_type} selection numbers must be 01 to {highest:02d}")
    pairs = list(pairwise(numbers))
    if order == "strict" and any(left >= right for left, right in pairs):
        raise LedgerError(f"{bet_type} selection must be in strictly ascending order")
    if order == "loose" and any(left > right for left, right in pairs):
        raise LedgerError(f"{bet_type} selection must be in ascending order")
    if order == "ordered" and len(set(numbers)) != len(numbers):
        raise LedgerError(f"{bet_type} selection numbers must differ")


def _object(line: str, number: int) -> dict[str, object]:
    if not line:
        raise LedgerError(f"line {number} is empty")
    try:
        value = json.loads(line, object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise LedgerError(f"line {number} is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"line {number} must be a JSON object")
    if json.dumps(value, sort_keys=True, ensure_ascii=True) != line:
        raise LedgerError(
            f"line {number} is not in the canonical form: sorted keys, the separators ', ' "
            "and ': ', no other whitespace, and default number and string forms (e.g. 1000)"
        )
    return cast(dict[str, object], value)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"{value} is not allowed")


def _clock(value: object, number: int) -> datetime:
    if not isinstance(value, str):
        raise LedgerError(f"line {number}: recorded_at must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"line {number}: recorded_at must be ISO 8601") from exc
    if parsed.utcoffset() is None:
        raise LedgerError(f"line {number}: recorded_at must be timezone-aware")
    return parsed


def _aware(value: object) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise LedgerError("times must be timezone-aware datetimes")


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _line(value: dict[str, object]) -> bytes:
    text = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    return (text + "\n").encode("ascii")


__all__ = [
    "BET_TYPES",
    "LEDGER_FORMAT",
    "LEDGER_FORMAT_VERSION",
    "LedgerBetType",
    "LedgerError",
    "Purchase",
    "PurchaseLedger",
    "append_entries",
    "new_ledger",
    "parse_bet",
    "parse_ledger",
    "required_confirmed_since",
]
