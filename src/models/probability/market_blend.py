"""Blend PL win probabilities with market probabilities by a two-coefficient conditional logit.

ADR-044: a horse's blended strength is ``alpha * log(p_win) + beta * log(q)``, where ``q`` is
the market probability ``(1/O) / sum(1/O)``. The coefficients maximise the winners' mean
log-likelihood over races of earlier years; top-two and top-three probabilities follow the
same Plackett-Luce strengths. numpy only; no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from models.probability.plackett_luce import RaceLayout, top3_marginal_probabilities

FloatArray = npt.NDArray[np.float64]
BlendFailure = Literal["insufficient_races", "not_concave", "not_converged"]
_MAX_STEP_HALVINGS = 30
_CONCAVITY_TOLERANCE = 1e-10
# Near the optimum a Newton step gains far less than the rounding error of the mean
# log-likelihood, so a step may lose this much relative to the current value.
_ROUNDING_SLACK = 1e-12
# On separable races (the winner always has the largest feature) no maximum exists: the
# coefficients grow while the mean log-likelihood flattens, so its curvature falls towards
# zero. A real optimum keeps a curvature of the order of the features' within-race variance.
_MIN_CURVATURE = 1e-6


@dataclass(frozen=True)
class BlendRace:
    """Hold one race's features (``log p_win``, ``log q``) and its winner's position."""

    log_p_win: tuple[float, ...]
    log_q: tuple[float, ...]
    winner: int

    def __post_init__(self) -> None:
        if len(self.log_p_win) != len(self.log_q) or len(self.log_p_win) < 2:
            raise ValueError("a blend race needs matching features for at least two horses")
        if not all(math.isfinite(value) for value in (*self.log_p_win, *self.log_q)):
            raise ValueError("blend features must be finite")
        if isinstance(self.winner, bool) or not 0 <= self.winner < len(self.log_p_win):
            raise ValueError("the winner must be a horse of the race")


@dataclass(frozen=True)
class BlendFit:
    """Hold fitted coefficients, or the reason the blend is unavailable."""

    alpha: float | None
    beta: float | None
    races: int
    iterations: int
    failure: BlendFailure | None

    @property
    def available(self) -> bool:
        """Return whether both coefficients were fitted."""
        return self.failure is None


def market_log_probabilities(odds: Sequence[float]) -> tuple[float, ...]:
    """Return ``log q`` for positive finite win odds, ``q = (1/O) / sum(1/O)``."""
    if not odds or any(not math.isfinite(value) or value <= 0.0 for value in odds):
        raise ValueError("market odds must be positive and finite")
    inverse = [1.0 / value for value in odds]
    log_total = math.log(math.fsum(inverse))
    return tuple(math.log(value) - log_total for value in inverse)


def fit_market_blend(
    races: Sequence[BlendRace], *, min_races: int, tolerance: float, max_iterations: int
) -> BlendFit:
    """Return the coefficients that maximise the winners' mean log-likelihood.

    Newton's method starts at ``alpha=1, beta=0`` and halves a step until the
    likelihood does not decrease by more than a rounding slack. It converges when the largest absolute gradient of the
    mean log-likelihood is below ``tolerance`` at a point with a negative definite Hessian
    whose curvature is at least ``1e-6`` in every direction (a flatter likelihood has no
    maximum, as on separable races).
    """
    _positive_integer(min_races, "min_races")
    _positive_integer(max_iterations, "max_iterations")
    if isinstance(tolerance, bool) or not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("tolerance must be positive and finite")
    count = len(races)
    if count < min_races:
        return BlendFit(None, None, count, 0, "insufficient_races")
    features = _padded_features(races)
    theta = np.array([1.0, 0.0])
    value, gradient, hessian = _derivatives(theta, features)
    for iteration in range(max_iterations + 1):
        if not _negative_definite(hessian):
            return BlendFit(None, None, count, iteration, "not_concave")
        if float(np.max(np.abs(gradient))) < tolerance:
            return BlendFit(float(theta[0]), float(theta[1]), count, iteration, None)
        if iteration == max_iterations:
            break
        step = -np.linalg.solve(hessian, gradient)
        for _ in range(_MAX_STEP_HALVINGS):
            candidate = theta + step
            candidate_value, candidate_gradient, candidate_hessian = _derivatives(
                candidate, features
            )
            if candidate_value >= value - _ROUNDING_SLACK * max(1.0, abs(value)):
                break
            step = step / 2.0
        else:
            return BlendFit(None, None, count, iteration, "not_converged")
        theta, value, gradient, hessian = (
            candidate,
            candidate_value,
            candidate_gradient,
            candidate_hessian,
        )
    return BlendFit(None, None, count, max_iterations, "not_converged")


def mean_log_likelihood(races: Sequence[BlendRace], alpha: float, beta: float) -> float:
    """Return the winners' mean log-likelihood at ``(alpha, beta)``."""
    value, _, _ = _derivatives(np.array([alpha, beta]), _padded_features(races))
    return value


def blend_probabilities(
    log_p_win: Sequence[float], log_q: Sequence[float], *, alpha: float, beta: float
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Return one race's blended win, top-two and top-three probabilities."""
    if len(log_p_win) != len(log_q) or len(log_p_win) < 3:
        raise ValueError("blended probabilities need matching features for at least three horses")
    strengths = alpha * np.asarray(log_p_win, dtype=np.float64) + beta * np.asarray(
        log_q, dtype=np.float64
    )
    if not np.all(np.isfinite(strengths)):
        raise ValueError("blended strengths must be finite")
    marginals = top3_marginal_probabilities(
        strengths, RaceLayout((len(strengths),)), temperature=1.0
    )
    return marginals.win, marginals.top2, marginals.top3


@dataclass(frozen=True)
class _Features:
    a: FloatArray
    b: FloatArray
    mask: npt.NDArray[np.bool_]
    winners: npt.NDArray[np.int64]


def _padded_features(races: Sequence[BlendRace]) -> _Features:
    width = max(len(race.log_p_win) for race in races)
    a = np.zeros((len(races), width))
    b = np.zeros((len(races), width))
    mask = np.zeros((len(races), width), dtype=bool)
    for index, race in enumerate(races):
        size = len(race.log_p_win)
        a[index, :size] = race.log_p_win
        b[index, :size] = race.log_q
        mask[index, :size] = True
    winners = np.array([race.winner for race in races], dtype=np.int64)
    return _Features(a, b, mask, winners)


def _derivatives(theta: FloatArray, features: _Features) -> tuple[float, FloatArray, FloatArray]:
    """Return the mean log-likelihood, its gradient and its Hessian."""
    strengths = np.where(features.mask, theta[0] * features.a + theta[1] * features.b, -np.inf)
    peak = np.max(strengths, axis=1, keepdims=True)
    weights = np.where(features.mask, np.exp(strengths - peak), 0.0)
    totals = np.sum(weights, axis=1, keepdims=True)
    probabilities = weights / totals
    log_partition = peak[:, 0] + np.log(totals[:, 0])
    rows = np.arange(len(features.winners))
    winner_a = features.a[rows, features.winners]
    winner_b = features.b[rows, features.winners]
    winner_strength = theta[0] * winner_a + theta[1] * winner_b
    count = float(len(features.winners))
    value = float(np.sum(winner_strength - log_partition) / count)
    mean_a = np.sum(probabilities * features.a, axis=1)
    mean_b = np.sum(probabilities * features.b, axis=1)
    gradient = np.array([np.sum(winner_a - mean_a) / count, np.sum(winner_b - mean_b) / count])
    centred_a = np.where(features.mask, features.a - mean_a[:, None], 0.0)
    centred_b = np.where(features.mask, features.b - mean_b[:, None], 0.0)
    covariance_aa = np.sum(probabilities * centred_a * centred_a) / count
    covariance_ab = np.sum(probabilities * centred_a * centred_b) / count
    covariance_bb = np.sum(probabilities * centred_b * centred_b) / count
    hessian = -np.array([[covariance_aa, covariance_ab], [covariance_ab, covariance_bb]])
    return value, gradient, hessian


def _negative_definite(hessian: FloatArray) -> bool:
    first = -float(hessian[0, 0])
    second = -float(hessian[1, 1])
    determinant = float(np.linalg.det(hessian))
    if not (first > 0.0 and second > 0.0 and determinant > _CONCAVITY_TOLERANCE * first * second):
        return False
    return float(np.min(np.linalg.eigvalsh(-hessian))) >= _MIN_CURVATURE


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


__all__ = [
    "BlendFailure",
    "BlendFit",
    "BlendRace",
    "blend_probabilities",
    "fit_market_blend",
    "market_log_probabilities",
    "mean_log_likelihood",
]
