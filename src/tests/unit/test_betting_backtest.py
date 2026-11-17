"""Tests for the ADR-043 backtest assembly under ADR-044's report version 2."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

import pytest

from models.betting.policy import BettingPolicy
from models.experiments.betting_backtest import (
    BettingBacktest,
    BettingBacktestSettings,
    GradedRaceInput,
    bets_table,
    run_betting_backtest,
)
from models.serialization.betting_inputs import BlendTraining, race_predictions
from models.serialization.final_odds_observations import HitObservation
from tests.betting_fixtures import (
    hr_row,
    o1_row,
    prediction_rows,
    ra_row,
    race_id,
    se_rows,
)

RACE = race_id(2025)


def _settings(**fields: object) -> BettingBacktestSettings:
    values: dict[str, object] = {
        "test_years": (2025,),
        "policy": BettingPolicy(),
        "train_start_year": 2023,
        "max_publication_age_seconds": 600,
        "place_bands": (1.0,),
        "quantiles": (0.1, 0.5, 0.9),
        "min_hits": 1,
        "graded_shrinkage_k": 2,
        "bootstrap_resamples": 20,
        "bootstrap_seed": 0,
        "bootstrap_confidence": 0.95,
        "blend_min_races": 1,
        "blend_tolerance": 1e-10,
        "blend_max_iterations": 100,
        "place_width_bands": (1.0, 1.5, 2.0, 3.0, 5.0),
    }
    values.update(fields)
    return BettingBacktestSettings(**values)  # type: ignore[arg-type]


def _race(race: str = RACE, **rows: Sequence[Mapping[str, object]]) -> GradedRaceInput:
    return GradedRaceInput(
        race_id=race,
        ra_rows=rows.get("ra", [ra_row(race)]),
        o1_rows=rows.get("o1", [o1_row(race)]),
        se_rows=rows.get("se", se_rows(race)),
        hr_rows=rows.get("hr", [hr_row(race)]),
    )


def _hits(year: int, ratio: float = 1.0) -> list[HitObservation]:
    race = race_id(year, 90)
    hits: list[HitObservation] = []
    for number, mid in ((1, 1.5), (2, 3.0), (3, 6.0)):
        hits.append(HitObservation(race, "place_mid", f"{number:02d}", mid, mid * ratio, 60))
        hits.append(HitObservation(race, "place_low", f"{number:02d}", mid, mid * ratio, 60))
    return hits


def _no_blend(years: Sequence[int]) -> BlendTraining:
    return BlendTraining(
        races={year: () for year in years},
        excluded={
            year: {"market_incomplete": 0, "zero_probability": 0, "winner_count": 0}
            for year in years
        },
    )


def _run(
    races: Sequence[GradedRaceInput] = (),
    *,
    predictions: Sequence[Mapping[str, object]] | None = None,
    hits: Sequence[HitObservation] | None = None,
    holds: Mapping[str, str] | None = None,
    settings: BettingBacktestSettings | None = None,
) -> BettingBacktest:
    chosen = settings or _settings()
    graded = list(races) or [_race()]
    rows = prediction_rows(RACE) if predictions is None else predictions
    return run_betting_backtest(
        settings=chosen,
        graded_races=graded,
        predictions=race_predictions(rows, variant="all_columns", test_years=chosen.test_years),
        target_hold_stages=holds or {},
        training_hits=_hits(2024) if hits is None else hits,
        blend_training=_no_blend(chosen.test_years),
        graded_race_ids=frozenset(),
        config={"fixture": True},
        inputs={"fixture": True},
        provenance={"source_sha256": "fixture"},
    )


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def test_one_graded_race_buys_scales_and_settles_the_expected_bets() -> None:
    result = _run()

    assert [
        (row["bet_type"], row["horse_number"], row["requested_stake_yen"], row["stake_yen"])
        for row in result.bets
    ] == [("win", "01", 2_500, 2_200), ("win", "02", 1_000, 800), ("place", "03", 2_100, 1_800)]
    assert [row["receipt_yen"] for row in result.bets] == [6_600, 0, 6_300]
    (race,) = result.races
    assert (race["stake_yen"], race["receipt_yen"], race["net_yen"], race["hit"]) == (
        4_800,
        12_900,
        8_100,
        True,
    )
    year = _mapping(_mapping(result.report["years"])["2025"])
    assert year["stake_yen"] == 4_800
    assert year["receipt_yen"] == 12_900
    assert year["recovery_rate"] == pytest.approx(12_900 / 4_800)
    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert counts["purchased"] == 1
    assert counts["scaled"] == 1


def test_report_has_the_adr044_keys_and_consistent_counts() -> None:
    other = race_id(2025, 2)
    held = race_id(2025, 3)
    result = _run(
        [_race(), _race(other), _race(held)],
        holds={held: "target_outcome"},
    )

    assert set(result.report) == {
        "format",
        "format_version",
        "config",
        "inputs",
        "provenance",
        "policy",
        "estimation",
        "selection",
        "counts",
        "years",
        "all_test_years",
        "common_years",
        "methods",
    }
    assert result.report["format"] == "ev_betting_backtest"
    assert result.report["format_version"] == 2
    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert counts["graded_races"] == 3
    assert counts["no_prediction"] == {
        "target_outcome": 1,
        "target_pre_freeze": 0,
        "other_held": 0,
        "unattributed": 1,
    }
    accounted = (
        sum(cast(dict[str, int], counts["no_prediction"]).values())
        + sum(cast(dict[str, int], counts["holds"]).values())
        + cast(int, counts["no_eligible_bet"])
        + cast(int, counts["purchased"])
        + cast(int, counts["budget_exhausted"])
    )
    assert accounted == counts["graded_races"]
    assert json.loads(json.dumps(result.report)) == result.report
    year = _mapping(_mapping(result.report["years"])["2025"])
    assert year["stake_yen"] == sum(cast(int, row["stake_yen"]) for row in result.bets)
    assert year["receipt_yen"] == sum(cast(int, row["receipt_yen"]) for row in result.races)


def test_place_correction_uses_only_hits_before_the_test_year_without_quinella() -> None:
    base = _run(hits=_hits(2024))
    changed = _run(hits=[*_hits(2024), *_hits(2025, ratio=3.0), *_hits(2026, ratio=3.0)])

    assert base.bets == changed.bets
    place = [row for row in base.bets if row["bet_type"] == "place"]
    assert place[0]["estimated_odds"] == pytest.approx(place[0]["freeze_odds"])


def test_earlier_hits_change_the_place_estimate() -> None:
    doubled = _run(hits=_hits(2024, ratio=2.0))

    place = [row for row in doubled.bets if row["bet_type"] == "place"]
    assert place
    assert place[0]["estimated_odds"] == pytest.approx(2.0 * cast(float, place[0]["freeze_odds"]))


def test_a_year_without_place_training_hits_is_rejected() -> None:
    with pytest.raises(ValueError, match="no place_mid training hits"):
        _run(hits=_hits(2025))


@pytest.mark.parametrize(
    ("race", "reason"),
    [
        (_race(o1=[o1_row(RACE, clock="1514")]), "stale_publication"),
        (_race(o1=[]), "no_publication"),
        (_race(se=se_rows(RACE)[:7]), "entrant_mismatch"),
        (_race(se=[]), "no_entrants"),
        (_race(ra=[ra_row(RACE, headDataKubun="9")]), "cancelled_race"),
    ],
)
def test_races_without_a_valid_freeze_market_or_entrants_are_held(
    race: GradedRaceInput, reason: str
) -> None:
    result = _run([race])

    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert counts["holds"] == {reason: 1}
    assert result.bets == ()


def test_market_odds_that_differ_from_o1_hold_the_race() -> None:
    result = _run(predictions=prediction_rows(RACE, market={"04": 9.9}))

    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert counts["holds"] == {"market_odds_mismatch": 1}


def test_four_entrants_offer_no_place_bets() -> None:
    horses = ("01", "02", "03", "04")
    rows = prediction_rows(RACE, horses=horses)
    for row, values in zip(
        rows, ((0.4, 0.7, 0.9), (0.3, 0.6, 0.85), (0.2, 0.4, 0.7), (0.1, 0.3, 0.55)), strict=True
    ):
        row["p_win"], row["p_top2"], row["p_top3"] = values
    race = _race(
        o1=[
            o1_row(
                RACE,
                horses=horses,
                win_codes=("0030", "0060", "0080", "0080"),
                place_codes=(("0030", "0040"),) * 4,
            )
        ],
        se=se_rows(RACE, horses),
    )

    result = _run([race], predictions=rows)

    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert counts["place_unavailable"] == 1
    assert {row["bet_type"] for row in result.bets} == {"win"}


def test_refunded_horses_are_settled_as_refunds() -> None:
    result = _run([_race(hr=[hr_row(RACE, HenkanUma1="1", HenkanFlag0="1")])])

    refunds = {row["horse_number"]: row["refund_yen"] for row in result.bets}
    assert refunds["02"] == 800
    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert counts["refunded_bets"] == 1


@pytest.mark.parametrize(
    "hr",
    [
        [hr_row(RACE, TokubaraiFlag0="1")],
        [hr_row(RACE, FuseirituFlag1="1")],
        [],
        [hr_row(RACE, headDataKubun="1")],
        [hr_row(RACE), hr_row(RACE, SyussoTosu="09")],
    ],
)
def test_a_purchased_race_that_cannot_be_settled_stops_the_backtest(
    hr: list[dict[str, object]],
) -> None:
    with pytest.raises(ValueError, match="purchased race cannot be settled"):
        _run([_race(hr=hr)])


def test_an_annual_budget_left_below_one_unit_is_counted() -> None:
    second = race_id(2025, 2)
    settings = _settings(policy=BettingPolicy(annual_budget_yen=4_850))
    result = _run(
        [_race(), _race(second)],
        predictions=[*prediction_rows(RACE), *prediction_rows(second)],
        settings=settings,
    )

    counts = _mapping(_mapping(result.report["counts"])["2025"])
    assert (counts["purchased"], counts["budget_exhausted"]) == (1, 1)


def test_predictions_outside_the_graded_races_are_rejected() -> None:
    with pytest.raises(ValueError, match="outside the graded test races"):
        _run(predictions=[*prediction_rows(RACE), *prediction_rows(race_id(2025, 4))])


def test_settings_reject_invalid_years() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        _settings(test_years=(2025, 2025))
    with pytest.raises(ValueError, match="before the first test year"):
        replace(_settings(), train_start_year=2025)


def test_later_payouts_results_and_hits_do_not_change_an_earlier_years_decisions() -> None:
    first, second = race_id(2024), race_id(2025)
    settings = _settings(test_years=(2024, 2025))
    rows = [*prediction_rows(first), *prediction_rows(second)]
    changed_rows = [
        {**row, "finish_position": 9 - cast(int, row["finish_position"])} for row in rows
    ]

    base = _run(
        [_race(first), _race(second)],
        predictions=rows,
        hits=_hits(2023),
        settings=settings,
    )
    changed = _run(
        [_race(first), _race(second, hr=[hr_row(second, win=(("05", 2_000),))])],
        predictions=changed_rows,
        hits=[*_hits(2023), *_hits(2024, ratio=3.0), *_hits(2025, ratio=3.0)],
        settings=settings,
    )

    decision_columns = (
        "race_id",
        "bet_type",
        "horse_number",
        "probability",
        "freeze_odds",
        "estimated_odds",
        "expected_return",
        "kelly_fraction",
        "requested_stake_yen",
        "stake_yen",
    )

    def decisions(result: BettingBacktest, year: int) -> list[tuple[object, ...]]:
        return [
            tuple(row[name] for name in decision_columns)
            for row in result.bets
            if row["test_year"] == year
        ]

    assert decisions(base, 2024) == decisions(changed, 2024)
    assert (
        bets_table(base)
        .slice(0, len(decisions(base, 2024)))
        .equals(bets_table(changed).slice(0, len(decisions(changed, 2024))))
    )
    assert decisions(base, 2025)
