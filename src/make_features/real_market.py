"""Interpret published O1 win quotes without inventing reception timestamps."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

MARKET_IMPLEMENTATION = "published_win_market_v1"
MARKET_COLUMN = "market_characteristics__market_win_odds"
RECEPTION_BASIS = "assumed_received_at_publication"
O1_TABLE = "ARCHIVE_O1_ODDS_TANFUKUWAKU"
RA_TABLE = "NL_RA_RACE"
SE_TABLE = "NL_SE_RACE_UMA"
KEY_COLUMNS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
WIN_COLUMNS = tuple(
    f"OddsTansyoInfo{i}{suffix}" for i in range(28) for suffix in ("Umaban", "Odds")
)
O1_COLUMNS = (*KEY_COLUMNS, "headDataKubun", "headMakeDate", "HappyoTime", *WIN_COLUMNS)
RA_COLUMNS = (
    *KEY_COLUMNS,
    "headDataKubun",
    "headMakeDate",
    "HassoTime",
    "SyussoTosu",
    "NyusenTosu",
)
SE_COLUMNS = (
    *KEY_COLUMNS,
    "headDataKubun",
    "headMakeDate",
    "Umaban",
    "KakuteiJyuni",
    "IJyoCD",
    "DochakuKubun",
)
JST = ZoneInfo("Asia/Tokyo")


def canonical_hash(value: object) -> str:
    """Hash the exact JSON-compatible selected source or manifest."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def timestamp(value: object) -> datetime:
    """Require an aware external timestamp; never infer an unknown clock."""
    if not isinstance(value, str):
        raise ValueError("an aware ISO timestamp is required")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("an aware ISO timestamp is required")
    return result


def race_key(race_id: object) -> tuple[str, ...]:
    """Read the repository's complete 16-digit race identity."""
    if not isinstance(race_id, str) or re.fullmatch(r"[0-9]{16}", race_id) is None:
        raise ValueError("race_id must contain the complete 16-digit race key")
    datetime.strptime(race_id[:8], "%Y%m%d")
    return (
        race_id[:4],
        race_id[4:8],
        race_id[8:10],
        race_id[10:12],
        race_id[12:14],
        race_id[14:16],
    )


def validate_market_settings(value: object) -> dict[str, object]:
    """Keep this one-column implementation independent from all-group settings."""
    if not isinstance(value, dict) or set(value) != {
        "freeze_offset_seconds",
        "reception_basis",
        "schedule_basis",
    }:
        raise ValueError(
            "published market settings require explicit freeze, reception and schedule bases"
        )
    if type(value["freeze_offset_seconds"]) is not int or value["freeze_offset_seconds"] != 300:
        raise ValueError("freeze_offset_seconds must be 300")
    if value["reception_basis"] != RECEPTION_BASIS:
        raise ValueError("reception_basis must explicitly assume receipt at publication")
    if value["schedule_basis"] not in {"provided_schedule_evidence", "assumed_stored_schedule"}:
        raise ValueError(
            "schedule_basis must explicitly select provided evidence or stored schedule assumption"
        )
    return dict(value)


def validate_races(value: object) -> tuple[dict[str, object], ...]:
    """Require an explicit, unique manifest rather than selecting races silently."""
    if not isinstance(value, list) or not value or any(not isinstance(r, dict) for r in value):
        raise ValueError("manifest requires a nonempty races list")
    races = cast(list[dict[str, object]], value)
    identities = [r.get("race_id") for r in races]
    for identity in identities:
        race_key(identity)
    if len(set(cast(list[str], identities))) != len(races):
        raise ValueError("duplicate manifest race_id")
    return tuple(races)


def schedule(
    race: Mapping[str, object], settings: Mapping[str, object], row: Mapping[str, object] | None
) -> tuple[datetime, datetime]:
    """Validate the five-minute boundary against explicit schedule provenance."""
    race_id = cast(str, race["race_id"])
    start = timestamp(race.get("scheduled_start_at"))
    freeze = timestamp(race.get("freeze_at"))
    if start.astimezone(JST).strftime("%Y%m%d") != race_id[:8] or start - freeze != timedelta(
        seconds=300
    ):
        raise ValueError(f"{race_id}: freeze must be scheduled_start_at minus 300 seconds")
    if settings["schedule_basis"] == "provided_schedule_evidence":
        if (
            not isinstance(race.get("schedule_source"), str)
            or not race["schedule_source"]
            or timestamp(race.get("schedule_known_at")) > freeze
        ):
            raise ValueError(f"{race_id}: schedule must be known by freeze with an explicit source")
    else:
        if (
            race.get("schedule_known_at") is not None
            or row is None
            or row.get("HassoTime") != start.astimezone(JST).strftime("%H%M")
        ):
            raise ValueError(
                f"{race_id}: assumed stored schedule must match RA and keep schedule_known_at null"
            )
    return start, freeze


def publication(row: Mapping[str, object]) -> datetime:
    """O1 MMDDHHmm is an intermediate publication clock, with race-key year."""
    value = row.get("HappyoTime")
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{8}", value) is None:
        raise ValueError("intermediate O1 requires a valid HappyoTime")
    try:
        return datetime.strptime(str(row["idYear"]) + value, "%Y%m%d%H%M").replace(tzinfo=JST)
    except ValueError as exc:
        raise ValueError("intermediate O1 requires a valid HappyoTime") from exc


def latest_o1(rows: Sequence[dict[str, object]], race: Mapping[str, object]) -> dict[str, object]:
    """Choose latest intermediate publication at or before the explicit freeze."""
    key = race_key(race["race_id"])
    freeze = timestamp(race.get("freeze_at"))
    candidates: dict[datetime, dict[str, dict[str, object]]] = {}
    for row in rows:
        if tuple(row.get(k) for k in KEY_COLUMNS) != key or row.get("headDataKubun") != "1":
            continue
        at = publication(row)
        if at <= freeze:
            candidates.setdefault(at, {})[canonical_hash(row)] = row
    if not candidates:
        raise ValueError(f"{race['race_id']}: no intermediate O1 publication at or before freeze")
    if any(len(versions) != 1 for versions in candidates.values()):
        raise ValueError(
            f"{race['race_id']}: conflicting intermediate O1 rows at the same publication"
        )
    return next(iter(candidates[max(candidates)].values()))


def win_quotes(row: Mapping[str, object]) -> tuple[tuple[str, float | None, str | None], ...]:
    """Preserve native nulls and sentinel reasons; no terminal-odds substitution."""
    values: dict[str, tuple[str, float | None, str | None]] = {}
    special = {
        "0000": "no_votes",
        "----": "cancelled_before_sale",
        "****": "cancelled_after_sale",
        "9999": "upper_censored",
    }
    for i in range(28):
        horse, raw = row.get(f"OddsTansyoInfo{i}Umaban"), row.get(f"OddsTansyoInfo{i}Odds")
        if horse in (None, "", "  ", "00"):
            if raw not in (None, "", "    ", "0000"):
                raise ValueError("O1 quote without a horse number")
            continue
        if (
            not isinstance(horse, str)
            or re.fullmatch(r"[0-9]{2}", horse) is None
            or not 1 <= int(horse) <= 28
            or horse in values
        ):
            raise ValueError("O1 requires unique valid horse numbers")
        reason = (
            "source_null"
            if raw is None
            else "not_registered"
            if raw in ("", "    ")
            else special.get(cast(str, raw))
        )
        if reason is not None:
            values[horse] = (horse, None, reason)
        elif isinstance(raw, str) and re.fullmatch(r"[0-9]{4}", raw) and int(raw) >= 10:
            values[horse] = (horse, int(raw) / 10, None)
        else:
            raise ValueError(f"invalid O1 win odds encoding for horse {horse}")
    if not values:
        raise ValueError("intermediate O1 has no horse set")
    return tuple(values[h] for h in sorted(values))
