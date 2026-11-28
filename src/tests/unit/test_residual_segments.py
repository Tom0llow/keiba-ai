"""Test fixed Plackett--Luce residual-segment classification."""

from __future__ import annotations

import numpy as np

from models.serialization.residual_segments import assign_residual_segments


def test_assign_residual_segments_honors_track_distance_position_age_and_prior_boundaries() -> None:
    assignments = assign_residual_segments(
        track_codes=["23", "23", "24", "24", "10", "22", "51", "10", "10"],
        distances_m=[1400, 1400, 1401, 1401, 1200, 1800, 1200, 1200, 1200],
        horse_numbers=[2, 5, 2, 5, 2, 5, 1, 3, 4],
        field_sizes=[6, 6, 6, 6, 6, 6, 3, 6, 6],
        ages=[2, 3, 4, 5, 6, 7, 8, 7, 4],
        prior_finish_positions=[1, 1, 2, 5, 2, 5, np.nan, 1, 6],
        prior_signed_gap_seconds=[-0.2, -0.25, 0.1, 0.1, 0.2, 0.0, np.nan, -0.3, 0.0],
    )

    assert assignments.unavailable == {}
    assert np.flatnonzero(assignments.member_masks["dirt_le1400_inner"]).tolist() == [0]
    assert np.flatnonzero(assignments.member_masks["dirt_le1400_outer"]).tolist() == [1]
    assert np.flatnonzero(assignments.member_masks["dirt_gt1400_inner"]).tolist() == [2]
    assert np.flatnonzero(assignments.member_masks["dirt_gt1400_outer"]).tolist() == [3]
    assert np.flatnonzero(assignments.member_masks["turf_inner"]).tolist() == [4]
    assert np.flatnonzero(assignments.member_masks["turf_outer"]).tolist() == [5]
    assert not assignments.member_masks["turf_outer"][8]
    assert np.flatnonzero(assignments.member_masks["age_7_plus"]).tolist() == [5, 6, 7]
    assert np.flatnonzero(assignments.member_masks["prior_win_margin_ge_0_3s"]).tolist() == [1, 7]
    assert np.flatnonzero(assignments.member_masks["prior_2to5_within_0_1s"]).tolist() == [2, 3, 5]


def test_assign_residual_segments_marks_only_signed_gap_segments_unavailable() -> None:
    assignments = assign_residual_segments(
        track_codes=["23", "10"],
        distances_m=[1200, 1600],
        horse_numbers=[1, 3],
        field_sizes=[3, 3],
        ages=[3, 7],
        prior_finish_positions=[1, 2],
        prior_signed_gap_seconds=None,
    )

    assert set(assignments.unavailable) == {
        "prior_win_margin_ge_0_3s",
        "prior_2to5_within_0_1s",
    }
    assert "dirt_le1400_inner" in assignments.member_masks
    assert "age_7_plus" in assignments.member_masks
