"""Small graded-race rows and PL predictions for the ADR-043 backtest tests.

One race has eight horses (numbers 01 to 08). At freeze (15:25 JST, from HassoTime 15:30)
the O1 quotes make three bets eligible under the fixed policy with an identity place
correction:

- win on 01 (P 0.4, odds 3.0): R 1.2, Kelly 0.1, 2,500 yen requested;
- win on 02 (P 0.2, odds 6.0): R 1.2, Kelly 0.04, 1,000 yen requested;
- place on 03 (P 0.35, sqrt(3.0 x 4.0)): R about 1.212, 2,100 yen requested.

The 5,600 yen race total is reduced to 5,000 yen: 2,200, 800 and 1,800 yen. The default
result pays win 01 at 300 yen and places 01, 02 and 03 at 120, 150 and 350 yen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from make_features.real_market import KEY_COLUMNS
from make_features.reference_raw import CARD_SE_COLUMNS
from models.serialization.final_odds_observations import HR_COLUMNS, O1_COLUMNS

HORSES = ("01", "02", "03", "04", "05", "06", "07", "08")
P_WIN = (0.4, 0.2, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05)
P_TOP2 = (0.6, 0.4, 0.2, 0.2, 0.15, 0.15, 0.15, 0.15)
P_TOP3 = (0.75, 0.6, 0.35, 0.35, 0.25, 0.25, 0.25, 0.2)
WIN_CODES = ("0030", "0060", "0080", "0080", "0200", "0200", "0200", "0200")
PLACE_CODES = (
    ("0011", "0015"),
    ("0015", "0020"),
    ("0030", "0040"),
    ("0020", "0030"),
    ("0020", "0030"),
    ("0020", "0030"),
    ("0020", "0030"),
    ("0020", "0030"),
)


def race_id(year: int, number: int = 1) -> str:
    """Return a 16-digit race ID on June 15 at venue 05."""
    return f"{year}0615050301{number:02d}"


def key(race: str) -> dict[str, object]:
    values = (race[:4], race[4:8], race[8:10], race[10:12], race[12:14], race[14:16])
    return dict(zip(KEY_COLUMNS, values, strict=True))


def horse_id(race: str, horse: str) -> str:
    """Return a stable ten-digit permanent ID for a horse in a race."""
    return f"{race[2:4]}{race[14:16]}0000{horse}"


def ra_row(race: str, **fields: object) -> dict[str, object]:
    row: dict[str, object] = {
        **key(race),
        "headDataKubun": "7",
        "headMakeDate": race[:8],
        "HassoTime": "1530",
        "GradeCD": "A",
        "TrackCD": "10",
    }
    row.update(fields)
    return row


def o1_row(
    race: str,
    *,
    clock: str = "1524",
    horses: Sequence[str] = HORSES,
    win_codes: Sequence[str] = WIN_CODES,
    place_codes: Sequence[tuple[str, str]] = PLACE_CODES,
) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(O1_COLUMNS)
    row.update(key(race), headDataKubun="1", headMakeDate=race[:8], HappyoTime=race[4:8] + clock)
    for i, (horse, code, (low, high)) in enumerate(
        zip(horses, win_codes, place_codes, strict=True)
    ):
        row[f"OddsTansyoInfo{i}Umaban"] = horse
        row[f"OddsTansyoInfo{i}Odds"] = code
        row[f"OddsFukusyoInfo{i}Umaban"] = horse
        row[f"OddsFukusyoInfo{i}OddsLow"] = low
        row[f"OddsFukusyoInfo{i}OddsHigh"] = high
    for name in ("TotalHyosuTansyo", "TotalHyosuFukusyo", "TotalHyosuWakuren"):
        row[name] = "1000"
    return row


def se_rows(race: str, horses: Sequence[str] = HORSES) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horse in horses:
        row: dict[str, object] = dict.fromkeys(CARD_SE_COLUMNS)
        row.update(
            key(race),
            headMakeDate=race[:8],
            KettoNum=horse_id(race, horse),
            Umaban=horse,
            Wakuban="1",
            Barei="4",
            SexCD="1",
            Futan="550",
            KisyuCode="00001",
            ChokyosiCode="00001",
        )
        rows.append(row)
    return rows


def hr_row(
    race: str,
    *,
    win: Sequence[tuple[str, int]] = (("01", 300),),
    place: Sequence[tuple[str, int]] = (("01", 120), ("02", 150), ("03", 350)),
    starters: int = 8,
    **fields: object,
) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(HR_COLUMNS, "")
    row.update(key(race), headDataKubun="2", headMakeDate=race[:8], SyussoTosu=f"{starters:02d}")
    for name in HR_COLUMNS:
        if "Flag" in name or name.startswith("HenkanUma"):
            row[name] = "0"
    for i, (horse, pay) in enumerate(win):
        row[f"PayTansyo{i}Umaban"] = horse
        row[f"PayTansyo{i}Pay"] = f"{pay:09d}"
    for i, (horse, pay) in enumerate(place):
        row[f"PayFukusyo{i}Umaban"] = horse
        row[f"PayFukusyo{i}Pay"] = f"{pay:09d}"
    row.update(fields)
    return row


def prediction_rows(
    race: str,
    *,
    variant: str = "all_columns",
    horses: Sequence[str] = HORSES,
    graded: bool = True,
    market: Mapping[str, float | None] | None = None,
) -> list[dict[str, object]]:
    """Return PL prediction rows; ``market`` overrides ``market_win_odds`` by horse."""
    rows: list[dict[str, object]] = []
    for index, horse in enumerate(horses):
        odds = int(WIN_CODES[index]) / 10
        rows.append(
            {
                "variant": variant,
                "test_year": int(race[:4]),
                "race_id": race,
                "horse_id": horse_id(race, horse),
                "finish_position": index + 1,
                "score": 0.0,
                "temperature": 1.0,
                "p_win": P_WIN[index],
                "p_top2": P_TOP2[index],
                "p_top3": P_TOP3[index],
                "market_win_odds": odds if market is None else market.get(horse, odds),
                "market_q": None,
                "in_jra_flat_graded_stakes": graded,
            }
        )
    return rows
