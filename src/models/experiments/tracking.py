"""Use a local MLflow client for runs, native artifacts and exact model versions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from configuration.experiments import TrackingConfig

if TYPE_CHECKING:
    from mlflow.tracking import MlflowClient


def local_tracking_client(config: TrackingConfig) -> MlflowClient:
    """Create an explicit SQLite client without global tracking URI state."""
    return local_client(config.database, config.artifact_root)


def local_client(database: Path, artifact_root: Path) -> MlflowClient:
    """Create a SQLite tracking and registry client for explicit local paths."""
    # Local experiment tracking does not need background telemetry or external services.
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    from mlflow.tracking import MlflowClient

    database.parent.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    uri = f"sqlite:///{database.as_posix()}"
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def experiment_id(client: MlflowClient, config: TrackingConfig) -> str:
    """Get or create an experiment with an explicitly local artifact location."""
    return active_experiment_id(client, config.experiment_name, config.artifact_root)


def active_experiment_id(client: MlflowClient, name: str, artifact_root: Path) -> str:
    """Get or create the named active experiment whose artifacts live under ``artifact_root``."""
    from mlflow.exceptions import MlflowException

    experiment = client.get_experiment_by_name(name)
    if experiment is None:
        try:
            return client.create_experiment(name, artifact_location=artifact_root.as_uri())
        except MlflowException as exc:
            if exc.error_code != "RESOURCE_ALREADY_EXISTS":
                raise
            experiment = client.get_experiment_by_name(name)
    if experiment is None or experiment.lifecycle_stage != "active":
        raise ValueError("MLflow experiment must exist and be active")
    if experiment.artifact_location != artifact_root.as_uri():
        raise ValueError("existing MLflow experiment artifact location differs from configuration")
    return str(experiment.experiment_id)


def ensure_registered_model(client: MlflowClient, name: str) -> None:
    """Create the named registry entry, preserving all its existing versions."""
    from mlflow.exceptions import MlflowException

    try:
        client.create_registered_model(name)
    except MlflowException as exc:
        if exc.error_code != "RESOURCE_ALREADY_EXISTS":
            raise
