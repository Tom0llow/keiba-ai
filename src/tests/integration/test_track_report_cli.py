"""Run `model track-report` against a real local MLflow SQLite store in a temporary cwd."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from mlflow.tracking import MlflowClient
from typer.testing import CliRunner, Result

from main import app
from tests.reference_fixtures import ROOT
from tests.unit.test_report_tracking import backtest_report, pl_report


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    return tmp_path


def _report_dir(root: Path, name: str, report: dict[str, object], *extra: str) -> Path:
    path = root / "output" / name
    path.mkdir()
    (path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    for file_name in extra:
        (path / file_name).write_bytes(b"parquet-bytes-" + file_name.encode())
    return path


def _track(report_dir: Path, *options: str) -> Result:
    return CliRunner().invoke(
        app, ["model", "track-report", "--report-dir", str(report_dir), *options]
    )


def _client(root: Path) -> MlflowClient:
    uri = f"sqlite:///{(root / 'output/mlflow/mlflow.db').resolve().as_posix()}"
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def _hashes(path: Path) -> dict[str, str]:
    return {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in path.iterdir()}


def test_pl_report_is_recorded_as_parent_and_variant_runs(workdir: Path) -> None:
    report_dir = _report_dir(workdir, "pl-eval", pl_report(), "predictions.parquet")
    before = _hashes(report_dir)

    result = _track(report_dir)

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("tracked: experiment=pl-evaluation run_id=")
    assert result.stdout.strip().endswith("children=2")
    assert _hashes(report_dir) == before
    client = _client(workdir)
    experiment = client.get_experiment_by_name("pl-evaluation")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert {run.info.status for run in runs} == {"FINISHED"}
    parents = [run for run in runs if run.data.tags.get("run_role") == "report"]
    assert len(parents) == 1
    parent = parents[0]
    report_sha256 = before["report.json"]
    assert parent.info.run_name == "pl-eval"
    assert parent.data.tags["report_sha256"] == report_sha256
    assert parent.data.tags["file_sha256.predictions.parquet"] == before["predictions.parquet"]
    assert parent.data.tags["report_dir"] == str(report_dir.resolve())
    assert parent.data.params["lightgbm.learning_rate"] == "0.05"
    artifacts = {item.path for item in client.list_artifacts(parent.info.run_id)}
    assert artifacts == {"report.json", "config.json"}
    children = sorted(
        (run for run in runs if run.data.tags.get("run_role") == "variant"),
        key=lambda run: run.info.run_name,
    )
    assert [run.info.run_name for run in children] == ["all_columns", "without_b"]
    for child in children:
        assert child.data.tags["mlflow.parentRunId"] == parent.info.run_id
    child = children[0]
    assert child.data.params["feature_count"] == "2"
    assert child.data.metrics["pooled/raw/winner_log_loss/mean_difference"] == 0.009
    history = client.get_metric_history(child.info.run_id, "fold/best_iteration")
    assert sorted((item.step, item.value) for item in history) == [(2024, 14.0), (2025, 15.0)]
    assert {item.path for item in client.list_artifacts(child.info.run_id)} == {
        "feature_names.json"
    }


def test_backtest_report_is_recorded_as_one_run_with_yearly_steps(workdir: Path) -> None:
    report_dir = _report_dir(workdir, "backtest", backtest_report(), "bets.parquet")

    result = _track(report_dir)

    assert result.exit_code == 0, result.output
    assert result.stdout.strip().endswith("children=0")
    client = _client(workdir)
    experiment = client.get_experiment_by_name("betting-backtest")
    assert experiment is not None
    (run,) = client.search_runs([experiment.experiment_id])
    assert run.info.status == "FINISHED"
    assert run.data.tags["pl_report_sha256"] == "a" * 64
    assert run.data.params["selection.2025"] == "blend_width"
    assert run.data.metrics["all/recovery_rate"] == 0.9
    history = client.get_metric_history(run.info.run_id, "method/pl_mid/flat_recovery_rate")
    assert sorted((item.step, item.value) for item in history) == [(2024, 0.7), (2025, 0.75)]


def test_recording_the_same_report_again_adds_no_run(workdir: Path) -> None:
    report_dir = _report_dir(workdir, "pl-eval", pl_report())
    first = _track(report_dir)
    assert first.exit_code == 0, first.output
    run_id = first.stdout.split("run_id=")[1].split()[0]

    second = _track(report_dir)

    assert second.exit_code == 0, second.output
    assert second.stdout.strip() == f"already recorded: run_id={run_id}"
    experiment = _client(workdir).get_experiment_by_name("pl-evaluation")
    assert experiment is not None
    assert len(_client(workdir).search_runs([experiment.experiment_id])) == 3


def test_failure_marks_created_runs_failed_and_a_retry_succeeds(workdir: Path) -> None:
    report_dir = _report_dir(workdir, "pl-eval", pl_report())

    with patch.object(MlflowClient, "log_artifact", side_effect=RuntimeError("disk\nfull")):
        failed = _track(report_dir)

    assert failed.exit_code == 1
    # MLflow may log its own database setup lines first; the command reports one line last.
    assert failed.stderr.strip().splitlines()[-1] == "model track-report failed: disk full"
    client = _client(workdir)
    experiment = client.get_experiment_by_name("pl-evaluation")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert runs
    assert {run.info.status for run in runs} == {"FAILED"}

    retried = _track(report_dir)

    assert retried.exit_code == 0, retried.output
    assert retried.stdout.startswith("tracked: ")
    finished = client.search_runs(
        [experiment.experiment_id], filter_string="attributes.status = 'FINISHED'"
    )
    assert len(finished) == 3


def test_interrupt_marks_created_runs_failed_and_exits_130(workdir: Path) -> None:
    report_dir = _report_dir(workdir, "pl-eval", pl_report())

    with patch.object(MlflowClient, "log_artifact", side_effect=KeyboardInterrupt):
        interrupted = _track(report_dir)

    assert interrupted.exit_code == 130
    assert interrupted.stderr.strip().splitlines()[-1] == "model track-report failed: interrupted"
    client = _client(workdir)
    experiment = client.get_experiment_by_name("pl-evaluation")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert runs
    assert {run.info.status for run in runs} == {"FAILED"}


def test_failure_after_children_finished_marks_every_run_failed(workdir: Path) -> None:
    report_dir = _report_dir(workdir, "pl-eval", pl_report())
    original = MlflowClient.set_terminated
    finished_calls: list[str] = []

    def fail_on_parent(self: MlflowClient, run_id: str, status: str | None = None) -> None:
        if status == "FINISHED":
            finished_calls.append(run_id)
            # Two variant children finish first; the third FINISHED call is the parent.
            if len(finished_calls) == 3:
                raise RuntimeError("parent not finished")
        original(self, run_id, status)

    with patch.object(MlflowClient, "set_terminated", fail_on_parent):
        failed = _track(report_dir)

    assert failed.exit_code == 1
    assert (
        failed.stderr.strip().splitlines()[-1] == "model track-report failed: parent not finished"
    )
    client = _client(workdir)
    experiment = client.get_experiment_by_name("pl-evaluation")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 3
    assert {run.info.status for run in runs} == {"FAILED"}

    retried = _track(report_dir)

    assert retried.exit_code == 0, retried.output
    finished = client.search_runs(
        [experiment.experiment_id], filter_string="attributes.status = 'FINISHED'"
    )
    assert len(finished) == 3


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (("--database", "../elsewhere.db"), "--database must be inside"),
        (("--artifact-root", "artifacts"), "--artifact-root must be inside"),
        (
            ("--database", "output/same", "--artifact-root", "output/same"),
            "must be distinct",
        ),
    ],
)
def test_tracking_paths_outside_output_or_equal_are_rejected(
    workdir: Path, options: tuple[str, ...], message: str
) -> None:
    report_dir = _report_dir(workdir, "pl-eval", pl_report())

    result = _track(report_dir, *options)

    assert result.exit_code == 1
    assert message in result.stderr
    assert not (workdir / "output/mlflow").exists()
    assert not (workdir / "output/same").exists()


def test_missing_or_unsupported_report_is_rejected_before_mlflow(workdir: Path) -> None:
    empty = workdir / "output" / "empty"
    empty.mkdir()
    unsupported = backtest_report()
    unsupported["format_version"] = 1
    old = _report_dir(workdir, "old-backtest", unsupported)

    missing = _track(empty)
    rejected = _track(old)
    absent = _track(workdir / "output" / "absent")

    assert missing.exit_code == 1
    assert "--report-dir has no report.json" in missing.stderr
    assert rejected.exit_code == 1
    assert "unsupported report format 'ev_betting_backtest' v1" in rejected.stderr
    assert absent.exit_code == 1
    assert "--report-dir must be an existing directory" in absent.stderr
    assert not (workdir / "output/mlflow").exists()


def test_track_report_help_does_not_import_mlflow() -> None:
    script = """
import sys
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "track-report", "--help"])
assert result.exit_code == 0, result.output
for name in ("mlflow", "models.experiments.report_tracking"):
    assert name not in sys.modules, name
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "src",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
