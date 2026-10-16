"""Verify declarative registrations reach audit, generation and saved contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from features.catalog.loader import load_feature_definitions
from features.catalog.registry import FeatureRegistry, create_feature_registry
from features.contracts.types import FeatureBatchInput, FeatureBuildError, FeatureGroupInput
from features.explanatory_variables import audit_feature_inputs, build_explanatory_variables
from features.jockey_combination import (
    JockeyCombinationBuilder,
    JockeyCombinationInput,
    build_jockey_combination,
)
from features.tables.build import build_feature_table
from features.tables.parquet import read_feature_table, write_feature_table
from features.validation.table import validate_feature_table
from main import app
from make_datamart.builder import join_feature_tables
from make_datamart.tables.parquet import read_datamart, write_datamart

CONFIG = Path(__file__).resolve().parents[2] / "config/features.toml"
FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)


def _custom_config(tmp_path: Path) -> Path:
    definitions = load_feature_definitions(CONFIG)
    definitions = tuple(
        replace(entry, feature_id=f"custom-{entry.name}") for entry in reversed(definitions)
    )
    path = tmp_path / "features.toml"
    path.write_text(
        "\n\n".join(
            f'[[features]]\nid = "{entry.feature_id}"\nname = "{entry.name}"'
            for entry in definitions
        ),
        encoding="utf-8",
    )
    return path


def _record(registry: FeatureRegistry, horse_id: str = "horse-1") -> FeatureBatchInput:
    return FeatureBatchInput(
        "race-1",
        horse_id,
        FREEZE_AT,
        {
            entry.definition.feature_id: FeatureGroupInput(
                feature_id=entry.definition.feature_id,
                values={
                    "market_win_odds"
                    if entry.definition.name == "market_characteristics"
                    else "past_value": 2.0
                },
                available_at=AVAILABLE_AT,
                source_event_at=AVAILABLE_AT,
                source_scope="historical",
                status="confirmed",
                source_race_ids=("past-race",),
                contains_target_result=False,
                contains_future_data=False,
            )
            for entry in registry.features
        },
    )


def test_default_catalog_preserves_existing_ids_and_order() -> None:
    registry = create_feature_registry(load_feature_definitions(CONFIG))

    assert len(registry.features) == 21
    assert registry.feature_ids == tuple(f"F{index:02d}" for index in range(1, 22))
    assert registry.by_id("F01").definition.name == "recent_performance"
    assert registry.by_name("jockey_combination").definition.feature_id == "F11"
    assert registry.by_id("F21").definition.name == "opponent_pagerank"
    with pytest.raises(FrozenInstanceError):
        registry.features[0].definition.__setattr__("feature_id", "changed")


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "features list"),
        ("features = []", "non-empty list"),
        ("features = 'invalid'", "non-empty list"),
        ("features = [1]", "requires only id and name"),
        ('[[features]]\nid="A"', "requires only id and name"),
        (
            '[[features]]\nid="A"\nname="recent_performance"\nmodule="arbitrary"',
            "requires only id and name",
        ),
        ('[[features]]\nid=1\nname="recent_performance"', "non-empty trimmed string"),
        ('[[features]]\nid=" "\nname="recent_performance"', "non-empty trimmed string"),
        ('[[features]]\nid=" A "\nname="recent_performance"', "non-empty trimmed string"),
        ('[[features]]\nid="A"\nname=1', "snake_case"),
        ('[[features]]\nid="A"\nname=""', "snake_case"),
        ('[[features]]\nid="A"\nname="arbitrary.module"', "snake_case"),
        (
            '[[features]]\nid="A"\nname="one"\n[[features]]\nid="A"\nname="two"',
            "duplicate feature id",
        ),
        (
            '[[features]]\nid="A"\nname="one"\n[[features]]\nid="B"\nname="one"',
            "duplicate feature name",
        ),
        ("features=[]\nextra=1", "only a features list"),
    ],
)
def test_invalid_catalog_is_rejected(tmp_path: Path, text: str, reason: str) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        load_feature_definitions(path)


def test_catalog_rejects_missing_file_and_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_feature_definitions(tmp_path / "missing.toml")
    path = tmp_path / "broken.toml"
    path.write_text("[[features", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected"):
        load_feature_definitions(path)


def test_registry_requires_every_implementation_and_rejects_unknown_names() -> None:
    definitions = load_feature_definitions(CONFIG)
    with pytest.raises(ValueError, match=r"missing=.*recent_performance"):
        create_feature_registry(definitions[1:])
    with pytest.raises(ValueError, match=r"unknown=.*unregistered"):
        create_feature_registry((replace(definitions[0], name="unregistered"), *definitions[1:]))


def test_custom_ids_and_order_reach_individual_and_batch_generation(tmp_path: Path) -> None:
    registry = create_feature_registry(load_feature_definitions(_custom_config(tmp_path)))
    record = _record(registry)
    result = build_explanatory_variables([record], registry=registry)
    registration = registry.by_name("jockey_combination")
    feature_id = registration.definition.feature_id
    group = record.groups[feature_id]
    individual = registration.input_type(
        feature_id=feature_id,
        race_id=record.race_id,
        horse_id=record.horse_id,
        freeze_at=record.freeze_at,
        values=group.values,
        available_at=group.available_at,
        source_event_at=group.source_event_at,
        source_scope=group.source_scope,
        status=group.status,
        source_race_ids=group.source_race_ids,
        contains_target_result=False,
        contains_future_data=False,
    )
    rows = registration.builder_type(registration.definition).build_rows([individual])
    assert isinstance(individual, JockeyCombinationInput)
    table = build_jockey_combination(
        [individual], definition=registration.definition, column_types={"past_value": pa.float64()}
    )

    assert tuple(result.rows) == registry.feature_ids
    combined_table = build_feature_table(
        registration.definition.name,
        list(result.rows[feature_id]),
        column_types={"past_value": pa.float64()},
        registered_names=registry.names,
    )
    individual_table = build_feature_table(
        registration.definition.name,
        rows,
        column_types={"past_value": pa.float64()},
        registered_names=registry.names,
    )
    assert combined_table.equals(individual_table, check_metadata=True)
    assert individual_table.equals(table, check_metadata=True)
    assert tuple(result.inputs[0].groups) == registry.feature_ids
    assert audit_feature_inputs([record], registry=registry).valid
    assert table["past_value"].to_pylist() == [2.0]
    path = tmp_path / "feature.parquet"
    write_feature_table(table, path, registered_names=registry.names)
    assert read_feature_table(path, registered_names=registry.names).equals(
        table, check_metadata=True
    )
    datamart = join_feature_tables([table], registered_names=registry.names)
    datamart_path = tmp_path / "datamart.parquet"
    write_datamart(datamart, datamart_path, registered_names=registry.names)
    assert read_datamart(datamart_path, registered_names=registry.names).equals(
        datamart, check_metadata=True
    )


def test_custom_market_id_reaches_feature_owned_audits(tmp_path: Path) -> None:
    registry = create_feature_registry(load_feature_definitions(_custom_config(tmp_path)))
    feature_id = registry.by_name("market_characteristics").definition.feature_id
    first = _record(registry)
    second = _record(registry, "horse-2")
    first = replace(
        first,
        groups={
            **first.groups,
            feature_id: replace(first.groups[feature_id], values={"ticket_total_tansyo": 100}),
        },
    )
    second = replace(
        second,
        groups={
            **second.groups,
            feature_id: replace(second.groups[feature_id], values={"ticket_total_tansyo": 200}),
        },
    )
    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([first, second], registry=registry)
    assert any(
        violation.feature_id == feature_id and "ticket total" in violation.reason
        for violation in error.value.audit.violations
    )


def test_individual_builder_rejects_wrong_definition() -> None:
    registry = create_feature_registry(load_feature_definitions(CONFIG))
    with pytest.raises(ValueError, match="match the builder"):
        JockeyCombinationBuilder(registry.by_name("recent_performance").definition)


def test_saved_unknown_names_are_rejected_even_when_metadata_is_consistent(tmp_path: Path) -> None:
    registry = create_feature_registry(load_feature_definitions(CONFIG))
    registration = registry.by_name("jockey_combination")
    record = _record(registry)
    rows = build_explanatory_variables([record], registry=registry).rows[
        registration.definition.feature_id
    ]
    table = build_feature_table(
        "unknown_feature",
        list(rows),
        column_types={"past_value": pa.float64()},
        registered_names=("unknown_feature",),
    )
    path = tmp_path / "unknown.parquet"
    pq.write_table(table, path)
    with pytest.raises(ValueError, match="unsupported feature_name"):
        read_feature_table(path, registered_names=registry.names)
    with pytest.raises(ValueError, match="unsupported feature_name"):
        write_feature_table(table, tmp_path / "rejected.parquet", registered_names=registry.names)
    with pytest.raises(ValueError, match="unsupported feature_name"):
        validate_feature_table(table, registered_names=registry.names)
    datamart = join_feature_tables([table], registered_names=("unknown_feature",))
    pq.write_table(datamart, tmp_path / "unknown-datamart.parquet")
    with pytest.raises(ValueError, match="feature_names metadata is invalid"):
        read_datamart(tmp_path / "unknown-datamart.parquet", registered_names=registry.names)
    rejected_path = tmp_path / "rejected-datamart.parquet"
    with pytest.raises(ValueError, match="feature_names metadata is invalid"):
        write_datamart(datamart, rejected_path, registered_names=registry.names)
    assert not rejected_path.exists()


def test_catalog_import_does_not_load_individual_implementations() -> None:
    src_dir = CONFIG.parent.parent / "src"
    script = f"""import sys
sys.path.insert(0, {str(src_dir)!r})
import features.catalog.loader
assert 'features.catalog.registry' not in sys.modules
assert 'features.recent_performance' not in sys.modules
assert 'features.market_characteristics' not in sys.modules
assert 'features.odds_ratio' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("command", [[], ["model"], ["model", "explanatory-variables"]])
def test_help_never_loads_feature_config(command: list[str]) -> None:
    with patch(
        "main.load_feature_definitions",
        side_effect=AssertionError("unexpected config read"),
    ) as loader:
        result = CliRunner().invoke(app, [*command, "--help"])
    assert result.exit_code == 0
    loader.assert_not_called()


def test_importing_entry_point_never_reads_feature_config() -> None:
    src_dir = CONFIG.parent.parent / "src"
    script = f"""import sys
sys.path.insert(0, {str(src_dir)!r})
from unittest.mock import patch
with patch('features.catalog.loader.load_feature_definitions', side_effect=AssertionError('unexpected config read')) as loader:
    import main
    loader.assert_not_called()
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_cli_reads_custom_catalog_once_and_preserves_output_order(tmp_path: Path) -> None:
    config = _custom_config(tmp_path)
    registry = create_feature_registry(load_feature_definitions(config))
    record = _record(registry)
    input_path = tmp_path / "inputs.json"
    output_path = tmp_path / "outputs.json"
    input_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "race_id": record.race_id,
                        "horse_id": record.horse_id,
                        "freeze_at": FREEZE_AT.isoformat(),
                        "groups": {
                            feature_id: {
                                "values": dict(group.values),
                                "available_at": AVAILABLE_AT.isoformat(),
                                "source_event_at": AVAILABLE_AT.isoformat(),
                                "source_scope": "historical",
                                "status": "confirmed",
                                "source_race_ids": ["past-race"],
                                "contains_target_result": False,
                                "contains_future_data": False,
                            }
                            for feature_id, group in record.groups.items()
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with patch("main.load_feature_definitions", wraps=load_feature_definitions) as loader:
        result = CliRunner().invoke(
            app,
            [
                "model",
                "explanatory-variables",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--features-config",
                str(config),
            ],
        )
    assert result.exit_code == 0, result.exception
    loader.assert_called_once_with(config)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["feature_ids"] == list(registry.feature_ids)
    assert tuple(payload["records"][0]["groups"]) == registry.feature_ids
    assert payload["audit"]["valid"]


def test_cli_reports_config_failure_with_input_error_and_exit_one(tmp_path: Path) -> None:
    output = tmp_path / "error.json"
    result = CliRunner().invoke(
        app,
        [
            "model",
            "explanatory-variables",
            "--input",
            str(tmp_path / "input.json"),
            "--output",
            str(output),
            "--features-config",
            str(tmp_path / "missing.toml"),
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["error"]["type"] == "input"
    assert "missing.toml" in payload["error"]["message"]
