"""Tests for feature-specific intermediate tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pytest

from features.feature_table import read_feature_table, validate_feature_table, write_feature_table
from features.odds_ratio import OddsRatioInput, build_odds_ratio
from features.pedigree import PedigreeInput, build_pedigree
from features.previous_race_result import PreviousRaceResultInput, build_previous_race_result

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)


def test_feature_builders_return_the_common_schema_and_keep_values() -> None:
    previous = build_previous_race_result(
        [
            PreviousRaceResultInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2),
            PreviousRaceResultInput("race-1", "horse-2", FREEZE_AT, None, None),
        ]
    )
    odds = build_odds_ratio(
        [OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0)]
    )
    pedigree = build_pedigree(
        [PedigreeInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, "Sire A", "Dam Sire B")]
    )

    assert previous.column_names == [
        "race_id",
        "horse_id",
        "freeze_at",
        "available_at",
        "previous_race_finish_position",
    ]
    assert previous["previous_race_finish_position"].to_pylist() == [2, None]
    assert odds["odds_ratio"].to_pylist() == [0.5]
    assert pedigree["sire"].to_pylist() == ["Sire A"]
    assert pedigree["broodmare_sire"].to_pylist() == ["Dam Sire B"]
    assert pedigree.schema.field("sire").type == pa.string()


@pytest.mark.parametrize(
    ("odds", "reference_odds"),
    [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0), (1.0, -1.0)],
)
def test_odds_ratio_rejects_non_positive_values(odds: float, reference_odds: float) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        build_odds_ratio(
            [OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, odds, reference_odds)]
        )


def test_odds_ratio_keeps_missing_input_as_null() -> None:
    table = build_odds_ratio([OddsRatioInput("race-1", "horse-1", FREEZE_AT, None, None, 2.0)])

    assert table["odds_ratio"].to_pylist() == [None]


def test_odds_ratio_normalizes_nan_missing_input_to_null() -> None:
    table = build_odds_ratio(
        [OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, float("nan"), 2.0)]
    )

    assert table["odds_ratio"].to_pylist() == [None]


def test_odds_ratio_rejects_non_finite_ratio() -> None:
    with pytest.raises(ValueError, match="odds_ratio must be finite"):
        build_odds_ratio(
            [OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 1e308, 1e-308)]
        )


def test_feature_table_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate feature key"):
        build_previous_race_result(
            [
                PreviousRaceResultInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 1),
                PreviousRaceResultInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2),
            ]
        )


def test_feature_table_rejects_invalid_feature_name_and_columns() -> None:
    table = build_previous_race_result(
        [PreviousRaceResultInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 1)]
    )

    with pytest.raises(ValueError, match="feature_name"):
        validate_feature_table(table, "unknown")

    invalid_columns = table.select(["race_id", "horse_id", "freeze_at", "available_at", "horse_id"])
    with pytest.raises(ValueError, match="columns"):
        validate_feature_table(invalid_columns, "previous_race_result")


def test_feature_table_round_trips_through_parquet(tmp_path: Path) -> None:
    table = build_pedigree(
        [PedigreeInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, "Sire A", None)]
    )
    path = tmp_path / "pedigree.parquet"

    write_feature_table(table, path)
    loaded = read_feature_table(path)

    assert loaded.equals(table)
    assert loaded.schema.metadata == table.schema.metadata


def test_feature_table_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_previous_race_result(
            [PreviousRaceResultInput("race-1", "horse-1", datetime(2026, 1, 1, 12), None, None)]
        )
