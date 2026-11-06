"""Connect all 21 calculations to JSON, native LightGBM and exact MLflow versions."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from configuration.experiments import load_experiment_config
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from main import app
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.contracts.observations import ObservationInput
from make_features.contracts.types import FeatureDefinition
from make_features.generation.calculate import calculate_features
from make_features.serialization.observations import normalized_payload
from models.dataset.builder import build_features
from models.evaluation.walk_forward import WalkForwardConfig, make_walk_forward_folds
from models.experiments.inputs import read_experiment_input
from models.experiments.runner import run_experiment
from models.serialization.inputs import parse_feature_inputs
from models.serialization.projection import parse_label_sources, prepare_model_payload
from tests.model_projection_fixtures import SELECTED_COLUMNS, frozen_input, target_result
from tests.observation_fixtures import at, evidence, parameters

_ROOT = Path(__file__).resolve().parents[3]


def _prepare(
    days: tuple[int, ...],
    *,
    labeled: bool = True,
    sources: tuple[ObservationInput, ...] | None = None,
) -> dict[str, object]:
    registry = create_feature_registry(load_feature_definitions(_ROOT / "configs/features.toml"))
    calculated = calculate_features(
        sources or tuple(frozen_input(day) for day in days), parameters(), registry=registry
    )
    return prepare_model_payload(
        calculated,
        registry=registry,
        selected_columns=SELECTED_COLUMNS,
        results=tuple(target_result(day) for day in days) if labeled else None,
    )


def _sources_with_shared_result() -> tuple[ObservationInput, ...]:
    later = frozen_input(11)
    return (
        frozen_input(10),
        replace(later, history=(*later.history, target_result(10))),
    )


def _training(path: Path) -> dict[str, object]:
    return run_experiment(
        load_experiment_config(
            _ROOT / "configs/experiments",
            action="train",
            overrides=[
                f"data.input='{path.as_posix()}'",
                "model.parameters.n_estimators=2",
                "model.parameters.min_child_samples=1",
            ],
        )
    )


def test_calculated_inputs_require_label_audit_before_walk_forward_folds() -> None:
    schema, records = parse_feature_inputs(_prepare((10, 11, 12)))
    dataset = build_features(records, feature_schema=schema).dataset
    assert dataset is not None
    with pytest.raises(ValueError, match=r"label-use audit.*model train"):
        make_walk_forward_folds(dataset, WalkForwardConfig(1, 1, 1, 1))


@pytest.mark.parametrize("label_evidence", ["present", "missing", "late"])
def test_walk_forward_cli_rejects_calculated_inputs_before_training(
    label_evidence: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _prepare((10, 11, 12))
    if label_evidence == "missing":
        payload.pop("label_sources")
    elif label_evidence == "late":
        sources = cast(list[dict[str, object]], payload["label_sources"])
        result = cast(dict[str, object], sources[0]["result"])
        source = cast(dict[str, object], result["evidence"])
        source["published_at"] = source["received_at"] = at(20, 16).isoformat()
    input_path, output_path = tmp_path / "features.json", tmp_path / "evaluation.json"
    write_json(input_path, payload)
    trainer = Mock(side_effect=AssertionError("training must not start"))
    monkeypatch.setattr("models.evaluation.walk_forward.train_lambdarank", trainer)
    outcome = CliRunner().invoke(
        app,
        [
            "model",
            "walk-forward",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--min-train-races",
            "1",
            "--validation-races",
            "1",
            "--test-races",
            "1",
            "--step-races",
            "1",
        ],
    )
    trainer.assert_not_called()
    assert outcome.exit_code == 1, outcome.output
    error = cast(dict[str, object], read_json(output_path)["error"])
    assert error["type"] == "input"
    assert "model train" in cast(str, error["message"])


def test_label_manifest_cannot_swap_results_between_entries_with_the_same_horses() -> None:
    payload = _prepare((10, 11))
    sources = cast(list[dict[str, object]], payload["label_sources"])
    sources[0]["result"], sources[1]["result"] = sources[1]["result"], sources[0]["result"]
    with pytest.raises(ValueError, match="label source identities"):
        parse_label_sources(payload, required=True)


@pytest.mark.parametrize(
    "change",
    [
        "truncated",
        "future_dependency",
        "model_value",
        "model_time",
        "model_freeze",
        "group_value",
        "rule",
        "groups",
    ],
)
def test_calculated_input_revalidates_its_full_manifest(change: str) -> None:
    payload = _prepare((10, 11, 12))
    calculation = cast(dict[str, object], payload["calculation"])
    dependencies = cast(list[dict[str, object]], calculation["dependencies"])
    groups = cast(dict[str, dict[str, object]], dependencies[0]["groups"])
    group = next(iter(groups.values()))
    records = cast(list[dict[str, object]], payload["records"])
    first = records[0]
    column = SELECTED_COLUMNS[0]
    if change == "truncated":
        payload["calculation"] = {"parameters": calculation["parameters"]}
    elif change == "future_dependency":
        cast(list[dict[str, object]], group["sources"])[0]["received_at"] = at(
            20, 14, 50
        ).isoformat()
    elif change == "model_value":
        cast(dict[str, object], first["features"])[column] = 999
    elif change == "model_time":
        cast(dict[str, object], first["available_at"])[column] = at(10, 14, 49).isoformat()
    elif change == "model_freeze":
        first["freeze_at"] = at(10, 14, 51).isoformat()
    elif change == "group_value":
        row = cast(list[dict[str, object]], calculation["records"])[0]
        raw_group = cast(dict[str, dict[str, object]], row["groups"])["F01"]
        cast(dict[str, object], raw_group["values"])["past_finish_lag1"] = 999
    elif change == "rule":
        group["rule_id"] = "different-rule"
    else:
        groups.pop(next(iter(groups)))
    message = {
        "truncated": "complete calculation payload",
        "future_dependency": "later than freeze_at",
        "model_value": "model values or availability differ",
        "model_time": "model values or availability differ",
        "model_freeze": "freeze_at differ",
        "group_value": "model values or availability differ",
        "rule": "matching rules",
        "groups": "dependency groups differ",
    }[change]
    with pytest.raises(ValueError, match=message):
        parse_feature_inputs(payload)


def test_prepared_input_retains_the_explicit_catalog_with_nonstandard_feature_ids() -> None:
    definitions = load_feature_definitions(_ROOT / "configs/features.toml")
    registry = create_feature_registry(
        tuple(
            FeatureDefinition(f"custom-{i}", definition.name)
            for i, definition in enumerate(definitions)
        )
    )
    calculated = calculate_features((frozen_input(10),), parameters(), registry=registry)
    payload = prepare_model_payload(
        calculated, registry=registry, selected_columns=SELECTED_COLUMNS
    )
    schema, records = parse_feature_inputs(payload)
    assert schema.feature_names == SELECTED_COLUMNS
    assert len(records) == 4


@pytest.mark.parametrize("source_value", [True, "1"])
def test_selected_calculation_source_value_cannot_be_boolean_or_string(
    source_value: object,
) -> None:
    payload = _prepare((10,))
    calculation = cast(dict[str, object], payload["calculation"])
    row = cast(list[dict[str, object]], calculation["records"])[0]
    groups = cast(dict[str, dict[str, object]], row["groups"])
    cast(dict[str, object], groups["F01"]["values"])["past_finish_lag1"] = source_value
    record = cast(list[dict[str, object]], payload["records"])[0]
    cast(dict[str, object], record["features"])[SELECTED_COLUMNS[0]] = 1
    with pytest.raises(ValueError, match="numeric or null"):
        parse_feature_inputs(payload)


@pytest.mark.parametrize(
    ("row_index", "field", "value"),
    [
        (0, "content_hash", "f" * 64),
        (1, "content_hash", "f" * 64),
        (0, "received_at", at(10, 11).isoformat()),
        (1, "received_at", at(10, 11).isoformat()),
    ],
)
def test_same_source_version_cannot_conflict_between_calculation_groups_or_rows(
    row_index: int,
    field: str,
    value: str,
) -> None:
    payload = _prepare((10,))
    calculation = cast(dict[str, object], payload["calculation"])
    row = cast(list[dict[str, object]], calculation["dependencies"])[row_index]
    groups = cast(dict[str, dict[str, object]], row["groups"])
    first_group = next(iter(groups.values()))
    source = cast(list[dict[str, object]], first_group["sources"])[0]
    assert source["observation_id"] != parameters().evidence.observation_id
    source[field] = value
    with pytest.raises(ValueError, match="conflicting source version"):
        parse_feature_inputs(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_hash", "f" * 64),
        ("published_at", at(10, 15, 6).isoformat()),
        ("received_at", at(10, 15, 6).isoformat()),
        ("event_at", at(10, 15, 4).isoformat()),
    ],
)
def test_shared_result_evidence_cannot_conflict_between_calculation_and_labels(
    field: str, value: str
) -> None:
    payload = _prepare((10, 11), sources=_sources_with_shared_result())
    sources = cast(list[dict[str, object]], payload["label_sources"])
    result = cast(dict[str, object], sources[0]["result"])
    cast(dict[str, object], result["evidence"])[field] = value
    parse_feature_inputs(payload)
    with pytest.raises(ValueError, match="conflicting source version"):
        parse_label_sources(payload, required=True)


@pytest.mark.parametrize("field", ["content_hash", "received_at"])
def test_experiment_reader_rejects_conflicting_shared_result_evidence(
    field: str, tmp_path: Path
) -> None:
    payload = _prepare((10, 11), sources=_sources_with_shared_result())
    sources = cast(list[dict[str, object]], payload["label_sources"])
    result = cast(dict[str, object], sources[0]["result"])
    cast(dict[str, object], result["evidence"])[field] = (
        "f" * 64 if field == "content_hash" else at(10, 15, 6).isoformat()
    )
    path = tmp_path / "conflicting.json"
    write_json(path, payload)
    with pytest.raises(ValueError, match="conflicting source version"):
        read_experiment_input(path)


@pytest.mark.parametrize("field", ["content_hash", "received_at"])
def test_model_preparation_rejects_conflicting_shared_result_evidence(field: str) -> None:
    registry = create_feature_registry(load_feature_definitions(_ROOT / "configs/features.toml"))
    calculated = calculate_features(_sources_with_shared_result(), parameters(), registry=registry)
    result = target_result(10)
    conflicting = replace(
        result,
        evidence=replace(result.evidence, content_hash="f" * 64)
        if field == "content_hash"
        else replace(result.evidence, received_at=at(10, 15, 6)),
    )
    with pytest.raises(ValueError, match="conflicting source version"):
        prepare_model_payload(
            calculated,
            registry=registry,
            selected_columns=SELECTED_COLUMNS,
            results=(conflicting, target_result(11)),
        )


def test_matching_result_version_can_be_reused_in_calculation_and_labels(tmp_path: Path) -> None:
    payload = _prepare((10, 11), sources=_sources_with_shared_result())
    parse_feature_inputs(payload)
    assert parse_label_sources(payload, required=True) == (target_result(10), target_result(11))
    path = tmp_path / "matching.json"
    write_json(path, payload)
    _, generated, _, results = read_experiment_input(path)
    assert generated.dataset is not None
    assert results == (target_result(10), target_result(11))


@pytest.mark.parametrize("conflict", [None, "content_hash", "received_at"])
def test_label_source_versions_are_consistent_even_without_a_calculation_manifest(
    conflict: str | None,
) -> None:
    prepared = _prepare((10, 11))
    sources = cast(list[dict[str, object]], prepared["label_sources"])
    first, second = (cast(dict[str, object], entry["result"]) for entry in sources)
    first["evidence"] = copy.deepcopy(second["evidence"])
    if conflict is not None:
        cast(dict[str, object], first["evidence"])[conflict] = (
            "f" * 64 if conflict == "content_hash" else at(11, 15, 6).isoformat()
        )
    payload = {"records": prepared["records"], "label_sources": sources}
    if conflict is None:
        assert len(parse_label_sources(payload, required=True)) == 2
    else:
        with pytest.raises(ValueError, match="conflicting source version"):
            parse_label_sources(payload, required=True)


def test_all_21_group_projection_retains_missing_sources_and_real_model_registry_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _prepare((10, 11, 12))
    training_path = tmp_path / "training.json"
    write_json(training_path, payload)
    schema, generated, digest, results = read_experiment_input(training_path)
    assert schema.feature_names == SELECTED_COLUMNS
    assert generated.dataset is not None
    assert generated.dataset.feature_matrix()[3][1] is None
    assert len(results) == 3
    assert len(digest) == 64
    assert set(cast(dict[str, object], payload["calculation"])) >= {
        "parameters",
        "dependencies",
        "source_missing_reasons",
        "records",
    }
    summary = _training(training_path)
    output = Path(str(summary["output_dir"]))
    context = read_json(output / "native/training.json")
    assert context["label_known_through"] == at(11, 15, 5).isoformat()
    assert context["label_assurance"] == "declared_timestamp_evidence_not_external_certification"
    assert len(cast(list[object], context["train_label_sources"])) == 2
    metadata = read_json(output / "native/ranking.model.metadata.json")
    assert metadata["format_version"] == 3
    prediction_path = tmp_path / "prediction.json"
    write_json(prediction_path, _prepare((13, 14), labeled=False))
    completed = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "src/main.py"),
            "model",
            "predict",
            "--config-dir",
            str(_ROOT / "configs/experiments"),
            "--override",
            f"data.input='{prediction_path.as_posix()}'",
            "--override",
            "model.version=1",
            "--override",
            "data.selection=latest_date",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    predicted = json.loads(completed.stdout)
    assert predicted["model_version"] == "1"
    assert predicted["label_known_through"] == context["label_known_through"]
    assert predicted["selected"]["race_ids"] == ["target-14"]
    values = read_json(Path(predicted["output_dir"]) / "predictions.json")["predictions"]
    assert isinstance(values, list)
    assert len(values) == 4
    assert all(set(v) == {"race_id", "horse_id", "score", "rank"} for v in values)


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "extra", "horses", "labels", "clock", "status", "tie"]
)
def test_strict_training_rejects_invalid_label_sources(kind: str) -> None:
    payload = _prepare((10,))
    sources = cast(list[dict[str, object]], payload["label_sources"])
    result = cast(dict[str, object], sources[0]["result"])
    if kind == "missing":
        payload.pop("label_sources")
    elif kind == "duplicate":
        sources.append(copy.deepcopy(sources[0]))
    elif kind == "extra":
        extra = copy.deepcopy(sources[0])
        extra["race_id"] = "unknown"
        sources.append(extra)
    elif kind == "horses":
        sources[0]["horse_ids"] = ["A", "B", "C"]
    elif kind == "labels":
        cast(list[dict[str, object]], payload["records"])[0]["finish_position"] = 4
    elif kind == "clock":
        cast(dict[str, object], result["evidence"])["received_at"] = "2026-06-10T14:00:00"
    elif kind == "status":
        cast(list[dict[str, object]], result["runners"])[0]["status"] = "cancelled"
    elif kind == "tie":
        cast(list[dict[str, object]], result["runners"])[0]["finish"] = 2
    with pytest.raises(
        ValueError, match=r"label_sources|identities|horse|labels|timezone|non-normal|contiguous"
    ):
        parse_label_sources(payload, required=True)


def test_train_result_known_at_holdout_freeze_is_rejected_but_test_results_may_be_later(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _prepare((10, 11, 12))
    label = cast(
        dict[str, object], cast(list[dict[str, object]], payload["label_sources"])[1]["result"]
    )
    proof = cast(dict[str, object], label["evidence"])
    proof["received_at"] = at(12, 14, 50).isoformat()
    path = tmp_path / "known-late.json"
    write_json(path, payload)
    with pytest.raises(ValueError, match=r"strictly before.*holdout"):
        _training(path)


def test_prediction_at_training_label_availability_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "training.json"
    write_json(path, _prepare((10, 11, 12)))
    _training(path)
    source = frozen_input(11)
    delta = timedelta(minutes=15)
    freeze = source.freeze_at + delta
    source = replace(
        source,
        freeze_at=freeze,
        card=replace(
            source.card,
            race_id="prediction-boundary",
            scheduled_start_at=source.card.scheduled_start_at + timedelta(hours=1),
        ),
        coverage=tuple(
            replace(c, end_at=freeze, evidence=evidence(f"boundary-{c.kind}", freeze))
            for c in source.coverage
        ),
        markets=tuple(
            replace(
                m,
                race_id="prediction-boundary",
                evidence=evidence(f"boundary-market-{i}", m.evidence.event_at + delta),
                pair_evidence=evidence(f"boundary-pair-{i}", m.pair_evidence.event_at + delta),
            )
            for i, m in enumerate(source.markets)
        ),
    )
    path = tmp_path / "prediction.json"
    write_json(path, _prepare((), labeled=False, sources=(source,)))
    config = load_experiment_config(
        _ROOT / "configs/experiments",
        action="predict",
        overrides=[f"data.input='{path.as_posix()}'", "model.version=1"],
    )
    with pytest.raises(ValueError, match="strictly after"):
        run_experiment(config)


def test_prepared_payload_parameters_and_missing_columns_are_not_silently_changed() -> None:
    payload = _prepare((10,))
    calculation = cast(dict[str, object], payload["calculation"])
    cast(dict[str, object], calculation["parameters"])["count_window"] = 2
    with pytest.raises(ValueError, match="parameters differ"):
        parse_feature_inputs(payload)
    registry = create_feature_registry(load_feature_definitions(_ROOT / "configs/features.toml"))
    calculated = calculate_features((frozen_input(10),), parameters(), registry=registry)
    feature_id = registry.by_name("recent_performance").definition.feature_id
    groups = dict(calculated.manifests[0])
    original = groups[feature_id]
    groups[feature_id] = replace(original, values={})
    broken = replace(calculated, manifests=(groups, *calculated.manifests[1:]))
    with pytest.raises(ValueError, match="column is missing"):
        prepare_model_payload(broken, registry=registry, selected_columns=SELECTED_COLUMNS)
    for value in (True, "1"):
        groups[feature_id] = replace(original, values={"past_finish_lag1": value})
        with pytest.raises(ValueError, match="numeric"):
            prepare_model_payload(broken, registry=registry, selected_columns=SELECTED_COLUMNS)


def test_prepare_cli_uses_mandatory_hydra_columns_and_refuses_input_or_existing_outputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "observations.json"
    results = tmp_path / "results.json"
    write_json(
        source, {"schema_version": 1, "observations": [normalized_payload(frozen_input(10))]}
    )
    write_json(results, {"schema_version": 1, "results": [normalized_payload(target_result(10))]})
    config = tmp_path / "config"
    config.mkdir()
    write_json(
        config / "prepare.yaml",
        {
            "parameters": normalized_payload(parameters()),
            "selected_columns": list(SELECTED_COLUMNS),
        },
    )
    output = tmp_path / "prepared.json"
    arguments = [
        "model",
        "prepare-input",
        "--input",
        str(source),
        "--results",
        str(results),
        "--output",
        str(output),
        "--config-dir",
        str(config),
        "--features-config",
        str(_ROOT / "configs/features.toml"),
    ]
    runner = CliRunner()
    first = runner.invoke(app, arguments)
    assert first.exit_code == 0, first.output
    schema, records = parse_feature_inputs(read_json(output))
    assert len(build_features(records, feature_schema=schema).feature_rows) == 4
    original = output.read_bytes()
    assert runner.invoke(app, arguments).exit_code == 1
    assert output.read_bytes() == original
    for protected in (source, results):
        args = arguments.copy()
        args[args.index("--output") + 1] = str(protected)
        assert runner.invoke(app, args).exit_code == 1
    args = arguments.copy()
    write_json(
        config / "prepare.yaml",
        {"parameters": normalized_payload(parameters()), "selected_columns": "???"},
    )
    args[args.index("--output") + 1] = str(tmp_path / "mandatory.json")
    assert runner.invoke(app, args).exit_code == 1
