"""Tests for the fixed expected-value betting policy in ADR-043."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from models.betting.policy import (
    BetCandidate,
    BettingPolicy,
    decide_races,
    place_probability,
    select_bets,
)

JST = ZoneInfo("Asia/Tokyo")


def test_select_bets_matches_the_expected_return_kelly_and_stake_example() -> None:
    (bet,) = select_bets([_candidate(probability=0.2, estimated_odds=6.0)])

    assert bet.expected_return == pytest.approx(1.2)
    assert bet.kelly_fraction == pytest.approx(0.04)
    assert bet.requested_stake_yen == 1_000
    assert bet.stake_yen == 1_000


def test_select_bets_excludes_low_return_non_positive_margin_and_zero_stakes() -> None:
    selected = select_bets(
        [
            _candidate(horse_number="01", probability=0.2, estimated_odds=5.49),
            _candidate(horse_number="02", probability=1.0, estimated_odds=1.0),
            _candidate(horse_number="03", probability=0.011, estimated_odds=100.0),
        ]
    )

    assert selected == ()


def test_select_bets_scales_each_race_to_the_budget_in_hundred_yen_units() -> None:
    bets = select_bets(
        [
            _candidate(horse_number="01", probability=0.2, estimated_odds=11.0),
            _candidate(horse_number="02", probability=0.2, estimated_odds=11.0),
        ]
    )

    assert [bet.requested_stake_yen for bet in bets] == [3_000, 3_000]
    assert [bet.stake_yen for bet in bets] == [2_500, 2_500]
    assert sum(bet.stake_yen for bet in bets) == 5_000


def test_select_bets_uses_only_prior_stakes_for_annual_budget_and_resets_each_year() -> None:
    policy = BettingPolicy(annual_budget_yen=5_000)
    candidates = [
        _candidate(race_id="2026", freeze_at=_at(2026, 1, 1), horse_number="01"),
        _candidate(race_id="2025-2", freeze_at=_at(2025, 2, 1), horse_number="02"),
        _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="03"),
        _candidate(race_id="2025-3", freeze_at=_at(2025, 3, 1), horse_number="04"),
    ]

    bets = select_bets(candidates, policy=policy)

    assert [(bet.race_id, bet.stake_yen) for bet in bets] == [
        ("2025-1", 3_000),
        ("2025-2", 2_000),
        ("2026", 3_000),
    ]


def test_select_bets_skips_a_race_when_the_remaining_annual_budget_is_below_one_unit() -> None:
    policy = BettingPolicy(annual_budget_yen=50, unit_yen=100)

    assert select_bets([_candidate()], policy=policy) == ()


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"min_expected_return": 0.9}, "at least 1.0"),
        ({"unit_yen": 50}, "multiple of 100"),
        ({"kelly_fraction": 0.0}, "kelly_fraction"),
    ],
)
def test_betting_policy_rejects_values_that_break_kelly_or_settlement(
    fields: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        BettingPolicy(**fields)  # type: ignore[arg-type]


def test_place_probability_uses_the_entrant_count_rule() -> None:
    assert place_probability(entrant_count=9, p_top2=0.4, p_top3=0.6) == 0.6
    assert place_probability(entrant_count=8, p_top2=0.4, p_top3=0.6) == 0.6
    assert place_probability(entrant_count=7, p_top2=0.4, p_top3=0.6) == 0.4
    assert place_probability(entrant_count=5, p_top2=0.4, p_top3=0.6) == 0.4
    assert place_probability(entrant_count=4, p_top2=0.4, p_top3=0.6) is None


def _candidate(
    *,
    race_id: str = "2025010101010101",
    freeze_at: datetime | None = None,
    horse_number: str = "01",
    probability: float = 0.2,
    estimated_odds: float = 11.0,
) -> BetCandidate:
    return BetCandidate(
        race_id=race_id,
        freeze_at=_at(2025, 1, 1) if freeze_at is None else freeze_at,
        bet_type="win",
        horse_number=horse_number,
        probability=probability,
        freeze_odds=estimated_odds,
        estimated_odds=estimated_odds,
    )


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 10, 0, tzinfo=JST)


def test_decide_races_reports_each_race_outcome_and_scaling() -> None:
    policy = BettingPolicy(annual_budget_yen=5_200)
    decisions = decide_races(
        [
            _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="01"),
            _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="02"),
            _candidate(race_id="2025-2", freeze_at=_at(2025, 2, 1), probability=0.01),
            _candidate(race_id="2025-3", freeze_at=_at(2025, 3, 1), horse_number="03"),
            _candidate(race_id="2025-4", freeze_at=_at(2025, 4, 1), horse_number="04"),
        ],
        policy=policy,
    )

    assert [(d.race_id, d.outcome, d.scaled) for d in decisions] == [
        ("2025-1", "purchased", True),
        ("2025-2", "no_eligible_bet", False),
        ("2025-3", "purchased", True),
        ("2025-4", "budget_exhausted", False),
    ]
    assert [bet.stake_yen for bet in decisions[0].bets] == [2_500, 2_500]
    assert [bet.stake_yen for bet in decisions[2].bets] == [200]


def test_races_sharing_a_freeze_are_processed_in_race_id_order() -> None:
    policy = BettingPolicy(annual_budget_yen=3_000)
    freeze = _at(2025, 1, 1)

    decisions = decide_races(
        [
            _candidate(race_id="2025010101010102", freeze_at=freeze, horse_number="02"),
            _candidate(race_id="2025010101010101", freeze_at=freeze, horse_number="01"),
        ],
        policy=policy,
    )

    assert [(d.race_id, d.outcome) for d in decisions] == [
        ("2025010101010101", "purchased"),
        ("2025010101010102", "budget_exhausted"),
    ]


def test_scaling_that_leaves_every_bet_below_one_unit_exhausts_the_budget() -> None:
    policy = BettingPolicy(annual_budget_yen=5_100)
    (first, second) = decide_races(
        [
            _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="01"),
            _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="02"),
            _candidate(race_id="2025-2", freeze_at=_at(2025, 2, 1), horse_number="03"),
            _candidate(race_id="2025-2", freeze_at=_at(2025, 2, 1), horse_number="04"),
        ],
        policy=policy,
    )

    assert first.outcome == "purchased"
    assert (second.outcome, second.scaled, second.bets) == ("budget_exhausted", True, ())


def test_an_exact_kelly_multiple_is_not_rounded_down_by_floating_point_error() -> None:
    # 0.3 x 4.5 = 1.35 and f = 0.35 / 3.5 = 0.1 give exactly 2,500 yen at a quarter Kelly.
    (bet,) = select_bets([_candidate(probability=0.3, estimated_odds=4.5)])

    assert bet.requested_stake_yen == 2_500


def test_empty_prior_spending_keeps_every_decision_unchanged() -> None:
    candidates = [
        _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="01"),
        _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="02"),
        _candidate(race_id="2025-2", freeze_at=_at(2025, 2, 1), horse_number="03"),
    ]

    assert decide_races(candidates) == decide_races(
        candidates, annual_spent_yen={}, race_spent_yen={}
    )


def test_prior_race_spending_lowers_the_race_cap() -> None:
    (decision,) = decide_races(
        [_candidate(probability=0.2, estimated_odds=11.0)],
        race_spent_yen={"2025010101010101": 4_000},
    )

    assert (decision.outcome, decision.scaled) == ("purchased", True)
    assert [bet.stake_yen for bet in decision.bets] == [1_000]


def test_prior_annual_spending_lowers_the_cap_and_is_not_modified() -> None:
    spent = {2025: 98_000}
    first, second = decide_races(
        [
            _candidate(race_id="2025-1", freeze_at=_at(2025, 1, 1), horse_number="01"),
            _candidate(race_id="2025-2", freeze_at=_at(2025, 2, 1), horse_number="02"),
        ],
        annual_spent_yen=spent,
    )

    assert (first.outcome, [bet.stake_yen for bet in first.bets]) == ("purchased", [2_000])
    assert (second.outcome, second.scaled) == ("budget_exhausted", False)
    assert spent == {2025: 98_000}


def test_a_cap_below_one_unit_or_negative_exhausts_the_budget_without_scaling() -> None:
    for race_spent in (4_950, 6_000):
        (decision,) = decide_races([_candidate()], race_spent_yen={"2025010101010101": race_spent})

        assert (decision.outcome, decision.scaled, decision.bets) == (
            "budget_exhausted",
            False,
            (),
        )


def test_a_cap_of_one_unit_that_floors_every_bet_to_zero_is_scaled_and_exhausted() -> None:
    (decision,) = decide_races(
        [
            _candidate(horse_number="01"),
            _candidate(horse_number="02"),
        ],
        race_spent_yen={"2025010101010101": 4_900},
    )

    assert (decision.outcome, decision.scaled, decision.bets) == ("budget_exhausted", True, ())


@pytest.mark.parametrize(
    ("annual", "race"),
    [
        ({2025: -1}, None),
        ({2025: True}, None),
        ({2025: 100.0}, None),
        ({"2025": 100}, None),
        ({True: 100}, None),
        (None, {"race": -100}),
        (None, {1: 100}),
        (None, {"": 100}),
    ],
)
def test_malformed_prior_spending_is_rejected_even_without_candidates(
    annual: dict[object, object] | None, race: dict[object, object] | None
) -> None:
    with pytest.raises(ValueError, match="spent_yen"):
        decide_races([], annual_spent_yen=annual, race_spent_yen=race)  # type: ignore[arg-type]


def test_annual_spending_already_includes_the_race_spending() -> None:
    # 300 yen on this race is part of the 99,500 yen of the year: the cap is 500, not 200.
    (decision,) = decide_races(
        [_candidate()],
        annual_spent_yen={2025: 99_500},
        race_spent_yen={"2025010101010101": 300},
    )

    assert (decision.outcome, [bet.stake_yen for bet in decision.bets]) == ("purchased", [500])
