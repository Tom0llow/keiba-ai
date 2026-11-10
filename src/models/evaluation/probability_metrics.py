"""Calculate race-level probability metrics and calibration summaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from models.probability.plackett_luce import (
    MarginalProbabilities,
    RaceLayout,
    top3_combination_log_probabilities,
    top3_marginal_probabilities,
    top3_plackett_luce,
)

type BoolArray = npt.NDArray[np.bool_]
type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]

_PROBABILITY_BOUND_TOLERANCE = 1e-9


@dataclass(frozen=True)
class RaceProbabilityMetrics:
    """Hold one probability metric value for each race."""

    winner_log_loss: FloatArray
    multiclass_brier: FloatArray
    exacta_log_loss: FloatArray
    quinella_log_loss: FloatArray
    trifecta_log_loss: FloatArray
    trio_log_loss: FloatArray
    stage_nll: FloatArray


@dataclass(frozen=True)
class ProbabilityCalibrationBin:
    """Describe calibration for one closed-open probability band."""

    lower: float
    upper: float
    count: int
    mean_prediction: float | None
    observed_rate: float | None


@dataclass(frozen=True)
class Top3ProbabilityCalibration:
    """Hold calibration tables for win, top-two, and top-three probabilities."""

    win: tuple[ProbabilityCalibrationBin, ...]
    top2: tuple[ProbabilityCalibrationBin, ...]
    top3: tuple[ProbabilityCalibrationBin, ...]


@dataclass(frozen=True)
class OddsCalibrationBin:
    """Describe win-probability calibration for one odds band."""

    lower: float
    upper: float | None
    count: int
    mean_model_probability: float | None
    mean_market_probability: float | None
    observed_win_rate: float | None


@dataclass(frozen=True)
class MarketWinProbabilities:
    """Hold normalized market win probabilities and complete-race indicators."""

    market_q: FloatArray
    complete_races: BoolArray

    @property
    def incomplete_race_count(self) -> int:
        """Return the number of races that do not have complete market odds."""
        return int((~self.complete_races).sum())


@dataclass(frozen=True)
class BootstrapComparison:
    """Hold a paired bootstrap comparison of race-level losses."""

    model_mean: float
    market_mean: float
    mean_difference: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    conclusion: Literal["model_better", "market_better", "inconclusive"]


def race_probability_metrics(
    scores: npt.ArrayLike,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    *,
    temperature: float = 1.0,
    probability_chunk_races: int = 256,
) -> RaceProbabilityMetrics:
    """Return race-level losses for PL scores at one temperature.

    Each returned one-dimensional metric is weighted equally by race when its
    caller takes the arithmetic mean. ``stage_nll`` has one row per race and
    columns for the first, second, and third finishing stages.
    """
    pl_result = top3_plackett_luce(scores, finish_positions, layout, temperature=temperature)
    marginals = top3_marginal_probabilities(
        scores,
        layout,
        temperature=temperature,
        chunk_races=probability_chunk_races,
    )
    combinations = top3_combination_log_probabilities(
        scores, finish_positions, layout, temperature=temperature
    )
    positions = _validated_finish_positions(finish_positions, layout)
    winner_indicator = (positions == 1).astype(np.float64)
    brier_rows = np.square(marginals.win - winner_indicator)

    return RaceProbabilityMetrics(
        winner_log_loss=-combinations.win,
        multiclass_brier=np.add.reduceat(brier_rows, layout.offsets[:-1]),
        exacta_log_loss=-combinations.exacta,
        quinella_log_loss=-combinations.quinella,
        trifecta_log_loss=-combinations.trifecta,
        trio_log_loss=-combinations.trio,
        stage_nll=pl_result.stage_nll,
    )


def probability_calibration_table(
    probabilities: npt.ArrayLike,
    outcomes: npt.ArrayLike,
    bands: Sequence[float],
) -> tuple[ProbabilityCalibrationBin, ...]:
    """Return horse-equally weighted calibration bins for binary outcomes.

    All bands are left-inclusive and right-exclusive except the final band,
    which also includes its upper endpoint.
    """
    probability_values = _probability_values(probabilities, "probabilities")
    outcome_values = _binary_outcomes(outcomes, len(probability_values))
    band_values = _probability_bands(bands)
    result: list[ProbabilityCalibrationBin] = []
    for index, lower in enumerate(band_values[:-1]):
        upper = band_values[index + 1]
        selected = probability_values >= lower
        if index == len(band_values) - 2:
            selected &= probability_values <= upper
        else:
            selected &= probability_values < upper
        count = int(selected.sum())
        result.append(
            ProbabilityCalibrationBin(
                lower=float(lower),
                upper=float(upper),
                count=count,
                mean_prediction=(float(probability_values[selected].mean()) if count else None),
                observed_rate=(float(outcome_values[selected].mean()) if count else None),
            )
        )
    return tuple(result)


def top3_probability_calibration_tables(
    marginals: MarginalProbabilities,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    bands: Sequence[float],
) -> Top3ProbabilityCalibration:
    """Return win, top-two, and top-three horse-weighted calibration tables."""
    positions = _validated_finish_positions(finish_positions, layout)
    return Top3ProbabilityCalibration(
        win=probability_calibration_table(marginals.win, positions == 1, bands),
        top2=probability_calibration_table(marginals.top2, positions <= 2, bands),
        top3=probability_calibration_table(marginals.top3, positions <= 3, bands),
    )


def market_win_probabilities(
    odds: npt.ArrayLike,
    layout: RaceLayout,
) -> MarketWinProbabilities:
    """Return market probabilities only for races with finite positive odds."""
    odds_values = _one_dimensional_float_values(odds, "odds", layout.row_count)
    valid_odds = np.isfinite(odds_values) & (odds_values > 0.0)
    valid_counts = np.add.reduceat(valid_odds.astype(np.int64), layout.offsets[:-1])
    complete_races = valid_counts == np.asarray(layout.group_sizes, dtype=np.int64)
    inverse_odds = np.zeros(layout.row_count, dtype=np.float64)
    np.divide(1.0, odds_values, out=inverse_odds, where=valid_odds)
    normalizers = np.add.reduceat(inverse_odds, layout.offsets[:-1])
    race_indices = _race_indices(layout)
    complete_rows = complete_races[race_indices]
    market_q = np.full(layout.row_count, np.nan, dtype=np.float64)
    market_q[complete_rows] = inverse_odds[complete_rows] / normalizers[race_indices[complete_rows]]
    return MarketWinProbabilities(market_q=market_q, complete_races=complete_races)


def odds_calibration_table(
    odds: npt.ArrayLike,
    model_win_probabilities: npt.ArrayLike,
    market_q: npt.ArrayLike,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    bands: Sequence[float],
) -> tuple[OddsCalibrationBin, ...]:
    """Return horse-weighted win calibration bins grouped by market odds.

    Rows without finite positive odds or a finite market probability are
    excluded. The final odds band is left-inclusive and unbounded above.
    """
    odds_values = _one_dimensional_float_values(odds, "odds", layout.row_count)
    model_values = _probability_values(model_win_probabilities, "model_win_probabilities")
    market_values = _one_dimensional_float_values(market_q, "market_q", layout.row_count)
    positions = _validated_finish_positions(finish_positions, layout)
    band_values = _odds_bands(bands)
    valid = (
        np.isfinite(odds_values)
        & (odds_values > 0.0)
        & np.isfinite(market_values)
        & (market_values >= 0.0)
        & (market_values <= 1.0)
    )
    winner_indicator = (positions == 1).astype(np.float64)
    result: list[OddsCalibrationBin] = []
    for index, lower in enumerate(band_values):
        selected = valid & (odds_values >= lower)
        upper: float | None
        if index == len(band_values) - 1:
            upper = None
        else:
            upper = float(band_values[index + 1])
            selected &= odds_values < upper
        count = int(selected.sum())
        result.append(
            OddsCalibrationBin(
                lower=float(lower),
                upper=upper,
                count=count,
                mean_model_probability=(float(model_values[selected].mean()) if count else None),
                mean_market_probability=(float(market_values[selected].mean()) if count else None),
                observed_win_rate=(float(winner_indicator[selected].mean()) if count else None),
            )
        )
    return tuple(result)


def paired_bootstrap_comparison(
    model_values: npt.ArrayLike,
    market_values: npt.ArrayLike,
    *,
    resamples: int,
    seed: int,
    confidence: float = 0.95,
) -> BootstrapComparison:
    """Compare paired race-level values with a percentile bootstrap interval."""
    model = _one_dimensional_float_values(model_values, "model_values")
    market = _one_dimensional_float_values(market_values, "market_values", len(model))
    if len(model) == 0:
        raise ValueError("model_values and market_values must not be empty")
    if not np.all(np.isfinite(model)) or not np.all(np.isfinite(market)):
        raise ValueError("model_values and market_values must be finite")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ValueError("resamples must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(confidence, bool):
        raise ValueError("confidence must be between zero and one")
    confidence_value = float(confidence)
    if not np.isfinite(confidence_value) or not 0.0 < confidence_value < 1.0:
        raise ValueError("confidence must be between zero and one")

    differences = model - market
    generator = np.random.default_rng(seed)
    sampled_means = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        sampled_indices = generator.integers(0, len(differences), size=len(differences))
        sampled_means[index] = differences[sampled_indices].mean()
    tail_probability = (1.0 - confidence_value) / 2.0
    lower = float(np.percentile(sampled_means, tail_probability * 100.0))
    upper = float(np.percentile(sampled_means, (1.0 - tail_probability) * 100.0))
    if upper < 0.0:
        conclusion: Literal["model_better", "market_better", "inconclusive"] = "model_better"
    elif lower > 0.0:
        conclusion = "market_better"
    else:
        conclusion = "inconclusive"
    return BootstrapComparison(
        model_mean=float(model.mean()),
        market_mean=float(market.mean()),
        mean_difference=float(differences.mean()),
        confidence_interval_lower=lower,
        confidence_interval_upper=upper,
        conclusion=conclusion,
    )


def _race_indices(layout: RaceLayout) -> IntArray:
    """Return the race index for every unpadded row."""
    return np.repeat(
        np.arange(layout.race_count, dtype=np.int64),
        np.asarray(layout.group_sizes, dtype=np.int64),
    )


def _validated_finish_positions(
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
) -> IntArray:
    values = np.asarray(finish_positions)
    if values.ndim != 1 or len(values) != layout.row_count:
        raise ValueError(
            "finish_positions must be a one-dimensional array matching the layout rows"
        )
    if np.issubdtype(values.dtype, np.bool_) or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("finish_positions must contain integers")
    padded_positions = np.full(layout.mask.shape, layout.mask.shape[1] + 1, dtype=np.int64)
    padded_positions[layout.mask] = values.astype(np.int64, copy=False)
    expected_positions = np.where(
        layout.mask,
        np.arange(1, layout.mask.shape[1] + 1, dtype=np.int64),
        layout.mask.shape[1] + 1,
    )
    if not np.array_equal(np.sort(padded_positions, axis=1), expected_positions):
        raise ValueError("finish_positions must be a 1..n permutation within every race")
    return values.astype(np.int64, copy=False)


def _probability_values(values: npt.ArrayLike, name: str) -> FloatArray:
    result = _one_dimensional_float_values(values, name)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain finite probabilities between zero and one")
    if np.any(
        (result < -_PROBABILITY_BOUND_TOLERANCE) | (result > 1.0 + _PROBABILITY_BOUND_TOLERANCE)
    ):
        raise ValueError(f"{name} must contain finite probabilities between zero and one")
    return np.clip(result, 0.0, 1.0)


def _binary_outcomes(values: npt.ArrayLike, expected_length: int) -> FloatArray:
    result = _one_dimensional_float_values(values, "outcomes", expected_length)
    if not np.all((result == 0.0) | (result == 1.0)):
        raise ValueError("outcomes must contain only zero or one")
    return result


def _one_dimensional_float_values(
    values: npt.ArrayLike,
    name: str,
    expected_length: int | None = None,
) -> FloatArray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a one-dimensional numeric array") from exc
    if result.ndim != 1 or (expected_length is not None and len(result) != expected_length):
        raise ValueError(f"{name} must be a one-dimensional array with the expected length")
    return result


def _probability_bands(bands: Sequence[float]) -> FloatArray:
    values = _bands(bands, "probability bands")
    if values[0] != 0.0 or values[-1] != 1.0:
        raise ValueError("probability bands must start at zero and end at one")
    return values


def _odds_bands(bands: Sequence[float]) -> FloatArray:
    values = _bands(bands, "odds bands")
    if not 0.0 < values[0] <= 1.0:
        raise ValueError("odds bands must start above zero and no higher than one")
    return values


def _bands(bands: Sequence[float], name: str) -> FloatArray:
    try:
        values = np.asarray(tuple(bands), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if values.ndim != 1 or len(values) < 2:
        raise ValueError(f"{name} must contain at least two values")
    if not np.all(np.isfinite(values)) or np.any(np.diff(values) <= 0.0):
        raise ValueError(f"{name} must be finite and strictly increasing")
    return values


__all__ = [
    "BootstrapComparison",
    "MarketWinProbabilities",
    "OddsCalibrationBin",
    "ProbabilityCalibrationBin",
    "RaceProbabilityMetrics",
    "Top3ProbabilityCalibration",
    "market_win_probabilities",
    "odds_calibration_table",
    "paired_bootstrap_comparison",
    "probability_calibration_table",
    "race_probability_metrics",
    "top3_probability_calibration_tables",
]
