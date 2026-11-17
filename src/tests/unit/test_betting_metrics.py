"""Tests for ADR-043 calendar-year betting metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import pytest

from models.betting.policy import Bet
from models.betting.settlement import SettledBet
from models.evaluation.betting_metrics import betting_metrics

JST = ZoneInfo("Asia/Tokyo")


def test_betting_metrics_match_hand_calculated_yearly_values() -> None:
    metrics = betting_metrics(
        [
            _settled("r1", 1, stake=100, payout=200),
            _settled("r2", 2, stake=100),
            _settled("r3", 3, stake=100, refund=100),
            _settled("r4", 4, stake=100),
        ],
        test_years=[2024, 2025],
        bootstrap_resamples=100,
        bootstrap_seed=7,
    )

    year = metrics.years[2025]
    assert (year.stake_yen, year.payout_yen, year.refund_yen, year.receipt_yen) == (
        400,
        200,
        100,
        300,
    )
    assert year.recovery_rate == pytest.approx(0.75)
    assert year.net_yen == -100
    assert (year.purchased_races, year.hit_races) == (4, 1)
    assert year.hit_rate == pytest.approx(0.25)
    assert year.maximum_drawdown_yen == 200
    assert year.maximum_consecutive_losses == 3
    assert [race.cumulative_net_yen for race in year.races] == [100, 0, 0, -100]
    assert [race.annual_stake_yen for race in year.races] == [100, 200, 300, 400]
    assert year.bet_types["win"].bets == 4
    assert year.bet_types["win"].hits == 1

    empty = metrics.years[2024]
    assert empty.recovery_rate is None
    assert empty.hit_rate is None
    assert empty.recovery_rate_interval.lower is None
    assert empty.recovery_rate_interval.upper is None
    assert metrics.all_test_years.maximum_drawdown_yen == 200
    assert metrics.all_test_years.maximum_consecutive_losses == 3


def test_betting_metrics_resets_drawdown_and_losing_streak_at_year_boundaries() -> None:
    metrics = betting_metrics(
        [
            _settled("r1", 1, stake=100, payout=300),
            _settled("r2", 2, stake=100),
            _settled("r3", 1, year=2026, stake=100),
            _settled("r4", 2, year=2026, stake=100),
        ],
        test_years=[2025, 2026],
        bootstrap_resamples=20,
    )

    # Across years the streak would be 3 and the drawdown 300 (peak +200, then -100).
    assert metrics.years[2025].maximum_consecutive_losses == 1
    assert metrics.years[2026].maximum_consecutive_losses == 2
    assert metrics.all_test_years.maximum_consecutive_losses == 2
    assert metrics.years[2025].maximum_drawdown_yen == 100
    assert metrics.years[2026].maximum_drawdown_yen == 200
    assert metrics.all_test_years.maximum_drawdown_yen == 200
    assert [race.cumulative_net_yen for race in metrics.years[2026].races] == [-100, -200]


def test_betting_metrics_bootstrap_is_deterministic() -> None:
    settled = [_settled("r1", 1, stake=100, payout=200), _settled("r2", 2, stake=100)]

    first = betting_metrics(settled, test_years=[2025], bootstrap_resamples=100, bootstrap_seed=11)
    second = betting_metrics(settled, test_years=[2025], bootstrap_resamples=100, bootstrap_seed=11)

    assert first == second
    interval = first.years[2025].recovery_rate_interval
    assert interval.lower is not None
    assert interval.upper is not None
    assert interval.lower < interval.upper


def _settled(
    race_id: str,
    day: int,
    *,
    year: int = 2025,
    stake: int,
    payout: int = 0,
    refund: int = 0,
    bet_type: Literal["win", "place"] = "win",
) -> SettledBet:
    bet = Bet(
        race_id=race_id,
        freeze_at=datetime(year, 1, day, 10, tzinfo=JST),
        bet_type=bet_type,
        horse_number="01",
        probability=0.2,
        freeze_odds=6.0,
        estimated_odds=6.0,
        expected_return=1.2,
        kelly_fraction=0.04,
        requested_stake_yen=stake,
        stake_yen=stake,
    )
    return SettledBet(bet, payout_yen=payout, refund_yen=refund)
