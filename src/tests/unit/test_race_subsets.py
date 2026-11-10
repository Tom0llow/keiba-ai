"""Tests for fixed-snapshot race subset classification."""

from __future__ import annotations

import pytest

from models.serialization.race_subsets import (
    JRA_FLAT_GRADED_STAKES_V1,
    classify_nl_ra_race_rows,
)


def test_flat_graded_subset_selects_only_grades_a_through_c_on_flat_tracks() -> None:
    rows = [
        _row("01", grade="A", track="10"),
        _row("02", grade="B", track="17"),
        _row("03", grade="C", track="24"),
        _row("04", grade="D", track="10"),
        _row("05", grade="L", track="10"),
        _row("06", grade="E", track="10"),
        _row("07", grade="", track="10"),
        _row("08", grade="A", track="51"),
        _row("09", grade="F", track="52"),
        _row("10", grade="G", track="53"),
        _row("11", grade="H", track="59"),
        _row("12", grade=None, track="10"),
        _row("13", grade="A", track=None),
    ]

    result = classify_nl_ra_race_rows(rows)

    assert result.subsets == {
        JRA_FLAT_GRADED_STAKES_V1: frozenset(
            {"2024010101010101", "2024010101010102", "2024010101010103"}
        )
    }
    assert result.race_ids == frozenset(f"20240101010101{race:02d}" for race in range(1, 14))


def test_race_subsets_reject_duplicate_and_invalid_race_keys() -> None:
    duplicate = _row("01", grade="A", track="10")

    with pytest.raises(ValueError, match="duplicate race_id"):
        classify_nl_ra_race_rows([duplicate, duplicate])
    with pytest.raises(ValueError, match="16-digit"):
        classify_nl_ra_race_rows([_row("1", grade="A", track="10")])


def test_race_subsets_reject_missing_code_columns() -> None:
    row = _row("01", grade="A", track="10")
    del row["TrackCD"]

    with pytest.raises(ValueError, match="TrackCD"):
        classify_nl_ra_race_rows([row])


def _row(race: str, *, grade: str | None, track: str | None) -> dict[str, object]:
    return {
        "idYear": "2024",
        "idMonthDay": "0101",
        "idJyoCD": "01",
        "idKaiji": "01",
        "idNichiji": "01",
        "idRaceNum": race,
        "GradeCD": grade,
        "TrackCD": track,
    }
