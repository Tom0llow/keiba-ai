"""Exercise real Hydra, LightGBM and the local MLflow SQLite registry together."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast
from unittest.mock import patch
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from configuration.experiments import ExperimentConfig, load_experiment_config
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from models.dataset.availability import FeatureGenerationError
from models.experiments.runner import run_experiment
from models.experiments.tracking import local_tracking_client

_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_DIR = _ROOT / "configs" / "experiments"


def _input(path: Path, *, days: tuple[int, ...] = (1, 2, 3, 4)) -> Path:
    records: list[dict[str, object]] = []
    for index, day in enumerate(days):
        freeze = f"2026-01-{day:02d}T{12 + index:02d}:00:00+09:00"
        for horse in range(1, 5):
            records.append(
                {
                    "race_id": f"race-{day}-{index}",
                    "horse_id": f"horse-{horse}",
                    "freeze_at": freeze,
                    "features": {"ability": 5 - horse, "historical_odds": None},
                    "available_at": {"ability": freeze},
                    "finish_position": horse,
                }
            )
    write_json(
        path,
        {
            "schema_id": "test-v1",
            "feature_names": ["ability", "historical_odds"],
            "records": records,
        },
    )
    return path


def _config(
    action: Literal["train", "predict"], input_path: Path, *overrides: str
) -> ExperimentConfig:
    return load_experiment_config(
        _CONFIG_DIR,
        action=action,
        overrides=[f"data.input='{input_path.as_posix()}'", *overrides],
    )


def _train(input_path: Path, *overrides: str) -> tuple[ExperimentConfig, dict[str, object]]:
    config = _config(
        "train",
        input_path,
        "model.parameters.n_estimators=3",
        "model.parameters.min_child_samples=1",
        *overrides,
    )
    return config, run_experiment(config)


def test_transient_finished_write_failure_is_recorded_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config("train", _input(tmp_path / "training.json"))
    client = local_tracking_client(config.tracking)
    terminate = client.set_terminated
    statuses: list[str] = []

    def fail_finished_once(run_id: str, status: str) -> None:
        statuses.append(status)
        if status == "FINISHED":
            raise RuntimeError("temporary completion write failure")
        terminate(run_id, status=status)

    with (
        patch("models.experiments.runner.local_tracking_client", return_value=client),
        patch.object(client, "set_terminated", side_effect=fail_finished_once),
        patch("models.experiments.runner._train", return_value={"model_version": "1"}),
        pytest.raises(RuntimeError, match="temporary completion"),
    ):
        run_experiment(config)
    assert statuses == ["FINISHED", "FAILED"]
    experiment = client.get_experiment_by_name("ranking")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 1
    assert runs[0].info.status == "FAILED"
    failure = read_json(config.output_dir / runs[0].info.run_id / "failure.json")
    assert failure["error_type"] == "RuntimeError"


def test_train_registers_each_version_and_fresh_process_predicts_latest_freeze_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = _input(tmp_path / "training.json")
    original = input_path.read_bytes()
    config, first = _train(input_path, "split.test_races=2")
    _, second = _train(input_path)
    assert first["model_version"] == "1"
    assert second["model_version"] == "2"
    assert input_path.read_bytes() == original
    client = local_tracking_client(config.tracking)
    run_id = str(first["run_id"])
    run = client.get_run(run_id)
    assert run.info.status == "FINISHED"
    assert set(run.data.metrics) == {"ndcg_at_3", "top1_accuracy", "top3_overlap"}
    assert run.data.params["model.objective"] == '"lambdarank"'
    assert run.data.params["model.label_gain"] == "[0, 1, 3, 7]"
    assert run.data.params["model.n_estimators"] == "3"
    assert run.data.params["model.learning_rate"] == "0.05"
    output = Path(str(first["output_dir"]))
    provenance = read_json(output / "provenance.json")
    assert len(str(provenance["source_sha256"])) == 64
    assert len(str(provenance["uv_lock_sha256"])) == 64
    summary = read_json(output / "input.json")
    train = cast(Mapping[str, object], summary["train"])
    test = cast(Mapping[str, object], summary["test"])
    assert train["races"] == 2
    assert test["races"] == 2
    assert train["missing_values_by_feature"] == {"ability": 0, "historical_odds": 8}
    assert test["missing_values_by_feature"] == {"ability": 0, "historical_odds": 8}
    assert not set(cast(list[str], train["race_ids"])) & set(cast(list[str], test["race_ids"]))
    assert cast(Mapping[str, object], summary["audit"])["missing_values"] == 16
    assert (output / "native" / "ranking.model.ready").is_file()
    assert not list(output.rglob("*.pkl"))
    prediction_input = _input(tmp_path / "prediction.json", days=(4, 5, 5))
    # File modification time is deliberately unrelated to the model input's dates.
    os.utime(prediction_input, (1, 1))
    completed = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "src" / "main.py"),
            "model",
            "predict",
            "--config-dir",
            str(_CONFIG_DIR),
            "--override",
            f"data.input='{prediction_input.as_posix()}'",
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
    prediction_output = Path(predicted["output_dir"])
    assert predicted["model_version"] == "1"
    assert predicted["selected"]["races"] == 2
    predictions = read_json(prediction_output / "predictions.json")["predictions"]
    assert isinstance(predictions, list)
    assert len(predictions) == 8
    assert {item["race_id"] for item in predictions} == {"race-5-1", "race-5-2"}
    assert all(set(item) == {"race_id", "horse_id", "score", "rank"} for item in predictions)
    assert client.get_run(predicted["run_id"]).info.status == "FINISHED"


@pytest.mark.parametrize("days", [(2, 1, 3, 4), (1, 1, 3, 4)])
def test_train_rejects_non_strict_chronology_and_records_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, days: tuple[int, ...]
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = _input(tmp_path / "training.json", days=days)
    if days == (1, 1, 3, 4):
        payload = read_json(input_path)
        records = cast(list[dict[str, object]], payload["records"])
        for row in records[4:8]:
            row["freeze_at"] = "2026-01-01T12:00:00+09:00"
            row["available_at"] = {"ability": row["freeze_at"]}
        write_json(input_path, payload)
    config = _config("train", input_path)
    with pytest.raises(ValueError, match=r"chronology|duplicate freeze_at"):
        run_experiment(config)
    client = local_tracking_client(config.tracking)
    experiment = client.get_experiment_by_name("ranking")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 1
    assert runs[0].info.status == "FAILED"
    assert not client.search_model_versions()


def test_future_available_feature_is_a_failed_run_with_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = _input(tmp_path / "training.json")
    payload = read_json(input_path)
    records = cast(list[dict[str, object]], payload["records"])
    records[0]["available_at"] = {"ability": "2026-01-02T12:00:00+09:00"}
    write_json(input_path, payload)
    with pytest.raises(FeatureGenerationError):
        _train(input_path)
    failure_paths = list((tmp_path / "output" / "experiments").glob("*/failure.json"))
    assert len(failure_paths) == 1
    failure = read_json(failure_paths[0])
    assert cast(Mapping[str, object], failure["audit"])["valid"] is False


def test_prediction_rejects_schema_mismatch_and_training_period(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = _input(tmp_path / "training.json")
    config, trained = _train(input_path)
    prediction = _input(tmp_path / "prediction.json", days=(5,))
    payload = read_json(prediction)
    payload["schema_id"] = "another-schema"
    write_json(prediction, payload)
    with pytest.raises(ValueError, match="schema does not match"):
        run_experiment(_config("predict", prediction, "model.version=1"))
    with pytest.raises(ValueError, match="strictly after"):
        run_experiment(_config("predict", input_path, "model.version=1"))
    client = local_tracking_client(config.tracking)
    experiment = client.get_experiment_by_name("ranking")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert sorted(run.info.status for run in runs) == ["FAILED", "FAILED", "FINISHED"]
    assert client.get_run(str(trained["run_id"])).info.status == "FINISHED"


def test_prediction_rejects_corrupt_native_missing_value_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    input_path = _input(tmp_path / "training.json")
    config, _ = _train(input_path)
    client = local_tracking_client(config.tracking)
    source = client.get_model_version_download_uri(config.tracking.registered_model_name, "1")
    metadata_path = Path(url2pathname(urlparse(source).path)) / "ranking.model.metadata.json"
    payload = read_json(metadata_path)
    schema = cast(dict[str, object], payload["feature_schema"])
    cast(list[dict[str, object]], schema["features"])[0]["missing_value_policy"] = "impute_zero"
    write_json(metadata_path, payload)
    prediction = _input(tmp_path / "prediction.json", days=(5,))
    with pytest.raises(ValueError, match="metadata does not match its digest"):
        run_experiment(_config("predict", prediction, "model.version=1"))


@pytest.mark.parametrize("version", ["latest", "0", "-1", "01", "true"])
def test_predict_config_requires_exact_model_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="version"):
        _config("predict", tmp_path / "input.json", f"model.version='{version}'")


def test_config_rejects_generated_paths_outside_output_and_does_not_change_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="output/ tree"):
        _config("train", tmp_path / "input.json", "output_dir=source")
    assert Path.cwd() == tmp_path
    assert not (tmp_path / "output").exists()
