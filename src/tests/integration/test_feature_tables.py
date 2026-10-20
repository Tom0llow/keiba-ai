"""Tests for feature-specific intermediate tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from make_features.pedigree import PedigreeInput, build_pedigree
from make_features.tables.parquet import read_feature_table, write_feature_table

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)


AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)


def test_feature_table_round_trips_through_parquet(tmp_path: Path) -> None:
    table = build_pedigree(
        [PedigreeInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, "Sire A", None)]
    )
    path = tmp_path / "pedigree.parquet"

    write_feature_table(table, path)
    loaded = read_feature_table(path)

    assert loaded.equals(table)
    assert loaded.schema.metadata == table.schema.metadata
