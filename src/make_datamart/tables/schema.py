"""Declare and decode datamart columns and persisted metadata."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pyarrow as pa

from features.tables.schema import (
    BASE_COLUMNS,
    FEATURE_COLUMNS,
    TIMESTAMP_TYPE,
    feature_column_types,
)

_DATAMART_FEATURE_NAMES_METADATA = b"keiba_ai.feature_names"


def contract_metadata(
    feature_names: list[str], value_types: dict[str, dict[str, pa.DataType]]
) -> dict[bytes, bytes]:
    """Return the existing ordered metadata for a datamart schema."""
    metadata = {
        b"keiba_ai.table_kind": b"datamart",
        _DATAMART_FEATURE_NAMES_METADATA: json.dumps(feature_names).encode("utf-8"),
    }
    if any(name not in FEATURE_COLUMNS for name in feature_names):
        metadata[b"keiba_ai.feature_column_types"] = json.dumps(
            {
                name: [(column, str(value_type)) for column, value_type in types.items()]
                for name, types in value_types.items()
            }
        ).encode("utf-8")
    return metadata


def expected_column_types(
    feature_names: list[str], value_types: dict[str, dict[str, pa.DataType]]
) -> dict[str, pa.DataType]:
    """Return ordered datamart columns and types while rejecting collisions."""
    expected_types = {
        "race_id": pa.string(),
        "horse_id": pa.string(),
        "freeze_at": TIMESTAMP_TYPE,
    }
    for feature_name in feature_names:
        available_column = f"{feature_name}__available_at"
        _ensure_output_column_is_free(expected_types, available_column)
        expected_types[available_column] = TIMESTAMP_TYPE
        for column_name, column_type in value_types[feature_name].items():
            _ensure_output_column_is_free(expected_types, column_name)
            expected_types[column_name] = column_type
    return expected_types


def _ensure_output_column_is_free(output_names: dict[str, pa.DataType], column_name: str) -> None:
    if column_name in BASE_COLUMNS or column_name in output_names:
        raise ValueError(f"feature column collision: {column_name!r}")


def datamart_column_types(
    metadata: dict[bytes, bytes],
    feature_names: list[str],
    *,
    registered_names: Sequence[str] = (),
) -> dict[str, dict[str, pa.DataType]]:
    """Resolve saved value-column types using explicit registered names."""
    raw = metadata.get(b"keiba_ai.feature_column_types")
    if raw is None:
        return {
            name: feature_column_types(name, registered_names=registered_names)
            for name in feature_names
        }
    scalar_types = {
        "int64": pa.int64(),
        "double": pa.float64(),
        "string": pa.string(),
        "bool": pa.bool_(),
    }
    try:
        decoded = json.loads(raw)
        if not isinstance(decoded, dict) or set(decoded) != set(feature_names):
            raise ValueError("datamart column type metadata must match feature names")
        schemas: dict[str, dict[str, pa.DataType]] = {}
        for name in feature_names:
            entries = decoded[name]
            if not isinstance(entries, list):
                raise ValueError("datamart column type entries must be a list")
            types: dict[str, pa.DataType] = {}
            for entry in entries:
                if not isinstance(entry, list) or len(entry) != 2:
                    raise ValueError("invalid datamart column type entry")
                column, type_name = entry
                if not isinstance(column, str) or not isinstance(type_name, str) or column in types:
                    raise ValueError("datamart value columns must be unique strings")
                types[column] = scalar_types[type_name]
            schemas[name] = feature_column_types(name, types, registered_names=registered_names)
        return schemas
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid datamart column type metadata") from exc


def datamart_feature_names(
    metadata: dict[bytes, bytes], *, registered_names: Sequence[str] = ()
) -> list[str]:
    """Decode ordered, unique and registered datamart feature names."""
    raw_feature_names = metadata.get(_DATAMART_FEATURE_NAMES_METADATA)
    if not isinstance(raw_feature_names, bytes):
        raise ValueError("datamart is missing feature_names metadata")
    try:
        decoded = json.loads(raw_feature_names.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("datamart feature_names metadata is invalid") from exc
    if (
        not isinstance(decoded, list)
        or not decoded
        or any(not isinstance(feature_name, str) for feature_name in decoded)
        or len(set(decoded)) != len(decoded)
        or any(
            feature_name not in FEATURE_COLUMNS and feature_name not in registered_names
            for feature_name in decoded
        )
    ):
        raise ValueError("datamart feature_names metadata is invalid")
    return decoded
