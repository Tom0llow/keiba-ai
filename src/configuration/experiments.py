"""Compose and validate explicit Hydra experiment configurations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from zoneinfo import ZoneInfo

from hydra import compose, initialize_config_dir
from omegaconf import DictConfig, OmegaConf


@dataclass(frozen=True)
class TrackingConfig:
    """Describe one local SQLite tracking and registry store."""

    database: Path
    artifact_root: Path
    experiment_name: str
    registered_model_name: str

    @property
    def uri(self) -> str:
        """Return the absolute SQLAlchemy SQLite URI."""
        return f"sqlite:///{self.database.as_posix()}"


@dataclass(frozen=True)
class ExperimentConfig:
    """Hold validated paths and the resolved configuration recorded with each run."""

    action: Literal["train", "predict"]
    input_path: Path
    output_dir: Path
    tracking: TrackingConfig
    resolved: Mapping[str, object]
    parameters: Mapping[str, object]
    test_races: int
    version: str | None
    selection: str
    date_timezone: str


def load_experiment_config(
    config_dir: Path,
    *,
    action: Literal["train", "predict"],
    config_name: str | None = None,
    overrides: Sequence[str] = (),
) -> ExperimentConfig:
    """Compose YAML groups without changing cwd or instantiating configured objects.

    Relative data and output paths are resolved from the invoking working
    directory. Generated files must stay within its ignored ``output/`` tree.
    """
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        composed = compose(config_name=config_name or action, overrides=list(overrides))
        resolved_value = OmegaConf.to_container(composed, resolve=True, throw_on_missing=True)
    resolved = _mapping(resolved_value, "configuration")
    _keys(resolved, {"data", "model", "mlflow", "output_dir", "split"}, "configuration")
    data = _mapping(resolved.get("data"), "data")
    _keys(data, {"input", "selection", "date_timezone"}, "data")
    output_dir = _output_path(resolved.get("output_dir"), "output_dir")
    mlflow = _mapping(resolved.get("mlflow"), "mlflow")
    _keys(
        mlflow, {"database", "artifact_root", "experiment_name", "registered_model_name"}, "mlflow"
    )
    tracking = TrackingConfig(
        database=_output_path(mlflow.get("database"), "mlflow.database"),
        artifact_root=_output_path(mlflow.get("artifact_root"), "mlflow.artifact_root"),
        experiment_name=_string(mlflow.get("experiment_name"), "mlflow.experiment_name"),
        registered_model_name=_string(
            mlflow.get("registered_model_name"), "mlflow.registered_model_name"
        ),
    )
    if tracking.database == tracking.artifact_root:
        raise ValueError("MLflow database and artifact root must be distinct")
    model = _mapping(resolved.get("model"), "model")
    parameters: dict[str, object] = {}
    test_races = 0
    version = None
    selection = "all"
    date_timezone = "UTC"
    if action == "train":
        _keys(data, {"input"}, "training data")
        _keys(model, {"parameters"}, "training model")
        parameters = _mapping(model.get("parameters"), "model.parameters")
        if any(name.startswith("_") for name in parameters):
            raise ValueError("model.parameters cannot contain Hydra object directives")
        split = _mapping(resolved.get("split"), "split")
        _keys(split, {"test_races"}, "split")
        value = split.get("test_races")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("split.test_races must be a positive integer")
        test_races = value
    else:
        _keys(model, {"version"}, "prediction model")
        if "split" in resolved:
            raise ValueError("prediction configuration cannot contain split")
        raw_version = model.get("version")
        if isinstance(raw_version, bool) or not isinstance(raw_version, (int, str)):
            raise ValueError("model.version must be an exact positive integer version")
        version = str(raw_version)
        if not version.isascii() or not version.isdecimal() or int(version) < 1:
            raise ValueError("model.version must be an exact positive integer version")
        if version != str(int(version)):
            raise ValueError("model.version must use canonical integer notation")
        selection = _string(data.get("selection"), "data.selection")
        if selection not in {"all", "latest_date"}:
            raise ValueError("data.selection must be all or latest_date")
        date_timezone = _string(data.get("date_timezone"), "data.date_timezone")
        ZoneInfo(date_timezone)
    return ExperimentConfig(
        action=action,
        input_path=Path(_string(data.get("input"), "data.input")).expanduser().resolve(),
        output_dir=output_dir,
        tracking=tracking,
        resolved=resolved,
        parameters=parameters,
        test_races=test_races,
        version=version,
        selection=selection,
        date_timezone=date_timezone,
    )


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, (dict, DictConfig)) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name} must be a mapping with string keys")
    return dict(cast(Mapping[str, object], value))


def _keys(value: Mapping[str, object], allowed: set[str], name: str) -> None:
    unexpected = value.keys() - allowed
    if unexpected:
        raise ValueError(f"unexpected {name} keys: {sorted(unexpected)}")


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _output_path(value: object, name: str) -> Path:
    path = Path(_string(value, name)).expanduser().resolve()
    if not path.is_relative_to((Path.cwd() / "output").resolve()):
        raise ValueError(f"{name} must be inside the working directory's output/ tree")
    return path
