"""Tests for ordered datamart joins of intermediate feature tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pyarrow as pa
import pytest
from typer.testing import CliRunner

from main import app
from make_datamart.builder import join_feature_tables
from make_features.contracts.rows import FeatureTableRow
from make_features.odds_ratio import OddsRatioInput, build_odds_ratio
from make_features.previous_race_result import PreviousRaceResultInput, build_previous_race_result
from make_features.tables.build import build_feature_table

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)


AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)


def test_datamart_cli_help_does_not_read_catalog_or_parquet() -> None:
    with (
        patch(
            "cli.make_datamart.load_feature_definitions",
            side_effect=AssertionError("catalog read"),
        ) as catalog,
        patch(
            "cli.make_datamart.make_datamart", side_effect=AssertionError("Parquet read")
        ) as build,
    ):
        result = CliRunner().invoke(app, ["datamart", "build", "--help"])
    assert result.exit_code == 0
    catalog.assert_not_called()
    build.assert_not_called()


def _base_table() -> pa.Table:
    return build_previous_race_result(
        [
            PreviousRaceResultInput("race-2", "horse-2", FREEZE_AT, AVAILABLE_AT, 4),
            PreviousRaceResultInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2),
        ]
    )


def test_datamart_rejects_extra_key() -> None:
    extra = build_odds_ratio(
        [
            OddsRatioInput("race-2", "horse-2", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0),
            OddsRatioInput("race-3", "horse-3", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0),
        ]
    )

    with pytest.raises(ValueError, match="extra key"):
        join_feature_tables([_base_table(), extra])


def test_datamart_rejects_freeze_at_mismatch_for_same_key() -> None:
    mismatched = build_odds_ratio(
        [
            OddsRatioInput(
                "race-1",
                "horse-1",
                FREEZE_AT + timedelta(minutes=1),
                AVAILABLE_AT,
                2.0,
                4.0,
            )
        ]
    )

    with pytest.raises(ValueError, match="freeze_at mismatch"):
        join_feature_tables([_base_table(), mismatched])


def test_datamart_rejects_duplicate_feature_name() -> None:
    with pytest.raises(ValueError, match="duplicate feature name"):
        join_feature_tables([_base_table(), _base_table()])


@pytest.mark.parametrize("first_column", ["past_value", "second_feature__available_at"])
def test_datamart_rejects_value_and_availability_column_collisions(first_column: str) -> None:
    names = ("first_feature", "second_feature")
    tables = [
        build_feature_table(
            name,
            [FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {column: 1})],
            column_types={column: pa.int64()},
            registered_names=names,
        )
        for name, column in zip(names, (first_column, "past_value"), strict=True)
    ]

    with pytest.raises(ValueError, match="feature column collision"):
        join_feature_tables(tables, registered_names=names)
