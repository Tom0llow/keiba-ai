"""Tests for race-level probability metrics and calibration summaries."""

from __future__ import annotations

from math import log

import numpy as np
import pytest

from models.evaluation.probability_metrics import (
    market_win_probabilities,
    odds_calibration_table,
    paired_bootstrap_comparison,
    probability_calibration_table,
    race_probability_metrics,
    top3_probability_calibration_tables,
)
from models.probability.plackett_luce import MarginalProbabilities, RaceLayout


def test_race_probability_metrics_match_a_small_hand_calculation() -> None:
    layout = RaceLayout((3,))
    scores = np.log(np.array([0.5, 0.3, 0.2]))
    positions = np.array([1, 2, 3], dtype=np.int64)

    result = race_probability_metrics(scores, positions, layout)

    assert result.winner_log_loss == pytest.approx([-log(0.5)])
    assert result.multiclass_brier == pytest.approx([0.38])
    assert result.exacta_log_loss == pytest.approx([-log(0.3)])
    assert result.quinella_log_loss == pytest.approx([-log(0.3 + 0.3 * 0.5 / 0.7)])
    assert result.trifecta_log_loss == pytest.approx([-log(0.3)])
    assert result.trio_log_loss == pytest.approx([0.0])
    assert np.allclose(result.stage_nll, [[-log(0.5), -log(0.6), 0.0]])


def test_race_probability_metrics_separate_every_bet_type_in_a_four_horse_race() -> None:
    layout = RaceLayout((4,))
    strengths = [0.4, 0.3, 0.2, 0.1]
    scores = np.log(np.array(strengths))
    positions = np.array([2, 1, 4, 3], dtype=np.int64)

    result = race_probability_metrics(scores, positions, layout)

    def order(*horses: int) -> float:
        remaining = 1.0
        probability = 1.0
        for horse in horses:
            probability *= strengths[horse] / remaining
            remaining -= strengths[horse]
        return probability

    assert result.winner_log_loss == pytest.approx([-log(0.3)])
    assert result.multiclass_brier == pytest.approx([0.16 + 0.49 + 0.04 + 0.01])
    assert result.exacta_log_loss == pytest.approx([-log(order(1, 0))])
    assert result.quinella_log_loss == pytest.approx([-log(order(1, 0) + order(0, 1))])
    assert result.trifecta_log_loss == pytest.approx([-log(order(1, 0, 3))])
    trio = sum(
        order(a, b, c)
        for a, b, c in ((1, 0, 3), (1, 3, 0), (0, 1, 3), (0, 3, 1), (3, 1, 0), (3, 0, 1))
    )
    assert result.trio_log_loss == pytest.approx([-log(trio)])
    assert np.allclose(result.stage_nll, [[-log(0.3), -log(0.4 / 0.7), -log(0.1 / 0.3)]])


def test_probability_calibration_table_uses_declared_band_boundaries() -> None:
    result = probability_calibration_table(
        np.array([0.0, 0.1, 0.2, 0.99, 1.0]),
        np.array([0, 1, 0, 1, 1]),
        [0.0, 0.2, 0.5, 1.0],
    )

    assert [(item.count, item.mean_prediction, item.observed_rate) for item in result] == [
        (2, 0.05, 0.5),
        (1, 0.2, 0.0),
        (2, 0.995, 1.0),
    ]


def test_probability_calibration_clips_small_rounding_boundary_violations() -> None:
    result = probability_calibration_table(
        np.array([-1e-15, 1.0 + 1e-15]),
        np.array([0, 1]),
        [0.0, 0.5, 1.0],
    )

    assert [(item.count, item.mean_prediction) for item in result] == [
        (1, 0.0),
        (1, 1.0),
    ]

    with pytest.raises(ValueError, match="finite probabilities"):
        probability_calibration_table(
            np.array([1.0 + 1e-6]),
            np.array([1]),
            [0.0, 1.0],
        )


def test_probability_calibration_requires_bands_to_cover_the_full_unit_interval() -> None:
    for bands in ([0.1, 1.0], [0.0, 0.9]):
        with pytest.raises(ValueError, match="start at zero and end at one"):
            probability_calibration_table(np.array([0.1]), np.array([0]), bands)


def test_top3_probability_calibration_counts_horses_across_unequal_race_sizes() -> None:
    layout = RaceLayout((3, 4))
    marginals = MarginalProbabilities(
        win=np.array([0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9]),
        top2=np.array([0.2, 0.2, 0.2, 0.95, 0.95, 0.95, 0.95]),
        top3=np.array([0.3, 0.3, 0.3, 1.0, 1.0, 1.0, 1.0]),
    )
    positions = np.array([1, 2, 3, 1, 2, 3, 4], dtype=np.int64)

    result = top3_probability_calibration_tables(marginals, positions, layout, [0.0, 0.5, 1.0])

    assert [item.count for item in result.win] == [3, 4]
    assert [item.observed_rate for item in result.win] == [
        pytest.approx(1 / 3),
        pytest.approx(1 / 4),
    ]


def test_market_probabilities_and_odds_calibration_exclude_incomplete_races() -> None:
    layout = RaceLayout((3, 3))
    odds = np.array([2.0, 3.0, 6.0, 3.0, np.nan, 5.0])
    positions = np.array([2, 1, 3, 1, 2, 3], dtype=np.int64)

    market = market_win_probabilities(odds, layout)
    calibration = odds_calibration_table(
        odds,
        np.array([0.6, 0.3, 0.1, 0.5, 0.2, 0.3]),
        market.market_q,
        positions,
        layout,
        [1.0, 3.0, 5.0],
    )

    assert market.complete_races.tolist() == [True, False]
    assert market.incomplete_race_count == 1
    assert market.market_q[:3] == pytest.approx([0.5, 1 / 3, 1 / 6])
    assert np.isnan(market.market_q[3:]).all()
    assert [(item.lower, item.upper, item.count) for item in calibration] == [
        (1.0, 3.0, 1),
        (3.0, 5.0, 1),
        (5.0, None, 1),
    ]
    assert [item.mean_model_probability for item in calibration] == pytest.approx([0.6, 0.3, 0.1])
    assert [item.mean_market_probability for item in calibration] == pytest.approx(
        [0.5, 1 / 3, 1 / 6]
    )
    assert [item.observed_win_rate for item in calibration] == [0.0, 1.0, 0.0]


def test_odds_calibration_requires_first_band_to_include_minimum_jra_odds() -> None:
    layout = RaceLayout((3,))

    with pytest.raises(ValueError, match="no higher than one"):
        odds_calibration_table(
            np.array([2.0, 3.0, 6.0]),
            np.array([0.6, 0.3, 0.1]),
            np.array([0.5, 1 / 3, 1 / 6]),
            np.array([2, 1, 3], dtype=np.int64),
            layout,
            [1.1, 3.0],
        )


def test_paired_bootstrap_is_deterministic_and_uses_the_documented_conclusions() -> None:
    model_better = paired_bootstrap_comparison([0.0, 0.0], [1.0, 1.0], resamples=100, seed=7)
    market_better = paired_bootstrap_comparison([1.0, 1.0], [0.0, 0.0], resamples=100, seed=7)
    inconclusive = paired_bootstrap_comparison([0.0, 2.0], [1.0, 1.0], resamples=100, seed=7)

    assert (
        paired_bootstrap_comparison([0.0, 2.0], [1.0, 1.0], resamples=100, seed=7) == inconclusive
    )
    assert model_better.conclusion == "model_better"
    assert market_better.conclusion == "market_better"
    assert inconclusive.conclusion == "inconclusive"
