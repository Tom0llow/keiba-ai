"""Train holdout ranking models and predict from exact local registry versions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse
from urllib.request import url2pathname

from configuration.experiments import ExperimentConfig
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from models.dataset.availability import FeatureGenerationError
from models.dataset.schema import FeatureSchema
from models.evaluation.metrics import evaluate_ranking
from models.evaluation.walk_forward import make_chronological_holdout
from models.experiments.inputs import (
    chronological_times,
    dataset_summary,
    file_sha256,
    read_experiment_input,
    select_prediction_rows,
)
from models.experiments.provenance import experiment_provenance
from models.experiments.tracking import (
    ensure_registered_model,
    experiment_id,
    local_tracking_client,
)
from models.ranking.ranker import RankingModel, RankingPrediction
from models.serialization.outputs import audit_payload, metrics_payload
from models.serialization.projection import label_known_through, label_manifest
from models.serialization.real_market import SnapshotResultLabel, market_assurance
from models.serialization.reference import reference_assurance
from models.training.train import effective_lambdarank_parameters, train_lambdarank

if TYPE_CHECKING:
    from mlflow.tracking import MlflowClient


def run_experiment(config: ExperimentConfig) -> dict[str, object]:
    """Run one audited experiment, marking every post-creation failure as FAILED.

    Each invocation owns a fresh run-ID directory. Existing output and source
    inputs are never replaced. Model registration uses native files rather than
    pickle, pyfunc or a configured Python target.
    """
    client = local_tracking_client(config.tracking)
    run = client.create_run(
        experiment_id(client, config.tracking),
        tags={"task": config.action, "model_format": "lightgbm_native"},
    )
    run_id = str(run.info.run_id)
    output = config.output_dir / run_id
    owns_output = False
    try:
        output.mkdir(parents=True, exist_ok=False)
        owns_output = True
        _record_json(client, run_id, output, "config.json", config.resolved)
        provenance = experiment_provenance()
        _record_json(client, run_id, output, "provenance.json", provenance)
        client.set_tag(run_id, "source_sha256", str(provenance["source_sha256"]))
        result = (
            _train(config, client, run_id, output)
            if config.action == "train"
            else _predict(config, client, run_id, output)
        )
        summary = {"run_id": run_id, "output_dir": str(output), **result}
        _record_json(client, run_id, output, "summary.json", summary)
        client.set_terminated(run_id, status="FINISHED")
    except BaseException as exc:
        try:
            if owns_output:
                failure: dict[str, object] = {"error_type": type(exc).__name__, "error": str(exc)}
                if isinstance(exc, FeatureGenerationError):
                    failure["audit"] = audit_payload(exc.audit)
                _record_json(client, run_id, output, "failure.json", failure)
        finally:
            client.set_terminated(run_id, status="FAILED")
        raise
    return summary


def _train(
    config: ExperimentConfig, client: MlflowClient, run_id: str, output: Path
) -> dict[str, object]:
    schema, generated, digest, results = read_experiment_input(config.input_path)
    if generated.dataset is None:
        raise ValueError("training requires finish_position on every input row")
    split = make_chronological_holdout(generated.dataset, test_races=config.test_races)
    train_ids = {row.race_id for row in split.train.rows}
    train_results = tuple(race for race in results if race.race_id in train_ids)
    known_through = (
        label_known_through(train_results) if schema.calculation_contract is not None else None
    )
    if known_through is not None and known_through >= chronological_times(split.test.rows)[0]:
        raise ValueError("training results must be known strictly before the first holdout freeze")
    assurance = (
        "declared_timestamp_evidence_not_external_certification"
        if known_through is not None
        else "legacy_label_time_unverified"
    )
    if train_results and isinstance(train_results[0], SnapshotResultLabel):
        assurances = {r.assurance for r in train_results if isinstance(r, SnapshotResultLabel)}
        if len(assurances) != 1 or any(
            not isinstance(r, SnapshotResultLabel) for r in train_results
        ):
            raise ValueError("training label assumptions must be consistent")
        assurance = next(iter(assurances))
    feature_assurance = _feature_assurance(schema)
    feature_sources = _market_sources(config.input_path, digest, schema)
    if feature_sources is not None:
        client.log_artifact(run_id, str(config.input_path), artifact_path="prepared_input")
        if file_sha256(config.input_path) != digest:
            raise ValueError("input changed while recording prepared source artifact")
    train_summary = dataset_summary(split.train.rows)
    test_summary = dataset_summary(split.test.rows)
    input_summary: dict[str, object] = {
        "input_path": str(config.input_path),
        "input_sha256": digest,
        "feature_schema": schema.as_metadata(),
        "audit": audit_payload(generated.audit),
        "train": train_summary,
        "test": test_summary,
        "label_known_through": known_through.isoformat() if known_through else None,
        "label_assurance": assurance,
        "train_label_sources": label_manifest(train_results),
        "input_assurance": feature_assurance,
        "feature_source_manifest": feature_sources,
        "label_boundary_meaning": "declared_usable_after"
        if train_results and isinstance(train_results[0], SnapshotResultLabel)
        else "actual_available_at"
        if known_through is not None
        else "unverified",
    }
    _record_json(client, run_id, output, "input.json", input_summary)
    client.log_param(run_id, "input_sha256", digest)
    parameters = effective_lambdarank_parameters(config.parameters)
    _record_json(client, run_id, output, "parameters.json", parameters)
    for name, value in parameters.items():
        client.log_param(run_id, f"model.{name}", json.dumps(value, sort_keys=True))
    client.log_param(run_id, "split.test_races", config.test_races)
    model = train_lambdarank(split.train, parameters=config.parameters)
    test_ids = {row.race_id for row in split.test.rows}
    test_rows = tuple(row for row in generated.feature_rows if row.race_id in test_ids)
    predictions = model.predict(test_rows, feature_schema=schema)
    scores_by_key = {(p.race_id, p.horse_id): p.score for p in predictions}
    scores = [scores_by_key[(row.race_id, row.horse_id)] for row in split.test.rows]
    metrics = metrics_payload(evaluate_ranking(split.test, scores))
    for name, value in metrics.items():
        client.log_metric(run_id, name, value)
    _record_json(
        client,
        run_id,
        output,
        "predictions.json",
        {
            **_predictions_payload(predictions),
            "input_assurance": feature_assurance,
            "label_assurance": assurance,
        },
    )
    native_dir = output / "native"
    model_path = native_dir / "ranking.model"
    model.save(model_path)
    training_context = {
        "format_version": 1,
        "run_id": run_id,
        "trained_through": train_summary["freeze_at_end"],
        "train_race_ids": train_summary["race_ids"],
        "input_sha256": digest,
        "native_sha256": file_sha256(model_path),
        "feature_schema": schema.as_metadata(),
        "label_known_through": known_through.isoformat() if known_through else None,
        "label_assurance": assurance,
        "train_label_sources": label_manifest(train_results),
        "input_assurance": feature_assurance,
        "feature_source_manifest": feature_sources,
        "label_boundary_meaning": "declared_usable_after"
        if train_results and isinstance(train_results[0], SnapshotResultLabel)
        else "actual_available_at"
        if known_through is not None
        else "unverified",
    }
    write_json(native_dir / "training.json", training_context)
    client.log_artifacts(run_id, str(native_dir), artifact_path="native")
    name = config.tracking.registered_model_name
    ensure_registered_model(client, name)
    version = client.create_model_version(
        name=name,
        source=f"{client.get_run(run_id).info.artifact_uri}/native",
        run_id=run_id,
        tags={
            "native_sha256": file_sha256(model_path),
            "training_context_sha256": file_sha256(native_dir / "training.json"),
        },
    )
    if version.status != "READY":
        raise ValueError("MLflow model version did not become READY")
    client.set_tag(run_id, "registered_model_name", name)
    client.set_tag(run_id, "registered_model_version", str(version.version))
    return {
        "registered_model_name": name,
        "model_version": str(version.version),
        "metrics": metrics,
        "train": train_summary,
        "test": test_summary,
        "input_sha256": digest,
    }


def _predict(
    config: ExperimentConfig, client: MlflowClient, run_id: str, output: Path
) -> dict[str, object]:
    if config.version is None:
        raise ValueError("prediction requires an exact model version")
    name = config.tracking.registered_model_name
    version = client.get_model_version(name, config.version)
    if version.status != "READY" or not version.run_id:
        raise ValueError(
            "registered model version must be READY and associated with a training run"
        )
    training_run = client.get_run(version.run_id)
    if training_run.info.status != "FINISHED" or training_run.data.tags.get("task") != "train":
        raise ValueError("registered model must come from a FINISHED training run")
    source = client.get_model_version_download_uri(name, config.version)
    _validate_local_model_source(source, config.tracking.artifact_root)
    expected_source = f"{training_run.info.artifact_uri}/native"
    if source != expected_source:
        raise ValueError("registered model source does not match its training run")
    download = output / "download"
    download.mkdir()
    local_dir = Path(client.download_artifacts(version.run_id, "native", str(download)))
    model_path = local_dir / "ranking.model"
    context_path = local_dir / "training.json"
    if file_sha256(context_path) != version.tags.get("training_context_sha256"):
        raise ValueError("training context does not match registered model version")
    context = read_json(context_path)
    if context.get("format_version") != 1 or context.get("run_id") != version.run_id:
        raise ValueError("invalid training context")
    if file_sha256(model_path) != version.tags.get("native_sha256"):
        raise ValueError("native model does not match registered model version")
    model = RankingModel.load(model_path)
    if context.get("feature_schema") != model.feature_schema.as_metadata():
        raise ValueError("training context feature schema differs from native model")
    trained_through = _aware_timestamp(context.get("trained_through"))
    schema, generated, digest, _ = read_experiment_input(config.input_path)
    if schema != model.feature_schema:
        raise ValueError("prediction feature schema does not match the trained model")
    known_through = None
    if schema.calculation_contract is not None:
        allowed = {"declared_timestamp_evidence_not_external_certification"}
        if schema.calculation_contract.settings["implementation"] in {
            "published_win_market_v1",
            "snapshot_reference_21_groups_v1",
        }:
            allowed = {
                "provided_result_clock_snapshot_revision_unverified",
                "assumed_snapshot_results_revision_time_unverified",
            }
        if context.get("label_assurance") not in allowed:
            raise ValueError("strict calculated prediction requires evidenced training labels")
        known_through = _aware_timestamp(context.get("label_known_through"))
    feature_assurance = _feature_assurance(schema)
    feature_sources = _market_sources(config.input_path, digest, schema)
    if (
        schema.calculation_contract is not None
        and schema.calculation_contract.settings["implementation"]
        in {"published_win_market_v1", "snapshot_reference_21_groups_v1"}
        and context.get("input_assurance") != feature_assurance
    ):
        raise ValueError("registered market assumptions differ from schema")
    rows = select_prediction_rows(
        generated.feature_rows, selection=config.selection, date_timezone=config.date_timezone
    )
    times = chronological_times(rows)
    train_ids = context.get("train_race_ids")
    if not isinstance(train_ids, list) or not all(isinstance(value, str) for value in train_ids):
        raise ValueError("invalid training race identities")
    if times[0] <= max(trained_through, known_through or trained_through) or any(
        row.race_id in train_ids for row in rows
    ):
        raise ValueError("prediction races must be strictly after the model's training period")
    input_summary: dict[str, object] = {
        "input_path": str(config.input_path),
        "input_sha256": digest,
        "feature_schema": schema.as_metadata(),
        "audit": audit_payload(generated.audit),
        "selection": config.selection,
        "date_timezone": config.date_timezone,
        "selected": dataset_summary(rows),
        "input": dataset_summary(generated.feature_rows),
        "label_assurance": context.get("label_assurance", "legacy_label_time_unverified"),
        "label_known_through": known_through.isoformat() if known_through else None,
        "input_assurance": feature_assurance,
        "feature_source_manifest": feature_sources,
    }
    _record_json(client, run_id, output, "input.json", input_summary)
    client.log_param(run_id, "input_sha256", digest)
    client.log_param(run_id, "model.name", name)
    client.log_param(run_id, "model.version", config.version)
    predictions = model.predict(rows, feature_schema=schema)
    _record_json(
        client,
        run_id,
        output,
        "predictions.json",
        {
            **_predictions_payload(predictions),
            "input_assurance": feature_assurance,
            "label_assurance": context.get("label_assurance", "legacy_label_time_unverified"),
        },
    )
    return {
        "registered_model_name": name,
        "model_version": config.version,
        "training_run_id": version.run_id,
        "trained_through": trained_through.isoformat(),
        "label_known_through": known_through.isoformat() if known_through else None,
        "label_assurance": context.get("label_assurance", "legacy_label_time_unverified"),
        "selected": dataset_summary(rows),
        "input_sha256": digest,
    }


def _record_json(
    client: MlflowClient,
    run_id: str,
    output: Path,
    name: str,
    payload: Mapping[str, object],
) -> None:
    path = output / name
    write_json(path, payload)
    client.log_artifact(run_id, str(path))


def _feature_assurance(schema: FeatureSchema) -> object:
    contract = schema.calculation_contract
    if contract is not None and contract.settings["implementation"] == "published_win_market_v1":
        return market_assurance(cast(Mapping[str, object], contract.settings["parameters"]))
    if (
        contract is not None
        and contract.settings["implementation"] == "snapshot_reference_21_groups_v1"
    ):
        parameters = cast(dict[str, object], contract.settings["parameters"])
        return reference_assurance(cast(Mapping[str, object], parameters["reference_rules"]))
    return (
        "declared_timestamp_evidence_not_external_certification"
        if contract is not None
        else "legacy_feature_input"
    )


def _market_sources(path: Path, digest: str, schema: FeatureSchema) -> object:
    contract = schema.calculation_contract
    if contract is None or contract.settings["implementation"] not in {
        "published_win_market_v1",
        "snapshot_reference_21_groups_v1",
    }:
        return None
    payload = read_json(path)
    if file_sha256(path) != digest:
        raise ValueError("input changed while recording market provenance")
    if contract.settings["implementation"] == "snapshot_reference_21_groups_v1":
        raw = cast(dict[str, object], payload["reference_input"])
        calculated = cast(dict[str, object], payload["calculation"])
        return {
            "reference_input_sha256": payload["reference_input_sha256"],
            "snapshot": raw["snapshot"],
            "rules": raw["rules"],
            "source_catalog": calculated["source_catalog"],
            "held_races": payload["held_races"],
        }
    return {
        "calculation": payload["calculation"],
        "preparation_config": payload.get("preparation_config"),
    }


def _predictions_payload(predictions: tuple[RankingPrediction, ...]) -> dict[str, object]:
    return {
        "predictions": [
            {"race_id": p.race_id, "horse_id": p.horse_id, "score": p.score, "rank": p.rank}
            for p in predictions
        ]
    }


def _aware_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("trained_through must be an aware timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("trained_through must be an aware timestamp")
    return parsed


def _validate_local_model_source(source: str, root: Path) -> None:
    parsed = urlparse(source)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("registered model source must be a local file URI")
    path = Path(url2pathname(parsed.path)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("registered model source must stay within the configured artifact root")
