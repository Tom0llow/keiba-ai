"""Calculate ADR-043 betting metrics from settled bets without I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import floor, isfinite
from numbers import Real
from random import Random

from models.betting.policy import JST, BetType
from models.betting.settlement import SettledBet

_BET_TYPES: tuple[BetType, ...] = ("win", "place")


@dataclass(frozen=True)
class RecoveryRateInterval:
    """Hold a percentile-bootstrap interval for a recovery rate."""

    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class BetTypeMetrics:
    """Hold one bet type's aggregate purchase and receipt metrics."""

    bets: int
    hits: int
    stake_yen: int
    receipt_yen: int
    recovery_rate: float | None


@dataclass(frozen=True)
class RaceBettingMetrics:
    """Hold settlement and running annual totals for one purchased race."""

    race_id: str
    freeze_at: datetime
    stake_yen: int
    payout_yen: int
    refund_yen: int
    receipt_yen: int
    net_yen: int
    cumulative_net_yen: int
    annual_stake_yen: int
    hit: bool


@dataclass(frozen=True)
class YearBettingMetrics:
    """Hold all required metrics for one calendar year or the test-year total."""

    stake_yen: int
    payout_yen: int
    refund_yen: int
    receipt_yen: int
    recovery_rate: float | None
    net_yen: int
    purchased_races: int
    hit_races: int
    hit_rate: float | None
    maximum_drawdown_yen: int
    maximum_consecutive_losses: int
    recovery_rate_interval: RecoveryRateInterval
    bet_types: Mapping[BetType, BetTypeMetrics]
    races: tuple[RaceBettingMetrics, ...]


@dataclass(frozen=True)
class BettingMetrics:
    """Hold calendar-year metrics and the ADR-043 all-test-years summary."""

    years: Mapping[int, YearBettingMetrics]
    all_test_years: YearBettingMetrics


@dataclass(frozen=True)
class _RaceSettlement:
    """Store one race's grouped settled bets before metric calculation."""

    race_id: str
    freeze_at: datetime
    bets: tuple[SettledBet, ...]


def betting_metrics(
    settled_bets: Sequence[SettledBet],
    *,
    test_years: Sequence[int],
    bootstrap_resamples: int = 2_000,
    bootstrap_seed: int = 0,
    bootstrap_confidence: float = 0.95,
) -> BettingMetrics:
    """Return calendar-year and all-test-years metrics for settled purchases.

    The recovery-rate interval resamples purchased races with replacement.  It
    intentionally does not replay the budget policy, as required by ADR-043.
    The all-years maximum drawdown and losing streak are the largest separate
    annual values; they never cross a calendar-year boundary.
    """
    years = _test_years(test_years)
    _bootstrap_settings(bootstrap_resamples, bootstrap_seed, bootstrap_confidence)
    grouped = _group_races(settled_bets)
    races_by_year: dict[int, list[_RaceSettlement]] = {year: [] for year in years}
    for race in grouped:
        year = race.freeze_at.astimezone(JST).year
        if year not in races_by_year:
            raise ValueError("settled bets must fall within test_years")
        races_by_year[year].append(race)
    yearly = {
        year: _year_metrics(
            races_by_year[year],
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_seed=bootstrap_seed,
            bootstrap_confidence=bootstrap_confidence,
        )
        for year in years
    }
    return BettingMetrics(
        yearly, _all_year_metrics(yearly, bootstrap_resamples, bootstrap_seed, bootstrap_confidence)
    )


def _test_years(values: Sequence[int]) -> tuple[int, ...]:
    years: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("test_years must contain positive integers")
        if value in years:
            raise ValueError("test_years must not contain duplicates")
        years.append(value)
    if not years:
        raise ValueError("test_years must not be empty")
    return tuple(sorted(years))


def _group_races(settled_bets: Sequence[SettledBet]) -> tuple[_RaceSettlement, ...]:
    grouped: dict[tuple[datetime, str], list[SettledBet]] = {}
    freezes: dict[str, datetime] = {}
    for settled in settled_bets:
        bet = settled.bet
        if bet.stake_yen < 1:
            raise ValueError("settled bets must have a positive stake_yen")
        if settled.payout_yen < 0 or settled.refund_yen < 0:
            raise ValueError("settled receipts must not be negative")
        prior = freezes.setdefault(bet.race_id, bet.freeze_at)
        if prior != bet.freeze_at:
            raise ValueError("one race_id must have one freeze_at")
        grouped.setdefault((bet.freeze_at, bet.race_id), []).append(settled)
    return tuple(
        _RaceSettlement(race_id, freeze_at, tuple(bets))
        for (freeze_at, race_id), bets in sorted(grouped.items())
    )


def _year_metrics(
    races: Sequence[_RaceSettlement],
    *,
    bootstrap_resamples: int,
    bootstrap_seed: int,
    bootstrap_confidence: float,
) -> YearBettingMetrics:
    stake_yen = 0
    payout_yen = 0
    refund_yen = 0
    cumulative_net_yen = 0
    annual_stake_yen = 0
    peak_net_yen = 0
    maximum_drawdown_yen = 0
    maximum_consecutive_losses = 0
    consecutive_losses = 0
    hit_races = 0
    race_metrics: list[RaceBettingMetrics] = []
    all_bets: list[SettledBet] = []
    for race in races:
        race_stake = sum(item.bet.stake_yen for item in race.bets)
        race_payout = sum(item.payout_yen for item in race.bets)
        race_refund = sum(item.refund_yen for item in race.bets)
        race_receipt = race_payout + race_refund
        race_net = race_receipt - race_stake
        stake_yen += race_stake
        payout_yen += race_payout
        refund_yen += race_refund
        annual_stake_yen += race_stake
        cumulative_net_yen += race_net
        peak_net_yen = max(peak_net_yen, cumulative_net_yen)
        maximum_drawdown_yen = max(maximum_drawdown_yen, peak_net_yen - cumulative_net_yen)
        hit = race_payout > 0
        if hit:
            hit_races += 1
            consecutive_losses = 0
        else:
            consecutive_losses += 1
            maximum_consecutive_losses = max(maximum_consecutive_losses, consecutive_losses)
        race_metrics.append(
            RaceBettingMetrics(
                race_id=race.race_id,
                freeze_at=race.freeze_at,
                stake_yen=race_stake,
                payout_yen=race_payout,
                refund_yen=race_refund,
                receipt_yen=race_receipt,
                net_yen=race_net,
                cumulative_net_yen=cumulative_net_yen,
                annual_stake_yen=annual_stake_yen,
                hit=hit,
            )
        )
        all_bets.extend(race.bets)
    receipt_yen = payout_yen + refund_yen
    return YearBettingMetrics(
        stake_yen=stake_yen,
        payout_yen=payout_yen,
        refund_yen=refund_yen,
        receipt_yen=receipt_yen,
        recovery_rate=_ratio(receipt_yen, stake_yen),
        net_yen=receipt_yen - stake_yen,
        purchased_races=len(races),
        hit_races=hit_races,
        hit_rate=_ratio(hit_races, len(races)),
        maximum_drawdown_yen=maximum_drawdown_yen,
        maximum_consecutive_losses=maximum_consecutive_losses,
        recovery_rate_interval=_bootstrap_recovery_rate(
            race_metrics,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
            confidence=bootstrap_confidence,
        ),
        bet_types=_bet_type_metrics(all_bets),
        races=tuple(race_metrics),
    )


def _all_year_metrics(
    yearly: Mapping[int, YearBettingMetrics],
    resamples: int,
    seed: int,
    confidence: float,
) -> YearBettingMetrics:
    values = tuple(yearly.values())
    races = tuple(race for year in values for race in year.races)
    stake_yen = sum(year.stake_yen for year in values)
    payout_yen = sum(year.payout_yen for year in values)
    refund_yen = sum(year.refund_yen for year in values)
    receipt_yen = payout_yen + refund_yen
    return YearBettingMetrics(
        stake_yen=stake_yen,
        payout_yen=payout_yen,
        refund_yen=refund_yen,
        receipt_yen=receipt_yen,
        recovery_rate=_ratio(receipt_yen, stake_yen),
        net_yen=receipt_yen - stake_yen,
        purchased_races=sum(year.purchased_races for year in values),
        hit_races=sum(year.hit_races for year in values),
        hit_rate=_ratio(
            sum(year.hit_races for year in values), sum(year.purchased_races for year in values)
        ),
        maximum_drawdown_yen=max(year.maximum_drawdown_yen for year in values),
        maximum_consecutive_losses=max(year.maximum_consecutive_losses for year in values),
        recovery_rate_interval=_bootstrap_recovery_rate(
            races, resamples=resamples, seed=seed, confidence=confidence
        ),
        bet_types=_all_bet_type_metrics(values),
        races=races,
    )


def _bet_type_metrics(bets: Sequence[SettledBet]) -> dict[BetType, BetTypeMetrics]:
    return {bet_type: _one_bet_type_metrics(bets, bet_type) for bet_type in _BET_TYPES}


def _all_bet_type_metrics(values: Sequence[YearBettingMetrics]) -> dict[BetType, BetTypeMetrics]:
    result: dict[BetType, BetTypeMetrics] = {}
    for bet_type in _BET_TYPES:
        type_values = [year.bet_types[bet_type] for year in values]
        stake_yen = sum(value.stake_yen for value in type_values)
        receipt_yen = sum(value.receipt_yen for value in type_values)
        result[bet_type] = BetTypeMetrics(
            bets=sum(value.bets for value in type_values),
            hits=sum(value.hits for value in type_values),
            stake_yen=stake_yen,
            receipt_yen=receipt_yen,
            recovery_rate=_ratio(receipt_yen, stake_yen),
        )
    return result


def _one_bet_type_metrics(bets: Sequence[SettledBet], bet_type: BetType) -> BetTypeMetrics:
    selected = [item for item in bets if item.bet.bet_type == bet_type]
    stake_yen = sum(item.bet.stake_yen for item in selected)
    receipt_yen = sum(item.receipt_yen for item in selected)
    return BetTypeMetrics(
        bets=len(selected),
        hits=sum(item.payout_yen > 0 for item in selected),
        stake_yen=stake_yen,
        receipt_yen=receipt_yen,
        recovery_rate=_ratio(receipt_yen, stake_yen),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _bootstrap_recovery_rate(
    races: Sequence[RaceBettingMetrics], *, resamples: int, seed: int, confidence: float
) -> RecoveryRateInterval:
    if not races:
        return RecoveryRateInterval(None, None)
    generator = Random(seed)
    values: list[float] = []
    for _ in range(resamples):
        selected = [races[generator.randrange(len(races))] for _ in range(len(races))]
        stake_yen = sum(race.stake_yen for race in selected)
        receipt_yen = sum(race.receipt_yen for race in selected)
        values.append(receipt_yen / stake_yen)
    values.sort()
    tail = (1.0 - confidence) / 2.0
    return RecoveryRateInterval(
        lower=_percentile(values, tail),
        upper=_percentile(values, 1.0 - tail),
    )


def _percentile(values: Sequence[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower_index = floor(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    return values[lower_index] * (1.0 - weight) + values[upper_index] * weight


def _bootstrap_settings(resamples: int, seed: int, confidence: float) -> None:
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ValueError("bootstrap_resamples must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("bootstrap_seed must be an integer")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, Real)
        or not isfinite(float(confidence))
    ):
        raise ValueError("bootstrap_confidence must be between zero and one")
    if not 0.0 < float(confidence) < 1.0:
        raise ValueError("bootstrap_confidence must be between zero and one")


__all__ = [
    "BetTypeMetrics",
    "BettingMetrics",
    "RaceBettingMetrics",
    "RecoveryRateInterval",
    "YearBettingMetrics",
    "betting_metrics",
]
