"""Pure JV-Data 4.9.0.1 field interpretation for explicitly assumed reference input."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, time, timedelta
from itertools import chain
from typing import cast

from make_features.contracts.observations import (
    CardRunner,
    Conditions,
    HistoricalRace,
    HistoricalRunner,
    ReferenceEvidence,
    Section,
    Workout,
)
from make_features.real_market import (
    JST,
    KEY_COLUMNS,
    O1_COLUMNS,
    RA_COLUMNS,
    SE_COLUMNS,
    canonical_hash,
    race_key,
)
from make_features.validation.observations import validate_race

O2_TABLE = "ARCHIVE_O2_ODDS_UMAREN"
HC_TABLE = "NL_HC_HANRO"
WC_TABLE = "NL_WC_WOOD"
UM_TABLE = "NL_UM_UMA"
CARD_RA_COLUMNS = (*KEY_COLUMNS, "headMakeDate", "HassoTime", "Kyori", "TrackCD", "CourseKubunCD")
CARD_SE_COLUMNS = (
    *KEY_COLUMNS,
    "headMakeDate",
    "KettoNum",
    "Umaban",
    "Wakuban",
    "Barei",
    "SexCD",
    "Futan",
    "KisyuCode",
    "ChokyosiCode",
)
HISTORY_RA_COLUMNS = tuple(
    dict.fromkeys(
        (
            *RA_COLUMNS,
            *CARD_RA_COLUMNS,
            "TenkoBabaSibaBabaCD",
            "TenkoBabaDirtBabaCD",
            "HaronTimeL3",
            *(f"LapTime{i}" for i in range(25)),
        )
    )
)
HISTORY_SE_COLUMNS = tuple(
    dict.fromkeys(
        (*SE_COLUMNS, *CARD_SE_COLUMNS, "Time", "TimeDiff", "HaronTimeL3", "Jyuni4c", "BaTaijyu")
    )
)
MARKET_O1_COLUMNS = (
    *O1_COLUMNS,
    "TotalHyosuTansyo",
    "TotalHyosuFukusyo",
    "TotalHyosuWakuren",
    *(
        f"OddsFukusyoInfo{i}{suffix}"
        for i in range(28)
        for suffix in ("Umaban", "OddsLow", "OddsHigh")
    ),
)
MARKET_O2_COLUMNS = (
    *KEY_COLUMNS,
    "headDataKubun",
    "headMakeDate",
    "HappyoTime",
    "TotalHyosuUmaren",
    *(f"OddsUmarenInfo{i}{suffix}" for i in range(153) for suffix in ("Kumi", "Odds")),
)
WORKOUT_KEYS = (
    "headMakeDate",
    "headDataKubun",
    "TresenKubun",
    "ChokyoDate",
    "ChokyoTime",
    "KettoNum",
)
HC_COLUMNS = (*WORKOUT_KEYS, *(f"LapTime{i}" for i in range(1, 5)))
WC_COLUMNS = (*WORKOUT_KEYS, "Course", "BabaAround", *(f"LapTime{i}" for i in range(1, 11)))
UM_COLUMNS = ("KettoNum", "headMakeDate", "Ketto3Info0HansyokuNum", "Ketto3Info4HansyokuNum")


def text(row: Mapping[str, object], name: str) -> str | None:
    """Trim format padding while retaining raw source values separately."""
    value = row.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name}: expected a nullable raw string")
    return value.strip() or None


def identifier(row: Mapping[str, object], name: str) -> str | None:
    value = text(row, name)
    return None if value is None or set(value) == {"0"} else value


def positive_integer(row: Mapping[str, object], name: str) -> int | None:
    value = text(row, name)
    if value is None or set(value) == {"0"}:
        return None
    if re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError(f"{name}: invalid positive integer encoding")
    return int(value)


def measured_tenths(row: Mapping[str, object], name: str) -> float | None:
    value = text(row, name)
    if value is None or set(value) in ({"0"}, {"9"}):
        return None
    number = positive_integer(row, name)
    return number / 10 if number is not None else None


def race_identity(row: Mapping[str, object]) -> str:
    values = [row.get(key) for key in KEY_COLUMNS]
    if any(not isinstance(v, str) for v in values):
        raise ValueError("incomplete raw race key")
    result = "".join(cast(list[str], values))
    race_key(result)
    return result


def validate_reference_projections(
    tables: object, *, label_results: Sequence[Mapping[str, object]] = ()
) -> None:
    """Require shared physical RA/SE rows to agree on every overlapping raw column."""
    if not isinstance(tables, Mapping):
        raise ValueError("reference input requires raw table projections")
    for kind in ("ra", "se"):
        projections = [
            _projected_rows(tables.get(f"{role}_{kind}")) for role in ("history", "target", "label")
        ]
        projections.extend(
            _projected_rows([result.get("ra")] if kind == "ra" else result.get("se"))
            for result in label_results
        )
        seen: dict[tuple[str, ...], dict[str, object]] = {}
        for row in chain.from_iterable(projections):
            key = race_key(race_identity(row))
            if key != tuple(row.get(column) for column in KEY_COLUMNS):
                raise ValueError("incomplete raw race key components")
            if kind == "se":
                horse = identifier(row, "KettoNum")
                if horse is None:
                    raise ValueError("incomplete raw SE horse key")
                key = (*key, horse)
            shared = seen.setdefault(key, {})
            for column, value in row.items():
                if column in shared and (
                    type(value) is not type(shared[column]) or value != shared[column]
                ):
                    raise ValueError(f"conflicting shared raw {kind.upper()} column: {column}")
                shared[column] = value


def _projected_rows(value: object) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("reference input requires raw row projections")
    return cast(Sequence[Mapping[str, object]], value)


def scheduled_start(row: Mapping[str, object]) -> datetime:
    identity = race_identity(row)
    clock = text(row, "HassoTime")
    if clock is None or clock == "0000" or re.fullmatch(r"[0-9]{4}", clock) is None:
        raise ValueError("stored HassoTime is missing or invalid")
    return datetime.strptime(identity[:8] + clock, "%Y%m%d%H%M").replace(tzinfo=JST)


def result_boundary(start: datetime, days: int) -> datetime:
    """Use results after the whole declared delay date, not at an invented receipt."""
    return datetime.combine(start.astimezone(JST).date() + timedelta(days=days + 1), time.min, JST)


def evidence(
    observation_id: str,
    source: str,
    raw: object,
    *,
    event: datetime,
    usable: datetime,
    basis: str,
    event_basis: str,
    published: datetime | None = None,
) -> ReferenceEvidence:
    return ReferenceEvidence(
        observation_id,
        source,
        1,
        canonical_hash(raw),
        published,
        None,
        event,
        usable,
        basis,
        event_basis,
    )


def conditions(row: Mapping[str, object], *, target: bool) -> Conditions:
    distance = positive_integer(row, "Kyori")
    if distance is None:
        raise ValueError("race distance is required")
    track = text(row, "TrackCD")
    surface = (
        "turf"
        if track in {str(i) for i in range(10, 23)}
        else "dirt"
        if track in {"23", "24"}
        else "jump"
        if track in {str(i) for i in range(51, 60)}
        else None
    )
    if surface is None:
        raise ValueError(f"unsupported TrackCD: {track}")
    going = (
        None
        if target or surface == "jump"
        else identifier(
            row, "TenkoBabaSibaBabaCD" if surface in {"turf", "jump"} else "TenkoBabaDirtBabaCD"
        )
    )
    course = f"{row['idJyoCD']}:{track}:{text(row, 'CourseKubunCD') or 'unspecified'}"
    return Conditions(distance, surface, cast(str, row["idJyoCD"]), course, going, None)


def card_runner(row: Mapping[str, object]) -> CardRunner:
    horse = identifier(row, "KettoNum")
    number = identifier(row, "Umaban")
    if horse is None or number is None:
        raise ValueError("card requires permanent KettoNum and Umaban mapping")
    return CardRunner(
        horse,
        number,
        positive_integer(row, "Wakuban"),
        positive_integer(row, "Barei"),
        {"1": "male", "2": "female", "3": "gelding"}.get(cast(str, row.get("SexCD"))),
        measured_tenths(row, "Futan"),
        identifier(row, "KisyuCode"),
        identifier(row, "ChokyosiCode"),
        True,
    )


def normal_result(
    ra: Mapping[str, object], runners: Sequence[dict[str, object]], *, days: int
) -> tuple[str, datetime, dict[str, int], dict[str, object]]:
    """Validate whole-race eligibility without silently dropping abnormal horses."""
    identity = race_identity(ra)
    start = scheduled_start(ra)
    usable = result_boundary(start, days)
    if ra.get("headDataKubun") != "7" or not runners:
        raise ValueError("not_final_normal_result")
    finishes: dict[str, int] = {}
    numbers: set[str] = set()
    for row in runners:
        horse, number, finish = (
            identifier(row, "KettoNum"),
            identifier(row, "Umaban"),
            positive_integer(row, "KakuteiJyuni"),
        )
        if (
            race_identity(row) != identity
            or row.get("headDataKubun") != "7"
            or row.get("IJyoCD") != "0"
            or row.get("DochakuKubun") != "0"
        ):
            raise ValueError("non_normal_or_tied_result")
        if (
            horse is None
            or number is None
            or finish is None
            or horse in finishes
            or number in numbers
        ):
            raise ValueError("duplicate_or_missing_result_identity")
        finishes[horse] = finish
        numbers.add(number)
    if sorted(finishes.values()) != list(range(1, len(runners) + 1)) or any(
        positive_integer(ra, field) != len(runners) for field in ("SyussoTosu", "NyusenTosu")
    ):
        raise ValueError("noncontiguous_or_incomplete_result")
    for source_row in (ra, *runners):
        made = text(source_row, "headMakeDate")
        if made is None or re.fullmatch(r"[0-9]{8}", made) is None:
            raise ValueError("result_creation_date_missing")
        date_made = datetime.strptime(made, "%Y%m%d").date()
        if date_made < start.date() or date_made >= usable.date():
            raise ValueError("result_created_after_declared_use_date")
    raw: dict[str, object] = {
        "ra": dict(ra),
        "se": sorted(runners, key=lambda r: str(r.get("Umaban"))),
    }
    return identity, usable, finishes, raw


def historical_race(
    ra: Mapping[str, object], runners: Sequence[dict[str, object]], *, days: int
) -> HistoricalRace:
    identity, usable, _, raw = normal_result(ra, runners, days=days)
    start, cond = scheduled_start(ra), conditions(ra, target=False)
    measured_runners = []
    for row in sorted(runners, key=lambda r: str(r["Umaban"])):
        duration = text(row, "Time")
        elapsed = None
        if duration and set(duration) not in ({"0"}, {"9"}):
            if re.fullmatch(r"[0-9]{4}", duration) is None or int(duration[1:3]) >= 60:
                raise ValueError("invalid minute-second-tenth race Time")
            elapsed = int(duration[0]) * 60 + int(duration[1:3]) + int(duration[3]) / 10
        gap_raw = text(row, "TimeDiff")
        gap = None
        if gap_raw and gap_raw != "9999":
            if re.fullmatch(r"[+-][0-9]{3}", gap_raw) is None:
                raise ValueError("invalid signed TimeDiff encoding")
            gap = int(gap_raw) / 10
        last = measured_tenths(row, "HaronTimeL3")
        body = positive_integer(row, "BaTaijyu")
        body_weight = float(body) if body is not None and 2 <= body <= 998 else None
        values: dict[str, object] = {
            "elapsed_sec": elapsed,
            "signed_gap_sec": gap,
            "last3f_sec": last,
            "last3f_distance_m": 600 if last is not None else None,
            "corner4": positive_integer(row, "Jyuni4c"),
            "body_weight_kg": body_weight,
            "carried_weight_kg": measured_tenths(row, "Futan"),
            "jockey_id": identifier(row, "KisyuCode"),
            "trainer_id": identifier(row, "ChokyosiCode"),
        }
        reasons = {
            name: "source_unmeasured_or_special_value"
            for name, value in values.items()
            if value is None
        }
        measured_runners.append(
            HistoricalRunner(
                cast(str, row["KettoNum"]),
                cast(int, positive_integer(row, "KakuteiJyuni")),
                "normal",
                cast(str | None, values["jockey_id"]),
                cast(str | None, values["trainer_id"]),
                elapsed,
                gap,
                last,
                cast(int | None, values["last3f_distance_m"]),
                cast(int | None, values["corner4"]),
                body_weight,
                cast(float | None, values["carried_weight_kg"]),
                reasons,
            )
        )
    distances = [cond.distance_m % 200] if cond.distance_m % 200 else []
    distances += [200] * (cond.distance_m // 200)
    if len(distances) > 25:
        raise ValueError("race distance exceeds available measured lap slots")
    sections = tuple(
        Section(distance, measured_tenths(ra, f"LapTime{i}"))
        for i, distance in enumerate(distances)
    )
    last = measured_tenths(ra, "HaronTimeL3")
    result = HistoricalRace(
        identity,
        start,
        cond,
        tuple(measured_runners),
        tuple(r.horse_id for r in measured_runners),
        True,
        sections,
        last,
        600 if last is not None else None,
        evidence(
            f"result:{identity}",
            "JV-Data:RA+SE",
            raw,
            event=start,
            usable=usable,
            basis="assumed_snapshot_results_revision_time_unverified",
            event_basis="assumed_stored_scheduled_start_as_historical_event_lower_bound",
        ),
    )
    validate_race(result)
    return result


def workout(row: Mapping[str, object], *, kind: str) -> Workout:
    day, clock = text(row, "ChokyoDate"), text(row, "ChokyoTime")
    if (
        day is None
        or clock is None
        or re.fullmatch(r"[0-9]{8}", day) is None
        or re.fullmatch(r"[0-9]{4}", clock) is None
    ):
        raise ValueError("workout requires an actual date and event time")
    event = datetime.strptime(day + clock, "%Y%m%d%H%M").replace(tzinfo=JST)
    facility = {"0": "miho", "1": "ritto"}.get(cast(str, row.get("TresenKubun")))
    horse = identifier(row, "KettoNum")
    if facility is None or horse is None:
        raise ValueError("workout requires a known facility and horse")
    course, turn = None, None
    count = 4
    if kind == "wc":
        course = {str(i): chr(ord("A") + i) for i in range(5)}.get(cast(str, row.get("Course")))
        turn = {"0": "right", "1": "left"}.get(cast(str, row.get("BabaAround")))
        if course is None or turn is None:
            raise ValueError("unknown wood course or turn")
        count = 10 if facility == "miho" else 9
    sections = tuple(Section(200, measured_tenths(row, f"LapTime{i}")) for i in range(count, 0, -1))
    usable = datetime.combine(event.date() + timedelta(days=1), time.min, JST)
    identity = f"{kind}:{facility}:{day}:{clock}:{horse}"
    return Workout(
        horse,
        kind,
        facility,
        course,
        turn,
        sections,
        evidence(
            identity,
            f"JV-Data:{kind}",
            dict(row),
            event=event,
            usable=usable,
            basis="previous_day_sessions_assumed_available_revision_unverified",
            event_basis="actual_workout_date_and_time",
        ),
    )
