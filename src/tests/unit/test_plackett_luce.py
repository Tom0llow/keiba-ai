"""Tests for the top-three Plackett--Luce probability calculations."""

from __future__ import annotations

from itertools import combinations, permutations
from math import exp, log

import numpy as np
import pytest

from models.probability.plackett_luce import (
    RaceLayout,
    top3_combination_log_probabilities,
    top3_marginal_probabilities,
    top3_order_probabilities,
    top3_plackett_luce,
)


def _scalar_nll(scores: np.ndarray, positions: np.ndarray) -> float:
    """Return one race's top-three PL NLL with scalar arithmetic."""
    remaining = set(range(len(scores)))
    result = 0.0
    for position in range(1, 4):
        winner = int(np.flatnonzero(positions == position)[0])
        maximum = max(float(scores[index]) for index in remaining)
        normalizer = sum(exp(float(scores[index]) - maximum) for index in remaining)
        result += maximum + log(normalizer) - float(scores[winner])
        remaining.remove(winner)
    return result


def _order_probability(scores: np.ndarray, order: tuple[int, ...]) -> float:
    """Return one ordered PL probability by direct enumeration."""
    remaining = set(range(len(scores)))
    probability = 1.0
    for horse in order:
        maximum = max(float(scores[index]) for index in remaining)
        numerator = exp(float(scores[horse]) - maximum)
        denominator = sum(exp(float(scores[index]) - maximum) for index in remaining)
        probability *= numerator / denominator
        remaining.remove(horse)
    return probability


def _assert_order_probability_totals(
    exacta: np.ndarray,
    trifecta: np.ndarray,
    quinella: np.ndarray,
    wide: np.ndarray,
    trio: np.ndarray,
) -> None:
    """Assert the total-probability identities for one race."""
    field_size = len(exacta)
    upper_indices = np.triu_indices(field_size, k=1)
    trio_indices = tuple(zip(*combinations(range(field_size), 3), strict=True))

    assert exacta.sum() == pytest.approx(1.0, abs=1e-12)
    assert trifecta.sum() == pytest.approx(1.0, abs=1e-12)
    assert quinella[upper_indices].sum() == pytest.approx(1.0, abs=1e-12)
    assert wide[upper_indices].sum() == pytest.approx(3.0, abs=1e-12)
    assert trio[trio_indices].sum() == pytest.approx(1.0, abs=1e-12)


def test_top3_nll_matches_scalar_reference_and_is_race_independent() -> None:
    scores = np.array([1.2, -0.4, 0.8, 2.0, -1.0, 0.1, 0.3, 1.1, -0.7], dtype=np.float64)
    positions = np.array([2, 3, 1, 4, 1, 3, 2, 5, 4], dtype=np.int64)
    layout = RaceLayout((4, 5))

    result = top3_plackett_luce(scores, positions, layout)

    assert result.race_nll == pytest.approx(
        [_scalar_nll(scores[:4], positions[:4]), _scalar_nll(scores[4:], positions[4:])],
        rel=1e-12,
    )
    shifted = top3_plackett_luce(scores + np.repeat([10.0, -4.0], [4, 5]), positions, layout)
    assert shifted.race_nll == pytest.approx(result.race_nll, rel=1e-12)
    probabilities = top3_marginal_probabilities(scores, layout)
    shifted_probabilities = top3_marginal_probabilities(
        scores + np.repeat([10.0, -4.0], [4, 5]), layout
    )
    assert shifted_probabilities.win == pytest.approx(probabilities.win, rel=1e-12)
    assert shifted_probabilities.top2 == pytest.approx(probabilities.top2, rel=1e-12)
    assert shifted_probabilities.top3 == pytest.approx(probabilities.top3, rel=1e-12)
    changed = top3_plackett_luce(scores + np.array([0.0] * 4 + [3.0] * 5), positions, layout)
    changed_probabilities = top3_marginal_probabilities(
        scores + np.array([0.0] * 4 + [3.0] * 5), layout
    )
    assert changed.race_nll[0] == pytest.approx(result.race_nll[0], rel=1e-12)
    assert changed.gradient[:4] == pytest.approx(result.gradient[:4], rel=1e-12)
    assert changed.hessian_diagonal[:4] == pytest.approx(result.hessian_diagonal[:4], rel=1e-12)
    assert changed_probabilities.win[:4] == pytest.approx(probabilities.win[:4], rel=1e-12)
    assert changed_probabilities.top2[:4] == pytest.approx(probabilities.top2[:4], rel=1e-12)
    assert changed_probabilities.top3[:4] == pytest.approx(probabilities.top3[:4], rel=1e-12)


def test_top3_nll_matches_scalar_reference_for_field_sizes_three_through_eighteen() -> None:
    generator = np.random.default_rng(42)
    group_sizes = tuple(range(3, 19))
    scores = np.concatenate([generator.normal(size=size) for size in group_sizes])
    positions = np.concatenate(
        [generator.permutation(np.arange(1, size + 1, dtype=np.int64)) for size in group_sizes]
    )
    layout = RaceLayout(group_sizes)

    result = top3_plackett_luce(scores, positions, layout)

    expected = []
    offset = 0
    for group_size in group_sizes:
        stop = offset + group_size
        expected.append(_scalar_nll(scores[offset:stop], positions[offset:stop]))
        offset = stop
    assert result.race_nll == pytest.approx(expected, rel=1e-12)


def test_derivatives_match_central_differences_for_field_sizes_three_through_eighteen() -> None:
    generator = np.random.default_rng(20261109)
    group_sizes = tuple(range(3, 19))
    scores = np.concatenate([generator.uniform(-30.0, 30.0, size=size) for size in group_sizes])
    scores[:2] = [30.0, -30.0]
    positions = np.concatenate(
        [generator.permutation(np.arange(1, size + 1, dtype=np.int64)) for size in group_sizes]
    )
    layout = RaceLayout(group_sizes)
    step = 1e-5
    result = top3_plackett_luce(scores, positions, layout)

    for index in range(layout.row_count):
        plus = scores.copy()
        minus = scores.copy()
        plus[index] += step
        minus[index] -= step
        numerical_gradient = (
            top3_plackett_luce(plus, positions, layout).total_nll
            - top3_plackett_luce(minus, positions, layout).total_nll
        ) / (2.0 * step)
        numerical_hessian = (
            top3_plackett_luce(plus, positions, layout).gradient[index]
            - top3_plackett_luce(minus, positions, layout).gradient[index]
        ) / (2.0 * step)
        assert numerical_gradient == pytest.approx(result.gradient[index], abs=1e-6)
        assert numerical_hessian == pytest.approx(result.hessian_diagonal[index], abs=1e-6)


_EXTREME_SIZES = (3, 6, 18)


def _extreme_scores(pattern: str) -> np.ndarray:
    """Return scores for a padded multi-race layout with a named extreme pattern."""
    parts = []
    for size in _EXTREME_SIZES:
        if pattern == "mixed":
            race = np.where(np.arange(size) % 2 == 0, 700.0, -700.0)
            race[-1] = 0.0
        elif pattern == "all_high":
            race = np.full(size, 700.0)
        else:
            race = np.linspace(-700.0, 700.0, size)
        parts.append(race)
    return np.concatenate(parts)


@pytest.mark.parametrize("pattern", ["mixed", "all_high", "uniform_spread"])
@pytest.mark.parametrize("temperature", [0.05, 1.0, 20.0])
def test_extreme_scores_in_padded_races_stay_finite_and_consistent(
    pattern: str, temperature: float
) -> None:
    scores = _extreme_scores(pattern)
    layout = RaceLayout(_EXTREME_SIZES)
    positions = np.concatenate([np.arange(1, size + 1, dtype=np.int64) for size in _EXTREME_SIZES])

    result = top3_plackett_luce(scores, positions, layout, temperature=temperature)
    probabilities = top3_marginal_probabilities(
        scores, layout, temperature=temperature, chunk_races=2
    )
    combinations = top3_combination_log_probabilities(
        scores, positions, layout, temperature=temperature
    )

    assert np.isfinite(result.total_nll)
    for values in (result.race_nll, result.stage_nll, result.gradient, result.hessian_diagonal):
        assert np.all(np.isfinite(values))
    for values in (probabilities.win, probabilities.top2, probabilities.top3):
        assert np.all(np.isfinite(values))
    for name in ("win", "exacta", "quinella", "trifecta", "trio"):
        values = getattr(combinations, name)
        assert np.all(np.isfinite(values))
        assert np.all(values <= 1e-12)
    offsets = layout.offsets
    for race in range(layout.race_count):
        selected = slice(int(offsets[race]), int(offsets[race + 1]))
        assert probabilities.win[selected].sum() == pytest.approx(1.0)
        assert probabilities.top2[selected].sum() == pytest.approx(2.0)
        assert probabilities.top3[selected].sum() == pytest.approx(3.0)
    assert np.all(probabilities.win <= probabilities.top2 + 1e-12)
    assert np.all(probabilities.top2 <= probabilities.top3 + 1e-12)
    assert np.all(probabilities.top3 <= 1.0 + 1e-12)


def test_marginals_and_combination_probabilities_match_enumeration_in_padded_races() -> None:
    generator = np.random.default_rng(20261109)
    group_sizes = (3, 6, 4, 7, 5)
    scores = generator.normal(size=sum(group_sizes))
    positions = np.concatenate(
        [generator.permutation(np.arange(1, size + 1, dtype=np.int64)) for size in group_sizes]
    )
    layout = RaceLayout(group_sizes)

    marginals = top3_marginal_probabilities(scores, layout, chunk_races=2)
    combinations = top3_combination_log_probabilities(scores, positions, layout)

    bounds = zip(layout.offsets[:-1].tolist(), layout.offsets[1:].tolist(), strict=True)
    for race, (start, stop) in enumerate(bounds):
        race_scores = scores[start:stop]
        race_positions = positions[start:stop]
        field_size = stop - start
        order_probabilities = {
            order: _order_probability(race_scores, order)
            for order in permutations(range(field_size), 3)
        }
        assert sum(order_probabilities.values()) == pytest.approx(1.0)
        for horse in range(field_size):
            assert marginals.win[start + horse] == pytest.approx(
                sum(v for order, v in order_probabilities.items() if order[0] == horse)
            )
            assert marginals.top2[start + horse] == pytest.approx(
                sum(v for order, v in order_probabilities.items() if horse in order[:2])
            )
            assert marginals.top3[start + horse] == pytest.approx(
                sum(v for order, v in order_probabilities.items() if horse in order)
            )
        ordered = np.argsort(race_positions)
        actual = (int(ordered[0]), int(ordered[1]), int(ordered[2]))
        exacta = _order_probability(race_scores, actual[:2])
        assert exp(combinations.win[race]) == pytest.approx(
            _order_probability(race_scores, actual[:1])
        )
        assert exp(combinations.exacta[race]) == pytest.approx(exacta)
        assert exp(combinations.quinella[race]) == pytest.approx(
            exacta + _order_probability(race_scores, actual[1::-1])
        )
        assert exp(combinations.trifecta[race]) == pytest.approx(order_probabilities[actual])
        assert exp(combinations.trio[race]) == pytest.approx(
            sum(v for order, v in order_probabilities.items() if set(order) == set(actual))
        )


def test_order_probabilities_match_marginals_and_actual_combination_probabilities() -> None:
    scores = np.array([1.2, -0.4, 0.8, 2.0, -1.0], dtype=np.float64)
    positions = np.array([2, 5, 3, 1, 4], dtype=np.int64)
    layout = RaceLayout((len(scores),))

    result = top3_order_probabilities(scores)

    _assert_order_probability_totals(
        result.exacta,
        result.trifecta,
        result.quinella,
        result.wide,
        result.trio,
    )
    assert result.quinella == pytest.approx(result.quinella.T, rel=1e-12)
    assert result.wide == pytest.approx(result.wide.T, rel=1e-12)
    assert np.diag(result.exacta) == pytest.approx(0.0)
    assert np.diag(result.quinella) == pytest.approx(0.0)
    assert np.diag(result.wide) == pytest.approx(0.0)
    for first_horse, second_horse, third_horse in combinations(range(len(scores)), 3):
        trio_values = (
            result.trio[first_horse, second_horse, third_horse],
            result.trio[first_horse, third_horse, second_horse],
            result.trio[second_horse, first_horse, third_horse],
            result.trio[second_horse, third_horse, first_horse],
            result.trio[third_horse, first_horse, second_horse],
            result.trio[third_horse, second_horse, first_horse],
        )
        assert trio_values == pytest.approx([trio_values[0]] * len(trio_values), rel=1e-12)
    for indices in np.ndindex(result.trifecta.shape):
        if len(set(indices)) < 3:
            assert result.trifecta[indices] == 0.0
            assert result.trio[indices] == 0.0

    marginals = top3_marginal_probabilities(scores, layout)
    win = result.trifecta.sum(axis=(1, 2))
    top2 = win + result.trifecta.sum(axis=(0, 2))
    top3 = top2 + result.trifecta.sum(axis=(0, 1))
    assert win == pytest.approx(marginals.win, rel=1e-12, abs=1e-12)
    assert top2 == pytest.approx(marginals.top2, rel=1e-12, abs=1e-12)
    assert top3 == pytest.approx(marginals.top3, rel=1e-12, abs=1e-12)

    actual = tuple(np.argsort(positions)[:3])
    combination_logs = top3_combination_log_probabilities(scores, positions, layout)
    assert result.exacta[actual[:2]] == pytest.approx(exp(combination_logs.exacta[0]), rel=1e-12)
    assert result.quinella[actual[:2]] == pytest.approx(
        exp(combination_logs.quinella[0]), rel=1e-12
    )
    assert result.trifecta[actual] == pytest.approx(exp(combination_logs.trifecta[0]), rel=1e-12)
    assert result.trio[actual] == pytest.approx(exp(combination_logs.trio[0]), rel=1e-12)


def test_order_probabilities_respect_temperature_and_score_shift() -> None:
    scores = np.array([1.2, -0.4, 0.8, 2.0, -1.0], dtype=np.float64)

    probabilities = top3_order_probabilities(scores)
    shifted = top3_order_probabilities(scores + 17.5)
    tempered = top3_order_probabilities(scores, temperature=2.0)
    scaled = top3_order_probabilities(scores / 2.0)

    for name in ("exacta", "trifecta", "quinella", "wide", "trio"):
        original = getattr(probabilities, name)
        assert getattr(shifted, name) == pytest.approx(original, rel=1e-12, abs=1e-12)
        assert getattr(tempered, name) == pytest.approx(getattr(scaled, name), rel=1e-12, abs=1e-12)
    assert not np.allclose(tempered.exacta, probabilities.exacta)


def test_order_probabilities_reject_field_sizes_smaller_than_three() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        top3_order_probabilities(np.array([0.0, 1.0]))


@pytest.mark.parametrize(
    ("scores", "dominant"),
    [
        ([700.0, -700.0, 0.0, 700.0, -700.0], False),
        # One horse wins with float64 probability exactly 1, so naive later stages divide by 0.
        ([700.0, -700.0, 0.0, -700.0, -700.0], True),
    ],
)
def test_order_probabilities_stay_finite_for_extreme_scores(
    scores: list[float], dominant: bool
) -> None:
    result = top3_order_probabilities(np.array(scores, dtype=np.float64), temperature=0.05)

    if dominant:
        layout = RaceLayout.from_group_sizes([len(scores)])
        win = top3_marginal_probabilities(
            np.array(scores, dtype=np.float64), layout, temperature=0.05
        ).win
        assert win[0] == 1.0
        assert result.exacta[0].sum() == pytest.approx(1.0, abs=1e-12)

    for values in (
        result.exacta,
        result.trifecta,
        result.quinella,
        result.wide,
        result.trio,
    ):
        assert np.all(np.isfinite(values))
        assert np.all(values >= 0.0)
    _assert_order_probability_totals(
        result.exacta,
        result.trifecta,
        result.quinella,
        result.wide,
        result.trio,
    )


def test_chunk_size_and_temperature_scaling_do_not_change_results() -> None:
    scores = np.array([0.5, -0.5, 1.0, 0.2, -0.2, 0.7, 1.1], dtype=np.float64)
    positions = np.array([2, 1, 3, 4, 1, 3, 2], dtype=np.int64)
    layout = RaceLayout((3, 4))

    by_race = top3_marginal_probabilities(scores, layout, temperature=2.0, chunk_races=1)
    together = top3_marginal_probabilities(scores, layout, temperature=2.0, chunk_races=10)
    scaled = top3_marginal_probabilities(scores / 2.0, layout)

    assert by_race.win == pytest.approx(together.win)
    assert by_race.top2 == pytest.approx(together.top2)
    assert by_race.top3 == pytest.approx(together.top3)
    assert by_race.win == pytest.approx(scaled.win)
    assert by_race.top2 == pytest.approx(scaled.top2)
    assert by_race.top3 == pytest.approx(scaled.top3)

    tempered = top3_plackett_luce(scores, positions, layout, temperature=2.0)
    divided = top3_plackett_luce(scores / 2.0, positions, layout)
    assert tempered.race_nll == pytest.approx(divided.race_nll, rel=1e-12)
    assert tempered.stage_nll.ravel() == pytest.approx(divided.stage_nll.ravel(), rel=1e-12)
    assert tempered.gradient == pytest.approx(divided.gradient / 2.0, rel=1e-12)
    assert tempered.hessian_diagonal == pytest.approx(divided.hessian_diagonal / 4.0, rel=1e-12)
    tempered_combinations = top3_combination_log_probabilities(
        scores, positions, layout, temperature=2.0
    )
    divided_combinations = top3_combination_log_probabilities(scores / 2.0, positions, layout)
    for name in ("win", "exacta", "quinella", "trifecta", "trio"):
        assert getattr(tempered_combinations, name) == pytest.approx(
            getattr(divided_combinations, name), rel=1e-12
        )


def test_layout_and_positions_require_valid_races() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        RaceLayout((2,))

    layout = RaceLayout((3,))
    with pytest.raises(ValueError, match="permutation"):
        top3_plackett_luce(np.zeros(3), np.array([1, 1, 3]), layout)
