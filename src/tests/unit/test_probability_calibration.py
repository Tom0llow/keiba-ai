"""Tests for top-three Plackett--Luce temperature calibration."""

from __future__ import annotations

import numpy as np
import pytest

from models.probability.calibration import calibrate_temperature
from models.probability.plackett_luce import RaceLayout


def _sample_positions(
    scores: np.ndarray,
    layout: RaceLayout,
    temperature: float,
    seed: int,
) -> np.ndarray:
    """Draw complete finishing orders from independent PL races."""
    generator = np.random.default_rng(seed)
    positions = np.empty(layout.row_count, dtype=np.int64)
    for start, stop in zip(layout.offsets[:-1], layout.offsets[1:], strict=True):
        remaining = np.arange(start, stop, dtype=np.int64)
        for position in range(1, len(remaining) + 1):
            scaled = scores[remaining] / temperature
            weights = np.exp(scaled - scaled.max())
            winner_offset = generator.choice(len(remaining), p=weights / weights.sum())
            winner = remaining[winner_offset]
            positions[winner] = position
            remaining = np.delete(remaining, winner_offset)
    return positions


def test_calibrate_temperature_recovers_synthetic_pl_temperature_deterministically() -> None:
    generator = np.random.default_rng(20261109)
    layout = RaceLayout((5,) * 1_000)
    scores = generator.normal(size=layout.row_count)
    expected_temperature = 1.7
    positions = _sample_positions(scores, layout, expected_temperature, seed=17)

    result = calibrate_temperature(scores, positions, layout)
    repeated = calibrate_temperature(scores, positions, layout)

    assert result.temperature == pytest.approx(expected_temperature, abs=0.2)
    assert result.calibrated_valid_nll <= result.raw_valid_nll
    assert not result.at_bound
    assert repeated == result


def test_calibrate_temperature_marks_an_out_of_range_optimum_at_the_bound() -> None:
    layout = RaceLayout((4,) * 20)
    scores = np.tile(np.array([3.0, 1.0, 0.0, -2.0]), layout.race_count)
    positions = np.tile(np.array([1, 2, 3, 4], dtype=np.int64), layout.race_count)

    result = calibrate_temperature(scores, positions, layout, temperature_bounds=(0.5, 2.0))

    assert result.at_bound
    assert result.temperature == pytest.approx(0.5, abs=1e-5)


def test_calibrate_temperature_rejects_invalid_search_settings() -> None:
    layout = RaceLayout((3,))
    scores = np.array([0.0, 0.5, -0.5])
    positions = np.array([1, 2, 3], dtype=np.int64)

    with pytest.raises(ValueError, match="strictly increasing"):
        calibrate_temperature(scores, positions, layout, temperature_bounds=(1.0, 1.0))
    with pytest.raises(ValueError, match="positive finite"):
        calibrate_temperature(scores, positions, layout, tolerance=0.0)
