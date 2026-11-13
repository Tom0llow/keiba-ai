"""Write, validate and use the final top-three PL model artifact (ADR-038).

An artifact is one directory with exactly ``model.txt`` (the LightGBM native text model
cut at its best iteration) and ``manifest.json``. The manifest is identified by the
SHA-256 of its bytes; every reader passes that identity explicitly. This module owns its
small byte I/O, as ``native_model.py`` does, and imports neither ``data`` nor the CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from math import isfinite
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt

from models.backends.lightgbm import (
    LoadedPLBooster,
    PLBooster,
    load_pl_booster,
    split_missing_types,
    validate_pl_parameters,
)
from models.probability.plackett_luce import (
    MarginalProbabilities,
    RaceLayout,
    top3_marginal_probabilities,
)

FORMAT = "pl_top3_model"
FORMAT_VERSION = 1
OBJECTIVE = "top3_plackett_luce"
MODEL_FILE = "model.txt"
MANIFEST_FILE = "manifest.json"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TOP_KEYS = frozenset(
    {
        "format",
        "format_version",
        "model",
        "features",
        "temperature",
        "training",
        "source_datamart",
        "provenance",
        "config",
    }
)
_MODEL_KEYS = frozenset(
    {
        "file",
        "sha256",
        "objective",
        "best_iteration",
        "best_valid_nll",
        "num_boost_round",
        "early_stopping_rounds",
        "lightgbm",
        "lightgbm_version",
        "numpy_version",
    }
)
_FEATURE_KEYS = frozenset({"columns", "variant", "excluded_columns", "nullable_in_training"})
_TEMPERATURE_KEYS = frozenset(
    {"value", "bounds", "raw_valid_nll", "calibrated_valid_nll", "at_bound"}
)
_TRAINING_KEYS = frozenset(
    {
        "train_start_year",
        "valid_year",
        "train_races",
        "train_rows",
        "valid_races",
        "valid_rows",
        "purged_train_races",
        "valid_first_freeze_at",
        "train_max_label_usable_after",
        "valid_max_label_usable_after",
        "label_usable_through",
    }
)
# The same binding the label-free prediction features carry (ADR-036), plus the
# closed numeric column definitions.
_SOURCE_KEYS = frozenset(
    {
        "manifest_sha256",
        "contract_sha256",
        "target_period",
        "label_usable_through",
        "provenance_source_sha256",
        "columns",
    }
)
_BINDING_KEYS = (
    "manifest_sha256",
    "contract_sha256",
    "target_period",
    "provenance_source_sha256",
)
_COLUMN_KEYS = frozenset({"name", "group", "column", "meaning", "unit"})


@dataclass(frozen=True)
class PLModelRecord:
    """Hold everything a final PL model artifact records besides the native model."""

    feature_names: tuple[str, ...]
    nullable_in_training: tuple[bool, ...]
    variant: str
    excluded_columns: tuple[str, ...]
    best_iteration: int
    best_valid_nll: float
    num_boost_round: int
    early_stopping_rounds: int
    lightgbm: Mapping[str, object]
    temperature: float
    temperature_bounds: tuple[float, float]
    raw_valid_nll: float
    calibrated_valid_nll: float
    temperature_at_bound: bool
    train_start_year: int
    valid_year: int
    train_races: int
    train_rows: int
    valid_races: int
    valid_rows: int
    purged_train_races: int
    valid_first_freeze_at: datetime
    train_max_label_usable_after: datetime
    valid_max_label_usable_after: datetime
    label_usable_through: datetime
    source_datamart: Mapping[str, object]
    provenance: Mapping[str, object]
    config: Mapping[str, object]


@dataclass(frozen=True)
class PLModel:
    """A validated final PL model: label-free scores, probabilities and binding checks."""

    manifest_sha256: str
    manifest: Mapping[str, object]
    feature_names: tuple[str, ...]
    nullable_in_training: tuple[bool, ...]
    temperature: float
    label_usable_through: datetime
    booster: LoadedPLBooster

    def predict_scores(
        self, features: npt.ArrayLike, feature_names: Sequence[str]
    ) -> npt.NDArray[np.float64]:
        """Return finite raw scores for rows whose columns follow ``feature_names``.

        Raises:
            ValueError: If the names or order differ from the model, the matrix shape is
                wrong, a column holds an infinite value (training rejects them), or a
                column without missing values in training has one here (LightGBM would
                score it as zero without an error), or LightGBM returns invalid scores.
        """
        if tuple(feature_names) != self.feature_names:
            raise ValueError("feature names or their order differ from the PL model")
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("PL features must be a two-dimensional matrix of the model columns")
        infinite = np.isinf(matrix).any(axis=0)
        unbounded = [
            name for name, found in zip(self.feature_names, infinite, strict=True) if found
        ]
        if unbounded:
            raise ValueError(f"PL features contain infinite values: {unbounded!r}")
        missing = np.isnan(matrix).any(axis=0)
        rejected = [
            name
            for name, nullable, has_missing in zip(
                self.feature_names, self.nullable_in_training, missing, strict=True
            )
            if has_missing and not nullable
        ]
        if rejected:
            raise ValueError(f"PL features miss values that training never missed: {rejected!r}")
        scores = np.asarray(self.booster.predict(matrix), dtype=np.float64)
        if scores.shape != (matrix.shape[0],) or not np.all(np.isfinite(scores)):
            raise ValueError("LightGBM returned invalid PL scores")
        return scores

    def probabilities(
        self, scores: npt.ArrayLike, group_sizes: Sequence[int]
    ) -> MarginalProbabilities:
        """Return calibrated win, top-two and top-three probabilities per horse."""
        values = np.asarray(scores, dtype=np.float64)
        layout = RaceLayout.from_group_sizes(list(group_sizes))
        if sum(group_sizes) != values.shape[0]:
            raise ValueError("PL group sizes do not cover every score")
        return top3_marginal_probabilities(values, layout, temperature=self.temperature)

    def require_compatible_features(self, prediction_manifest: Mapping[str, object]) -> None:
        """Require prediction features built from this model's training datamart.

        The features' ``source_datamart`` (ADR-036) must name the same datamart,
        contract, period, label boundary and source digest, and their closed numeric
        column definitions must equal the model's.
        """
        source = cast(Mapping[str, object], self.manifest["source_datamart"])
        binding = prediction_manifest.get("source_datamart")
        if not isinstance(binding, Mapping):
            raise ValueError("prediction features have no source datamart binding")
        for key in _BINDING_KEYS:
            if binding.get(key) != source[key]:
                raise ValueError(f"prediction features differ from the PL model in {key}")
        through = binding.get("label_usable_through")
        try:
            prediction_through = datetime.fromisoformat(cast(str, through))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "prediction features label_usable_through must be an ISO 8601 clock"
            ) from exc
        if prediction_through.utcoffset() is None:
            raise ValueError("prediction features label_usable_through must be timezone-aware")
        if prediction_through != _utc(source["label_usable_through"], "label_usable_through"):
            raise ValueError("prediction features differ from the PL model in label_usable_through")
        if prediction_manifest.get("columns") != source["columns"]:
            raise ValueError("prediction feature columns differ from the PL model")

    def require_prediction_after(self, freeze_at: datetime) -> None:
        """Require a freeze strictly after every label the model used (ADR-035/038)."""
        if not isinstance(freeze_at, datetime) or freeze_at.utcoffset() is None:
            raise ValueError("prediction freeze_at must be a timezone-aware datetime")
        if freeze_at <= self.label_usable_through:
            raise ValueError(
                "prediction freeze_at must be after the PL model label boundary "
                f"{self.label_usable_through.isoformat()}"
            )


def write_pl_model(directory: Path, record: PLModelRecord, booster: PLBooster) -> str:
    """Write the artifact into an existing empty directory and return its manifest SHA-256.

    Before any file is written, the manifest built from ``record`` is validated with
    the reader's manifest rules and serialized as strict JSON, so a record whose
    manifest the reader would reject leaves the directory empty. The writer does not
    compare the record with the booster beyond the missing-value branches; the
    caller reads the written artifact back to check that. An I/O failure while
    writing can leave part of the artifact behind; the caller owns the directory,
    removes it on failure and publishes it on success (the CLI uses a staging
    directory for both).

    Raises:
        ValueError: If the directory is missing or not empty, the booster dump is
            malformed or does not match the record's columns, a column missing in
            training splits without a missing-value branch, or the manifest built from
            the record (including its clocks) is invalid or not strict JSON.
    """
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("PL model staging must be an existing empty directory")
    _require_missing_branches(
        booster.dump_model(num_iteration=record.best_iteration),
        record.feature_names,
        record.nullable_in_training,
    )
    # The model digest is unknown until model.txt exists; a well-formed placeholder
    # lets every record-derived field be validated and serialized first.
    _manifest_payload(_manifest(record, "0" * 64))
    model_path = directory / MODEL_FILE
    booster.save_model(str(model_path), num_iteration=record.best_iteration)
    _fsync(model_path)
    payload = _manifest_payload(
        _manifest(record, hashlib.sha256(model_path.read_bytes()).hexdigest())
    )
    with (directory / MANIFEST_FILE).open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def read_pl_model(path: Path, *, expected_manifest_sha256: str) -> PLModel:
    """Read and validate a PL model artifact pinned by its manifest SHA-256.

    Raises:
        ValueError: If the identity, the file set, the manifest, the native model hash,
            the running LightGBM version, the feature names or the iteration count
            differ from what the manifest records, or a column that accepts missing
            values splits without a missing-value branch.
    """
    if not isinstance(expected_manifest_sha256, str) or not _HEX64.fullmatch(
        expected_manifest_sha256
    ):
        raise ValueError("expected_manifest_sha256 must be 64 lowercase hex digits")
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("PL model path must be a directory")
    if sorted(item.name for item in root.iterdir()) != sorted((MANIFEST_FILE, MODEL_FILE)):
        raise ValueError("PL model directory must hold exactly model.txt and manifest.json")
    manifest_bytes = (root / MANIFEST_FILE).read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
        raise ValueError("PL model manifest SHA-256 differs from the expected identity")
    try:
        manifest = json.loads(manifest_bytes, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PL model manifest is not valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("PL model manifest must be a JSON object")
    _validate_manifest(manifest)
    model = cast(dict[str, object], manifest["model"])
    running = version("lightgbm")
    if model["lightgbm_version"] != running:
        raise ValueError(
            f"PL model was trained with LightGBM {model['lightgbm_version']}, not {running}"
        )
    model_bytes = (root / MODEL_FILE).read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != model["sha256"]:
        raise ValueError("PL native model SHA-256 differs from its manifest")
    features = cast(dict[str, object], manifest["features"])
    names = tuple(cast(list[str], features["columns"]))
    booster = load_pl_booster(model_bytes.decode("utf-8"), names)
    if booster.current_iteration() != model["best_iteration"]:
        raise ValueError("PL native model iterations differ from its best_iteration")
    nullable = tuple(cast(list[bool], features["nullable_in_training"]))
    _require_missing_branches(booster.dump_model(), names, nullable)
    temperature = cast(dict[str, object], manifest["temperature"])
    training = cast(dict[str, object], manifest["training"])
    return PLModel(
        manifest_sha256=expected_manifest_sha256,
        manifest=manifest,
        feature_names=names,
        nullable_in_training=nullable,
        temperature=cast(float, temperature["value"]),
        label_usable_through=_utc(training["label_usable_through"], "label_usable_through"),
        booster=booster,
    )


def _manifest(record: PLModelRecord, model_sha256: str) -> dict[str, object]:
    lower, upper = record.temperature_bounds
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "model": {
            "file": MODEL_FILE,
            "sha256": model_sha256,
            "objective": OBJECTIVE,
            "best_iteration": record.best_iteration,
            "best_valid_nll": record.best_valid_nll,
            "num_boost_round": record.num_boost_round,
            "early_stopping_rounds": record.early_stopping_rounds,
            "lightgbm": dict(record.lightgbm),
            "lightgbm_version": version("lightgbm"),
            "numpy_version": np.__version__,
        },
        "features": {
            "columns": list(record.feature_names),
            "variant": record.variant,
            "excluded_columns": list(record.excluded_columns),
            "nullable_in_training": list(record.nullable_in_training),
        },
        "temperature": {
            "value": record.temperature,
            "bounds": [lower, upper],
            "raw_valid_nll": record.raw_valid_nll,
            "calibrated_valid_nll": record.calibrated_valid_nll,
            "at_bound": record.temperature_at_bound,
        },
        "training": {
            "train_start_year": record.train_start_year,
            "valid_year": record.valid_year,
            "train_races": record.train_races,
            "train_rows": record.train_rows,
            "valid_races": record.valid_races,
            "valid_rows": record.valid_rows,
            "purged_train_races": record.purged_train_races,
            "valid_first_freeze_at": _iso(record.valid_first_freeze_at),
            "train_max_label_usable_after": _iso(record.train_max_label_usable_after),
            "valid_max_label_usable_after": _iso(record.valid_max_label_usable_after),
            "label_usable_through": _iso(record.label_usable_through),
        },
        "source_datamart": dict(record.source_datamart),
        "provenance": dict(record.provenance),
        "config": dict(record.config),
    }


def _manifest_payload(manifest: Mapping[str, object]) -> bytes:
    """Validate the manifest and return its ASCII JSON bytes (sorted keys, no NaN)."""
    _validate_manifest(manifest)
    try:
        text = json.dumps(manifest, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"PL model manifest is not strict JSON: {exc}") from exc
    return (text + "\n").encode("ascii")


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    _keys(manifest, _TOP_KEYS, "manifest")
    if manifest["format"] != FORMAT or manifest["format_version"] != FORMAT_VERSION:
        raise ValueError("unsupported PL model format or format_version")
    model = _keys(manifest["model"], _MODEL_KEYS, "model")
    if model["file"] != MODEL_FILE or model["objective"] != OBJECTIVE:
        raise ValueError("PL model file or objective differs from the format")
    _hex64(model["sha256"], "model.sha256")
    best = _integer(model["best_iteration"], "best_iteration")
    rounds = _integer(model["num_boost_round"], "num_boost_round")
    _integer(model["early_stopping_rounds"], "early_stopping_rounds")
    if not 1 <= best <= rounds:
        raise ValueError("PL model best_iteration must lie in 1..num_boost_round")
    _number(model["best_valid_nll"], "best_valid_nll")
    if not isinstance(model["lightgbm"], dict):
        raise ValueError("PL model lightgbm parameters must be an object")
    validate_pl_parameters(cast(dict[str, object], model["lightgbm"]))
    for name in ("lightgbm_version", "numpy_version"):
        if not isinstance(model[name], str) or not model[name]:
            raise ValueError(f"PL model {name} must be a nonempty string")

    source = _keys(manifest["source_datamart"], _SOURCE_KEYS, "source_datamart")
    for name in ("manifest_sha256", "contract_sha256", "provenance_source_sha256"):
        _hex64(source[name], f"source_datamart.{name}")
    period = _keys(source["target_period"], frozenset({"start", "end"}), "target_period")
    if not all(isinstance(period[name], str) for name in ("start", "end")):
        raise ValueError("source_datamart.target_period must hold date strings")
    datamart_through = _utc(source["label_usable_through"], "source_datamart.label_usable_through")
    definitions = source["columns"]
    if not isinstance(definitions, list) or not definitions:
        raise ValueError("source_datamart.columns must be a nonempty list")
    for definition in definitions:
        column = _keys(definition, _COLUMN_KEYS, "source_datamart.columns")
        if not all(isinstance(column[name], str) for name in _COLUMN_KEYS):
            raise ValueError("source_datamart.columns entries must hold strings")
    defined = [cast(str, cast(dict[str, object], item)["name"]) for item in definitions]

    features = _keys(manifest["features"], _FEATURE_KEYS, "features")
    columns, excluded = features["columns"], features["excluded_columns"]
    nullable = features["nullable_in_training"]
    if (
        not isinstance(columns, list)
        or not isinstance(excluded, list)
        or not isinstance(nullable, list)
        or not isinstance(features["variant"], str)
        or not features["variant"]
        or not all(isinstance(name, str) for name in [*columns, *excluded])
        or not all(isinstance(value, bool) for value in nullable)
    ):
        raise ValueError("PL model features are invalid")
    if (
        not set(excluded) <= set(defined)
        or len(set(excluded)) != len(excluded)
        or columns != [name for name in defined if name not in set(excluded)]
        or len(nullable) != len(columns)
        or not columns
    ):
        raise ValueError("PL model columns differ from the datamart columns minus excluded")

    temperature = _keys(manifest["temperature"], _TEMPERATURE_KEYS, "temperature")
    value = _number(temperature["value"], "temperature.value")
    bounds = temperature["bounds"]
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise ValueError("PL model temperature bounds are invalid")
    lower = _number(bounds[0], "temperature.bounds")
    upper = _number(bounds[1], "temperature.bounds")
    if not 0 < lower <= value <= upper:
        raise ValueError("PL model temperature must be positive and within its bounds")
    _number(temperature["raw_valid_nll"], "raw_valid_nll")
    _number(temperature["calibrated_valid_nll"], "calibrated_valid_nll")
    if not isinstance(temperature["at_bound"], bool):
        raise ValueError("PL model temperature.at_bound must be a boolean")

    training = _keys(manifest["training"], _TRAINING_KEYS, "training")
    start = _integer(training["train_start_year"], "train_start_year")
    valid_year = _integer(training["valid_year"], "valid_year")
    if start > valid_year - 1:
        raise ValueError("PL model train_start_year must be before valid_year")
    for name in ("train_races", "train_rows", "valid_races", "valid_rows"):
        _integer(training[name], name)
    if (
        isinstance(training["purged_train_races"], bool)
        or not isinstance(training["purged_train_races"], int)
        or training["purged_train_races"] < 0
    ):
        raise ValueError("PL model purged_train_races must be a nonnegative integer")
    first_valid = _utc(training["valid_first_freeze_at"], "valid_first_freeze_at")
    train_max = _utc(training["train_max_label_usable_after"], "train_max_label_usable_after")
    valid_max = _utc(training["valid_max_label_usable_after"], "valid_max_label_usable_after")
    through = _utc(training["label_usable_through"], "label_usable_through")
    if train_max >= first_valid:
        raise ValueError("PL model train labels cross the valid freeze boundary")
    if through != max(train_max, valid_max):
        raise ValueError("PL model label_usable_through differs from its train and valid labels")
    if through > datamart_through:
        raise ValueError("PL model label boundary is later than its datamart boundary")
    for name in ("provenance", "config"):
        if not isinstance(manifest[name], dict):
            raise ValueError(f"PL model {name} must be an object")


def _keys(value: object, expected: frozenset[str], where: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"PL model {where} keys differ from the format")
    return cast(dict[str, object], value)


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"PL model {name} must be a positive integer")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"PL model {name} must be a finite number")
    return float(value)


def _hex64(value: object, name: str) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ValueError(f"PL model {name} must be 64 lowercase hex digits")


def _iso(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("PL model clocks must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _utc(value: object, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(cast(str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"PL model {name} must be an ISO 8601 UTC clock") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"PL model {name} must be an ISO 8601 UTC clock")
    return parsed


def _require_missing_branches(dump: object, names: Sequence[str], nullable: Sequence[bool]) -> None:
    """Require a missing-value branch on every split of a column that accepts NaN."""
    kinds = split_missing_types(dump, len(names))
    lacking = [
        name
        for name, accepts, found in zip(names, nullable, kinds, strict=True)
        if accepts and found - {"NaN"}
    ]
    if lacking:
        raise ValueError(
            "PL model splits columns missing in training without a missing-value branch: "
            f"{lacking!r}; set bin_construct_sample_cnt to at least the train rows"
        )


def _reject_constant(value: str) -> object:
    raise ValueError(f"PL model manifest must not contain {value}")


def _fsync(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "PLModel",
    "PLModelRecord",
    "read_pl_model",
    "write_pl_model",
]
