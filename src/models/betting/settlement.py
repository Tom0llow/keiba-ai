"""Settle policy-selected bets from finalized B3 payout observations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from models.betting.policy import Bet
from models.serialization.final_odds_observations import BetType as PayoutType
from models.serialization.final_odds_observations import RacePayouts


@dataclass(frozen=True)
class SettledBet:
    """Hold one purchased bet and its payout and refund receipts in yen."""

    bet: Bet
    payout_yen: int
    refund_yen: int

    @property
    def receipt_yen(self) -> int:
        """Return the total settlement receipt in yen."""
        return self.payout_yen + self.refund_yen


def settle_bets(bets: Sequence[Bet], payouts: RacePayouts) -> tuple[SettledBet, ...]:
    """Return the final settlement of one race's selected bets.

    A refunded horse receives its stake and no payout.  Other bets receive the
    matching finalized payout, if any.  ``race_payouts`` rejects special,
    unestablished, missing, ambiguous and unfinalized payout rows before this
    function can receive a ``RacePayouts`` value.
    """
    if not bets:
        return ()
    race_ids = {bet.race_id for bet in bets}
    if len(race_ids) != 1 or payouts.race_id not in race_ids:
        raise ValueError("bets and payouts must belong to one matching race")
    refunded = set(payouts.refunded_horse_numbers)
    settled: list[SettledBet] = []
    for bet in bets:
        if bet.stake_yen < 1:
            raise ValueError("bets must have a positive stake_yen")
        if bet.horse_number in refunded:
            settled.append(SettledBet(bet, payout_yen=0, refund_yen=bet.stake_yen))
            continue
        payout_odds = _payout_odds(payouts, bet)
        payout_yen = round(bet.stake_yen * payout_odds) if payout_odds is not None else 0
        settled.append(SettledBet(bet, payout_yen=payout_yen, refund_yen=0))
    return tuple(settled)


def _payout_odds(payouts: RacePayouts, bet: Bet) -> float | None:
    payout_type: PayoutType = "win" if bet.bet_type == "win" else "place_mid"
    matches = [odds for horse, odds in payouts.paid[payout_type] if horse == bet.horse_number]
    if len(matches) > 1:
        raise ValueError("payouts must not contain duplicate horse payouts")
    return matches[0] if matches else None


__all__ = ["SettledBet", "settle_bets"]
