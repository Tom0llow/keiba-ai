"""Estimate a single Plackett--Luce temperature from validation races."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, isfinite, log, sqrt
from numbers import Real

import numpy.typing as npt

from models.probability.plackett_luce import RaceLayout, top3_plackett_luce

DEFAULT_TEMPERATURE_BOUNDS = (0.05, 20.0)
DEFAULT_TEMPERATURE_TOLERANCE = 1e-6
DEFAULT_TEMPERATURE_MAX_ITERATIONS = 128


@dataclass(frozen=True)
class TemperatureCalibration:
    """Hold a validation-set temperature estimate and its NLL comparison."""

    temperature: float
    raw_valid_nll: float
    calibrated_valid_nll: float
    at_bound: bool


def calibrate_temperature(
    scores: npt.ArrayLike,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    *,
    temperature_bounds: Sequence[float] = DEFAULT_TEMPERATURE_BOUNDS,
    tolerance: float = DEFAULT_TEMPERATURE_TOLERANCE,
    max_iterations: int = DEFAULT_TEMPERATURE_MAX_ITERATIONS,
) -> TemperatureCalibration:
    """Estimate the temperature that minimizes mean validation top-three PL NLL.

    The optimization uses golden-section search over ``log(1 / temperature)``.
    This makes the result deterministic and optimizes the convex inverse-
    temperature objective without preferring either end of the temperature range.
    """
    minimum_temperature, maximum_temperature = _temperature_bounds(temperature_bounds)
    tolerance_value = _positive_finite(tolerance, "tolerance")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValueError("max_iterations must be a positive integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")

    raw_valid_nll = _mean_race_nll(scores, finish_positions, layout, temperature=1.0)
    lower_log_beta = log(1.0 / maximum_temperature)
    upper_log_beta = log(1.0 / minimum_temperature)
    minimum_log_beta = lower_log_beta
    maximum_log_beta = upper_log_beta
    golden_ratio = (sqrt(5.0) - 1.0) / 2.0
    first = upper_log_beta - golden_ratio * (upper_log_beta - lower_log_beta)
    second = lower_log_beta + golden_ratio * (upper_log_beta - lower_log_beta)
    first_nll = _mean_race_nll(scores, finish_positions, layout, temperature=exp(-first))
    second_nll = _mean_race_nll(scores, finish_positions, layout, temperature=exp(-second))

    for _ in range(max_iterations):
        if upper_log_beta - lower_log_beta <= tolerance_value:
            break
        if first_nll <= second_nll:
            upper_log_beta = second
            second = first
            second_nll = first_nll
            first = upper_log_beta - golden_ratio * (upper_log_beta - lower_log_beta)
            first_nll = _mean_race_nll(scores, finish_positions, layout, temperature=exp(-first))
        else:
            lower_log_beta = first
            first = second
            first_nll = second_nll
            second = lower_log_beta + golden_ratio * (upper_log_beta - lower_log_beta)
            second_nll = _mean_race_nll(scores, finish_positions, layout, temperature=exp(-second))

    candidates = [
        (first_nll, first),
        (second_nll, second),
        (
            _mean_race_nll(scores, finish_positions, layout, temperature=exp(-minimum_log_beta)),
            minimum_log_beta,
        ),
        (
            _mean_race_nll(scores, finish_positions, layout, temperature=exp(-maximum_log_beta)),
            maximum_log_beta,
        ),
    ]
    if minimum_log_beta <= 0.0 <= maximum_log_beta:
        candidates.append((raw_valid_nll, 0.0))
    calibrated_valid_nll, log_beta = min(candidates, key=lambda candidate: candidate[0])

    return TemperatureCalibration(
        temperature=exp(-log_beta),
        raw_valid_nll=raw_valid_nll,
        calibrated_valid_nll=calibrated_valid_nll,
        at_bound=log_beta in {minimum_log_beta, maximum_log_beta},
    )


def _temperature_bounds(temperature_bounds: Sequence[float]) -> tuple[float, float]:
    values = tuple(temperature_bounds)
    if len(values) != 2:
        raise ValueError("temperature_bounds must contain exactly two values")
    minimum_temperature = _positive_finite(values[0], "temperature_bounds")
    maximum_temperature = _positive_finite(values[1], "temperature_bounds")
    if minimum_temperature >= maximum_temperature:
        raise ValueError("temperature_bounds must be strictly increasing")
    return minimum_temperature, maximum_temperature


def _positive_finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    converted = float(value)
    if not isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return converted


def _mean_race_nll(
    scores: npt.ArrayLike,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    *,
    temperature: float,
) -> float:
    """Return the race-equally weighted top-three PL NLL."""
    result = top3_plackett_luce(scores, finish_positions, layout, temperature=temperature)
    return float(result.race_nll.mean())


__all__ = [
    "DEFAULT_TEMPERATURE_BOUNDS",
    "DEFAULT_TEMPERATURE_MAX_ITERATIONS",
    "DEFAULT_TEMPERATURE_TOLERANCE",
    "TemperatureCalibration",
    "calibrate_temperature",
]
