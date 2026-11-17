"""Tests for the ADR-044 width-banded place correction (plan AC-3)."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from models.market.final_odds_correction import fit_all_correction, fit_graded_correction
from models.market.place_width_correction import (
    PlaceWidthObservation,
    fit_place_width_correction,
    place_width,
    recover_place_high,
    validate_width_bands,
    width_band,
)

WIDTH_BANDS = (1.0, 1.5, 2.0, 3.0, 5.0)
EDGES = validate_width_bands(WIDTH_BANDS)


@pytest.mark.parametrize(
    ("low", "high", "band"),
    [(1.0, 1.0, 0), (1.0, 1.4, 0), (1.0, 1.5, 1), (1.2, 2.4, 2), (1.2, 3.6, 3), (1.1, 5.5, 4)],
)
def test_widths_on_band_edges_fall_in_the_upper_band(low: float, high: float, band: int) -> None:
    width = place_width(low, high)

    assert width is not None
    assert width_band(width, EDGES) == band


@pytest.mark.parametrize(("low", "high"), [(1.0, 1.0), (1.2, 2.4), (1.2, 3.6), (2.3, 7.9)])
def test_a_hit_recovers_the_same_width_as_its_quote(low: float, high: float) -> None:
    mid = math.sqrt(low * high)

    assert recover_place_high(low, mid) == high
    assert place_width(low, recover_place_high(low, mid)) == place_width(low, high)


def test_a_high_bound_below_the_low_bound_has_no_width() -> None:
    assert place_width(2.0, 1.9) is None
    assert place_width(1.0, 1.0) == Fraction(1)


def test_width_bands_are_validated() -> None:
    assert (Fraction(1), Fraction(3, 2), Fraction(2), Fraction(3), Fraction(5)) == EDGES
    with pytest.raises(ValueError, match=r"start at 1\.0"):
        validate_width_bands([1.2, 2.0])
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_width_bands([1.0, 2.0, 2.0])
    with pytest.raises(ValueError, match="finite numbers"):
        validate_width_bands([])


def _observations(
    width: Fraction, ratio: float, count: int, prefix: str = "2020"
) -> list[PlaceWidthObservation]:
    return [
        PlaceWidthObservation(f"{prefix}0101050101{index:02d}", odds, odds * ratio, width)
        for index in range(count)
        for odds in (1.5, 3.0)
    ]


def test_each_width_band_uses_the_existing_graded_correction_of_its_own_hits() -> None:
    narrow = _observations(Fraction(1), 1.1, 3)
    wide = _observations(Fraction(4), 0.7, 3)
    graded = {narrow[0].race_id, wide[0].race_id}

    correction = fit_place_width_correction(
        [*narrow, *wide],
        width_bands=WIDTH_BANDS,
        place_bands=(1.0, 2.0),
        quantiles=(0.5,),
        min_hits=2,
        shrinkage_k=1,
        graded_race_ids=graded,
    )

    for hits, width in ((narrow, Fraction(1)), (wide, Fraction(4))):
        all_correction = fit_all_correction(
            [item.freeze_odds for item in hits],
            [item.final_odds for item in hits],
            bands=(1.0, 2.0),
            quantiles=(0.5,),
            min_hits=2,
        )
        graded_hits = [item for item in hits if item.race_id in graded]
        expected = fit_graded_correction(
            [item.freeze_odds for item in graded_hits],
            [item.final_odds for item in graded_hits],
            bands=(1.0, 2.0),
            quantiles=(0.5,),
            min_hits=2,
            shrinkage_k=1,
            all_correction=all_correction,
        )
        for odds in (1.4, 2.5, 4.0):
            assert correction.estimate(odds, width) == pytest.approx(
                expected.estimate(odds).final_odds
            )
    assert correction.groups == ((0, 1, 2), (3, 4))


def test_undersized_width_bands_merge_downward_and_the_first_band_upward() -> None:
    observations = [
        *_observations(Fraction(1), 1.0, 1),  # band 0: 2 hits
        *_observations(Fraction(7, 4), 1.0, 5),  # band 1: 10 hits
        *_observations(Fraction(5, 2), 1.0, 1),  # band 2: 2 hits
        *_observations(Fraction(4), 1.0, 5),  # band 3: 10 hits
        *_observations(Fraction(6), 1.0, 5),  # band 4: 10 hits
    ]

    correction = fit_place_width_correction(
        observations,
        width_bands=WIDTH_BANDS,
        place_bands=(1.0,),
        quantiles=(0.5,),
        min_hits=5,
        shrinkage_k=0,
        graded_race_ids=(),
    )

    assert correction.groups == ((0, 1, 2), (3,), (4,))
    assert correction.hit_counts == (14, 10, 10)


def test_no_observations_are_rejected() -> None:
    with pytest.raises(ValueError, match="no place_mid training hits"):
        fit_place_width_correction(
            [],
            width_bands=WIDTH_BANDS,
            place_bands=(1.0,),
            quantiles=(0.5,),
            min_hits=1,
            shrinkage_k=0,
            graded_race_ids=(),
        )
