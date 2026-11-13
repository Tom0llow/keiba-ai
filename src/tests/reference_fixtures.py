"""Small explicit raw projections; trial configuration is never a learned optimum."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from configuration.reference_input import load_reference_input_config
from make_features.catalog.registry import FeatureRegistry
from make_features.real_market import (
    JST,
    KEY_COLUMNS,
    O1_TABLE,
    RA_TABLE,
    SE_TABLE,
    canonical_hash,
)
from make_features.reference_raw import (
    CARD_RA_COLUMNS,
    CARD_SE_COLUMNS,
    HC_COLUMNS,
    HC_TABLE,
    HISTORY_RA_COLUMNS,
    HISTORY_SE_COLUMNS,
    MARKET_O1_COLUMNS,
    MARKET_O2_COLUMNS,
    O2_TABLE,
    UM_TABLE,
    WC_COLUMNS,
    WC_TABLE,
)
from models.serialization.reference_datamart import (
    MarketRows,
    PreparedTargets,
    ReferenceDatamartBuilder,
    ReferenceYearOutput,
    workout_window,
)

ROOT = Path(__file__).resolve().parents[2]


def key(day: date, race: str = "09") -> dict[str, object]:
    return dict(
        zip(KEY_COLUMNS, (str(day.year), day.strftime("%m%d"), "01", "01", "01", race), strict=True)
    )


def race_rows(
    day: date, *, offset: int = 0, race_number: str = "09"
) -> tuple[dict[str, object], list[dict[str, object]]]:
    ra: dict[str, object] = dict.fromkeys(HISTORY_RA_COLUMNS)
    ra.update(key(day, race_number))
    made = (day + timedelta(days=1)).strftime("%Y%m%d")
    ra.update(
        headDataKubun="7",
        headMakeDate=made,
        HassoTime="1500",
        Kyori="1600",
        TrackCD="11",
        CourseKubunCD="A ",
        SyussoTosu="04",
        NyusenTosu="04",
        TenkoBabaSibaBabaCD="1",
        HaronTimeL3="360",
    )
    for i in range(8):
        ra[f"LapTime{i}"] = "132"
    se = []
    for i in range(1, 5):
        row: dict[str, object] = dict.fromkeys(HISTORY_SE_COLUMNS)
        row.update(key(day, race_number))
        row.update(
            headDataKubun="7",
            headMakeDate=made,
            KettoNum=f"202010{i + offset:04d}",
            Umaban=f"{i:02d}",
            Wakuban=f"{i:01d}",
            Barei="04",
            SexCD="1",
            Futan="570",
            KisyuCode=f"{i:05d}",
            ChokyosiCode="00011",
            KakuteiJyuni=f"{i:02d}",
            IJyoCD="0",
            DochakuKubun="0",
            Time=f"1{45 + i - 1:02d}6",
            TimeDiff="-001" if i == 1 else f"+{i:03d}",
            HaronTimeL3=f"{350 + i * 10:03d}",
            Jyuni4c=f"{i:02d}",
            BaTaijyu=f"{480 + i * 2:03d}",
        )
        se.append(row)
    return ra, se


def markets(
    day: date, *, clock: str, total: int, race_number: str = "09"
) -> tuple[dict[str, object], dict[str, object]]:
    o1: dict[str, object] = dict.fromkeys(MARKET_O1_COLUMNS)
    o2: dict[str, object] = dict.fromkeys(MARKET_O2_COLUMNS)
    for row in (o1, o2):
        row.update(key(day, race_number))
        row.update(
            headDataKubun="1",
            headMakeDate=day.strftime("%Y%m%d"),
            HappyoTime=day.strftime("%m%d") + clock,
        )
    for i in range(4):
        for prefix in ("OddsTansyoInfo", "OddsFukusyoInfo"):
            o1[f"{prefix}{i}Umaban"] = f"{i + 1:02d}"
        o1[f"OddsTansyoInfo{i}Odds"] = f"{20 + i * 10:04d}"
        o1[f"OddsFukusyoInfo{i}OddsLow"] = "0011"
        o1[f"OddsFukusyoInfo{i}OddsHigh"] = "0020"
    for name in ("TotalHyosuTansyo", "TotalHyosuFukusyo", "TotalHyosuWakuren"):
        o1[name] = str(total)
    o2["TotalHyosuUmaren"] = str(total)
    for index, (a, b) in enumerate(combinations(range(1, 5), 2)):
        o2[f"OddsUmarenInfo{index}Kumi"] = f"{a:02d}{b:02d}"
        o2[f"OddsUmarenInfo{index}Odds"] = "000120"
    return o1, o2


def raw_input(
    days: tuple[date, ...] = (date(2026, 9, 6),), *, labels: bool = False
) -> dict[str, object]:
    config = load_reference_input_config(
        ROOT / "configs/reference_input", config_name="trial", overrides=["processed_root=unused"]
    )
    tables: dict[str, list[dict[str, object]]] = {
        name: []
        for name in (
            "history_ra",
            "history_se",
            "target_ra",
            "target_se",
            "label_ra",
            "label_se",
            "o1",
            "o2",
            "hc",
            "wc",
            "um",
        )
    }
    for day in (date(2026, 8, 1), date(2026, 8, 15), date(2026, 8, 29)):
        for offset, number in ((0, "09"), (4, "10")):
            ra, se = race_rows(day, offset=offset, race_number=number)
            tables["history_ra"].append(ra)
            tables["history_se"].extend(se)
    races = []
    for day in days:
        ra, se = race_rows(day)
        identity = "".join(cast(str, ra[k]) for k in KEY_COLUMNS)
        races.append(
            {
                "race_id": identity,
                "scheduled_start_at": f"{day}T15:00:00+09:00",
                "freeze_at": f"{day}T14:55:00+09:00",
                "schedule_known_at": None,
            }
        )
        tables["target_ra"].append({k: ra[k] for k in CARD_RA_COLUMNS})
        tables["target_se"].extend({k: r[k] for k in CARD_SE_COLUMNS} for r in se)
        if labels:
            tables["label_ra"].append(ra)
            tables["label_se"].extend(se)
        for clock, total in (("1444", 1000), ("1454", 2000)):
            o1, o2 = markets(day, clock=clock, total=total)
            tables["o1"].append(o1)
            tables["o2"].append(o2)
        workout_day = day - timedelta(days=1)
        for i in range(1, 6):
            for kind, columns in (("hc", HC_COLUMNS), ("wc", WC_COLUMNS)):
                row: dict[str, object] = dict.fromkeys(columns)
                row.update(
                    headDataKubun="1",
                    headMakeDate="20261031",
                    TresenKubun="0",
                    ChokyoDate=workout_day.strftime("%Y%m%d"),
                    ChokyoTime="0600",
                    KettoNum=f"202010{i:04d}",
                )
                if kind == "wc":
                    row.update(Course="0", BabaAround="0")
                for section in range(1, 5):
                    row[f"LapTime{section}"] = "120" if i <= 4 else "140"
                tables[kind].append(row)
    for i in range(1, 9):
        tables["um"].append(
            {
                "KettoNum": f"202010{i:04d}",
                "headMakeDate": "20261031",
                "Ketto3Info0HansyokuNum": "SIRE" + str(i % 2),
                "Ketto3Info4HansyokuNum": "DAM" + str(i % 3),
            }
        )
    names = (RA_TABLE, SE_TABLE, O1_TABLE, O2_TABLE, HC_TABLE, WC_TABLE, UM_TABLE)
    return {
        "format_version": 1,
        "snapshot": {
            "snapshot_id": "fixture-v1",
            "snapshot_path": "fixture",
            "tables": {name: {"file": name + ".parquet", "sha256": "a" * 64} for name in names},
        },
        "rules": config["reference_rules"],
        "calculation_settings": config["calculation_settings"],
        "races": races,
        "tables": tables,
        "include_labels": labels,
    }


def parquet_snapshot(
    root: Path, raw: dict[str, object], *, snapshot_id: str = "fixture-v1"
) -> Path:
    version = root / "snapshots" / snapshot_id
    version.mkdir(parents=True)
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    physical = {
        RA_TABLE: tables["history_ra"] + tables["label_ra"],
        SE_TABLE: tables["history_se"] + tables["label_se"],
        O1_TABLE: tables["o1"],
        O2_TABLE: tables["o2"],
        HC_TABLE: tables["hc"],
        WC_TABLE: tables["wc"],
        UM_TABLE: tables["um"],
    }
    if not tables["label_ra"]:
        for race in cast(list[dict[str, object]], raw["races"]):
            ra, se = race_rows(
                datetime.fromisoformat(cast(str, race["scheduled_start_at"])).astimezone(JST).date()
            )
            physical[RA_TABLE].append(ra)
            physical[SE_TABLE].extend(se)
    for name, rows in physical.items():
        # Target dates of longer fixtures are also earlier history; store each row once.
        rows = _unique_rows(rows)
        schema = pa.schema([(column, pa.string()) for column in rows[0]])
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), version / f"{name}.parquet")
    (root / "CURRENT").write_text(snapshot_id, encoding="utf-8")
    return version


def _unique_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result = []
    for row in rows:
        identity = canonical_hash(row)
        if identity not in seen:
            seen.add(identity)
            result.append(row)
    return result


def _in_year(row: dict[str, object], year: int, end: date) -> bool:
    return row["idYear"] == str(year) and f"{row['idYear']}{row['idMonthDay']}" <= end.strftime(
        "%Y%m%d"
    )


def datamart_from_raw(
    raw: dict[str, object],
    *,
    registry: FeatureRegistry,
    target_start: date,
    target_end: date,
    labeled: bool = True,
) -> tuple[ReferenceDatamartBuilder, list[ReferenceYearOutput]]:
    """Feed a raw fixture to the chronological builder exactly as the CLI reads a snapshot."""
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    builder = ReferenceDatamartBuilder(
        settings=cast(dict[str, object], raw["calculation_settings"]),
        rules=cast(dict[str, object], raw["rules"]),
        registry=registry,
        target_start=target_start,
        target_end=target_end,
        snapshot=cast(dict[str, object], raw["snapshot"]),
        pedigree_rows=tables["um"],
        labeled=labeled,
    )
    outputs = [
        builder.add_year(year, **_year_inputs(raw, builder, year), markets=day_markets(raw))
        for year in builder.years
    ]
    return builder, outputs


def prepared_from_raw(
    raw: dict[str, object],
    *,
    registry: FeatureRegistry,
    day: date,
    edit: Callable[[list[dict[str, object]], list[dict[str, object]]], None] | None = None,
) -> tuple[ReferenceDatamartBuilder, PreparedTargets]:
    """Feed history years through ``add_year`` and prepare the one label-free date.

    ``edit`` receives the target year's de-duplicated RA and SE row lists and may
    change them in place before ``prepare_targets`` reads them.
    """
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    builder = ReferenceDatamartBuilder(
        settings=cast(dict[str, object], raw["calculation_settings"]),
        rules=cast(dict[str, object], raw["rules"]),
        registry=registry,
        target_start=day,
        target_end=day,
        snapshot=cast(dict[str, object], raw["snapshot"]),
        pedigree_rows=tables["um"],
        labeled=False,
    )
    for year in builder.years:
        if year < day.year:
            builder.add_year(year, **_year_inputs(raw, builder, year), markets=day_markets(raw))
    inputs = _year_inputs(raw, builder, day.year)
    if edit is not None:
        edit(inputs["ra_rows"], inputs["se_rows"])
    return builder, builder.prepare_targets(day.year, **inputs)


def day_markets(raw: dict[str, object]) -> MarketRows:
    """Return the fixture's O1/O2 rows of one date, as the CLI reads a pinned snapshot."""
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])

    def markets(day: date) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        stamp = (str(day.year), day.strftime("%m%d"))
        o1, o2 = (
            [row for row in tables[name] if (row["idYear"], row["idMonthDay"]) == stamp]
            for name in ("o1", "o2")
        )
        return o1, o2

    return markets


def _year_inputs(
    raw: dict[str, object], builder: ReferenceDatamartBuilder, year: int
) -> dict[str, Any]:
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    ra_rows = _unique_rows(tables["history_ra"] + tables["label_ra"])
    se_rows = _unique_rows(tables["history_se"] + tables["label_se"])
    days_window = cast(int, cast(dict[str, object], raw["calculation_settings"])["days_window"])
    window = workout_window(
        year,
        target_start=builder.target_start,
        target_end=builder.target_end,
        days_window=days_window,
    )
    workouts = (
        [
            (kind, row)
            for kind in ("hc", "wc")
            for row in tables[kind]
            if window[0].strftime("%Y%m%d")
            <= cast(str, row["ChokyoDate"])
            <= window[1].strftime("%Y%m%d")
        ]
        if window is not None
        else []
    )
    return {
        "ra_rows": [row for row in ra_rows if _in_year(row, year, builder.target_end)],
        "se_rows": [row for row in se_rows if _in_year(row, year, builder.target_end)],
        "workout_rows": workouts,
    }


RICH_TARGET_DAYS = (date(2026, 12, 20), date(2026, 12, 27), date(2027, 1, 3))
RICH_HISTORY_DAYS = tuple(date(2026, 11, 1) + timedelta(days=7 * week) for week in range(7))
RICH_RACES = (("09", "1500", 0), ("10", "1530", 2))


def _workout_row(kind: str, horse: str, day: date, clock: str, lap: str) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(HC_COLUMNS if kind == "hc" else WC_COLUMNS)
    row.update(
        headDataKubun="1",
        headMakeDate="20270110",
        TresenKubun="0",
        ChokyoDate=day.strftime("%Y%m%d"),
        ChokyoTime=clock,
        KettoNum=horse,
    )
    if kind == "wc":
        row.update(Course="0", BabaAround="0")
    for section in range(1, 5):
        row[f"LapTime{section}"] = lap
    return row


def rich_raw_input(
    *,
    abnormal_history: bool = True,
    abnormal_target: bool = True,
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return three target dates with two races each, real history and boundary workouts.

    Race 09 starts at 15:00 and race 10 at 15:30 on every date, so their freeze windows
    start at different minutes. Results become usable after seven days, so 2026-12-20
    results enter 2027-01-03 history but not 2026-12-27 history.
    """
    raw = raw_input(())
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    for name in tables:
        tables[name].clear()
    calculation = dict(cast(dict[str, object], raw["calculation_settings"]))
    calculation["history_start"] = "2026-11-01"
    calculation.update(settings or {})
    raw["calculation_settings"] = calculation
    races: list[dict[str, object]] = []
    for day in RICH_HISTORY_DAYS + RICH_TARGET_DAYS:
        for number, clock, offset in RICH_RACES:
            ra, se = race_rows(day, offset=offset, race_number=number)
            ra["HassoTime"] = clock
            if number == "10":
                ra["Kyori"] = "1800"
            # Rotate finishing order and clocks so prior results differ between races.
            shift = (day.toordinal() + int(number)) % 4
            for index, row in enumerate(se):
                place = (index + shift) % 4 + 1
                row["KakuteiJyuni"] = f"{place:02d}"
                row["Time"] = f"1{45 + place - 1:02d}{(day.day + index) % 10}"
                row["Jyuni4c"] = f"{(index + shift + 1) % 4 + 1:02d}"
                row["Wakuban"] = f"{index // 2 + 1}"
            if abnormal_history and day == RICH_HISTORY_DAYS[2] and number == "10":
                se[0]["IJyoCD"] = "1"
            if abnormal_target and day == RICH_TARGET_DAYS[1] and number == "10":
                se[1]["IJyoCD"] = "4"
            identity = "".join(cast(str, ra[k]) for k in KEY_COLUMNS)
            if day in RICH_TARGET_DAYS:
                hour, minute = int(clock[:2]), int(clock[2:])
                start = datetime.combine(day, datetime.min.time(), JST).replace(
                    hour=hour, minute=minute
                )
                races.append(
                    {
                        "race_id": identity,
                        "scheduled_start_at": start.isoformat(),
                        "freeze_at": (start - timedelta(seconds=300)).isoformat(),
                        "schedule_known_at": None,
                    }
                )
                tables["target_ra"].append({k: ra[k] for k in CARD_RA_COLUMNS})
                tables["target_se"].extend({k: r[k] for k in CARD_SE_COLUMNS} for r in se)
                tables["label_ra"].append(ra)
                tables["label_se"].extend(se)
                before = start - timedelta(minutes=16)
                for publication, total in ((before, 1000), (start - timedelta(minutes=6), 2000)):
                    o1, o2 = markets(
                        day, clock=publication.strftime("%H%M"), total=total, race_number=number
                    )
                    tables["o1"].append(o1)
                    tables["o2"].append(o2)
            if day < RICH_TARGET_DAYS[-1]:
                tables["history_ra"].append(ra)
                tables["history_se"].extend(se)
    # Jump races have no going, so a going condition key is unknown for them, and the first
    # one's unmeasured winner clock makes the later one's as-of reference unusable. The
    # 2026-12-19 race becomes usable exactly at 2026-12-27 00:00 (eight days later).
    for day, number, track, distance, offset in (
        (RICH_HISTORY_DAYS[1], "11", "52", "3000", 3),
        (RICH_HISTORY_DAYS[4], "11", "52", "3000", 3),
        (date(2026, 12, 19), "11", "11", "1600", 1),
    ):
        ra, se = race_rows(day, offset=offset, race_number=number)
        ra.update(HassoTime="1600", TrackCD=track, Kyori=distance)
        if day == RICH_HISTORY_DAYS[1]:
            next(row for row in se if row["KakuteiJyuni"] == "01")["Time"] = "0000"
        tables["history_ra"].append(ra)
        tables["history_se"].extend(se)
    # Sessions are stored out of date order, with one identical duplicate row and one
    # session on the window's first day between the two freeze windows.
    for target in RICH_TARGET_DAYS:
        boundary = target - timedelta(days=cast(int, calculation["days_window"]))
        for horse_index in range(1, 7):
            horse = f"202010{horse_index:04d}"
            for kind in ("hc", "wc"):
                for days_before, clock in ((2, "0600"), (9, "0610"), (16, "0620")):
                    lap = f"{118 + (horse_index + days_before) % 5}"
                    tables[kind].append(
                        _workout_row(kind, horse, target - timedelta(days=days_before), clock, lap)
                    )
        tables["hc"].append(_workout_row("hc", "2020100001", boundary, "1510", "125"))
        tables["hc"].append(_workout_row("hc", "2020100003", boundary, "1510", "121"))
        tables["hc"].append(
            _workout_row("hc", "2020100004", target - timedelta(days=0), "0500", "110")
        )
    tables["hc"].reverse()
    tables["hc"].append(dict(next(row for row in tables["hc"] if row["ChokyoDate"] == "20261225")))
    for i in range(1, 9):
        tables["um"].append(
            {
                "KettoNum": f"202010{i:04d}",
                "headMakeDate": "20261031",
                "Ketto3Info0HansyokuNum": "SIRE" + str(i % 2),
                "Ketto3Info4HansyokuNum": "DAM" + str(i % 3),
            }
        )
    raw["races"] = races
    raw["include_labels"] = True
    return raw


def add_post_freeze_markets(raw: dict[str, object], *, cancelled_after_freeze: bool = True) -> None:
    """Add one intermediate publication two minutes before each target's start.

    Publications after freeze never change features; a label-free build needs them as
    evidence that the snapshot observed the market beyond freeze. The last target's
    late quote also marks a scratch that appears only after freeze.
    """
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    for race in cast(list[dict[str, object]], raw["races"]):
        start = datetime.fromisoformat(cast(str, race["scheduled_start_at"])).astimezone(JST)
        identity = cast(str, race["race_id"])
        o1, o2 = markets(
            start.date(),
            clock=(start - timedelta(minutes=2)).strftime("%H%M"),
            total=3000,
            race_number=identity[-2:],
        )
        if cancelled_after_freeze and race is cast(list[dict[str, object]], raw["races"])[-1]:
            o1["OddsTansyoInfo3Odds"] = "----"
        tables["o1"].append(o1)
        tables["o2"].append(o2)


PRE_RACE_RA = {
    "headDataKubun": "2",
    "SyussoTosu": "",
    "NyusenTosu": "",
    "TenkoBabaSibaBabaCD": "0",
    "HaronTimeL3": "000",
}
PRE_RACE_SE = {
    "headDataKubun": "2",
    "KakuteiJyuni": "00",
    "IJyoCD": "0",
    "Time": "0000",
    "TimeDiff": "",
    "HaronTimeL3": "000",
    "Jyuni4c": "00",
    "BaTaijyu": "",
}


def pre_race(raw: dict[str, object], day: date, *, race_number: str | None = None) -> None:
    """Rewrite one date's stored RA/SE rows in place to their shape before the race."""
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    stamp = (str(day.year), day.strftime("%m%d"))
    for name, values in (
        ("history_ra", PRE_RACE_RA),
        ("label_ra", PRE_RACE_RA),
        ("history_se", PRE_RACE_SE),
        ("label_se", PRE_RACE_SE),
    ):
        for row in tables[name]:
            if (row["idYear"], row["idMonthDay"]) != stamp:
                continue
            if race_number is not None and row["idRaceNum"] != race_number:
                continue
            row.update(values)
            if name.endswith("_ra"):
                for i in range(25):
                    if row.get(f"LapTime{i}") is not None:
                        row[f"LapTime{i}"] = "000"
