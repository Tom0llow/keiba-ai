"""Small explicit raw projections; trial configuration is never a learned optimum."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq

from configuration.reference_input import load_reference_input_config
from make_features.real_market import JST, KEY_COLUMNS, O1_TABLE, RA_TABLE, SE_TABLE
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


def markets(day: date, *, clock: str, total: int) -> tuple[dict[str, object], dict[str, object]]:
    o1: dict[str, object] = dict.fromkeys(MARKET_O1_COLUMNS)
    o2: dict[str, object] = dict.fromkeys(MARKET_O2_COLUMNS)
    for row in (o1, o2):
        row.update(key(day))
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


def parquet_snapshot(root: Path, raw: dict[str, object]) -> Path:
    version = root / "snapshots" / "fixture-v1"
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
        schema = pa.schema([(column, pa.string()) for column in rows[0]])
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), version / f"{name}.parquet")
    (root / "CURRENT").write_text("fixture-v1", encoding="utf-8")
    return version
