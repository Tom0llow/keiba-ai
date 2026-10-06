"""Validate and persist feature-specific intermediate Arrow tables."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

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
_TABLE_KIND_METADATA = b"keiba_ai.table_kind"
_TIMESTAMP_TIMEZONE_METADATA = b"keiba_ai.timestamp_timezone"
_TABLE_KIND = b"intermediate_feature"
_FEATURE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def build_feature_table(
    feature_name: str,
    rows: list[FeatureTableRow],
) -> IntermediateFeatureTable:
    """Build a validated intermediate table from normalized typed rows."""
    feature_columns = _feature_columns(feature_name)
    arrays: list[pa.Array] = [
        pa.array([row.race_id for row in rows], type=pa.string()),
        pa.array([row.horse_id for row in rows], type=pa.string()),
        pa.array([row.freeze_at for row in rows], type=TIMESTAMP_TYPE),
        pa.array(
            [None if row.available_at is None else row.available_at for row in rows],
            type=TIMESTAMP_TYPE,
        ),
    ]
    for column_name in feature_columns:
        arrays.append(
            pa.array(
                [row.values[column_name] for row in rows],
                type=_value_type(feature_name, column_name),
            )
        )

    metadata = _contract_metadata(feature_name)
    table = pa.Table.from_arrays(
        arrays,
        schema=pa.schema(
            [
                pa.field("race_id", pa.string(), nullable=False),
                pa.field("horse_id", pa.string(), nullable=False),
                pa.field("freeze_at", TIMESTAMP_TYPE, nullable=False),
                pa.field("available_at", TIMESTAMP_TYPE),
                *[
                    pa.field(column_name, _value_type(feature_name, column_name))
                    for column_name in feature_columns
                ],
            ],
            metadata=metadata,
        ),
    )
    return validate_feature_table(table, feature_name)


def validate_feature_table(
    table: IntermediateFeatureTable,
    feature_name: str | None = None,
    *,
    expected_freeze_at: datetime | None = None,
) -> IntermediateFeatureTable:
    """Validate an intermediate feature table and return it unchanged.

    The table must contain exactly the common columns and the registered value
    columns for one feature. Each ``(race_id, horse_id)`` key must be unique,
    and timestamps must be timezone-aware UTC values.
    """
    if not isinstance(table, pa.Table):
        raise TypeError("table must be a pyarrow.Table")

    resolved_feature_name = _resolve_feature_name(table, feature_name)
    expected_columns = (*BASE_COLUMNS, *_feature_columns(resolved_feature_name))
    actual_columns = tuple(table.column_names)
    if actual_columns != expected_columns:
        raise ValueError(
            f"feature table columns for {resolved_feature_name!r} must be "
            f"{expected_columns!r}, got {actual_columns!r}"
        )

    expected_types = {
        "race_id": pa.string(),
        "horse_id": pa.string(),
        "freeze_at": TIMESTAMP_TYPE,
        "available_at": TIMESTAMP_TYPE,
    }
    expected_types.update(
        {
            column_name: _value_type(resolved_feature_name, column_name)
            for column_name in _feature_columns(resolved_feature_name)
        }
    )
    for column_name in expected_columns:
        actual_type = table.schema.field(column_name).type
        if actual_type != expected_types[column_name]:
            raise ValueError(
                f"feature table column {column_name!r} must have type "
                f"{expected_types[column_name]}, got {actual_type}"
            )

    metadata = table.schema.metadata or {}
    _validate_metadata(metadata, resolved_feature_name)
    _validate_rows(table, resolved_feature_name, expected_freeze_at)
    return table


def write_feature_table(
    table: IntermediateFeatureTable,
    path: str | Path,
    feature_name: str | None = None,
) -> None:
    """Validate and write one intermediate feature table to Parquet."""
    resolved_feature_name = _resolve_feature_name(table, feature_name)
    metadata = _contract_metadata(resolved_feature_name)
    table_with_metadata = table.replace_schema_metadata(metadata)
    validate_feature_table(table_with_metadata, resolved_feature_name)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table_with_metadata, destination)


def read_feature_table(
    path: str | Path,
    feature_name: str | None = None,
) -> IntermediateFeatureTable:
    """Read and validate one intermediate feature table from Parquet."""
    table = pq.read_table(Path(path))
    return validate_feature_table(table, feature_name)


save_feature_table = write_feature_table
load_feature_table = read_feature_table
write_intermediate_table = write_feature_table
read_intermediate_table = read_feature_table


class FeatureTableRow:
    """Typed normalized row used by feature-specific table builders."""

    __slots__ = ("available_at", "freeze_at", "horse_id", "race_id", "values")

    def __init__(
        self,
        race_id: str,
        horse_id: str,
        freeze_at: datetime,
        available_at: datetime | None,
        values: dict[str, object],
    ) -> None:
        self.race_id = race_id
        self.horse_id = horse_id
        self.freeze_at = freeze_at
        self.available_at = available_at
        self.values = values


def normalize_timestamp(value: datetime, field_name: str) -> datetime:
    """Return a timezone-aware timestamp normalized to UTC."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def validate_common_row(
    race_id: str,
    horse_id: str,
    freeze_at: datetime,
    available_at: datetime | None,
    value: object,
    value_column: str,
) -> tuple[datetime, datetime | None]:
    """Validate identifiers and availability for a typed feature input."""
    if not isinstance(race_id, str) or not race_id:
        raise ValueError("race_id must be a non-empty string")
    if not isinstance(horse_id, str) or not horse_id:
        raise ValueError("horse_id must be a non-empty string")
    normalized_freeze_at = normalize_timestamp(freeze_at, "freeze_at")
    normalized_available_at = (
        None if available_at is None else normalize_timestamp(available_at, "available_at")
    )
    if value is not None and normalized_available_at is None:
        raise ValueError(f"non-missing {value_column} requires available_at")
    if normalized_available_at is not None and normalized_available_at > normalized_freeze_at:
        raise ValueError("available_at must not be after freeze_at")
    return normalized_freeze_at, normalized_available_at


def _resolve_feature_name(table: IntermediateFeatureTable, feature_name: str | None) -> str:
    metadata = table.schema.metadata or {}
    metadata_value = metadata.get(_FEATURE_NAME_METADATA)
    if metadata_value is not None:
        try:
            metadata_feature_name = metadata_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("feature name metadata must be UTF-8") from exc
        if feature_name is not None and feature_name != metadata_feature_name:
            raise ValueError("feature_name does not match table metadata")
        feature_name = metadata_feature_name
    if feature_name is None:
        raise ValueError("feature table requires a feature_name")
    _validate_feature_name(feature_name)
    return feature_name


def _validate_feature_name(feature_name: str) -> None:
    if not isinstance(feature_name, str) or not _FEATURE_NAME_PATTERN.fullmatch(feature_name):
        raise ValueError("feature_name must be a non-empty snake_case string")
    if feature_name not in FEATURE_COLUMNS:
        raise ValueError(f"unsupported feature_name: {feature_name!r}")


def _feature_columns(feature_name: str) -> tuple[str, ...]:
    _validate_feature_name(feature_name)
    return FEATURE_COLUMNS[feature_name]


def _value_type(feature_name: str, column_name: str) -> pa.DataType:
    if feature_name == "previous_race_result":
        return pa.int64()
    if feature_name == "odds_ratio":
        return pa.float64()
    if feature_name == "pedigree":
        return pa.string()
    raise ValueError(f"unsupported feature_name: {feature_name!r}")


def feature_column_type(feature_name: str, column_name: str) -> pa.DataType:
    """Return the registered Arrow type for one feature value column."""
    if column_name not in _feature_columns(feature_name):
        raise ValueError(f"unsupported feature column: {column_name!r}")
    return _value_type(feature_name, column_name)


def _contract_metadata(feature_name: str) -> dict[bytes, bytes]:
    columns = _feature_columns(feature_name)
    return {
        _TABLE_KIND_METADATA: _TABLE_KIND,
        _TIMESTAMP_TIMEZONE_METADATA: b"UTC",
        _FEATURE_NAME_METADATA: feature_name.encode("utf-8"),
        _FEATURE_COLUMNS_METADATA: json.dumps(columns).encode("utf-8"),
    }


def _validate_metadata(metadata: dict[bytes, bytes], feature_name: str) -> None:
    expected = _contract_metadata(feature_name)
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"invalid feature table metadata for {feature_name!r}")


def _validate_rows(
    table: IntermediateFeatureTable,
    feature_name: str,
    expected_freeze_at: datetime | None,
) -> None:
    freeze_limit = (
        None
        if expected_freeze_at is None
        else normalize_timestamp(expected_freeze_at, "expected_freeze_at")
    )
    seen_keys: set[tuple[str, str]] = set()
    for row_index in range(table.num_rows):
        race_id = table["race_id"][row_index].as_py()
        horse_id = table["horse_id"][row_index].as_py()
        if not isinstance(race_id, str) or not race_id:
            raise ValueError(f"race_id must be a non-empty string at row {row_index}")
        if not isinstance(horse_id, str) or not horse_id:
            raise ValueError(f"horse_id must be a non-empty string at row {row_index}")
        key = (race_id, horse_id)
        if key in seen_keys:
            raise ValueError(f"duplicate feature key: {key!r}")
        seen_keys.add(key)

        freeze_at = table["freeze_at"][row_index].as_py()
        if not isinstance(freeze_at, datetime):
            raise ValueError(f"freeze_at must be non-null at row {row_index}")
        normalized_freeze_at = _stored_timestamp(freeze_at, "freeze_at")
        if freeze_limit is not None and normalized_freeze_at != freeze_limit:
            raise ValueError("freeze_at does not match the expected freeze_at")

        available_at = table["available_at"][row_index].as_py()
        if available_at is not None:
            normalized_available_at = _stored_timestamp(available_at, "available_at")
            if normalized_available_at > normalized_freeze_at:
                raise ValueError("available_at must not be after freeze_at")

        for column_name in _feature_columns(feature_name):
            value = table[column_name][row_index].as_py()
            if value is not None and available_at is None:
                raise ValueError(f"non-missing {column_name} requires available_at")
            if (
                feature_name == "odds_ratio"
                and value is not None
                and (not isinstance(value, (int, float)) or not isfinite(float(value)))
            ):
                raise ValueError("odds_ratio must be finite or null")


def _normalize_timestamp(value: datetime) -> datetime:
    return normalize_timestamp(value, "timestamp")


def _storage_timestamp(value: datetime) -> datetime:
    """Return a UTC timestamp for Arrow persistence."""
    return normalize_timestamp(value, "timestamp")


def _stored_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be non-null")
    return _storage_timestamp(value)


__all__ = [
    "BASE_COLUMNS",
    "FEATURE_COLUMNS",
    "TIMESTAMP_TYPE",
    "FeatureTableRow",
    "IntermediateFeatureTable",
    "build_feature_table",
    "feature_column_type",
    "load_feature_table",
    "normalize_timestamp",
    "read_feature_table",
    "read_intermediate_table",
    "save_feature_table",
    "validate_common_row",
    "validate_feature_table",
    "write_feature_table",
    "write_intermediate_table",
]
