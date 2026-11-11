"""Verify the closed numeric schema and reproducible semantic calculation identity."""

import copy
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from main import app
from models.dataset.calculated import (
    CalculationContract,
    closed_numeric_columns,
    resolve_numeric_column,
)
from models.dataset.rows import FeatureRow, FeatureValue
from models.dataset.schema import FeatureSchema, validate_feature_names
from models.dataset.validation import validate_feature_rows
from tests.model_projection_fixtures import SELECTED_COLUMNS
from tests.observation_fixtures import at, evidence, parameters


def test_calculated_contract_roundtrip_excludes_source_clock_and_normalizes_numbers() -> None:
    p = parameters()
    first = CalculationContract.create(p, SELECTED_COLUMNS)
    second = CalculationContract.create(
        replace(p, evidence=evidence("later-rules", at(2)), half_life_days=1), SELECTED_COLUMNS
    )
    assert first == second
    schema = FeatureSchema.calculated(first)
    assert FeatureSchema.from_metadata(schema.as_metadata()) == schema
    assert "evidence" not in str(first.as_metadata())
    assert len(schema.features) == 21
    assert schema.features[2].unit == "dimensionless"
    assert schema.features[19].unit == "dimensionless"
    velocity = FeatureSchema.calculated(
        CalculationContract.create(
            replace(p, metric="velocity_mps", metric_direction="higher"),
            ["same_gate_and_trainer_relative__same_gate_ability_diff"],
        )
    )
    assert velocity.features[0].unit == "dimensionless"
    assert CalculationContract.create(replace(p, count_window=2), SELECTED_COLUMNS) != first
    assert CalculationContract.create(p, SELECTED_COLUMNS[::-1]) != first


@pytest.mark.parametrize(
    "name",
    [
        "finish_position",
        "arbitrary_numeric",
        "recent_performance__past_small_sample",
        "basic_conditions_and_weight__sex",
        "recent_performance__past_finish_lag0",
        "recent_performance__past_finish_lag01",
        "recent_performance__past_finish_lag5",
        "recent_stability__past_velocity_mps_mean",
        "market_characteristics__final_odds",
    ],
)
def test_unapproved_result_categorical_and_unbounded_lag_columns_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="allow-list"):
        CalculationContract.create(parameters(), [name])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit", "wrong"),
        ("generation_rule", "unchecked"),
        ("missing_value_policy", "fill_zero"),
        ("result_derived", True),
    ],
)
def test_schema_rejects_modified_semantics(field: str, value: object) -> None:
    schema = FeatureSchema.calculated(CalculationContract.create(parameters(), SELECTED_COLUMNS))
    metadata = schema.as_metadata()
    cast(list[dict[str, object]], metadata["features"])[0][field] = value
    with pytest.raises(ValueError, match=r"specifications|policy|result-derived"):
        FeatureSchema.from_metadata(metadata)


def test_hash_parameters_order_and_schema_id_are_bound() -> None:
    schema = FeatureSchema.calculated(CalculationContract.create(parameters(), SELECTED_COLUMNS))
    metadata = schema.as_metadata()
    modified = copy.deepcopy(metadata)
    cast(dict[str, object], modified["calculation_contract"])["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        FeatureSchema.from_metadata(modified)
    metadata["schema_id"] = "unbound"
    with pytest.raises(ValueError, match="schema_id"):
        FeatureSchema.from_metadata(metadata)
    contract = schema.calculation_contract
    assert contract is not None
    settings = contract.settings
    cast(dict[str, object], settings["parameters"])["days_window"] = True
    with pytest.raises(ValueError, match="normalized type"):
        CalculationContract.from_metadata({"settings": settings, "sha256": contract.sha256})
    with pytest.raises(ValueError, match=r"reserved|allow-list"):
        FeatureSchema.from_names(SELECTED_COLUMNS, schema_id=schema.schema_id)
    with pytest.raises(ValueError, match=r"reserved|allow-list"):
        validate_feature_names(SELECTED_COLUMNS)


@pytest.mark.parametrize("value", [True, "1"])
def test_numeric_calculated_rows_require_a_verified_schema_and_reject_scalar_encoding(
    value: object,
) -> None:
    schema = FeatureSchema.calculated(
        CalculationContract.create(parameters(), SELECTED_COLUMNS[:1])
    )
    row = FeatureRow("r", "h", {SELECTED_COLUMNS[0]: cast(FeatureValue, value)})
    with pytest.raises(ValueError, match=r"reserved|allow-list"):
        validate_feature_rows((row,), schema.feature_names)
    with pytest.raises(TypeError, match="numeric"):
        validate_feature_rows((row,), schema.feature_names, feature_schema=schema)


def test_old_schema_metadata_remains_unchanged() -> None:
    schema = FeatureSchema.from_names(("ability", "historical_odds"), schema_id="legacy")
    assert "calculation_contract" not in schema.as_metadata()
    assert FeatureSchema.from_metadata(schema.as_metadata()) == schema


def test_closed_numeric_columns_enumerate_every_dynamic_family_in_contract_order() -> None:
    p = parameters()
    semantic = CalculationContract.create(p, SELECTED_COLUMNS).settings["parameters"]
    assert isinstance(semantic, dict)
    columns = closed_numeric_columns(semantic)
    assert len(columns) == 36
    assert [column.name for column in columns[-16:-12]] == [
        f"recent_performance__past_finish_lag{lag}" for lag in range(1, 5)
    ]
    assert columns[18].name == "recent_stability__past_elapsed_sec_mean"
    assert columns[19].name == "within_race_relative__relative_elapsed_sec_rank"
    assert all(resolve_numeric_column(column.name, semantic) == column for column in columns)


_METRIC_UNITS = {
    "elapsed_sec": "seconds",
    "velocity_mps": "metres_per_second",
    "last3f_sec": "seconds",
    "finish_relative": "fraction",
    "condition_time_advantage": "dimensionless",
}
_LAG_FAMILIES = (
    "recent_performance__past_finish",
    "past_racing_ability__past_velocity_mps",
    "running_style_and_position__past_corner4_relative",
    "past_lap_and_running_style__past_pace_velocity_gap_mps",
)


@pytest.mark.parametrize("lag_count", [1, 2, 3])
@pytest.mark.parametrize("metric", sorted(_METRIC_UNITS))
def test_closed_numeric_columns_follow_lag_count_and_metric(lag_count: int, metric: str) -> None:
    columns = closed_numeric_columns({"metric": metric, "lag_count": lag_count})
    names = [column.name for column in columns]
    # 18 fixed columns, two metric-dependent columns, then lag_count per lag family.
    assert len(columns) == 18 + 2 + 4 * lag_count
    assert names[18] == f"recent_stability__past_{metric}_mean"
    assert names[19] == f"within_race_relative__relative_{metric}_rank"
    assert columns[18].unit == _METRIC_UNITS[metric]
    assert columns[19].unit == "rank"
    assert names[20:] == [
        f"{family}_lag{lag}" for family in _LAG_FAMILIES for lag in range(1, lag_count + 1)
    ]
    assert len(set(names)) == len(names)
    settings = {"metric": metric, "lag_count": lag_count}
    assert all(
        resolve_numeric_column(name, settings) == column
        for name, column in zip(names, columns, strict=True)
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"metric": "unknown_metric", "lag_count": 4},
        {"metric": "elapsed_sec", "lag_count": 0},
        {"metric": "elapsed_sec", "lag_count": True},
        {"metric": "elapsed_sec", "lag_count": "4"},
    ],
)
def test_closed_numeric_columns_reject_unsupported_metric_or_lag_count(
    settings: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="supported metric and positive lag_count"):
        closed_numeric_columns(settings)


def test_prepare_cli_rejects_a_dangling_symlink_before_loading_or_writing() -> None:
    with (
        patch.object(Path, "exists", return_value=False),
        patch.object(Path, "is_symlink", return_value=True),
        patch("cli.model_projection.read_json") as reader,
        patch("cli.model_projection.write_json") as writer,
    ):
        result = CliRunner().invoke(
            app,
            ["model", "prepare-input", "--input", "input.json", "--output", "dangling-link.json"],
        )
    assert result.exit_code == 1
    assert "new path" in result.output
    reader.assert_not_called()
    writer.assert_not_called()
