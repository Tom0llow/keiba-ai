"""Small fits and records for the ADR-045 race-day betting estimator tests."""

from __future__ import annotations

import math
from collections.abc import Sequence
from random import Random

from models.artifacts.betting_estimator import BettingEstimatorRecord
from models.betting.methods import METHODS, Method
from models.betting.policy import BettingPolicy
from models.experiments.betting_backtest import BettingBacktestSettings
from models.experiments.betting_estimator import BacktestResults, fit_betting_estimator
from models.probability.market_blend import BlendRace
from models.serialization.betting_inputs import BlendTraining
from models.serialization.final_odds_observations import HitObservation
from tests.betting_scenario import scenario_hits

NO_EXCLUSIONS = {"market_incomplete": 0, "zero_probability": 0, "winner_count": 0}
SOURCES: dict[str, object] = {
    "backtest_report_sha256": "a" * 64,
    "pl_evaluation": {"report_sha256": "b" * 64, "predictions_sha256": "c" * 64, "variant": "v"},
    "snapshot": {"snapshot_id": "d" * 32, "tables": {"NL_RA_RACE": "e" * 64}},
}


def estimator_settings(test_years: Sequence[int], **fields: object) -> BettingBacktestSettings:
    """Return small backtest settings whose fits run on the scenario hits."""
    values: dict[str, object] = {
        "test_years": tuple(test_years),
        "policy": BettingPolicy(),
        "train_start_year": 2020,
        "max_publication_age_seconds": 600,
        "place_bands": (1.0, 2.0),
        "quantiles": (0.1, 0.5, 0.9),
        "min_hits": 1,
        "graded_shrinkage_k": 2,
        "bootstrap_resamples": 20,
        "bootstrap_seed": 0,
        "bootstrap_confidence": 0.95,
        "blend_min_races": 20,
        "blend_tolerance": 1e-10,
        "blend_max_iterations": 100,
        "place_width_bands": (1.0, 1.5, 2.0, 3.0, 5.0),
    }
    values.update(fields)
    return BettingBacktestSettings(**values)  # type: ignore[arg-type]


def varied_hits(years: Sequence[int]) -> list[HitObservation]:
    """Return place hits whose width bands have different final-to-freeze ratios."""
    ratios = {"01": 1.0, "02": 1.5, "03": 0.6}
    return [
        HitObservation(
            hit.race_id,
            hit.bet_type,
            hit.combination,
            hit.freeze_odds,
            hit.final_odds * ratios[hit.combination] * (1.0 + 0.01 * (year - 2020)),
            hit.publication_age_seconds,
        )
        for year in years
        for hit in scenario_hits(year)
    ]


def blend_races(year: int, count: int = 60) -> tuple[BlendRace, ...]:
    """Return races whose winners favour a mix of the model and the market."""
    generator = Random(year)
    races: list[BlendRace] = []
    for _ in range(count):
        a = _log_softmax([generator.gauss(0.0, 1.0) for _ in range(8)])
        b = _log_softmax([generator.gauss(0.0, 1.0) + 0.5 * value for value in a])
        weights = [math.exp(0.3 * x + 0.9 * y) for x, y in zip(a, b, strict=True)]
        winner = generator.choices(range(8), weights=weights)[0]
        races.append(BlendRace(tuple(a), tuple(b), winner))
    return tuple(races)


def blend_training(years: Sequence[int]) -> BlendTraining:
    return BlendTraining(
        races={year: blend_races(year) for year in years},
        excluded={year: dict(NO_EXCLUSIONS) for year in years},
    )


def flat_results(years: Sequence[int], winner: Method = "blend_width") -> BacktestResults:
    """Return flat results in which ``winner`` has the best pooled recovery rate."""
    return BacktestResults(
        flat={
            method: {year: (90 if method == winner else 50, 100) for year in years}
            for method in METHODS
        }
    )


def estimator_record(
    target_year: int = 2025, winner: Method = "blend_width", *, graded: bool = False
) -> BettingEstimatorRecord:
    """Return a fitted record for ``target_year`` from the scenario hits and blend races.

    With ``graded`` the hit race of every other year is graded, so the graded fits hold
    both empty and fitted bands.
    """
    test_years = tuple(range(target_year - 2, target_year))
    graded_ids = (
        frozenset(hit.race_id for hit in scenario_hits(target_year - 2)) if graded else frozenset()
    )
    record, _ = fit_betting_estimator(
        settings=estimator_settings(test_years),
        results=flat_results(test_years, winner),
        hits=varied_hits(range(2021, target_year)),
        graded_race_ids=graded_ids,
        blend_training=blend_training(test_years),
        sources=SOURCES,
        provenance={"fixture": True},
    )
    return record


def _log_softmax(values: list[float]) -> list[float]:
    peak = max(values)
    total = math.log(sum(math.exp(value - peak) for value in values)) + peak
    return [value - total for value in values]
