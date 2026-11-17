"""Tests for the ADR-044 PL and market blend (plan AC-1 and AC-2)."""

from __future__ import annotations

import math
from random import Random

import numpy as np
import pytest

from models.probability.market_blend import (
    BlendRace,
    blend_probabilities,
    fit_market_blend,
    market_log_probabilities,
    mean_log_likelihood,
)
from models.probability.plackett_luce import RaceLayout, top3_marginal_probabilities


def _races(count: int = 300, seed: int = 1) -> list[BlendRace]:
    """Return races whose winners follow strengths 0.7·a + 0.5·b with noise-free sampling."""
    generator = Random(seed)
    races: list[BlendRace] = []
    for _ in range(count):
        size = generator.randint(5, 10)
        raw_a = [generator.gauss(0.0, 1.0) for _ in range(size)]
        raw_b = [generator.gauss(0.0, 1.0) + 0.3 * value for value in raw_a]
        a = _log_softmax(raw_a)
        b = _log_softmax(raw_b)
        strengths = [0.7 * x + 0.5 * y for x, y in zip(a, b, strict=True)]
        weights = [math.exp(value) for value in strengths]
        winner = generator.choices(range(size), weights=weights)[0]
        races.append(BlendRace(tuple(a), tuple(b), winner))
    return races


def _log_softmax(values: list[float]) -> list[float]:
    peak = max(values)
    total = math.log(sum(math.exp(value - peak) for value in values)) + peak
    return [value - total for value in values]


def _gradient(races: list[BlendRace], alpha: float, beta: float) -> tuple[float, float]:
    step = 1e-6
    return (
        (
            mean_log_likelihood(races, alpha + step, beta)
            - mean_log_likelihood(races, alpha - step, beta)
        )
        / (2 * step),
        (
            mean_log_likelihood(races, alpha, beta + step)
            - mean_log_likelihood(races, alpha, beta - step)
        )
        / (2 * step),
    )


def _analytic_gradient(races: list[BlendRace], alpha: float, beta: float) -> tuple[float, float]:
    count = len(races)
    gradient_a = gradient_b = 0.0
    for race in races:
        strengths = [alpha * a + beta * b for a, b in zip(race.log_p_win, race.log_q, strict=True)]
        peak = max(strengths)
        weights = [math.exp(value - peak) for value in strengths]
        total = sum(weights)
        gradient_a += (
            race.log_p_win[race.winner]
            - sum(w * a for w, a in zip(weights, race.log_p_win, strict=True)) / total
        )
        gradient_b += (
            race.log_q[race.winner]
            - sum(w * b for w, b in zip(weights, race.log_q, strict=True)) / total
        )
    return gradient_a / count, gradient_b / count


def test_the_fit_is_a_stationary_maximum_of_the_mean_log_likelihood() -> None:
    races = _races()

    fit = fit_market_blend(races, min_races=10, tolerance=1e-12, max_iterations=100)

    assert fit.available
    assert fit.alpha is not None
    assert fit.beta is not None
    gradient = _analytic_gradient(races, fit.alpha, fit.beta)
    assert max(abs(value) for value in gradient) < 1e-8
    best = mean_log_likelihood(races, fit.alpha, fit.beta)
    for d_alpha, d_beta in ((1e-4, 0), (-1e-4, 0), (0, 1e-4), (0, -1e-4), (1e-4, 1e-4)):
        assert mean_log_likelihood(races, fit.alpha + d_alpha, fit.beta + d_beta) <= best
    assert fit.races == len(races)


def test_the_likelihood_gradient_matches_finite_differences() -> None:
    races = _races(40)

    for alpha, beta in ((1.0, 0.0), (0.3, 0.9), (1.4, -0.2)):
        numeric = _gradient(races, alpha, beta)
        analytic = _analytic_gradient(races, alpha, beta)
        assert numeric == pytest.approx(analytic, rel=1e-6, abs=1e-9)


def test_the_hessian_matches_finite_differences_of_the_gradient() -> None:
    from models.probability import market_blend

    races = _races(40)
    features = market_blend._padded_features(races)
    theta = np.array([0.6, 0.4])
    _, _, hessian = market_blend._derivatives(theta, features)
    step = 1e-5
    numeric = np.zeros((2, 2))
    for column in range(2):
        shift = np.zeros(2)
        shift[column] = step
        _, upper, _ = market_blend._derivatives(theta + shift, features)
        _, lower, _ = market_blend._derivatives(theta - shift, features)
        numeric[:, column] = (upper - lower) / (2 * step)

    assert np.allclose(hessian, numeric, rtol=1e-6, atol=1e-10)


def test_a_feature_that_is_a_multiple_of_the_other_is_not_concave() -> None:
    races = [
        BlendRace(race.log_p_win, tuple(2.0 * value for value in race.log_p_win), race.winner)
        for race in _races(50)
    ]

    fit = fit_market_blend(races, min_races=10, tolerance=1e-10, max_iterations=100)

    assert (fit.available, fit.failure, fit.alpha, fit.beta) == (False, "not_concave", None, None)


def test_too_few_races_and_too_few_iterations_are_unavailable() -> None:
    races = _races(20)

    assert fit_market_blend(races, min_races=21, tolerance=1e-10, max_iterations=100).failure == (
        "insufficient_races"
    )
    assert fit_market_blend([], min_races=1, tolerance=1e-10, max_iterations=5).races == 0
    assert fit_market_blend(races, min_races=1, tolerance=1e-14, max_iterations=1).failure == (
        "not_converged"
    )


def test_identity_coefficients_reproduce_the_pl_marginals() -> None:
    log_p_win = _log_softmax([0.9, 0.2, -0.1, -0.6, -1.3])
    log_q = market_log_probabilities([2.5, 4.0, 6.0, 12.0, 30.0])

    win, top2, top3 = blend_probabilities(log_p_win, log_q, alpha=1.0, beta=0.0)

    assert win == pytest.approx([math.exp(value) for value in log_p_win], abs=1e-12)
    expected = top3_marginal_probabilities(np.asarray(log_p_win), RaceLayout((5,)))
    assert np.allclose(top2, expected.top2, atol=1e-12)
    assert np.allclose(top3, expected.top3, atol=1e-12)


def test_blended_probabilities_sum_to_one_two_and_three() -> None:
    log_p_win = _log_softmax([0.9, 0.2, -0.1, -0.6, -1.3, -2.0])
    log_q = market_log_probabilities([2.5, 4.0, 6.0, 12.0, 30.0, 80.0])

    win, top2, top3 = blend_probabilities(log_p_win, log_q, alpha=0.4, beta=0.8)

    assert (float(win.sum()), float(top2.sum()), float(top3.sum())) == pytest.approx(
        (1.0, 2.0, 3.0), abs=1e-9
    )
    expected = top3_marginal_probabilities(
        0.4 * np.asarray(log_p_win) + 0.8 * np.asarray(log_q), RaceLayout((6,))
    )
    assert np.allclose(top3, expected.top3, atol=1e-12)


def test_market_log_probabilities_normalise_inverse_odds() -> None:
    assert market_log_probabilities([2.0, 2.0]) == pytest.approx((math.log(0.5), math.log(0.5)))
    with pytest.raises(ValueError, match="positive and finite"):
        market_log_probabilities([2.0, 0.0])


def test_invalid_races_are_rejected() -> None:
    with pytest.raises(ValueError, match="matching features"):
        BlendRace((0.0,), (0.0,), 0)
    with pytest.raises(ValueError, match="finite"):
        BlendRace((-math.inf, 0.0), (0.0, 0.0), 0)
    with pytest.raises(ValueError, match="winner"):
        BlendRace((0.0, 0.0), (0.0, 0.0), 2)


def test_a_realistic_fit_converges_at_the_measurement_tolerance() -> None:
    # Seed 105 put a step-acceptance test on the rounding noise of the mean likelihood:
    # without a rounding slack, Newton stalled and reported not_converged after 100 steps.
    generator = np.random.default_rng(105)
    races: list[BlendRace] = []
    for _ in range(3_000):
        size = int(generator.integers(8, 19))
        za = generator.normal(0.0, 1.2, size)
        zb = 0.8 * za + generator.normal(0.0, 0.8, size)
        a = za - np.log(np.exp(za).sum())
        b = zb - np.log(np.exp(zb).sum())
        strengths = 0.7 * a + 0.4 * b
        weights = np.exp(strengths - strengths.max())
        winner = int(generator.choice(size, p=weights / weights.sum()))
        races.append(BlendRace(tuple(a.tolist()), tuple(b.tolist()), winner))

    fit = fit_market_blend(races, min_races=1_000, tolerance=1e-10, max_iterations=100)

    assert fit.failure is None
    assert fit.iterations <= 10


def test_separable_races_have_no_maximum_and_are_unavailable() -> None:
    # The winner always has the largest log p_win, so the likelihood rises without bound.
    races = [
        BlendRace(
            tuple(_log_softmax([2.0, 1.0, 0.0, -1.0])), tuple(_log_softmax([0.5, 1.0, 0.0, 0.2])), 0
        )
        for _ in range(50)
    ]

    fit = fit_market_blend(races, min_races=10, tolerance=1e-10, max_iterations=100)

    assert (fit.failure, fit.alpha, fit.beta) == ("not_concave", None, None)
