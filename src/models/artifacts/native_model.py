"""Publish, validate, and recover native model artifacts as one complete set."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from models.backends.lightgbm import NativeBooster, load_native_booster, validate_native_booster
from models.dataset.rows import FeatureValueType, MissingValuePolicy
from models.dataset.schema import FeatureSchema, FeatureSpec, validate_feature_names
from models.ranking.rules import LABEL_GAIN, OBJECTIVE, TIE_BREAK_RULE

_MODEL_FORMAT_VERSION = 3
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class NativeModelContents:
    """Hold the validated booster and metadata loaded from a native artifact."""

    booster: NativeBooster
    feature_schema: FeatureSchema
    objective: str
    tie_break_rule: str


@dataclass(frozen=True)
class NativeModelArtifact:
    """Own native model files, metadata, and publication markers at one path."""

    path: Path

    def save(self, booster: NativeBooster, feature_schema: FeatureSchema) -> None:
        """Save the native booster and JSON schema metadata without pickle."""
        validate_native_booster(booster, feature_schema.feature_names)
        path = self.path
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
            booster.save_model(str(temporary_model_path))
            _fsync_file(temporary_model_path)
            metadata_payload = {
                "feature_schema": feature_schema.as_metadata(),
                "feature_names": list(feature_schema.feature_names),
                "format_version": _MODEL_FORMAT_VERSION,
                "label_gain": list(LABEL_GAIN),
                "native_sha256": _sha256_file(temporary_model_path),
                "objective": OBJECTIVE,
                "tie_break_rule": TIE_BREAK_RULE,
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

    def load(self) -> NativeModelContents:
        """Load a native LightGBM model after validating its JSON metadata."""
        path = self.path
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
        if objective != OBJECTIVE:
            raise ValueError(f"model metadata objective must be {OBJECTIVE!r}")
        _metadata_label_gain(metadata)
        tie_break_rule = _metadata_string(metadata, "tie_break_rule")
        if tie_break_rule != TIE_BREAK_RULE:
            raise ValueError(f"model metadata tie_break_rule must be {TIE_BREAK_RULE!r}")
        feature_names = _metadata_feature_names(metadata)
        feature_schema = _metadata_feature_schema(metadata, feature_names)
        booster = load_native_booster(path, feature_names)
        return NativeModelContents(booster, feature_schema, objective, tie_break_rule)


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
        validate_feature_names(names)
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


def _metadata_string(metadata: Mapping[str, object], name: str) -> str:
    value = metadata.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"model metadata has invalid {name}")
    return value


def _metadata_label_gain(metadata: Mapping[str, object]) -> tuple[int, ...]:
    value = metadata.get("label_gain")
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise ValueError("model metadata has invalid label_gain")
    label_gain = tuple(cast(list[int], value))
    if label_gain != LABEL_GAIN:
        raise ValueError("model metadata label_gain does not match the MVP contract")
    return label_gain


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
