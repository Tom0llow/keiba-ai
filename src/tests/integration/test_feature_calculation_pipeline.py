"""Exercise Hydra, normalized files, all-group auditing and Parquet contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from hydra.errors import ConfigCompositionException
from omegaconf.errors import MissingMandatoryValue
from typer.testing import CliRunner

from configuration.feature_calculation import load_feature_calculation_config
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from main import app
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.explanatory_variables import build_explanatory_variables
from make_features.generation.calculate import calculate_features
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.observations import (
    calculation_payload,
    normalized_payload,
    parse_observation_inputs,
)
from make_features.tables.build import build_feature_table
from make_features.tables.parquet import read_feature_table, write_feature_table
from tests.observation_fixtures import (
    at,
    fixture_column_types,
    observations,
    parameters,
    race,
    result_runner,
)


def test_all_groups_preserve_field_shapes_dependencies_and_future_invariance() -> None:
    registry = create_feature_registry(load_feature_definitions("configs/features.toml"))
    source, p = observations(), parameters()
    result = calculate_features((source,), p, registry=registry)
    assert result.built.audit.valid
    assert result.built.audit.groups_checked == 84
    assert len(result.built.inputs) == 4
    for registration in registry.features:
        rows = result.built.rows[registration.definition.feature_id]
        assert len({tuple(row.values) for row in rows}) == 1
    for record, manifest in zip(result.built.inputs, result.manifests, strict=True):
        for feature_id, group in record.groups.items():
            dependencies = manifest[feature_id].dependencies
            assert source.card.race_id not in group.source_race_ids
            if group.available_at is not None:
                assert group.available_at == max(e.available_at for e in dependencies)
            assert group.source_event_at == max(e.event_at for e in dependencies)
            assert source.card.scheduled_start_at not in {e.event_at for e in dependencies}
    future = race(
        "future", 11, (result_runner("A", 1, 2.0, 1, 500.0), result_runner("B", 2, 3.0, 2, 500.0))
    )
    same_day = replace(future, race_id="same-day", started_at=at(10, 8))
    revised = replace(
        source.history[-1],
        evidence=replace(
            source.history[-1].evidence, version=2, published_at=at(11), received_at=at(11)
        ),
        runners=tuple(replace(r, elapsed_sec=999.0) for r in source.history[-1].runners),
    )
    workout = replace(
        source.workouts[0],
        evidence=replace(
            source.workouts[0].evidence, version=2, published_at=at(11), received_at=at(11)
        ),
    )
    pedigree = replace(
        source.pedigrees[0],
        sire="future-parent",
        evidence=replace(
            source.pedigrees[0].evidence, version=2, published_at=at(11), received_at=at(11)
        ),
    )
    changed = replace(
        source,
        history=(
            *source.history,
            future,
            same_day,
            replace(future, race_id=source.card.race_id),
            revised,
        ),
        workouts=(*source.workouts, workout),
        pedigrees=(*source.pedigrees, pedigree),
    )
    assert calculation_payload(
        calculate_features((changed,), p, registry=registry), feature_ids=registry.feature_ids
    ) == calculation_payload(result, feature_ids=registry.feature_ids)


def test_cli_calculates_evidence_json_and_reuses_all_existing_parquet_contracts(
    tmp_path: Path,
) -> None:
    source, p = observations(), parameters()
    inputs, output = tmp_path / "normalized.json", tmp_path / "calculated.json"
    write_json(inputs, {"schema_version": 1, "observations": [normalized_payload(source)]})
    config = tmp_path / "config"
    config.mkdir()
    (config / "calculate.yaml").write_text(
        json.dumps({"parameters": normalized_payload(p)}), encoding="utf-8"
    )
    completed = CliRunner().invoke(
        app,
        [
            "model",
            "calculate-features",
            "--input",
            str(inputs),
            "--output",
            str(output),
            "--config-dir",
            str(config),
        ],
    )
    assert completed.exit_code == 0, completed.output
    assert "4 rows across 21" in completed.output
    payload = read_json(output)
    assert payload["parameters"] == normalized_payload(p)
    assert isinstance(payload["dependencies"], list)
    assert parse_observation_inputs(read_json(inputs)) == (source,)
    records = parse_explanatory_inputs(payload)
    registry = create_feature_registry(load_feature_definitions("configs/features.toml"))
    result = calculate_features((source,), p, registry=registry)
    assert build_explanatory_variables(records, registry=registry).inputs == result.built.inputs
    for registration in registry.features:
        feature_id = registration.definition.feature_id
        rows = result.built.rows[feature_id]
        # Explicit fixture schemas cover every generated column, including all-null lags.
        column_types = fixture_column_types(registration.definition.name)
        assert set(column_types) == set(rows[0].values)
        table = build_feature_table(
            registration.definition.name,
            list(rows),
            column_types=column_types,
            registered_names=registry.names,
        )
        path = tmp_path / f"{feature_id}.parquet"
        write_feature_table(table, path, registered_names=registry.names)
        restored = read_feature_table(path, registered_names=registry.names)
        assert restored.equals(table, check_metadata=True)


def test_cli_rejects_raw_missing_coverage_and_output_overwrite(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "calculate.yaml").write_text(
        json.dumps({"parameters": normalized_payload(parameters())}), encoding="utf-8"
    )
    input_path, output = tmp_path / "input.json", tmp_path / "output.json"
    write_json(input_path, {"rows": []})
    arguments = [
        "model",
        "calculate-features",
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--config-dir",
        str(config),
    ]
    failed = CliRunner().invoke(app, arguments)
    assert failed.exit_code == 1
    assert "raw/Parquet" in failed.output
    assert not output.exists()
    source = replace(observations(), coverage=())
    write_json(input_path, {"schema_version": 1, "observations": [normalized_payload(source)]})
    failed = CliRunner().invoke(app, arguments)
    assert failed.exit_code == 1
    assert "coverage evidence is required" in failed.output
    assert not output.exists()
    write_json(output, {"keep": "existing artifact"})
    failed = CliRunner().invoke(app, arguments)
    assert failed.exit_code == 1
    assert read_json(output) == {"keep": "existing artifact"}
    same = arguments.copy()
    same[same.index("--output") + 1] = str(input_path)
    before = input_path.read_bytes()
    assert CliRunner().invoke(app, same).exit_code == 1
    assert input_path.read_bytes() == before


def test_hydra_requires_business_choices_and_rejects_unknown_override() -> None:
    with pytest.raises(MissingMandatoryValue, match="parameters"):
        load_feature_calculation_config(Path("configs/feature_calculation"))
    with pytest.raises(ConfigCompositionException, match="unknown_option"):
        load_feature_calculation_config(
            Path("configs/feature_calculation"), overrides=("parameters.unknown_option=1",)
        )


def test_empty_or_missing_sources_do_not_succeed_as_all_missing() -> None:
    registry = create_feature_registry(load_feature_definitions("configs/features.toml"))
    with pytest.raises(ValueError, match="at least one"):
        calculate_features((), parameters(), registry=registry)
    source = replace(observations(), markets=())
    with pytest.raises(ValueError, match="no received normalized observation"):
        calculate_features((source,), parameters(), registry=registry)
