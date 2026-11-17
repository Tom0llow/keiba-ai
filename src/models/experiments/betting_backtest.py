"""Replay ADR-043's fixed policy under ADR-044's four estimation methods and report the results.

Pure: the CLI reads the snapshot, the PL evaluation and the datamart holds, and this module
fits each year's place corrections and PL-market blend from earlier years only, builds every
method's candidates, scores each method by flat 100-yen stakes, selects a method for each
test year from earlier years' graded flat results, applies the policy in time order, settles
the purchases and assembles the report and the two tables. No I/O.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import Literal

import pyarrow as pa

from models.betting.policy import Bet, BetCandidate, BettingPolicy, place_probability
from models.betting.policy import decide_races as decide_policy_races
from models.betting.settlement import SettledBet, settle_bets
from models.evaluation.betting_metrics import (
    BettingMetrics,
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
from models.market.place_width_correction import (
    PlaceWidthCorrection,
    PlaceWidthObservation,
    fit_place_width_correction,
    place_width,
    recover_place_high,
    validate_width_bands,
)
from models.probability.market_blend import (
    MAX_TOLERANCE,
    BlendFit,
    BlendRace,
    blend_probabilities,
    fit_market_blend,
    market_log_probabilities,
)
from models.serialization.betting_inputs import (
    BLEND_EXCLUSIONS,
    BlendTraining,
    HorsePrediction,
    RacePrediction,
    freeze_quotes,
    race_entrants,
)
from models.serialization.final_odds_observations import (
    HitObservation,
    ObservationHold,
    RacePayouts,
    race_freeze,
    race_payouts,
)

REPORT_FORMAT = "ev_betting_backtest"
REPORT_FORMAT_VERSION = 2
NO_PREDICTION_STAGES = ("target_outcome", "target_pre_freeze", "other_held", "unattributed")
Method = Literal["pl_mid", "blend_mid", "pl_width", "blend_width"]
# The fixed order also breaks ties: the current ADR-043 method first, the most changed last.
METHODS: tuple[Method, ...] = ("pl_mid", "blend_mid", "pl_width", "blend_width")
BASELINE_METHOD: Method = "pl_mid"
_BET_TYPE_ORDER = {"win": 0, "place": 1}


@dataclass(frozen=True)
class BettingBacktestSettings:
    """Hold ADR-043's fixed policy, ADR-042's place settings and ADR-044's estimation."""

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
    blend_min_races: int
    blend_tolerance: float
    blend_max_iterations: int
    place_width_bands: tuple[float, ...]

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
        for name in ("blend_min_races", "blend_max_iterations"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        tolerance = self.blend_tolerance
        if (
            isinstance(tolerance, bool)
            or not math.isfinite(tolerance)
            or not 0.0 < tolerance <= MAX_TOLERANCE
        ):
            raise ValueError(f"blend_tolerance must be positive and at most {MAX_TOLERANCE:g}")
        validate_width_bands(self.place_width_bands)


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
    place_width_invalid: int = 0


@dataclass(frozen=True)
class _Flat:
    bets: int
    hits: int
    stake_yen: int
    receipt_yen: int


@dataclass(frozen=True)
class _YearEstimators:
    """Hold one test year's fits, each from data before that year only."""

    mid: FinalOddsCorrection
    width: PlaceWidthCorrection
    blend: BlendFit
    blend_excluded: Mapping[str, int]


@dataclass(frozen=True)
class _MethodYear:
    counts: _YearCounts
    flat: _Flat
    settled: tuple[SettledBet, ...]


def run_betting_backtest(
    *,
    settings: BettingBacktestSettings,
    graded_races: Sequence[GradedRaceInput],
    predictions: Mapping[str, RacePrediction],
    target_hold_stages: Mapping[str, str],
    training_hits: Sequence[HitObservation],
    blend_training: BlendTraining,
    graded_race_ids: frozenset[str],
    config: Mapping[str, object],
    inputs: Mapping[str, object],
    provenance: Mapping[str, object],
) -> BettingBacktest:
    """Replay every method over the graded test races and assemble the outputs.

    ``training_hits`` are ADR-042 hit observations of every race from
    ``train_start_year``; ``place_mid`` hits of years before each test year fit the
    corrections, and each ``place_mid`` hit's ``place_low`` partner gives its width.
    ``blend_training`` holds every test year's races for the PL-market blend; a year's
    blend is fitted on earlier test years only. ``graded_race_ids`` is the graded subset
    over the training years and the test years. ``target_hold_stages`` maps a held target
    race to its datamart stage.

    Raises:
        ValueError: If race IDs repeat or fall outside the test years, a prediction is not
            one of the graded races, a test year has no place training hits, a
            ``place_mid`` hit has no ``place_low`` partner, or a bought race cannot be
            settled (no, ambiguous or unfinal payout row, special payout or unestablished
            race).
    """
    test_years = settings.test_years
    by_id = {race.race_id: race for race in graded_races}
    if len(by_id) != len(graded_races):
        raise ValueError("graded races must be unique")
    if any(int(race_id[:4]) not in test_years for race_id in by_id):
        raise ValueError("graded races must fall within test_years")
    if not set(predictions) <= set(by_id):
        raise ValueError("PL predictions contain a race outside the graded test races")
    width_observations = _width_observations(training_hits)
    estimators = {
        year: _year_estimators(
            year, settings, training_hits, width_observations, blend_training, graded_race_ids
        )
        for year in test_years
    }
    results: dict[Method, dict[int, _MethodYear]] = {method: {} for method in METHODS}
    for method in METHODS:
        for year in test_years:
            if _available(method, estimators[year]):
                results[method][year] = _method_year(
                    method,
                    year,
                    [by_id[race_id] for race_id in sorted(by_id) if int(race_id[:4]) == year],
                    predictions,
                    target_hold_stages,
                    estimators[year],
                    settings,
                )
    selection = _selection(results, test_years)
    common = tuple(year for year in test_years if all(year in results[m] for m in METHODS))
    selected = {year: results[selection[year][0]][year] for year in test_years}
    selected_settled = [item for year in test_years for item in selected[year].settled]
    selected_metrics = _metrics(selected_settled, test_years, settings)
    report: dict[str, object] = {
        "format": REPORT_FORMAT,
        "format_version": REPORT_FORMAT_VERSION,
        "config": dict(config),
        "inputs": dict(inputs),
        "provenance": dict(provenance),
        "policy": _policy_payload(settings.policy),
        "estimation": _estimation_payload(settings),
        "selection": {
            str(year): {
                "method": method,
                "comparison_years": list(years),
                "flat_recovery_rate": {
                    name: _ratio(*_flat_totals(results[name], years)) if years else None
                    for name in METHODS
                },
            }
            for year, (method, years) in selection.items()
        },
        "counts": {str(year): _counts_payload(selected[year].counts) for year in test_years},
        "years": {str(year): _metrics_payload(selected_metrics.years[year]) for year in test_years},
        "all_test_years": _metrics_payload(selected_metrics.all_test_years),
        "common_years": _common_payload(results, selected, common, settings),
        "methods": {
            method: _method_payload(method, results[method], estimators, test_years, settings)
            for method in METHODS
        },
    }
    return BettingBacktest(
        report=report,
        bets=tuple(
            _bet_row(item, selection[int(item.bet.race_id[:4])][0])
            for item in sorted(selected_settled, key=_settled_order)
        ),
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
                "method": selection[year][0],
            }
            for year in test_years
            for race in selected_metrics.years[year].races
        ),
    )


def _year_estimators(
    year: int,
    settings: BettingBacktestSettings,
    hits: Sequence[HitObservation],
    width_observations: Sequence[PlaceWidthObservation],
    blend_training: BlendTraining,
    graded_race_ids: frozenset[str],
) -> _YearEstimators:
    """Fit one test year's corrections and blend from data before ``year`` only."""
    earlier_years = [y for y in settings.test_years if y < year]
    blend_races: list[BlendRace] = [
        race for y in earlier_years for race in blend_training.races.get(y, ())
    ]
    excluded = {
        reason: sum(blend_training.excluded.get(y, {}).get(reason, 0) for y in earlier_years)
        for reason in BLEND_EXCLUSIONS
    }
    return _YearEstimators(
        mid=_place_correction(hits, year, settings, graded_race_ids),
        width=fit_place_width_correction(
            [
                item
                for item in width_observations
                if settings.train_start_year <= int(item.race_id[:4]) < year
            ],
            width_bands=settings.place_width_bands,
            place_bands=settings.place_bands,
            quantiles=settings.quantiles,
            min_hits=settings.min_hits,
            shrinkage_k=settings.graded_shrinkage_k,
            graded_race_ids=graded_race_ids,
        ),
        blend=fit_market_blend(
            blend_races,
            min_races=settings.blend_min_races,
            tolerance=settings.blend_tolerance,
            max_iterations=settings.blend_max_iterations,
        ),
        blend_excluded=excluded,
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


def _width_observations(hits: Sequence[HitObservation]) -> list[PlaceWidthObservation]:
    """Pair every ``place_mid`` hit with its ``place_low`` partner to give its width.

    A hit whose recovered ``OddsHigh`` is below ``OddsLow`` has no width and is not used.
    """
    lows = {(hit.race_id, hit.combination): hit for hit in hits if hit.bet_type == "place_low"}
    observations: list[PlaceWidthObservation] = []
    for hit in hits:
        if hit.bet_type != "place_mid":
            continue
        low = lows.get((hit.race_id, hit.combination))
        if low is None:
            raise ValueError(f"{hit.race_id}: place_mid hit {hit.combination} has no place_low")
        width = place_width(low.freeze_odds, recover_place_high(low.freeze_odds, hit.freeze_odds))
        if width is not None:
            observations.append(
                PlaceWidthObservation(hit.race_id, hit.freeze_odds, hit.final_odds, width)
            )
    return observations


def _available(method: Method, estimators: _YearEstimators) -> bool:
    return not method.startswith("blend") or estimators.blend.available


def _method_year(
    method: Method,
    year: int,
    races: Sequence[GradedRaceInput],
    predictions: Mapping[str, RacePrediction],
    target_hold_stages: Mapping[str, str],
    estimators: _YearEstimators,
    settings: BettingBacktestSettings,
) -> _MethodYear:
    """Build one method's candidates of one year, score them flat and apply the policy."""
    count = _YearCounts()
    candidates: list[BetCandidate] = []
    hr_rows: dict[str, Sequence[Mapping[str, object]]] = {}
    for race in races:
        count.graded_races += 1
        prediction = predictions.get(race.race_id)
        if prediction is None:
            count.no_prediction[_no_prediction_stage(target_hold_stages.get(race.race_id))] += 1
            continue
        count.predicted += 1
        try:
            race_candidates, place_offered, width_invalid = _race_candidates(
                race, prediction, method, estimators, settings
            )
        except ObservationHold as hold:
            count.holds[hold.reason] += 1
            continue
        count.place_width_invalid += width_invalid
        if not place_offered:
            count.place_unavailable += 1
        if not race_candidates:
            count.no_eligible_bet += 1
            continue
        candidates.extend(race_candidates)
        hr_rows[race.race_id] = race.hr_rows
    flat = _flat(candidates, hr_rows, settings.policy)
    settled: list[SettledBet] = []
    for decision in decide_policy_races(candidates, policy=settings.policy):
        if decision.outcome == "no_eligible_bet":
            count.no_eligible_bet += 1
            continue
        if decision.outcome == "budget_exhausted":
            count.budget_exhausted += 1
            continue
        count.purchased += 1
        count.scaled += decision.scaled
        race_settled = settle_bets(decision.bets, _payouts(decision.race_id, hr_rows))
        count.refunded_bets += sum(item.refund_yen > 0 for item in race_settled)
        settled.extend(race_settled)
    return _MethodYear(count, flat, tuple(settled))


def _race_candidates(
    race: GradedRaceInput,
    prediction: RacePrediction,
    method: Method,
    estimators: _YearEstimators,
    settings: BettingBacktestSettings,
) -> tuple[list[BetCandidate], bool, int]:
    """Return one race's candidates, whether place bets are offered and invalid widths.

    Raises:
        ObservationHold: For ADR-042's race and O1 holds, ``no_entrants``,
            ``entrant_mismatch``, ``market_odds_mismatch``, and for the blend methods
            ``blend_market_incomplete`` and ``blend_zero_probability``.
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
    numbers = sorted(entrants)
    probabilities = _probabilities(race_id, method, numbers, entrants, horses, estimators)
    entrant_count = len(entrants)
    place_offered = entrant_count > 4
    candidates: list[BetCandidate] = []
    width_invalid = 0
    for number in numbers:
        p_win, p_top2, p_top3 = probabilities[number]
        win_odds = quotes.win[number]
        if win_odds is not None:
            candidates.append(
                BetCandidate(race_id, freeze, "win", number, p_win, win_odds, win_odds)
            )
        probability = place_probability(entrant_count=entrant_count, p_top2=p_top2, p_top3=p_top3)
        place_odds = quotes.place.get(number)
        if probability is None or place_odds is None:
            continue
        if method.endswith("mid"):
            estimate = estimators.mid.estimate(place_odds).final_odds
        else:
            width = place_width(
                _quote(quotes.place_low.get(number)), _quote(quotes.place_high.get(number))
            )
            if width is None:
                width_invalid += 1
                continue
            estimate = estimators.width.estimate(place_odds, width)
        candidates.append(
            BetCandidate(race_id, freeze, "place", number, probability, place_odds, estimate)
        )
    return candidates, place_offered, width_invalid


def _probabilities(
    race_id: str,
    method: Method,
    numbers: Sequence[str],
    entrants: Mapping[str, str],
    horses: Mapping[str, HorsePrediction],
    estimators: _YearEstimators,
) -> dict[str, tuple[float, float, float]]:
    """Return each horse number's (win, top-two, top-three) probability under ``method``."""
    predicted = [horses[entrants[number]] for number in numbers]
    if not method.startswith("blend"):
        return {
            number: (horse.p_win, horse.p_top2, horse.p_top3)
            for number, horse in zip(numbers, predicted, strict=True)
        }
    odds: list[float] = []
    for horse in predicted:
        if horse.market_win_odds is None or horse.market_win_odds <= 0.0:
            raise ObservationHold("blend_market_incomplete", race_id)
        odds.append(horse.market_win_odds)
    p_win = [horse.p_win for horse in predicted]
    if any(value <= 0.0 for value in p_win):
        raise ObservationHold("blend_zero_probability", race_id)
    fit = estimators.blend
    if fit.alpha is None or fit.beta is None:
        raise AssertionError("blend methods run only in years with a fitted blend")
    win, top2, top3 = blend_probabilities(
        [math.log(value) for value in p_win],
        market_log_probabilities(odds),
        alpha=fit.alpha,
        beta=fit.beta,
    )
    # Floating-point marginals may leave [0, 1] by a rounding error only.
    return {
        number: (_unit(win[index]), _unit(top2[index]), _unit(top3[index]))
        for index, number in enumerate(numbers)
    }


def _flat(
    candidates: Sequence[BetCandidate],
    hr_rows: Mapping[str, Sequence[Mapping[str, object]]],
    policy: BettingPolicy,
) -> _Flat:
    """Buy every eligible candidate at one unit, regardless of its Kelly stake."""
    by_race: dict[str, list[Bet]] = {}
    for candidate in candidates:
        expected_return = candidate.probability * candidate.estimated_odds
        if expected_return < policy.min_expected_return or candidate.estimated_odds <= 1.0:
            continue
        by_race.setdefault(candidate.race_id, []).append(
            Bet(
                race_id=candidate.race_id,
                freeze_at=candidate.freeze_at,
                bet_type=candidate.bet_type,
                horse_number=candidate.horse_number,
                probability=candidate.probability,
                freeze_odds=candidate.freeze_odds,
                estimated_odds=candidate.estimated_odds,
                expected_return=expected_return,
                kelly_fraction=(expected_return - 1.0) / (candidate.estimated_odds - 1.0),
                requested_stake_yen=policy.unit_yen,
                stake_yen=policy.unit_yen,
            )
        )
    settled = [
        item
        for race_id, bets in sorted(by_race.items())
        for item in settle_bets(bets, _payouts(race_id, hr_rows))
    ]
    return _Flat(
        bets=len(settled),
        hits=sum(item.payout_yen > 0 for item in settled),
        stake_yen=sum(item.bet.stake_yen for item in settled),
        receipt_yen=sum(item.receipt_yen for item in settled),
    )


def _payouts(race_id: str, hr_rows: Mapping[str, Sequence[Mapping[str, object]]]) -> RacePayouts:
    try:
        return race_payouts(race_id, hr_rows[race_id])
    except ObservationHold as hold:
        raise ValueError(f"{race_id}: purchased race cannot be settled ({hold.reason})") from hold


def _selection(
    results: Mapping[Method, Mapping[int, _MethodYear]], test_years: Sequence[int]
) -> dict[int, tuple[Method, tuple[int, ...]]]:
    """Return each test year's method and comparison years (ADR-044 Decision 4)."""
    selection: dict[int, tuple[Method, tuple[int, ...]]] = {}
    for year in test_years:
        years = tuple(y for y in test_years if y < year and all(y in results[m] for m in METHODS))
        best: Method = BASELINE_METHOD
        best_totals: tuple[int, int] | None = None
        if years:
            for method in METHODS:
                receipt, stake = _flat_totals(results[method], years)
                if stake == 0:
                    continue
                # receipt/stake > best_receipt/best_stake, compared exactly in integers.
                if best_totals is None or receipt * best_totals[1] > best_totals[0] * stake:
                    best, best_totals = method, (receipt, stake)
        if year not in results[best]:
            best = BASELINE_METHOD
        selection[year] = (best, years)
    return selection


def _flat_totals(results: Mapping[int, _MethodYear], years: Sequence[int]) -> tuple[int, int]:
    return (
        sum(results[year].flat.receipt_yen for year in years),
        sum(results[year].flat.stake_yen for year in years),
    )


def _metrics(
    settled: Sequence[SettledBet], years: Sequence[int], settings: BettingBacktestSettings
) -> BettingMetrics:
    return betting_metrics(
        settled,
        test_years=years,
        bootstrap_resamples=settings.bootstrap_resamples,
        bootstrap_seed=settings.bootstrap_seed,
        bootstrap_confidence=settings.bootstrap_confidence,
    )


def _common_payload(
    results: Mapping[Method, Mapping[int, _MethodYear]],
    selected: Mapping[int, _MethodYear],
    years: tuple[int, ...],
    settings: BettingBacktestSettings,
) -> dict[str, object]:
    """Compare the selected path and every method over the years all methods cover."""
    if not years:
        return {"years": [], "selected": None, "methods": dict.fromkeys(METHODS)}

    def summary(by_year: Mapping[int, _MethodYear]) -> dict[str, object]:
        settled = [item for year in years for item in by_year[year].settled]
        return _metrics_payload(_metrics(settled, years, settings).all_test_years)

    return {
        "years": list(years),
        "selected": summary(selected),
        "methods": {method: summary(results[method]) for method in METHODS},
    }


def _method_payload(
    method: Method,
    results: Mapping[int, _MethodYear],
    estimators: Mapping[int, _YearEstimators],
    test_years: Sequence[int],
    settings: BettingBacktestSettings,
) -> dict[str, object]:
    available = tuple(year for year in test_years if year in results)
    metrics = (
        _metrics(
            [item for year in available for item in results[year].settled], available, settings
        )
        if available
        else None
    )
    years: dict[str, object] = {}
    for year in test_years:
        result = results.get(year)
        years[str(year)] = {
            "available": result is not None,
            "blend": _blend_payload(estimators[year]) if method.startswith("blend") else None,
            "counts": None if result is None else _counts_payload(result.counts),
            "flat": None if result is None else _flat_payload(result.flat),
            "policy": None
            if result is None or metrics is None
            else _metrics_payload(metrics.years[year]),
        }
    return {
        "years": years,
        "available_years": list(available),
        "all_available_years": None
        if metrics is None
        else _metrics_payload(metrics.all_test_years),
    }


def _blend_payload(estimators: _YearEstimators) -> dict[str, object]:
    fit = estimators.blend
    return {
        "alpha": fit.alpha,
        "beta": fit.beta,
        "races": fit.races,
        "excluded": dict(estimators.blend_excluded),
        "failure": fit.failure,
    }


def _flat_payload(flat: _Flat) -> dict[str, object]:
    return {
        "bets": flat.bets,
        "hits": flat.hits,
        "stake_yen": flat.stake_yen,
        "receipt_yen": flat.receipt_yen,
        "recovery_rate": _ratio(flat.receipt_yen, flat.stake_yen),
    }


def _estimation_payload(settings: BettingBacktestSettings) -> dict[str, object]:
    return {
        "methods": list(METHODS),
        "blend_min_races": settings.blend_min_races,
        "blend_tolerance": settings.blend_tolerance,
        "blend_max_iterations": settings.blend_max_iterations,
        "place_width_bands": list(settings.place_width_bands),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _unit(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _quote(value: float | None) -> float:
    if value is None:
        raise AssertionError("a place_mid quote always has both bounds")
    return value


def _no_prediction_stage(stage: str | None) -> str:
    if stage is None:
        return "unattributed"
    return stage if stage in ("target_outcome", "target_pre_freeze") else "other_held"


def _settled_order(item: SettledBet) -> tuple[datetime, str, int, str]:
    bet = item.bet
    return bet.freeze_at, bet.race_id, _BET_TYPE_ORDER[bet.bet_type], bet.horse_number


def _bet_row(item: SettledBet, method: Method) -> dict[str, object]:
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
        "method": method,
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
        "place_width_invalid": count.place_width_invalid,
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
        pa.field("method", pa.string(), nullable=False),
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
        pa.field("method", pa.string(), nullable=False),
    ]
)


def bets_table(backtest: BettingBacktest) -> pa.Table:
    """Return ``bets.parquet``'s rows with ADR-044's exact schema."""
    return pa.Table.from_pylist(list(backtest.bets), schema=BETS_SCHEMA)


def races_table(backtest: BettingBacktest) -> pa.Table:
    """Return ``races.parquet``'s rows with ADR-044's exact schema."""
    return pa.Table.from_pylist(list(backtest.races), schema=RACES_SCHEMA)


__all__ = [
    "BASELINE_METHOD",
    "BETS_SCHEMA",
    "METHODS",
    "NO_PREDICTION_STAGES",
    "RACES_SCHEMA",
    "REPORT_FORMAT",
    "REPORT_FORMAT_VERSION",
    "BettingBacktest",
    "BettingBacktestSettings",
    "GradedRaceInput",
    "Method",
    "bets_table",
    "races_table",
    "run_betting_backtest",
]
