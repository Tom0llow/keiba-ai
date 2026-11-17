"""Replay ADR-043's fixed win and place policy on graded races and report the results.

Pure: the CLI reads the snapshot, the PL evaluation and the datamart holds, and this module
fits the yearly place corrections, builds the candidates, applies the policy in time order,
settles the purchases and assembles the report and the two tables. No I/O.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise

import pyarrow as pa

from models.betting.policy import BetCandidate, BettingPolicy, place_probability
from models.betting.policy import decide_races as decide_policy_races
from models.betting.settlement import SettledBet, settle_bets
from models.evaluation.betting_metrics import (
    BetTypeMetrics,
    YearBettingMetrics,
    betting_metrics,
)
from models.market.final_odds_correction import (
    FinalOddsCorrection,
    fit_all_correction,
    fit_graded_correction,
    validate_odds_bands,
    validate_quantiles,
)
from models.serialization.betting_inputs import (
    RacePrediction,
    freeze_quotes,
    race_entrants,
)
from models.serialization.final_odds_observations import (
    HitObservation,
    ObservationHold,
    race_freeze,
    race_payouts,
)

REPORT_FORMAT = "ev_betting_backtest"
REPORT_FORMAT_VERSION = 1
NO_PREDICTION_STAGES = ("target_outcome", "target_pre_freeze", "other_held", "unattributed")
_BET_TYPE_ORDER = {"win": 0, "place": 1}


@dataclass(frozen=True)
class BettingBacktestSettings:
    """Hold ADR-043's fixed policy and the ADR-042 place-correction settings."""

    test_years: tuple[int, ...]
    policy: BettingPolicy
    train_start_year: int
    max_publication_age_seconds: int
    place_bands: tuple[float, ...]
    quantiles: tuple[float, ...]
    min_hits: int
    graded_shrinkage_k: int
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence: float

    def __post_init__(self) -> None:
        years = self.test_years
        if not years or any(isinstance(y, bool) or not isinstance(y, int) for y in years):
            raise ValueError("test_years must be a non-empty tuple of integers")
        if any(right <= left for left, right in pairwise(years)):
            raise ValueError("test_years must be strictly increasing without duplicates")
        if self.train_start_year >= years[0]:
            raise ValueError("train_start_year must be before the first test year")
        if self.max_publication_age_seconds < 1:
            raise ValueError("max_publication_age_seconds must be positive")
        validate_odds_bands(self.place_bands)
        validate_quantiles(self.quantiles)
        if self.min_hits < 1 or self.graded_shrinkage_k < 0:
            raise ValueError("min_hits must be positive and graded_shrinkage_k non-negative")


@dataclass(frozen=True)
class GradedRaceInput:
    """Hold one graded test race's stored rows (RA, O1, SE and HR)."""

    race_id: str
    ra_rows: Sequence[Mapping[str, object]]
    o1_rows: Sequence[Mapping[str, object]]
    se_rows: Sequence[Mapping[str, object]]
    hr_rows: Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class BettingBacktest:
    """Hold the report and the rows of ``bets.parquet`` and ``races.parquet``."""

    report: dict[str, object]
    bets: tuple[dict[str, object], ...]
    races: tuple[dict[str, object], ...]


@dataclass
class _YearCounts:
    graded_races: int = 0
    predicted: int = 0
    no_prediction: Counter[str] = field(default_factory=Counter)
    holds: Counter[str] = field(default_factory=Counter)
    place_unavailable: int = 0
    no_eligible_bet: int = 0
    purchased: int = 0
    scaled: int = 0
    budget_exhausted: int = 0
    refunded_bets: int = 0


def run_betting_backtest(
    *,
    settings: BettingBacktestSettings,
    graded_races: Sequence[GradedRaceInput],
    predictions: Mapping[str, RacePrediction],
    target_hold_stages: Mapping[str, str],
    training_hits: Sequence[HitObservation],
    graded_race_ids: frozenset[str],
    config: Mapping[str, object],
    inputs: Mapping[str, object],
    provenance: Mapping[str, object],
) -> BettingBacktest:
    """Replay the policy over the graded test races and assemble the outputs.

    ``training_hits`` are ADR-042 hit observations of every race from
    ``train_start_year``; only ``place_mid`` hits of years before each test year are used.
    ``graded_race_ids`` is the graded subset over the training years and the test years.
    ``target_hold_stages`` maps a held target race to its datamart stage.

    Raises:
        ValueError: If race IDs repeat or fall outside the test years, a prediction is not
            one of the graded races, a test year has no place training hits, or a purchased
            race cannot be settled (no, ambiguous or unfinal payout row, special payout or
            unestablished race).
    """
    test_years = settings.test_years
    by_id = {race.race_id: race for race in graded_races}
    if len(by_id) != len(graded_races):
        raise ValueError("graded races must be unique")
    if any(int(race_id[:4]) not in test_years for race_id in by_id):
        raise ValueError("graded races must fall within test_years")
    if not set(predictions) <= set(by_id):
        raise ValueError("PL predictions contain a race outside the graded test races")
    corrections = {
        year: _place_correction(training_hits, year, settings, graded_race_ids)
        for year in test_years
    }
    counts = {year: _YearCounts() for year in test_years}
    candidates: list[BetCandidate] = []
    hr_rows: dict[str, Sequence[Mapping[str, object]]] = {}
    for race_id in sorted(by_id):
        race = by_id[race_id]
        year = int(race_id[:4])
        count = counts[year]
        count.graded_races += 1
        prediction = predictions.get(race_id)
        if prediction is None:
            count.no_prediction[_no_prediction_stage(target_hold_stages.get(race_id))] += 1
            continue
        count.predicted += 1
        try:
            race_candidates, place_offered = _race_candidates(
                race, prediction, corrections[year], settings
            )
        except ObservationHold as hold:
            count.holds[hold.reason] += 1
            continue
        if not place_offered:
            count.place_unavailable += 1
        if not race_candidates:
            count.no_eligible_bet += 1
            continue
        candidates.extend(race_candidates)
        hr_rows[race_id] = race.hr_rows
    settled: list[SettledBet] = []
    for decision in decide_policy_races(candidates, policy=settings.policy):
        count = counts[int(decision.race_id[:4])]
        if decision.outcome == "no_eligible_bet":
            count.no_eligible_bet += 1
            continue
        if decision.outcome == "budget_exhausted":
            count.budget_exhausted += 1
            continue
        count.purchased += 1
        count.scaled += decision.scaled
        try:
            payouts = race_payouts(decision.race_id, hr_rows[decision.race_id])
        except ObservationHold as hold:
            raise ValueError(
                f"{decision.race_id}: purchased race cannot be settled ({hold.reason})"
            ) from hold
        race_settled = settle_bets(decision.bets, payouts)
        count.refunded_bets += sum(item.refund_yen > 0 for item in race_settled)
        settled.extend(race_settled)
    metrics = betting_metrics(
        settled,
        test_years=test_years,
        bootstrap_resamples=settings.bootstrap_resamples,
        bootstrap_seed=settings.bootstrap_seed,
        bootstrap_confidence=settings.bootstrap_confidence,
    )
    report: dict[str, object] = {
        "format": REPORT_FORMAT,
        "format_version": REPORT_FORMAT_VERSION,
        "config": dict(config),
        "inputs": dict(inputs),
        "provenance": dict(provenance),
        "policy": _policy_payload(settings.policy),
        "counts": {str(year): _counts_payload(counts[year]) for year in test_years},
        "years": {str(year): _metrics_payload(metrics.years[year]) for year in test_years},
        "all_test_years": _metrics_payload(metrics.all_test_years),
    }
    return BettingBacktest(
        report=report,
        bets=tuple(_bet_row(item) for item in sorted(settled, key=_settled_order)),
        races=tuple(
            {
                "test_year": year,
                "race_id": race.race_id,
                "freeze_at": race.freeze_at,
                "stake_yen": race.stake_yen,
                "receipt_yen": race.receipt_yen,
                "net_yen": race.net_yen,
                "cumulative_net_yen": race.cumulative_net_yen,
                "annual_stake_yen": race.annual_stake_yen,
                "hit": race.hit,
            }
            for year in test_years
            for race in metrics.years[year].races
        ),
    )


def _place_correction(
    hits: Sequence[HitObservation],
    test_year: int,
    settings: BettingBacktestSettings,
    graded_race_ids: frozenset[str],
) -> FinalOddsCorrection:
    """Fit the graded ``place_mid`` correction from hits before ``test_year`` only."""
    train = [
        hit
        for hit in hits
        if hit.bet_type == "place_mid"
        and settings.train_start_year <= int(hit.race_id[:4]) < test_year
    ]
    if not train:
        raise ValueError(f"no place_mid training hits before {test_year}")
    all_correction = fit_all_correction(
        [hit.freeze_odds for hit in train],
        [hit.final_odds for hit in train],
        bands=settings.place_bands,
        quantiles=settings.quantiles,
        min_hits=settings.min_hits,
    )
    graded = [hit for hit in train if hit.race_id in graded_race_ids]
    return fit_graded_correction(
        [hit.freeze_odds for hit in graded],
        [hit.final_odds for hit in graded],
        bands=settings.place_bands,
        quantiles=settings.quantiles,
        min_hits=settings.min_hits,
        shrinkage_k=settings.graded_shrinkage_k,
        all_correction=all_correction,
    )


def _race_candidates(
    race: GradedRaceInput,
    prediction: RacePrediction,
    correction: FinalOddsCorrection,
    settings: BettingBacktestSettings,
) -> tuple[list[BetCandidate], bool]:
    """Return one race's win and place candidates and whether place bets are offered.

    Raises:
        ObservationHold: For ADR-042's race and O1 holds, ``no_entrants``,
            ``entrant_mismatch`` and ``market_odds_mismatch``.
    """
    race_id = race.race_id
    freeze: datetime = race_freeze(race_id, race.ra_rows)
    quotes = freeze_quotes(
        race_id,
        race.o1_rows,
        freeze,
        max_publication_age_seconds=settings.max_publication_age_seconds,
    )
    entrants = race_entrants(race_id, race.se_rows)
    horses = {horse.horse_id: horse for horse in prediction.horses}
    if set(entrants) != set(quotes.win) or set(entrants.values()) != set(horses):
        raise ObservationHold("entrant_mismatch", f"{race_id}: predictions, entrants and O1 differ")
    for number, horse_id in entrants.items():
        market = horses[horse_id].market_win_odds
        quote = quotes.win[number]
        if (market is None) != (quote is None) or (
            market is not None and quote is not None and not math.isclose(market, quote)
        ):
            raise ObservationHold("market_odds_mismatch", f"{race_id}: horse {number}")
    entrant_count = len(entrants)
    place_offered = entrant_count > 4
    candidates: list[BetCandidate] = []
    for number in sorted(entrants):
        horse = horses[entrants[number]]
        win_odds = quotes.win[number]
        if win_odds is not None:
            candidates.append(
                BetCandidate(race_id, freeze, "win", number, horse.p_win, win_odds, win_odds)
            )
        probability = place_probability(
            entrant_count=entrant_count, p_top2=horse.p_top2, p_top3=horse.p_top3
        )
        place_odds = quotes.place.get(number)
        if probability is not None and place_odds is not None:
            estimate = correction.estimate(place_odds).final_odds
            candidates.append(
                BetCandidate(race_id, freeze, "place", number, probability, place_odds, estimate)
            )
    return candidates, place_offered


def _no_prediction_stage(stage: str | None) -> str:
    if stage is None:
        return "unattributed"
    return stage if stage in ("target_outcome", "target_pre_freeze") else "other_held"


def _settled_order(item: SettledBet) -> tuple[datetime, str, int, str]:
    bet = item.bet
    return bet.freeze_at, bet.race_id, _BET_TYPE_ORDER[bet.bet_type], bet.horse_number


def _bet_row(item: SettledBet) -> dict[str, object]:
    bet = item.bet
    return {
        "test_year": int(bet.race_id[:4]),
        "race_id": bet.race_id,
        "freeze_at": bet.freeze_at,
        "bet_type": bet.bet_type,
        "horse_number": bet.horse_number,
        "probability": bet.probability,
        "freeze_odds": bet.freeze_odds,
        "estimated_odds": bet.estimated_odds,
        "expected_return": bet.expected_return,
        "kelly_fraction": bet.kelly_fraction,
        "requested_stake_yen": bet.requested_stake_yen,
        "stake_yen": bet.stake_yen,
        "payout_yen": item.payout_yen,
        "refund_yen": item.refund_yen,
        "receipt_yen": item.receipt_yen,
    }


def _policy_payload(policy: BettingPolicy) -> dict[str, object]:
    return {
        "bet_types": ["win", "place"],
        "min_expected_return": policy.min_expected_return,
        "kelly_fraction": policy.kelly_fraction,
        "bankroll_yen": policy.bankroll_yen,
        "annual_budget_yen": policy.annual_budget_yen,
        "race_budget_yen": policy.race_budget_yen,
        "unit_yen": policy.unit_yen,
    }


def _counts_payload(count: _YearCounts) -> dict[str, object]:
    return {
        "graded_races": count.graded_races,
        "predicted": count.predicted,
        "no_prediction": {stage: count.no_prediction[stage] for stage in NO_PREDICTION_STAGES},
        "holds": dict(sorted(count.holds.items())),
        "place_unavailable": count.place_unavailable,
        "no_eligible_bet": count.no_eligible_bet,
        "purchased": count.purchased,
        "scaled": count.scaled,
        "budget_exhausted": count.budget_exhausted,
        "refunded_bets": count.refunded_bets,
    }


def _metrics_payload(metrics: YearBettingMetrics) -> dict[str, object]:
    return {
        "stake_yen": metrics.stake_yen,
        "payout_yen": metrics.payout_yen,
        "refund_yen": metrics.refund_yen,
        "receipt_yen": metrics.receipt_yen,
        "recovery_rate": metrics.recovery_rate,
        "net_yen": metrics.net_yen,
        "purchased_races": metrics.purchased_races,
        "hit_races": metrics.hit_races,
        "hit_rate": metrics.hit_rate,
        "maximum_drawdown_yen": metrics.maximum_drawdown_yen,
        "maximum_consecutive_losses": metrics.maximum_consecutive_losses,
        "recovery_rate_interval": {
            "lower": metrics.recovery_rate_interval.lower,
            "upper": metrics.recovery_rate_interval.upper,
        },
        "bet_types": {
            bet_type: _bet_type_payload(values) for bet_type, values in metrics.bet_types.items()
        },
    }


def _bet_type_payload(values: BetTypeMetrics) -> dict[str, object]:
    return {
        "bets": values.bets,
        "hits": values.hits,
        "stake_yen": values.stake_yen,
        "receipt_yen": values.receipt_yen,
        "recovery_rate": values.recovery_rate,
    }


BETS_SCHEMA = pa.schema(
    [
        pa.field("test_year", pa.int64(), nullable=False),
        pa.field("race_id", pa.string(), nullable=False),
        pa.field("freeze_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("bet_type", pa.string(), nullable=False),
        pa.field("horse_number", pa.string(), nullable=False),
        pa.field("probability", pa.float64(), nullable=False),
        pa.field("freeze_odds", pa.float64(), nullable=False),
        pa.field("estimated_odds", pa.float64(), nullable=False),
        pa.field("expected_return", pa.float64(), nullable=False),
        pa.field("kelly_fraction", pa.float64(), nullable=False),
        pa.field("requested_stake_yen", pa.int64(), nullable=False),
        pa.field("stake_yen", pa.int64(), nullable=False),
        pa.field("payout_yen", pa.int64(), nullable=False),
        pa.field("refund_yen", pa.int64(), nullable=False),
        pa.field("receipt_yen", pa.int64(), nullable=False),
    ]
)
RACES_SCHEMA = pa.schema(
    [
        pa.field("test_year", pa.int64(), nullable=False),
        pa.field("race_id", pa.string(), nullable=False),
        pa.field("freeze_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("stake_yen", pa.int64(), nullable=False),
        pa.field("receipt_yen", pa.int64(), nullable=False),
        pa.field("net_yen", pa.int64(), nullable=False),
        pa.field("cumulative_net_yen", pa.int64(), nullable=False),
        pa.field("annual_stake_yen", pa.int64(), nullable=False),
        pa.field("hit", pa.bool_(), nullable=False),
    ]
)


def bets_table(backtest: BettingBacktest) -> pa.Table:
    """Return ``bets.parquet``'s rows with ADR-043's exact schema."""
    return pa.Table.from_pylist(list(backtest.bets), schema=BETS_SCHEMA)


def races_table(backtest: BettingBacktest) -> pa.Table:
    """Return ``races.parquet``'s rows with ADR-043's exact schema."""
    return pa.Table.from_pylist(list(backtest.races), schema=RACES_SCHEMA)


__all__ = [
    "BETS_SCHEMA",
    "NO_PREDICTION_STAGES",
    "RACES_SCHEMA",
    "REPORT_FORMAT",
    "REPORT_FORMAT_VERSION",
    "BettingBacktest",
    "BettingBacktestSettings",
    "GradedRaceInput",
    "bets_table",
    "races_table",
    "run_betting_backtest",
]
