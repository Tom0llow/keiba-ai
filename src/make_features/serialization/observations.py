"""Convert normalized evidence JSON without reading files or decoding raw codes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from math import isfinite
from types import UnionType
from typing import cast, get_args, get_origin, get_type_hints

from make_features.contracts.observations import (
    CalculationDependencyRecord,
    CalculationParameters,
    Evidence,
    HistoricalRace,
    ObservationInput,
)
from make_features.contracts.types import FeatureScalar
from make_features.generation.calculate import FeatureCalculationResult
from make_features.serialization.outputs import explanatory_payload
from make_features.validation.observations import reject_reference


def parse_observation_inputs(
    payload: Mapping[str, object], *, reference: bool = False
) -> tuple[ObservationInput, ...]:
    """Require the normalized schema and source evidence, rejecting raw-shaped input."""
    if (
        set(payload) != {"schema_version", "observations"}
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != 1
    ):
        raise ValueError(
            "normalized schema_version=1 and observations are required; raw/Parquet lacks reception/version evidence"
        )
    result = cast(
        tuple[ObservationInput, ...],
        _decode(payload["observations"], tuple[ObservationInput, ...], "observations"),
    )
    if not reference:
        reject_reference(result)
        if any(w.course is None or w.turn is None for source in result for w in source.workouts):
            raise ValueError("strict workout course and turn must be nonnull categories")
    return result


def parse_calculation_parameters(
    payload: Mapping[str, object], *, reference: bool = False
) -> CalculationParameters:
    """Require every explicit calculation option, rejecting unknown or missing keys."""
    result = cast(CalculationParameters, _decode(payload, CalculationParameters, "parameters"))
    if not reference:
        reject_reference(result)
    return result


def parse_calculation_dependencies(
    value: object, *, reference: bool = False
) -> tuple[CalculationDependencyRecord, ...]:
    """Decode the complete dependency manifest with the normalized evidence types."""
    result = cast(
        tuple[CalculationDependencyRecord, ...],
        _decode(value, tuple[CalculationDependencyRecord, ...], "dependencies"),
    )
    if not reference:
        reject_reference(result)
    return result


def parse_historical_results(payload: Mapping[str, object]) -> tuple[HistoricalRace, ...]:
    """Decode separate complete normalized results without joining them to features."""
    if (
        set(payload) != {"schema_version", "results"}
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != 1
    ):
        raise ValueError("normalized result schema_version=1 and results are required")
    result = cast(
        tuple[HistoricalRace, ...],
        _decode(payload["results"], tuple[HistoricalRace, ...], "results"),
    )
    reject_reference(result)
    return result


def normalized_payload(value: object) -> object:
    """Convert known dataclasses, timestamps and mappings to JSON-compatible values."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: normalized_payload(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: normalized_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized_payload(item) for item in value]
    return value


def calculation_payload(
    result: FeatureCalculationResult, *, feature_ids: tuple[str, ...]
) -> dict[str, object]:
    """Serialize existing middle rows plus rules and all mixed-source dependencies."""
    payload = explanatory_payload(result.built, feature_ids=feature_ids)
    payload.update(
        calculation_schema_version=1,
        parameters=normalized_payload(result.parameters),
        source_missing_reasons=normalized_payload(result.source_missing_reasons),
        dependencies=[
            {
                "race_id": record.race_id,
                "horse_id": record.horse_id,
                "groups": {
                    feature_id: {
                        "rule_id": result.parameters.rule_id,
                        "sources": normalized_payload(group.dependencies),
                        "historical_race_ids": list(group.historical_race_ids),
                        "missing_reasons": dict(group.missing_reasons),
                        "diagnostics": dict(group.diagnostics),
                    }
                    for feature_id, group in manifest.items()
                },
            }
            for record, manifest in zip(result.built.inputs, result.manifests, strict=True)
        ],
    )
    return payload


def _decode(value: object, expected: object, location: str) -> object:
    if expected is Evidence:
        return _decode(value, Evidence.__value__, location)
    if expected is FeatureScalar:
        return _decode(value, FeatureScalar.__value__, location)
    origin, args = get_origin(expected), get_args(expected)
    if origin is UnionType:
        for choice in args:
            try:
                return _decode(value, choice, location)
            except ValueError:
                pass
        raise ValueError(f"{location} does not match its nullable normalized type")
    if expected is type(None):
        if value is None:
            return None
        raise ValueError(f"{location} must be null")
    if expected in (datetime, date):
        if not isinstance(value, str):
            raise ValueError(f"{location} requires an explicit ISO-8601 string")
        return datetime.fromisoformat(value) if expected is datetime else date.fromisoformat(value)
    if expected in (str, int, bool, float):
        if expected is float and type(value) in (int, float) and isfinite(cast(float, value)):
            return float(cast(float, value))
        if type(value) is expected and expected is not float:
            return value
        raise ValueError(f"{location} requires {cast(type, expected).__name__}")
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError(f"{location} requires a JSON array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0], f"{location}[{i}]") for i, item in enumerate(value))
        if len(value) != len(args):
            raise ValueError(f"{location} requires exactly {len(args)} entries")
        return tuple(
            _decode(item, t, f"{location}[{i}]")
            for i, (item, t) in enumerate(zip(value, args, strict=True))
        )
    if origin is Mapping:
        if not isinstance(value, Mapping):
            raise ValueError(f"{location} requires an object")
        return {
            _decode(key, args[0], location): _decode(item, args[1], f"{location}.{key}")
            for key, item in value.items()
        }
    if isinstance(expected, type) and is_dataclass(expected):
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
            raise ValueError(f"{location} requires a normalized object with SourceEvidence")
        annotations = get_type_hints(expected)
        if set(value) != annotations.keys():
            raise ValueError(
                f"{location}: missing={sorted(annotations.keys() - value.keys())}, unsupported={sorted(value.keys() - annotations.keys())}"
            )
        return expected(
            **{
                name: _decode(value[name], annotation, f"{location}.{name}")
                for name, annotation in annotations.items()
            }
        )
    raise ValueError(f"{location} has an unsupported normalized contract")
