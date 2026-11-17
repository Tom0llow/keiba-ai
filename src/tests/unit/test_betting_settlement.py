"""Tests for final payout and refund settlement under ADR-043."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import pytest

from models.betting.policy import Bet
from models.betting.settlement import settle_bets
from models.serialization.final_odds_observations import RacePayouts

JST = ZoneInfo("Asia/Tokyo")
RACE_ID = "2025010101010101"


def test_settle_bets_pays_wins_loses_and_refunds_in_yen() -> None:
    settled = settle_bets(
        [
            _bet("01", "win", 1_000),
            _bet("02", "place", 100),
            _bet("03", "win", 300),
            _bet("04", "win", 500),
        ],
        _payouts(refunded=("04",)),
    )

    assert [(item.payout_yen, item.refund_yen, item.receipt_yen) for item in settled] == [
        (4_800, 0, 4_800),
        (230, 0, 230),
        (0, 0, 0),
        (0, 500, 500),
    ]


def test_settle_bets_pays_each_dead_heat_payout_row() -> None:
    settled = settle_bets(
        [_bet("01", "win", 100), _bet("02", "win", 100)],
        _payouts(win=(("01", 4.8), ("02", 6.0))),
    )

    assert [item.receipt_yen for item in settled] == [480, 600]


def test_settle_bets_rejects_bets_for_another_race() -> None:
    with pytest.raises(ValueError, match="matching race"):
        settle_bets([_bet("01", "win", 100, race_id="other")], _payouts())


def _bet(
    horse_number: str,
    bet_type: Literal["win", "place"],
    stake_yen: int,
    *,
    race_id: str = RACE_ID,
) -> Bet:
    return Bet(
        race_id=race_id,
        freeze_at=datetime(2025, 1, 1, 10, tzinfo=JST),
        bet_type=bet_type,
        horse_number=horse_number,
        probability=0.2,
        freeze_odds=6.0,
        estimated_odds=6.0,
        expected_return=1.2,
        kelly_fraction=0.04,
        requested_stake_yen=stake_yen,
        stake_yen=stake_yen,
    )


def _payouts(
    *,
    win: tuple[tuple[str, float], ...] = (("01", 4.8),),
    refunded: tuple[str, ...] = (),
) -> RacePayouts:
    return RacePayouts(
        race_id=RACE_ID,
        paid={
            "win": win,
            "place_low": (("02", 2.3),),
            "place_mid": (("02", 2.3),),
            "quinella": (),
        },
        expected={"win": 1, "place_low": 3, "place_mid": 3, "quinella": 1},
        refund=bool(refunded),
        refunded_horse_numbers=refunded,
    )
