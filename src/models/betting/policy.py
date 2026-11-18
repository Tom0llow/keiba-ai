"""Apply ADR-043's fixed expected-value betting policy without I/O."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from math import floor, isfinite
from numbers import Real
from typing import Literal
from zoneinfo import ZoneInfo

BetType = Literal["win", "place"]
RaceOutcome = Literal["purchased", "no_eligible_bet", "budget_exhausted"]
JST = ZoneInfo("Asia/Tokyo")
MAX_HORSE_NUMBER = 28


@dataclass(frozen=True)
class BettingPolicy:
    """Hold the fixed amounts and thresholds of ADR-043 Decision 5."""

    min_expected_return: float = 1.10
    kelly_fraction: float = 0.25
    bankroll_yen: int = 100_000
    annual_budget_yen: int = 100_000
    race_budget_yen: int = 5_000
    unit_yen: int = 100

    def __post_init__(self) -> None:
        # Below 1.0 the Kelly fraction of an eligible bet could be negative.
        if _positive_finite_real(self.min_expected_return, "min_expected_return") < 1.0:
            raise ValueError("min_expected_return must be at least 1.0")
        _positive_finite_real(self.kelly_fraction, "kelly_fraction")
        for name, value in (
            ("bankroll_yen", self.bankroll_yen),
            ("annual_budget_yen", self.annual_budget_yen),
            ("race_budget_yen", self.race_budget_yen),
            ("unit_yen", self.unit_yen),
        ):
            _positive_integer(value, name)
        # Settlement pays stake x payout / 100 yen, which is whole only for 100-yen multiples.
        if self.unit_yen % 100 != 0:
            raise ValueError("unit_yen must be a multiple of 100 (the JRA selling unit)")


@dataclass(frozen=True)
class BetCandidate:
    """Describe one win or place bet before the policy assigns a stake."""

    race_id: str
    freeze_at: datetime
    bet_type: BetType
    horse_number: str
    probability: float
    freeze_odds: float
    estimated_odds: float

    def __post_init__(self) -> None:
        if not isinstance(self.race_id, str) or not self.race_id:
            raise ValueError("race_id must be a non-empty string")
        if self.freeze_at.tzinfo is None or self.freeze_at.utcoffset() is None:
            raise ValueError("freeze_at must be timezone-aware")
        if self.bet_type not in ("win", "place"):
            raise ValueError("bet_type must be 'win' or 'place'")
        _horse_number(self.horse_number)
        probability = _finite_real(self.probability, "probability")
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be between zero and one")
        _positive_finite_real(self.freeze_odds, "freeze_odds")
        _positive_finite_real(self.estimated_odds, "estimated_odds")


@dataclass(frozen=True)
class Bet:
    """Describe a policy-selected bet, including its requested and final stake."""

    race_id: str
    freeze_at: datetime
    bet_type: BetType
    horse_number: str
    probability: float
    freeze_odds: float
    estimated_odds: float
    expected_return: float
    kelly_fraction: float
    requested_stake_yen: int
    stake_yen: int


@dataclass(frozen=True)
class RaceDecision:
    """Describe the policy outcome of one race that had bet candidates.

    ``no_eligible_bet`` means no candidate reached the expected-return threshold
    with a positive stake. ``budget_exhausted`` means the remaining annual
    budget, or the proportional reduction to it, left no stake of one unit.
    ``scaled`` is true when the race total was reduced to its cap.
    """

    race_id: str
    freeze_at: datetime
    outcome: RaceOutcome
    scaled: bool
    bets: tuple[Bet, ...]


def place_probability(*, entrant_count: int, p_top2: float, p_top3: float) -> float | None:
    """Return the ADR-043 place probability for an entrant count.

    Place bets are not available for four or fewer entrants.  Five to seven
    entrants use the top-two probability, and eight or more use top-three.
    """
    _positive_integer(entrant_count, "entrant_count")
    _probability(p_top2, "p_top2")
    _probability(p_top3, "p_top3")
    if entrant_count <= 4:
        return None
    return p_top2 if entrant_count <= 7 else p_top3


def select_bets(
    candidates: Sequence[BetCandidate], *, policy: BettingPolicy | None = None
) -> tuple[Bet, ...]:
    """Return the purchased bets of ``decide_races`` in processing order."""
    decisions = decide_races(candidates, policy=policy)
    return tuple(bet for decision in decisions for bet in decision.bets)


def decide_races(
    candidates: Sequence[BetCandidate], *, policy: BettingPolicy | None = None
) -> tuple[RaceDecision, ...]:
    """Return one decision per race with candidates, under the annual and race limits.

    Races are processed by freeze then race ID.  A race over its remaining cap
    has every requested stake proportionally reduced and rounded down to the
    configured unit.  Neither refunds nor payouts participate in this policy.
    """
    selected_policy = BettingPolicy() if policy is None else policy
    _consistent_race_freezes(candidates)
    ordered = sorted(candidates, key=_candidate_order_key)
    decisions: list[RaceDecision] = []
    annual_spent: dict[int, int] = {}
    index = 0
    while index < len(ordered):
        candidate = ordered[index]
        race_key = (candidate.freeze_at, candidate.race_id)
        group: list[BetCandidate] = []
        while (
            index < len(ordered) and (ordered[index].freeze_at, ordered[index].race_id) == race_key
        ):
            group.append(ordered[index])
            index += 1
        requested = [
            bet for item in group if (bet := requested_bet(item, selected_policy)) is not None
        ]
        race_id, freeze_at = candidate.race_id, candidate.freeze_at
        if not requested:
            decisions.append(RaceDecision(race_id, freeze_at, "no_eligible_bet", False, ()))
            continue
        year = freeze_at.astimezone(JST).year
        remaining = selected_policy.annual_budget_yen - annual_spent.get(year, 0)
        cap = min(selected_policy.race_budget_yen, remaining)
        total_requested = sum(bet.requested_stake_yen for bet in requested)
        scaled = total_requested > cap
        funded = (
            _scale_bets(requested, cap=cap, unit_yen=selected_policy.unit_yen)
            if scaled
            else requested
        )
        if not funded:
            reduced = scaled and cap >= selected_policy.unit_yen
            decisions.append(RaceDecision(race_id, freeze_at, "budget_exhausted", reduced, ()))
            continue
        annual_spent[year] = annual_spent.get(year, 0) + sum(bet.stake_yen for bet in funded)
        decisions.append(RaceDecision(race_id, freeze_at, "purchased", scaled, tuple(funded)))
    return tuple(decisions)


def requested_bet(candidate: BetCandidate, policy: BettingPolicy) -> Bet | None:
    """Return the candidate's Kelly bet before any cap, or None when it is not eligible."""
    expected_return = candidate.probability * candidate.estimated_odds
    if expected_return < policy.min_expected_return or candidate.estimated_odds <= 1.0:
        return None
    kelly_fraction = (expected_return - 1.0) / (candidate.estimated_odds - 1.0)
    requested_stake = _floor_to_unit(
        policy.kelly_fraction * kelly_fraction * policy.bankroll_yen, policy.unit_yen
    )
    if requested_stake == 0:
        return None
    return Bet(
        race_id=candidate.race_id,
        freeze_at=candidate.freeze_at,
        bet_type=candidate.bet_type,
        horse_number=candidate.horse_number,
        probability=candidate.probability,
        freeze_odds=candidate.freeze_odds,
        estimated_odds=candidate.estimated_odds,
        expected_return=expected_return,
        kelly_fraction=kelly_fraction,
        requested_stake_yen=requested_stake,
        stake_yen=requested_stake,
    )


def _scale_bets(bets: Sequence[Bet], *, cap: int, unit_yen: int) -> list[Bet]:
    if cap < unit_yen:
        return []
    total = sum(bet.requested_stake_yen for bet in bets)
    scaled: list[Bet] = []
    for bet in bets:
        stake = bet.requested_stake_yen * cap // (total * unit_yen) * unit_yen
        if stake:
            scaled.append(replace(bet, stake_yen=stake))
    return scaled


def _consistent_race_freezes(candidates: Sequence[BetCandidate]) -> None:
    freezes: dict[str, datetime] = {}
    seen: set[tuple[str, BetType, str]] = set()
    for candidate in candidates:
        prior = freezes.setdefault(candidate.race_id, candidate.freeze_at)
        if prior != candidate.freeze_at:
            raise ValueError("one race_id must have one freeze_at")
        identity = (candidate.race_id, candidate.bet_type, candidate.horse_number)
        if identity in seen:
            raise ValueError(
                "candidates must not contain duplicate race, bet type and horse number"
            )
        seen.add(identity)


def _candidate_order_key(candidate: BetCandidate) -> tuple[datetime, str, BetType, str]:
    return candidate.freeze_at, candidate.race_id, candidate.bet_type, candidate.horse_number


def _floor_to_unit(value: float, unit_yen: int) -> int:
    # The tolerance keeps an exact multiple such as 1,000 yen from falling to 900 yen
    # through floating-point error in the Kelly fraction.
    return floor(value / unit_yen + 1e-9) * unit_yen


def _horse_number(value: str) -> None:
    if not isinstance(value, str) or len(value) != 2 or not value.isdigit():
        raise ValueError("horse_number must be a two-digit string")
    if not 1 <= int(value) <= MAX_HORSE_NUMBER:
        raise ValueError("horse_number must be between 01 and 28")


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _finite_real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _positive_finite_real(value: float, name: str) -> float:
    number = _finite_real(value, name)
    if number <= 0.0:
        raise ValueError(f"{name} must be a positive finite real number")
    return number


def _probability(value: float, name: str) -> None:
    number = _finite_real(value, name)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


__all__ = [
    "Bet",
    "BetCandidate",
    "BetType",
    "BettingPolicy",
    "RaceDecision",
    "RaceOutcome",
    "decide_races",
    "place_probability",
    "select_bets",
]
