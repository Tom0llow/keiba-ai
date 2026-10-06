"""LightGBM ranking model and native model persistence."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

from models.ranking_dataset import (
    TIE_BREAK_RULE,
    FeatureRow,
    FeatureSchema,
    FeatureSpec,
    FeatureValueType,
    MissingValuePolicy,
    _validate_feature_names,
    validate_feature_rows,
)

_MODEL_FORMAT_VERSION = 2
_OBJECTIVE = "lambdarank"
_LABEL_GAIN = (0, 1, 3, 7)
_HASH_CHUNK_SIZE = 1024 * 1024


class LightGBMUnavailableError(ImportError):
    """Indicate that the optional LightGBM dependency is not installed."""


class _NativeBooster(Protocol):
    params: Mapping[str, object]

    def predict(self, data: object) -> object:
        """Return raw model scores."""

    def feature_name(self) -> object:
        """Return the native model feature names."""

    def save_model(self, filename: str) -> object:
        """Write the LightGBM native model format."""


class _LightGBMRanker(Protocol):
    booster_: _NativeBooster

    def fit(
        self,
        features: object,
        labels: object,
        *,
        group: Sequence[int],
        feature_name: Sequence[str],
    ) -> object:
        """Fit the ranker."""


@dataclass(frozen=True)
class RankingPrediction:
    """Return one finite score and its deterministic race-local rank."""

    race_id: str
    horse_id: str
    score: float
    rank: int


@dataclass(frozen=True)
class RankingModel:
    """Wrap a native LightGBM booster for score-only ranking inference."""

    _booster: _NativeBooster
    feature_names: tuple[str, ...]
    feature_schema: FeatureSchema
    objective: str = _OBJECTIVE
    tie_break_rule: str = TIE_BREAK_RULE

    def __post_init__(self) -> None:
        """Validate the fixed model contract."""
        _validate_feature_names(self.feature_names)
        if self.feature_schema.feature_names != self.feature_names:
            raise ValueError("feature_schema names must match feature_names")
        if self.objective != _OBJECTIVE:
            raise ValueError(f"objective must be {_OBJECTIVE!r}")
        if self.tie_break_rule != TIE_BREAK_RULE:
            raise ValueError(f"tie_break_rule must be {TIE_BREAK_RULE!r}")
        _validate_native_booster(self._booster, self.feature_names)

    @classmethod
    def from_native_booster(
        cls,
        booster: _NativeBooster,
        feature_names: Sequence[str],
        feature_schema: FeatureSchema,
    ) -> RankingModel:
        """Create a model wrapper around a trained native booster."""
        names = tuple(feature_names)
        if feature_schema.feature_names != names:
            raise ValueError("feature_schema names must match feature_names")
        return cls(booster, names, feature_schema)

    def predict_scores(
        self,
        rows: Sequence[FeatureRow],
        *,
        feature_schema: FeatureSchema | None = None,
    ) -> tuple[float, ...]:
        """Return finite LightGBM scores in the input row order."""
        schema = feature_schema or self.feature_schema
        if schema != self.feature_schema:
            raise ValueError("feature_schema does not match the trained model")
        normalized = validate_feature_rows(rows, self.feature_names)
        raw_scores = self._booster.predict(
            [[row.features.get(name) for name in self.feature_names] for row in normalized]
        )
        values = cast(Sequence[object], raw_scores)
        if len(values) != len(normalized):
            raise ValueError("LightGBM returned an unexpected number of scores")
        scores = tuple(_finite_score(value) for value in values)
        return scores

    def predict(
        self,
        rows: Sequence[FeatureRow],
        *,
        feature_schema: FeatureSchema | None = None,
    ) -> tuple[RankingPrediction, ...]:
        """Return only race-local finite scores and ranks for all input rows."""
        normalized = validate_feature_rows(rows, self.feature_names)
        scores = self.predict_scores(normalized, feature_schema=feature_schema)
        predictions: list[RankingPrediction] = []
        start = 0
        for group_size in _race_groups(normalized):
            race_rows = normalized[start : start + group_size]
            race_scores = scores[start : start + group_size]
            order = sorted(
                range(group_size),
                key=lambda index: (-race_scores[index], race_rows[index].horse_id),
            )
            for rank, row_index in enumerate(order, start=1):
                row = race_rows[row_index]
                predictions.append(
                    RankingPrediction(
                        race_id=row.race_id,
                        horse_id=row.horse_id,
                        score=race_scores[row_index],
                        rank=rank,
                    )
                )
            start += group_size
        return tuple(predictions)

    def save(self, path: Path) -> None:
        """Save the native booster and JSON schema metadata without pickle."""
        if path.exists() and path.is_dir():
            raise IsADirectoryError(path)
        metadata_path = _metadata_path(path)
        ready_path = _ready_path(path)
        publishing_path = _publishing_path(path)
        if ready_path.exists():
            if publishing_path.exists():
                with suppress(FileNotFoundError):
                    publishing_path.unlink()
                return
            raise FileExistsError(ready_path)
        if publishing_path.exists():
            _recover_incomplete_artifact(path, metadata_path, publishing_path)
        if path.exists():
            raise FileExistsError(path)
        if metadata_path.exists():
            raise FileExistsError(metadata_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_model_path: Path | None = None
        temporary_metadata_path: Path | None = None
        temporary_publishing_path: Path | None = None
        try:
            temporary_publishing_path = _temporary_path(publishing_path)
            with temporary_publishing_path.open("w", encoding="ascii", newline="\n") as marker:
                marker.write("publishing\n")
                marker.flush()
                os.fsync(marker.fileno())
            _publish_new_file(temporary_publishing_path, publishing_path)
            temporary_publishing_path = None
            temporary_model_path = _temporary_path(path)
            self._booster.save_model(str(temporary_model_path))
            _fsync_file(temporary_model_path)
            metadata_payload = {
                "feature_schema": self.feature_schema.as_metadata(),
                "feature_names": list(self.feature_names),
                "format_version": _MODEL_FORMAT_VERSION,
                "native_sha256": _sha256_file(temporary_model_path),
                "objective": self.objective,
                "tie_break_rule": self.tie_break_rule,
            }
            metadata = {
                **metadata_payload,
                "metadata_sha256": _sha256_metadata_payload(metadata_payload),
            }
            temporary_metadata_path = _temporary_path(metadata_path)
            with temporary_metadata_path.open("w", encoding="utf-8", newline="\n") as metadata_file:
                metadata_file.write(
                    json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                    + "\n"
                )
                metadata_file.flush()
                os.fsync(metadata_file.fileno())
            _publish_new_file(temporary_model_path, path)
            temporary_model_path = None
            _publish_new_file(temporary_metadata_path, metadata_path)
            temporary_metadata_path = None
            _publish_ready_marker(ready_path)
        finally:
            for temporary_path in (
                temporary_model_path,
                temporary_metadata_path,
                temporary_publishing_path,
            ):
                if temporary_path is not None:
                    with suppress(FileNotFoundError):
                        temporary_path.unlink()
        with suppress(FileNotFoundError):
            publishing_path.unlink()

    @classmethod
    def load(cls, path: Path) -> RankingModel:
        """Load a native LightGBM model after validating its JSON metadata."""
        if not path.is_file():
            raise FileNotFoundError(path)
        metadata_path = _metadata_path(path)
        if not metadata_path.is_file():
            raise FileNotFoundError(metadata_path)
        ready_path = _ready_path(path)
        if not ready_path.is_file():
            raise FileNotFoundError(ready_path)
        metadata = _read_metadata(metadata_path)
        if _sha256_metadata_payload(metadata) != _metadata_payload_sha256(metadata):
            raise ValueError("model metadata does not match its digest")
        if _sha256_file(path) != _metadata_sha256(metadata):
            raise ValueError("native model does not match metadata")
        objective = _metadata_string(metadata, "objective")
        if objective != _OBJECTIVE:
            raise ValueError(f"model metadata objective must be {_OBJECTIVE!r}")
        tie_break_rule = _metadata_string(metadata, "tie_break_rule")
        if tie_break_rule != TIE_BREAK_RULE:
            raise ValueError(f"model metadata tie_break_rule must be {TIE_BREAK_RULE!r}")
        feature_names = _metadata_feature_names(metadata)
        feature_schema = _metadata_feature_schema(metadata, feature_names)
        module = _load_lightgbm()
        booster_constructor = cast(Callable[..., object], module.__dict__["Booster"])
        booster = cast(_NativeBooster, booster_constructor(model_file=str(path)))
        _validate_native_booster(booster, feature_names)
        return cls(
            _booster=booster,
            feature_names=feature_names,
            feature_schema=feature_schema,
            objective=objective,
            tie_break_rule=tie_break_rule,
        )


def _load_lightgbm() -> ModuleType:
    try:
        return importlib.import_module("lightgbm")
    except ImportError as exc:
        raise LightGBMUnavailableError(
            "LightGBM is required for training, prediction, and model loading"
        ) from exc


def _metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.metadata.json")


def _ready_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.ready")


def _publishing_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.publishing")


def _recover_incomplete_artifact(
    path: Path,
    metadata_path: Path,
    publishing_path: Path,
) -> None:
    """Remove only the files owned by an interrupted publication."""
    for artifact_path in (path, metadata_path, publishing_path):
        with suppress(FileNotFoundError):
            artifact_path.unlink()


def _temporary_path(path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return Path(name)


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as file:
        os.fsync(file.fileno())


def _publish_new_file(temporary_path: Path, destination: Path) -> None:
    """Publish a new artifact without replacing an existing destination."""
    os.link(temporary_path, destination)
    temporary_path.unlink()


def _publish_ready_marker(path: Path) -> None:
    temporary_path: Path | None = _temporary_path(path)
    try:
        assert temporary_path is not None
        with temporary_path.open("w", encoding="ascii", newline="\n") as marker:
            marker.write("ready\n")
            marker.flush()
            os.fsync(marker.fileno())
        _publish_new_file(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            with suppress(FileNotFoundError):
                temporary_path.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_metadata_payload(metadata: Mapping[str, object]) -> str:
    payload = {key: value for key, value in metadata.items() if key != "metadata_sha256"}
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


def _read_metadata(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("model metadata must be a JSON object")
    metadata = cast(dict[str, object], value)
    if metadata.get("format_version") != _MODEL_FORMAT_VERSION:
        raise ValueError("unsupported model metadata format")
    return metadata


def _metadata_feature_names(metadata: Mapping[str, object]) -> tuple[str, ...]:
    value = metadata.get("feature_names")
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        raise ValueError("model metadata has invalid feature_names")
    names = tuple(cast(list[str], value))
    try:
        _validate_feature_names(names)
    except ValueError as exc:
        raise ValueError("model metadata has invalid feature_names") from exc
    return names


def _metadata_feature_schema(
    metadata: Mapping[str, object],
    feature_names: Sequence[str],
) -> FeatureSchema:
    value = metadata.get("feature_schema")
    if not isinstance(value, dict):
        raise ValueError("model metadata has invalid feature_schema")
    schema_data = cast(dict[str, object], value)
    schema_id = schema_data.get("schema_id")
    raw_features = schema_data.get("features")
    if not isinstance(schema_id, str) or not isinstance(raw_features, list):
        raise ValueError("model metadata has invalid feature_schema")
    specs: list[FeatureSpec] = []
    try:
        for raw_feature in raw_features:
            if not isinstance(raw_feature, dict):
                raise ValueError("feature schema entries must be objects")
            feature = cast(dict[str, object], raw_feature)
            specs.append(
                FeatureSpec(
                    name=cast(str, feature.get("name")),
                    generation_rule=cast(str, feature.get("generation_rule")),
                    result_derived=cast(bool, feature.get("result_derived")),
                    value_type=cast(FeatureValueType, feature.get("value_type")),
                    unit=cast(str | None, feature.get("unit")),
                    missing_value_policy=cast(
                        MissingValuePolicy, feature.get("missing_value_policy")
                    ),
                )
            )
        schema = FeatureSchema(schema_id=schema_id, features=tuple(specs))
    except (TypeError, ValueError) as exc:
        raise ValueError("model metadata has invalid feature_schema") from exc
    if schema.feature_names != tuple(feature_names):
        raise ValueError("model metadata feature_schema names do not match feature_names")
    return schema


def _native_feature_names(booster: _NativeBooster) -> tuple[str, ...]:
    value = booster.feature_name()
    if not isinstance(value, Sequence) or not all(isinstance(name, str) for name in value):
        raise ValueError("native model has invalid feature names")
    return tuple(cast(Sequence[str], value))


def _validate_native_booster(
    booster: _NativeBooster,
    feature_names: Sequence[str],
) -> None:
    if _native_feature_names(booster) != tuple(feature_names):
        raise ValueError("native model feature names do not match metadata")
    parameters = booster.params
    if parameters.get("objective") != _OBJECTIVE:
        raise ValueError(f"native model objective must be {_OBJECTIVE!r}")
    label_gain = parameters.get("label_gain")
    if not isinstance(label_gain, Sequence) or isinstance(label_gain, (str, bytes)):
        raise ValueError("native model has invalid label_gain")
    if tuple(label_gain) != _LABEL_GAIN:
        raise ValueError("native model label_gain does not match the MVP contract")


def _metadata_string(metadata: Mapping[str, object], name: str) -> str:
    value = metadata.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"model metadata has invalid {name}")
    return value


def _metadata_sha256(metadata: Mapping[str, object]) -> str:
    return _validated_sha256(metadata, "native_sha256")


def _metadata_payload_sha256(metadata: Mapping[str, object]) -> str:
    return _validated_sha256(metadata, "metadata_sha256")


def _validated_sha256(metadata: Mapping[str, object], name: str) -> str:
    value = metadata.get(name)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"model metadata has invalid {name}")
    return value


def _finite_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("LightGBM returned a non-numeric score")
    score = float(value)
    if not isfinite(score):
        raise ValueError("LightGBM returned a non-finite score")
    return score


def _race_groups(rows: Sequence[FeatureRow]) -> tuple[int, ...]:
    groups: list[int] = []
    current_race: str | None = None
    for row in rows:
        if row.race_id != current_race:
            groups.append(1)
            current_race = row.race_id
        else:
            groups[-1] += 1
    return tuple(groups)
