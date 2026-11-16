"""Tests for hit-conditional final-odds metrics and bootstrap intervals."""

from __future__ import annotations

from math import log

import pytest

from models.evaluation.final_odds_metrics import (
    bootstrap_final_odds_metrics,
    final_odds_metrics,
    paired_bootstrap_final_odds_metrics,
)


def test_final_odds_metrics_match_a_hand_calculation() -> None:
    result = final_odds_metrics(
        [1.0, 2.0, 3.0],
        [10.0, 20.0, 40.0],
        [10.0, 10.0, 50.0],
        bands=[1.0, 2.0],
        interval_lower=[9.0, 15.0, 41.0],
        interval_upper=[11.0, 25.0, 50.0],
    )

    assert result.hits == 3
    assert result.payout_ratio == 1.0
    assert result.mean_payout_ratio == pytest.approx((1.0 + 2.0 + 0.8) / 3)
    assert result.median_abs_error_pct == pytest.approx(25.0)
    assert result.within_10pct == pytest.approx(1 / 3)
    assert result.over_20pct == pytest.approx(2 / 3)
    assert result.mean_log_error == pytest.approx((log(0.5) + log(1.25)) / 3)
    assert result.interval_coverage == pytest.approx(2 / 3)
    assert [(band.hits, band.payout_ratio, band.mean_payout_ratio) for band in result.bands] == [
        (1, 1.0, 1.0),
        (2, 1.0, pytest.approx(1.4)),
    ]


def test_final_odds_metrics_return_nulls_for_an_empty_collection() -> None:
    result = final_odds_metrics([], [], [], bands=[1.0, 2.0])

    assert result.hits == 0
    assert result.payout_ratio is None
    assert result.mean_payout_ratio is None
    assert result.median_abs_error_pct is None
    assert result.within_10pct is None
    assert result.over_20pct is None
    assert result.mean_log_error is None
    assert result.interval_coverage is None
    assert [(band.lower, band.upper, band.hits) for band in result.bands] == [
        (1.0, 2.0, 0),
        (2.0, None, 0),
    ]


def test_bootstrap_resamples_whole_races_deterministically() -> None:
    first = bootstrap_final_odds_metrics(
        ["race-a", "race-a", "race-b"],
        [10.0, 20.0, 30.0],
        [10.0, 10.0, 60.0],
        resamples=100,
        seed=7,
    )
    second = bootstrap_final_odds_metrics(
        ["race-a", "race-a", "race-b"],
        [10.0, 20.0, 30.0],
        [10.0, 10.0, 60.0],
        resamples=100,
        seed=7,
    )

    assert first == second
    assert first.payout_ratio.point_estimate == pytest.approx(0.75)
    assert first.mean_payout_ratio.point_estimate == pytest.approx((1.0 + 2.0 + 0.5) / 3)
    assert first.payout_ratio.confidence_interval_lower is not None
    assert first.payout_ratio.confidence_interval_upper is not None


def test_bootstrap_resamples_a_multi_hit_race_as_one_unit() -> None:
    result = bootstrap_final_odds_metrics(
        ["race-a", "race-a"],
        [10.0, 20.0],
        [10.0, 5.0],
        resamples=100,
        seed=7,
    )

    assert result.payout_ratio.point_estimate == pytest.approx(2.0)
    assert result.payout_ratio.confidence_interval_lower == pytest.approx(2.0)
    assert result.payout_ratio.confidence_interval_upper == pytest.approx(2.0)
    assert result.mean_payout_ratio.point_estimate == pytest.approx(2.5)
    assert result.mean_payout_ratio.confidence_interval_lower == pytest.approx(2.5)
    assert result.mean_payout_ratio.confidence_interval_upper == pytest.approx(2.5)


def test_paired_bootstrap_uses_the_same_race_samples_for_both_variants() -> None:
    race_ids = ["race-a", "race-a", "race-b"]
    final_odds = [10.0, 20.0, 30.0]
    left_predicted_odds = [10.0, 10.0, 60.0]
    right_predicted_odds = [20.0, 20.0, 120.0]
    left = bootstrap_final_odds_metrics(
        race_ids,
        final_odds,
        left_predicted_odds,
        resamples=100,
        seed=11,
    )
    right = bootstrap_final_odds_metrics(
        race_ids,
        final_odds,
        right_predicted_odds,
        resamples=100,
        seed=11,
    )
    result = paired_bootstrap_final_odds_metrics(
        race_ids,
        final_odds,
        left_predicted_odds,
        right_predicted_odds,
        resamples=100,
        seed=11,
    )

    assert left.payout_ratio.point_estimate is not None
    assert right.payout_ratio.point_estimate is not None
    assert left.mean_payout_ratio.point_estimate is not None
    assert right.mean_payout_ratio.point_estimate is not None
    assert result.payout_ratio.point_estimate == pytest.approx(
        left.payout_ratio.point_estimate - right.payout_ratio.point_estimate
    )
    assert result.mean_payout_ratio.point_estimate == pytest.approx(
        left.mean_payout_ratio.point_estimate - right.mean_payout_ratio.point_estimate
    )
    assert left.payout_ratio.confidence_interval_lower is not None
    assert left.payout_ratio.confidence_interval_upper is not None
    assert left.mean_payout_ratio.confidence_interval_lower is not None
    assert left.mean_payout_ratio.confidence_interval_upper is not None
    assert left.payout_ratio.confidence_interval_lower < left.payout_ratio.confidence_interval_upper
    assert (
        left.mean_payout_ratio.confidence_interval_lower
        < left.mean_payout_ratio.confidence_interval_upper
    )
    assert result.payout_ratio.confidence_interval_lower == pytest.approx(
        0.5 * left.payout_ratio.confidence_interval_lower
    )
    assert result.payout_ratio.confidence_interval_upper == pytest.approx(
        0.5 * left.payout_ratio.confidence_interval_upper
    )
    assert result.mean_payout_ratio.confidence_interval_lower == pytest.approx(
        0.5 * left.mean_payout_ratio.confidence_interval_lower
    )
    assert result.mean_payout_ratio.confidence_interval_upper == pytest.approx(
        0.5 * left.mean_payout_ratio.confidence_interval_upper
    )


@pytest.mark.parametrize(
    ("interval_lower", "interval_upper", "message"),
    [
        ([1.0, 2.0], None, "provided together"),
        (None, [1.0, 2.0], "provided together"),
        ([1.0, 2.0], [1.0], "expected length"),
    ],
)
def test_final_odds_metrics_rejects_incomplete_or_mismatched_intervals(
    interval_lower: list[float] | None,
    interval_upper: list[float] | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        final_odds_metrics(
            [1.0, 2.0],
            [1.0, 2.0],
            [1.0, 2.0],
            bands=[1.0, 2.0],
            interval_lower=interval_lower,
            interval_upper=interval_upper,
        )


def test_final_odds_metrics_rejects_freeze_odds_below_the_first_band() -> None:
    with pytest.raises(ValueError, match="below the first odds-band"):
        final_odds_metrics(
            [0.9],
            [1.0],
            [1.0],
            bands=[1.0, 2.0],
        )
