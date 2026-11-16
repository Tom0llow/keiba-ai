"""Tests for pure hit-conditional final-odds correction fitting."""

from __future__ import annotations

from math import log, sqrt

import pytest

from models.market.final_odds_correction import (
    fit_all_correction,
    fit_graded_correction,
    validate_odds_bands,
    validate_quantiles,
)


def test_all_correction_interpolates_multiplier_on_log_freeze_odds() -> None:
    correction = fit_all_correction(
        [1.0, 4.0],
        [2.0, 4.0],
        bands=[1.0, 2.0],
        quantiles=[0.0, 0.5, 1.0],
        min_hits=1,
    )

    estimate = correction.estimate(2.0)

    assert [band.mean_ratio for band in correction.bands] == [2.0, 1.0]
    assert [band.mean_log_freeze_odds for band in correction.bands] == pytest.approx(
        [0.0, log(4.0)]
    )
    assert [band.ratio_quantiles for band in correction.bands] == [(2.0, 2.0, 2.0), (1.0, 1.0, 1.0)]
    assert estimate.multiplier == pytest.approx(1.5)
    assert estimate.final_odds == pytest.approx(3.0)
    assert correction.estimate(1.0).multiplier == 2.0
    assert correction.estimate(10.0).multiplier == 1.0


def test_all_correction_merges_undersized_bands_and_records_the_source_bands() -> None:
    correction = fit_all_correction(
        [1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 3.3],
        [2.2, 2.4, 4.2, 4.4, 3.1, 3.2, 3.3],
        bands=[1.0, 2.0, 3.0],
        quantiles=[0.5],
        min_hits=3,
    )

    assert [
        (band.lower, band.upper, band.source_lowers, band.hit_count) for band in correction.bands
    ] == [
        (1.0, 3.0, (1.0, 2.0), 4),
        (3.0, None, (3.0,), 3),
    ]


def test_all_correction_merges_an_undersized_top_band_into_its_lower_neighbor() -> None:
    correction = fit_all_correction(
        [1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1],
        [2.2, 2.4, 2.6, 6.3, 6.6, 6.9, 24.8],
        bands=[1.0, 2.0, 3.0],
        quantiles=[0.5],
        min_hits=3,
    )

    assert [
        (band.lower, band.upper, band.source_lowers, band.hit_count) for band in correction.bands
    ] == [
        (1.0, 2.0, (1.0,), 3),
        (2.0, None, (2.0, 3.0), 4),
    ]
    assert correction.bands[0].mean_ratio == pytest.approx(2.0)
    assert correction.bands[1].mean_ratio == pytest.approx(4.25)


def test_all_correction_repeats_merges_until_a_combined_band_is_large_enough() -> None:
    correction = fit_all_correction(
        [1.1, 2.1, 3.1, 4.1, 4.2, 4.3],
        [1.1, 4.2, 9.3, 16.4, 16.8, 17.2],
        bands=[1.0, 2.0, 3.0, 4.0],
        quantiles=[0.5],
        min_hits=3,
    )

    assert [
        (band.lower, band.upper, band.source_lowers, band.hit_count) for band in correction.bands
    ] == [
        (1.0, 4.0, (1.0, 2.0, 3.0), 3),
        (4.0, None, (4.0,), 3),
    ]
    assert correction.bands[0].mean_ratio == pytest.approx(2.0)
    assert correction.bands[1].mean_ratio == pytest.approx(4.0)


def test_graded_correction_uses_declared_shrinkage_and_all_quantiles_when_small() -> None:
    all_correction = fit_all_correction(
        [1.0, 1.0, 2.0, 2.0, 4.0, 4.0],
        [2.0, 4.0, 6.0, 10.0, 16.0, 24.0],
        bands=[1.0, 2.0, 4.0],
        quantiles=[0.5],
        min_hits=1,
    )
    correction = fit_graded_correction(
        [1.0, 1.0, 2.0],
        [5.0, 7.0, 18.0],
        bands=[1.0, 2.0, 4.0],
        quantiles=[0.5],
        min_hits=2,
        shrinkage_k=2,
        all_correction=all_correction,
    )

    low, middle, high = correction.bands
    assert low.shrinkage_target == 3.0
    assert low.mean_ratio == pytest.approx((2 * 6.0 + 2 * 3.0) / 4)
    assert low.ratio_quantiles == (5.0,)
    assert middle.shrinkage_target == 4.0
    assert middle.mean_ratio == pytest.approx((1 * 9.0 + 2 * 4.0) / 3)
    assert middle.ratio_quantiles == (3.0,)
    assert high.hit_count == 0
    assert high.ratio_quantiles is None
    assert correction.estimate(sqrt(2.0)).multiplier == pytest.approx(61.0 / 12.0)
    assert correction.estimate(4.0).ratio_quantiles == (4.0,)
    assert correction.estimate(4.0).multiplier == all_correction.estimate(4.0).multiplier
    assert correction.estimate(8.0).multiplier == all_correction.estimate(8.0).multiplier


def test_graded_correction_uses_the_all_multiplier_inside_an_empty_interior_band() -> None:
    all_correction = fit_all_correction(
        [1.0, 1.0, 2.0, 2.0, 4.0, 4.0],
        [2.0, 4.0, 6.0, 10.0, 16.0, 24.0],
        bands=[1.0, 2.0, 4.0],
        quantiles=[0.5],
        min_hits=1,
    )
    correction = fit_graded_correction(
        [1.0, 4.0],
        [5.0, 24.0],
        bands=[1.0, 2.0, 4.0],
        quantiles=[0.5],
        min_hits=1,
        shrinkage_k=2,
        all_correction=all_correction,
    )

    low, middle, high = correction.bands
    assert middle.hit_count == 0
    assert low.mean_ratio == pytest.approx((5.0 + 2 * 3.0) / 3)
    assert high.mean_ratio == pytest.approx((6.0 + 2 * 5.0) / 3)
    for odds in (2.0, 3.0, 3.9):
        assert correction.estimate(odds).multiplier == all_correction.estimate(odds).multiplier
        assert correction.estimate(odds).ratio_quantiles == (
            all_correction.estimate(odds).ratio_quantiles
        )
    assert correction.estimate(1.5).multiplier == pytest.approx(
        11.0 / 3.0 + log(1.5) / log(4.0) * (16.0 / 3.0 - 11.0 / 3.0)
    )
    assert correction.estimate(4.0).multiplier == pytest.approx(16.0 / 3.0)


@pytest.mark.parametrize(
    ("bands", "quantiles"),
    [
        ([1.0, 2.0], [0.5]),
        ([1.0], [0.25]),
    ],
)
def test_graded_correction_rejects_an_incompatible_all_correction(
    bands: list[float], quantiles: list[float]
) -> None:
    all_correction = fit_all_correction(
        [1.0],
        [1.0],
        bands=[1.0],
        quantiles=[0.5],
        min_hits=1,
    )

    with pytest.raises(ValueError, match="same odds bands and quantiles"):
        fit_graded_correction(
            [1.0],
            [1.0],
            bands=bands,
            quantiles=quantiles,
            min_hits=1,
            shrinkage_k=0,
            all_correction=all_correction,
        )


@pytest.mark.parametrize(
    ("bands", "message"),
    [
        ([0.9, 2.0], "start at 1.0"),
        ([1.0, 1.0], "strictly increasing"),
        ([1.0, float("inf")], "finite"),
        ([], "must not be empty"),
    ],
)
def test_odds_band_validation_rejects_invalid_configurations(
    bands: list[float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_odds_bands(bands)


@pytest.mark.parametrize(
    ("quantiles", "message"),
    [
        ([-0.1, 0.5], "between zero and one"),
        ([0.2, 0.2], "strictly increasing"),
        ([0.1, float("nan")], "finite"),
        ([], "must not be empty"),
    ],
)
def test_quantile_validation_rejects_invalid_configurations(
    quantiles: list[float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_quantiles(quantiles)


def test_fit_and_apply_reject_freeze_odds_below_the_first_band() -> None:
    with pytest.raises(ValueError, match="below the first odds-band"):
        fit_all_correction(
            [0.9],
            [1.0],
            bands=[1.0, 2.0],
            quantiles=[0.5],
            min_hits=1,
        )

    correction = fit_all_correction(
        [1.0],
        [1.0],
        bands=[1.0],
        quantiles=[0.5],
        min_hits=1,
    )
    with pytest.raises(ValueError, match="below the first odds-band"):
        correction.estimate(0.9)
