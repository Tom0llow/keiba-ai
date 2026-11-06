"""Use a local MLflow client for runs, native artifacts and exact model versions."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from configuration.experiments import TrackingConfig

if TYPE_CHECKING:
    from mlflow.tracking import MlflowClient


def local_tracking_client(config: TrackingConfig) -> MlflowClient:
    """Create an explicit SQLite client without global tracking URI state."""
    # Local experiment tracking does not need background telemetry or external services.
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    from mlflow.tracking import MlflowClient

    config.database.parent.mkdir(parents=True, exist_ok=True)
    config.artifact_root.mkdir(parents=True, exist_ok=True)
    return MlflowClient(tracking_uri=config.uri, registry_uri=config.uri)


def experiment_id(client: MlflowClient, config: TrackingConfig) -> str:
    """Get or create an experiment with an explicitly local artifact location."""
    from mlflow.exceptions import MlflowException

    experiment = client.get_experiment_by_name(config.experiment_name)
    if experiment is None:
        try:
            return client.create_experiment(
                config.experiment_name, artifact_location=config.artifact_root.as_uri()
            )
        except MlflowException as exc:
            if exc.error_code != "RESOURCE_ALREADY_EXISTS":
                raise
            experiment = client.get_experiment_by_name(config.experiment_name)
    if experiment is None or experiment.lifecycle_stage != "active":
        raise ValueError("MLflow experiment must exist and be active")
    if experiment.artifact_location != config.artifact_root.as_uri():
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
