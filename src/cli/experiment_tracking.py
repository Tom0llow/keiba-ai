"""Record a published PL evaluation or betting backtest report in local MLflow (ADR-050)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from mlflow.entities import Metric
    from mlflow.tracking import MlflowClient

    from models.experiments.report_tracking import MetricValue, ReportRecord, RunRecord

_COMMAND = "model track-report"
# MLflow's per-request limits for log_batch.
_MAX_METRICS_PER_BATCH = 1000
_MAX_PARAMS_TAGS_PER_BATCH = 100


def model_track_report(
    report_dir: Annotated[Path, typer.Option("--report-dir")],
    database: Annotated[Path, typer.Option("--database")] = Path("output/mlflow/mlflow.db"),
    artifact_root: Annotated[Path, typer.Option("--artifact-root")] = Path(
        "output/mlflow/artifacts"
    ),
) -> None:
    """Record a published report.json as an MLflow run; the output directory is not changed."""
    # Keep MLflow out of imports and CLI help.
    from data.loader.file_hash import file_sha256
    from models.experiments.report_tracking import REPORT_FILE, report_record
    from models.experiments.tracking import active_experiment_id, local_client

    created: list[str] = []
    client: MlflowClient | None = None
    try:
        database_path = _tracking_path(database, "--database")
        artifact_path = _tracking_path(artifact_root, "--artifact-root")
        if database_path == artifact_path:
            raise ValueError("--database and --artifact-root must be distinct")
        if not report_dir.is_dir():
            raise ValueError("--report-dir must be an existing directory")
        source = report_dir.resolve()
        for option, path in (("--database", database_path), ("--artifact-root", artifact_path)):
            # The published output directory is read-only; MLflow must not write into it.
            if path.is_relative_to(source) or source.is_relative_to(path):
                raise ValueError(f"{option} must not overlap --report-dir")
        report_path = source / REPORT_FILE
        if not report_path.is_file():
            raise ValueError(f"--report-dir has no {REPORT_FILE}")
        files = {
            path.name: file_sha256(path) for path in sorted(source.iterdir()) if path.is_file()
        }
        record = report_record(report_path.read_bytes(), report_dir=str(source), file_sha256=files)
        client = local_client(database_path, artifact_path)
        experiment = active_experiment_id(client, record.experiment_name, artifact_path)
        existing = _finished_run(client, experiment, record)
        if existing is not None:
            typer.echo(f"already recorded: run_id={existing}")
            return
        parent_id = _start_run(client, experiment, record.parent, created, parent_id=None)
        child_ids = [
            _start_run(client, experiment, child, created, parent_id=parent_id)
            for child in record.children
        ]
        # Children finish first, so a finished parent always means a complete record.
        for run_id in (*child_ids, parent_id):
            client.set_terminated(run_id, "FINISHED")
    except KeyboardInterrupt as exc:
        _fail_runs(client, created)
        typer.echo(f"{_COMMAND} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, marks the runs it created FAILED and reports one line.
        _fail_runs(client, created)
        typer.echo(f"{_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"tracked: experiment={record.experiment_name} run_id={parent_id} children={len(child_ids)}"
    )


def _tracking_path(value: Path, option: str) -> Path:
    """Resolve a generated path; it must stay inside the working directory's output/ tree."""
    path = value.expanduser().resolve()
    if not path.is_relative_to((Path.cwd() / "output").resolve()):
        raise ValueError(f"{option} must be inside the working directory's output/ tree")
    return path


def _finished_run(client: MlflowClient, experiment: str, record: ReportRecord) -> str | None:
    """Return a finished parent run already holding this report, if any."""
    from models.experiments.report_tracking import PARENT_ROLE

    runs = client.search_runs(
        [experiment],
        filter_string=(
            f"tags.report_sha256 = '{record.report_sha256}' "
            f"and tags.run_role = '{PARENT_ROLE}' and attributes.status = 'FINISHED'"
        ),
        max_results=1,
    )
    return str(runs[0].info.run_id) if runs else None


def _start_run(
    client: MlflowClient,
    experiment: str,
    run: RunRecord,
    created: list[str],
    *,
    parent_id: str | None,
) -> str:
    """Create one run and log its tags, params, metrics and artifacts; leave it running."""
    from mlflow.entities import Param, RunTag

    tags = {} if parent_id is None else {"mlflow.parentRunId": parent_id}
    run_id = str(client.create_run(experiment, run_name=run.name, tags=tags).info.run_id)
    created.append(run_id)
    for chunk in _chunks(sorted(run.tags.items()), _MAX_PARAMS_TAGS_PER_BATCH):
        client.log_batch(run_id, tags=[RunTag(key, value) for key, value in chunk])
    for chunk in _chunks(sorted(run.params.items()), _MAX_PARAMS_TAGS_PER_BATCH):
        client.log_batch(run_id, params=[Param(key, value) for key, value in chunk])
    timestamp = int(time() * 1000)
    for metric_chunk in _chunks(run.metrics, _MAX_METRICS_PER_BATCH):
        client.log_batch(run_id, metrics=_metrics(metric_chunk, timestamp))
    if run.artifacts:
        with TemporaryDirectory() as staging:
            for name, data in sorted(run.artifacts.items()):
                path = Path(staging) / name
                path.write_bytes(data)
                client.log_artifact(run_id, str(path))
    return run_id


def _metrics(values: Sequence[MetricValue], timestamp: int) -> list[Metric]:
    from mlflow.entities import Metric

    return [Metric(item.key, item.value, timestamp, item.step) for item in values]


def _chunks[T](values: Sequence[T], size: int) -> list[Sequence[T]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _fail_runs(client: MlflowClient | None, run_ids: Sequence[str]) -> None:
    """Mark created runs FAILED so a later attempt can record the same report again."""
    if client is None:
        return
    for run_id in run_ids:
        try:
            client.set_terminated(run_id, "FAILED")
        except Exception as exc:  # keep the original error as the reported one
            typer.echo(f"{_COMMAND}: could not mark run {run_id} FAILED: {exc}", err=True)
