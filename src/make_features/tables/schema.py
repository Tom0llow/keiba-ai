"""Declare and resolve registered intermediate feature schemas."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

import pyarrow as pa

from make_features.validation.leakage import is_result_field

type IntermediateFeatureTable = pa.Table

BASE_COLUMNS = ("race_id", "horse_id", "freeze_at", "available_at")
FEATURE_COLUMNS = {
    "previous_race_result": ("previous_race_finish_position",),
    "odds_ratio": ("odds_ratio",),
    "pedigree": ("sire", "broodmare_sire"),
}
TIMESTAMP_TYPE = pa.timestamp("us", tz="UTC")

_FEATURE_NAME_METADATA = b"keiba_ai.feature_name"
_FEATURE_COLUMNS_METADATA = b"keiba_ai.feature_columns"
_FEATURE_TYPES_METADATA = b"keiba_ai.feature_column_types"
_TABLE_KIND_METADATA = b"keiba_ai.table_kind"
_TIMESTAMP_TIMEZONE_METADATA = b"keiba_ai.timestamp_timezone"
_TABLE_KIND = b"intermediate_feature"
_FEATURE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SCALAR_TYPES = {
    "int64": pa.int64(),
    "double": pa.float64(),
    "string": pa.string(),
    "bool": pa.bool_(),
}


def feature_column_types(
    feature_name: str,
    column_types: Mapping[str, pa.DataType] | None = None,
    *,
    registered_names: Sequence[str] = (),
) -> dict[str, pa.DataType]:
    """Resolve registered or explicitly supplied scalar value-column types."""
    validate_feature_name(feature_name, registered_names=registered_names)
    if feature_name in FEATURE_COLUMNS:
        value_type = (
            pa.int64()
            if feature_name == "previous_race_result"
            else pa.float64()
            if feature_name == "odds_ratio"
            else pa.string()
        )
        registered = {name: value_type for name in FEATURE_COLUMNS[feature_name]}
        if column_types is not None and dict(column_types) != registered:
            raise ValueError("column types must match the registered feature schema")
        return registered
    if column_types is None:
        raise ValueError("explicit column_types are required for this feature")
    resolved = dict(column_types)
    for name, value_type in resolved.items():
        if not isinstance(name, str) or not name or name in BASE_COLUMNS:
            raise ValueError(
                "value column names must be non-empty and not collide with base columns"
            )
        if is_result_field(name):
            raise ValueError(f"result-derived value column is not allowed: {name!r}")
        if value_type not in _SCALAR_TYPES.values():
            raise ValueError("feature column types must be int64, float64, string, or bool")
    return resolved


def table_column_types(
    table: IntermediateFeatureTable, *, registered_names: Sequence[str] = ()
) -> dict[str, pa.DataType]:
    """Return and validate the value-column schema declared by a feature table."""
    feature_name = resolve_feature_name(table, None, registered_names=registered_names)
    if feature_name in FEATURE_COLUMNS:
        return feature_column_types(feature_name, registered_names=registered_names)
    metadata = table.schema.metadata or {}
    try:
        decoded = json.loads(metadata[_FEATURE_TYPES_METADATA])
        if not isinstance(decoded, list):
            raise ValueError("feature column types metadata must be a list")
        types: dict[str, pa.DataType] = {}
        for entry in decoded:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("invalid feature column type entry")
            name, type_name = entry
            if not isinstance(name, str) or not isinstance(type_name, str) or name in types:
                raise ValueError("feature column types require unique string names")
            types[name] = _SCALAR_TYPES[type_name]
        return feature_column_types(feature_name, types, registered_names=registered_names)
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid feature column types metadata") from exc


def validate_feature_name(feature_name: str, *, registered_names: Sequence[str] = ()) -> None:
    """Require a fixed-schema or explicitly registered snake_case feature name."""
    if not isinstance(feature_name, str) or not _FEATURE_NAME_PATTERN.fullmatch(feature_name):
        raise ValueError("feature_name must be a non-empty snake_case string")
    if feature_name not in FEATURE_COLUMNS and feature_name not in registered_names:
        raise ValueError(f"unsupported feature_name: {feature_name!r}")


def resolve_feature_name(
    table: IntermediateFeatureTable,
    feature_name: str | None,
    *,
    registered_names: Sequence[str] = (),
) -> str:
    """Resolve a registered name while checking caller and metadata agreement."""
    metadata = table.schema.metadata or {}
    value = metadata.get(_FEATURE_NAME_METADATA)
    if value is not None:
        try:
            stored = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("feature name metadata must be UTF-8") from exc
        if feature_name is not None and stored != feature_name:
            raise ValueError("feature_name does not match table metadata")
        feature_name = stored
    if feature_name is None:
        raise ValueError("feature table requires a feature_name")
    validate_feature_name(feature_name, registered_names=registered_names)
    return feature_name


def feature_column_type(
    feature_name: str, column_name: str, *, registered_names: Sequence[str] = ()
) -> pa.DataType:
    """Return the registered type of an existing fixed-schema value column."""
    types = feature_column_types(feature_name, registered_names=registered_names)
    if column_name not in types:
        raise ValueError(f"unsupported feature column: {column_name!r}")
    return types[column_name]


def contract_metadata(
    feature_name: str, column_types: Mapping[str, pa.DataType]
) -> dict[bytes, bytes]:
    """Return the existing ordered schema metadata for one feature table."""
    metadata = {
        _TABLE_KIND_METADATA: _TABLE_KIND,
        _TIMESTAMP_TIMEZONE_METADATA: b"UTC",
        _FEATURE_NAME_METADATA: feature_name.encode("utf-8"),
        _FEATURE_COLUMNS_METADATA: json.dumps(tuple(column_types)).encode("utf-8"),
    }
    if feature_name not in FEATURE_COLUMNS:
        metadata[_FEATURE_TYPES_METADATA] = json.dumps(
            [(name, str(value_type)) for name, value_type in column_types.items()]
        ).encode("utf-8")
    return metadata
