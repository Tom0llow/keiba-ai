"""Tests for hit-conditional final-odds observations (ADR-042, plan AC-1 to AC-6)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime

import pytest

from make_features.real_market import KEY_COLUMNS, latest_o1
from make_features.reference_raw import race_identity
from make_features.reference_snapshot import decimal_odds
from models.serialization.final_odds_observations import (
    HR_COLUMNS,
    O1_COLUMNS,
    O2_COLUMNS,
    SCAN_COLUMNS,
    HitExclusion,
    HitObservation,
    RaceHold,
    RaceObservations,
    build_race_observations,
    race_freeze,
    race_payouts,
    select_publication_pairs,
)

RACE = "2025061505030111"  # 2025-06-15, venue 05; HassoTime 15:30 -> freeze 15:25 JST
MAX_AGE = 600


# --- AC-1: decimal_odds -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        ("0025", 4, 2.5),
        ("0010", 4, 1.0),
        ("001234", 6, 123.4),
        (None, 4, None),
        ("", 4, None),
        ("    ", 4, None),
        ("0000", 4, None),
        ("----", 4, None),
        ("****", 4, None),
        ("9999", 4, None),
        ("999999", 6, None),
    ],
)
def test_decimal_odds_converts_tenths_and_returns_none_for_sentinels(
    value: str | None, digits: int, expected: float | None
) -> None:
    assert decimal_odds(value, digits=digits) == expected


@pytest.mark.parametrize(("value", "digits"), [("025", 4), ("0009", 4), ("00025", 6), ("12a4", 4)])
def test_decimal_odds_rejects_invalid_encodings(value: str, digits: int) -> None:
    with pytest.raises(ValueError, match="invalid decimal odds encoding"):
        decimal_odds(value, digits=digits)


def test_decimal_odds_rejects_non_string_values() -> None:
    with pytest.raises(ValueError, match="raw nullable strings"):
        decimal_odds(25, digits=4)


# --- AC-2 / AC-4 / AC-5 / AC-6: building observations -----------------------------------


def test_a_normal_race_yields_every_bet_type_with_final_odds_from_payouts() -> None:
    result = _build()

    assert result.holds == ()
    assert result.exclusions == ()
    assert result.refund is False
    assert result.publication_ages == {"o1": 60, "o2": 60}
    assert set(result.hits) == {
        HitObservation(RACE, "win", "03", 5.0, 4.8, 60),
        HitObservation(RACE, "place_low", "03", 1.5, 1.8, 60),
        HitObservation(RACE, "place_low", "05", 2.0, 2.3, 60),
        HitObservation(RACE, "place_low", "07", 4.0, 5.1, 60),
        HitObservation(RACE, "place_mid", "03", math.sqrt(1.5 * 2.4), 1.8, 60),
        HitObservation(RACE, "place_mid", "05", math.sqrt(2.0 * 3.2), 2.3, 60),
        HitObservation(RACE, "place_mid", "07", math.sqrt(4.0 * 6.4), 5.1, 60),
        HitObservation(RACE, "quinella", "0305", 12.3, 11.5, 60),
    }


def test_a_publication_at_the_freeze_minute_is_used_and_one_minute_later_is_not() -> None:
    o1 = [_o1("06151525", win_code="0050"), _o1("06151526", win_code="0090")]

    result = _build(o1=o1)

    win = _hit(result, "win", "03")
    assert win.freeze_odds == 5.0
    assert win.publication_age_seconds == 0


@pytest.mark.parametrize("kubun", ["2", "3", "4"])
def test_rows_other_than_intermediate_publications_are_never_used(kubun: str) -> None:
    o1 = [_o1("06151519"), _o1("06151524", win_code="0090", kubun=kubun)]

    assert _hit(_build(o1=o1), "win", "03").freeze_odds == 5.0


def test_a_december_publication_is_not_used_for_a_january_race() -> None:
    race = "2025010505030111"
    o1 = [_o1("12301500", race=race)]

    result = _build(race=race, o1=o1, o2=[_o2("01051519", race=race)])

    assert result.holds == (
        RaceHold(
            race,
            "o1",
            "no_publication",
            f"{race}: no intermediate O1 publication at or before freeze",
        ),
    )
    assert {hit.bet_type for hit in result.hits} == {"quinella"}


def test_a_stale_publication_holds_only_its_table() -> None:
    result = _build(o1=[_o1("06151514")])

    assert [(h.scope, h.reason) for h in result.holds] == [("o1", "stale_publication")]
    assert result.publication_ages == {"o1": 660, "o2": 60}
    assert {hit.bet_type for hit in result.hits} == {"quinella"}


def test_a_quinella_conflict_holds_only_quinella() -> None:
    o2 = [_o2("06151524"), _o2("06151524", pair_code="000999")]

    result = _build(o2=o2)

    assert [(h.scope, h.reason) for h in result.holds] == [("o2", "conflicting_publication")]
    assert {hit.bet_type for hit in result.hits} == {"win", "place_low", "place_mid"}


def test_an_invalid_publication_clock_holds_its_table() -> None:
    result = _build(o1=[_o1("06151524"), _o1("0615xx24")])

    assert [(h.scope, h.reason) for h in result.holds] == [("o1", "invalid_publication")]


def test_an_invalid_quote_holds_its_table() -> None:
    result = _build(o2=[_o2("06151524", pair_code="12")])

    assert [(h.scope, h.reason) for h in result.holds] == [("o2", "invalid_quote")]


@pytest.mark.parametrize(
    ("ra", "hr", "reason"),
    [
        ({"headDataKubun": "9"}, {}, "cancelled_race"),
        ({"headDataKubun": "0"}, {}, "deleted_race"),
        ({"HassoTime": "0000"}, {}, "invalid_schedule"),
        ({"HassoTime": None}, {}, "invalid_schedule"),
        ({"HassoTime": "0003"}, {}, "freeze_on_other_date"),
        ({}, {"headDataKubun": "1"}, "payout_not_final"),
        ({}, {"TokubaraiFlag1": "1"}, "special_payout"),
        ({}, {"FuseirituFlag8": "1"}, "unestablished"),
    ],
)
def test_race_level_holds_drop_every_bet_type(
    ra: dict[str, object], hr: dict[str, object], reason: str
) -> None:
    result = _build(ra=[{**_ra(), **ra}], hr=[{**_hr(), **hr}])

    assert [(h.scope, h.reason) for h in result.holds] == [("race", reason)]
    assert result.hits == ()


def test_missing_or_ambiguous_race_and_payout_rows_hold_the_race() -> None:
    assert _build(ra=[]).holds[0].reason == "no_race_row"
    assert _build(ra=[_ra(), _ra(GradeCD="A")]).holds[0].reason == "ambiguous_race_row"
    assert _build(hr=[]).holds[0].reason == "no_payout_row"
    assert _build(hr=[_hr(), _hr(SyussoTosu="11")]).holds[0].reason == "ambiguous_payout_row"
    assert _build(ra=[_ra(), _ra()]).holds == ()


def test_refunds_are_flagged_and_hits_are_kept() -> None:
    result = _build(hr=[_hr(HenkanFlag0="1")])

    assert result.refund is True
    assert result.holds == ()
    assert len(result.hits) == 8


def test_race_payouts_return_one_based_refunded_horse_numbers() -> None:
    payouts = race_payouts(
        RACE,
        [_hr(HenkanUma0="1", HenkanUma4="1", HenkanUma27="1", HenkanFlag0="1")],
    )

    assert payouts.refund is True
    assert payouts.refunded_horse_numbers == ("01", "05", "28")


def test_a_win_dead_heat_excludes_every_win_payout() -> None:
    result = _build(hr=[_hr(PayTansyo1Umaban="05", PayTansyo1Pay="000000600")])

    assert {e for e in result.exclusions if e.bet_type == "win"} == {
        HitExclusion(RACE, "win", "03", "dead_heat"),
        HitExclusion(RACE, "win", "05", "dead_heat"),
    }
    assert not [hit for hit in result.hits if hit.bet_type == "win"]


@pytest.mark.parametrize(
    ("starters", "horses", "dead_heat"),
    [
        ("08", ("03", "05", "07"), False),
        ("08", ("03", "05", "07", "09"), True),
        ("07", ("03", "05"), False),
        ("07", ("03", "05", "07"), True),
        ("05", ("03", "05"), False),
        ("05", ("03", "05", "07"), True),
        ("04", (), False),
        ("04", ("03",), True),
    ],
)
def test_place_dead_heat_depends_on_the_number_of_starters(
    starters: str, horses: tuple[str, ...], dead_heat: bool
) -> None:
    hr = _hr(SyussoTosu=starters)
    for i in range(5):
        horse = horses[i] if i < len(horses) else ""
        hr[f"PayFukusyo{i}Umaban"] = horse
        hr[f"PayFukusyo{i}Pay"] = f"{100 + i:09d}" if horse else ""

    result = _build(hr=[hr])

    for bet_type in ("place_low", "place_mid"):
        hits = {hit.combination for hit in result.hits if hit.bet_type == bet_type}
        excluded = {
            exclusion.combination
            for exclusion in result.exclusions
            if exclusion.bet_type == bet_type and exclusion.reason == "dead_heat"
        }
        if dead_heat:
            assert (hits, excluded) == (set(), set(horses))
        else:
            assert (hits, excluded) == (set(horses), set())


def test_a_quinella_dead_heat_excludes_every_quinella_payout() -> None:
    result = _build(hr=[_hr(PayUmaren1Kumi="0307", PayUmaren1Pay="000002000")])

    assert {e.combination for e in result.exclusions if e.reason == "dead_heat"} == {
        "0305",
        "0307",
    }


def test_combinations_without_a_freeze_quote_are_excluded_with_reasons() -> None:
    o1 = [_o1("06151524", win_code="0000", place={"05": ("0000", "0032"), "07": ("0040", "0000")})]
    o2 = [_o2("06151524", pair_code="000000")]

    result = _build(o1=o1, o2=o2)

    assert set(result.exclusions) == {
        HitExclusion(RACE, "win", "03", "no_votes"),
        HitExclusion(RACE, "place_low", "03", "no_freeze_quote"),
        HitExclusion(RACE, "place_mid", "03", "no_freeze_quote"),
        HitExclusion(RACE, "place_low", "05", "unquoted"),
        HitExclusion(RACE, "place_mid", "05", "unquoted"),
        HitExclusion(RACE, "place_mid", "07", "unquoted_high"),
        HitExclusion(RACE, "quinella", "0305", "unquoted"),
    }
    assert [(hit.bet_type, hit.combination) for hit in result.hits] == [("place_low", "07")]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"PayTansyo0Pay": "480"}, "positive nine-digit amount"),
        ({"PayTansyo0Pay": "000000000"}, "positive nine-digit amount"),
        ({"PayTansyo0Umaban": "AB"}, "invalid horse number"),
        ({"PayTansyo0Umaban": "29"}, "invalid or duplicate horse number"),
        ({"PayTansyo1Umaban": "", "PayTansyo1Pay": "000000600"}, "without a horse number"),
        ({"PayFukusyo1Umaban": "03"}, "invalid or duplicate horse number"),
        ({"PayUmaren0Kumi": "0503"}, "invalid or duplicate combination"),
        ({"PayUmaren0Kumi": "03"}, "invalid or duplicate combination"),
        ({"PayUmaren1Kumi": "", "PayUmaren1Pay": "000000600"}, "without a combination"),
        ({"SyussoTosu": None}, "two-digit SyussoTosu"),
        ({"HenkanUma0": "2"}, "HenkanUma0 to be 0 or 1"),
        ({"HenkanUma27": ""}, "HenkanUma27 to be 0 or 1"),
        ({"HenkanUma5": None}, "HenkanUma5 to be 0 or 1"),
    ],
)
def test_malformed_payouts_are_rejected(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _build(hr=[{**_hr(), **fields}])


@pytest.mark.parametrize(
    ("horses", "dead_heat"),
    [
        (("03", "05", "07"), False),
        (("03", "05", "07", "09"), True),
    ],
)
def test_horses_withdrawn_after_sales_opened_count_for_the_place_payouts(
    horses: tuple[str, ...], dead_heat: bool
) -> None:
    # Eight horses at the start of sales, one refunded: three places are paid.
    hr = _hr(SyussoTosu="07", HenkanUma10="1", HenkanFlag1="1")
    for i in range(5):
        horse = horses[i] if i < len(horses) else ""
        hr[f"PayFukusyo{i}Umaban"] = horse
        hr[f"PayFukusyo{i}Pay"] = f"{100 + i:09d}" if horse else ""

    result = _build(hr=[hr])

    for bet_type in ("place_low", "place_mid"):
        hits = {hit.combination for hit in result.hits if hit.bet_type == bet_type}
        excluded = {
            exclusion.combination
            for exclusion in result.exclusions
            if exclusion.bet_type == bet_type and exclusion.reason == "dead_heat"
        }
        if dead_heat:
            assert (hits, excluded) == (set(), set(horses))
        else:
            assert (hits, excluded) == (set(horses), set())


@pytest.mark.parametrize("empty", [None, "", "  ", "00"])
def test_empty_payout_slots_are_ignored(empty: str | None) -> None:
    result = _build(hr=[_hr(PayTansyo1Umaban=empty, PayTansyo1Pay=None)])

    assert _hit(result, "win", "03").final_odds == 4.8


def test_the_maximum_publication_age_must_be_a_positive_integer() -> None:
    with pytest.raises(ValueError, match="max_publication_age_seconds"):
        _build(max_age=0)


def test_race_freeze_is_five_minutes_before_the_stored_start() -> None:
    assert race_freeze(RACE, [_ra()]) == datetime.fromisoformat("2025-06-15T15:25:00+09:00")


# --- AC-3: the pre-filter keeps latest_o1's outcome ---------------------------------------


def test_selected_pairs_give_the_same_latest_o1_outcome_as_all_rows() -> None:
    races = {f"20250615050301{n:02d}": "1530" for n in range(1, 7)}
    freezes = {race: race_freeze(race, [_ra(race=race)]) for race in races}
    rows = [
        # 01: an early conflict and a clean latest publication -> held as a conflict.
        _o1("06151510", race=_r(1)),
        _o1("06151510", race=_r(1), win_code="0070"),
        _o1("06151519", race=_r(1)),
        # 02: an invalid clock beside a valid publication -> rejected.
        _o1("06151519", race=_r(2)),
        _o1("0615zz00", race=_r(2)),
        _o1(None, race=_r(2)),
        # 03: identical duplicates at the latest time -> the latest row.
        _o1("06151524", race=_r(3)),
        _o1("06151524", race=_r(3)),
        _o1("06151510", race=_r(3), win_code="0070"),
        # 04: only publications after freeze -> no publication.
        _o1("06151526", race=_r(4)),
        # 05: several valid times, other kinds and a later row -> the latest at freeze.
        _o1("06151500", race=_r(5), win_code="0070"),
        _o1("06151519", race=_r(5)),
        _o1("06151525", race=_r(5), win_code="0060"),
        _o1("06151524", race=_r(5), kubun="3"),
        _o1("06151527", race=_r(5), win_code="0080"),
        # 06: a December clock for this June race is a later date in the race year.
        _o1("12011200", race=_r(6)),
        _o1("06151519", race=_r(6)),
    ]
    scan = [{name: row[name] for name in SCAN_COLUMNS} for row in rows]

    pairs = select_publication_pairs(scan, freezes)
    selected = [row for row in rows if (race_identity(row), row["HappyoTime"]) in pairs]

    for race, freeze in freezes.items():
        target = {"race_id": race, "freeze_at": freeze.isoformat()}
        assert _outcome(rows, target) == _outcome(selected, target), race
    assert (_r(5), "06151525") in pairs
    assert (_r(5), "06151527") not in pairs
    assert (_r(2), None) in pairs


def test_publication_pairs_ignore_races_without_a_freeze_and_other_kinds() -> None:
    rows = [_o1("06151519"), _o1("06151520", kubun="2"), _o1("06151519", race=_r(9))]
    scan = [{name: row[name] for name in SCAN_COLUMNS} for row in rows]

    assert select_publication_pairs(scan, {RACE: race_freeze(RACE, [_ra()])}) == frozenset(
        {(RACE, "06151519")}
    )


def test_publication_pairs_reject_non_string_clocks() -> None:
    scan = [{**{name: _o1("06151519")[name] for name in SCAN_COLUMNS}, "HappyoTime": 615}]

    with pytest.raises(ValueError, match="nullable string"):
        select_publication_pairs(scan, {RACE: race_freeze(RACE, [_ra()])})


# --- helpers ------------------------------------------------------------------------------


def _r(number: int) -> str:
    return f"20250615050301{number:02d}"


def _key(race: str) -> dict[str, object]:
    values = (race[:4], race[4:8], race[8:10], race[10:12], race[12:14], race[14:16])
    return dict(zip(KEY_COLUMNS, values, strict=True))


def _ra(*, race: str = RACE, **fields: object) -> dict[str, object]:
    row: dict[str, object] = {
        **_key(race),
        "headDataKubun": "7",
        "headMakeDate": race[:8],
        "HassoTime": "1530",
        "GradeCD": "",
        "TrackCD": "10",
    }
    row.update(fields)
    return row


def _o1(
    clock: str | None,
    *,
    race: str = RACE,
    kubun: str = "1",
    win_code: str = "0050",
    place: Mapping[str, tuple[str, str]] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(O1_COLUMNS)
    row.update(_key(race), headDataKubun=kubun, headMakeDate=race[:8], HappyoTime=clock)
    quotes = {"03": win_code, "05": "0080", "07": "0150"}
    places = place or {"03": ("0015", "0024"), "05": ("0020", "0032"), "07": ("0040", "0064")}
    for i, (horse, code) in enumerate(quotes.items()):
        row[f"OddsTansyoInfo{i}Umaban"] = horse
        row[f"OddsTansyoInfo{i}Odds"] = code
    for i, (horse, (low, high)) in enumerate(places.items()):
        row[f"OddsFukusyoInfo{i}Umaban"] = horse
        row[f"OddsFukusyoInfo{i}OddsLow"] = low
        row[f"OddsFukusyoInfo{i}OddsHigh"] = high
    for name in ("TotalHyosuTansyo", "TotalHyosuFukusyo", "TotalHyosuWakuren"):
        row[name] = "1000"
    return row


def _o2(clock: str, *, race: str = RACE, pair_code: str = "000123") -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(O2_COLUMNS)
    row.update(_key(race), headDataKubun="1", headMakeDate=race[:8], HappyoTime=clock)
    row["TotalHyosuUmaren"] = "1000"
    for i, (pair, code) in enumerate({"0305": pair_code, "0307": "000456"}.items()):
        row[f"OddsUmarenInfo{i}Kumi"] = pair
        row[f"OddsUmarenInfo{i}Odds"] = code
    return row


def _hr(*, race: str = RACE, **fields: object) -> dict[str, object]:
    row: dict[str, object] = {name: "" for name in HR_COLUMNS}
    row.update(_key(race), headDataKubun="2", headMakeDate=race[:8], SyussoTosu="10")
    for name in HR_COLUMNS:
        if "Flag" in name or name.startswith("HenkanUma"):
            row[name] = "0"
    row.update(PayTansyo0Umaban="03", PayTansyo0Pay="000000480")
    for i, (horse, pay) in enumerate((("03", 180), ("05", 230), ("07", 510))):
        row[f"PayFukusyo{i}Umaban"] = horse
        row[f"PayFukusyo{i}Pay"] = f"{pay:09d}"
    row.update(PayUmaren0Kumi="0305", PayUmaren0Pay="000001150")
    row.update(fields)
    return row


def _build(
    *,
    race: str = RACE,
    ra: Sequence[Mapping[str, object]] | None = None,
    o1: Sequence[Mapping[str, object]] | None = None,
    o2: Sequence[Mapping[str, object]] | None = None,
    hr: Sequence[Mapping[str, object]] | None = None,
    max_age: int = MAX_AGE,
) -> RaceObservations:
    return build_race_observations(
        race,
        ra_rows=[_ra(race=race)] if ra is None else ra,
        o1_rows=[_o1("06151524", race=race)] if o1 is None else o1,
        o2_rows=[_o2("06151524", race=race)] if o2 is None else o2,
        hr_rows=[_hr(race=race)] if hr is None else hr,
        max_publication_age_seconds=max_age,
    )


def _hit(result: RaceObservations, bet_type: str, combination: str) -> HitObservation:
    (hit,) = [h for h in result.hits if h.bet_type == bet_type and h.combination == combination]
    return hit


def _outcome(rows: Sequence[dict[str, object]], target: Mapping[str, object]) -> object:
    try:
        return latest_o1(rows, target)
    except ValueError as exc:
        return ("error", str(exc))
