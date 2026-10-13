"""Build, validate and persist feature tables with explicitly declared schemas."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from features.common.availability import normalize_timestamp
from features.common.leakage import is_result_field
from features.common.rows import FeatureTableRow as FeatureTableRow

type IntermediateFeatureTable = pa.Table

BASE_COLUMNS = ("race_id", "horse_id", "freeze_at", "available_at")
FEATURE_COLUMNS = {
    "previous_race_result": ("previous_race_finish_position",),
    "odds_ratio": ("odds_ratio",),
    "pedigree": ("sire", "broodmare_sire"),
}
TIMESTAMP_TYPE = pa.timestamp("us", tz="UTC")
_EXPLICIT_FEATURE_NAMES = frozenset(
    {
        "recent_performance",
        "past_racing_ability",
        "condition_adjusted_ability",
        "recent_stability",
        "condition_suitability",
        "rest_and_condition_change",
        "jockey_performance",
        "trainer_performance",
        "within_race_relative",
        "basic_conditions_and_weight",
        "jockey_combination",
        "running_style_and_position",
        "expected_race_development",
        "pedigree_suitability",
        "history_volume_and_missingness",
        "past_body_weight",
        "hill_and_wood_workouts",
        "past_lap_and_running_style",
        "market_characteristics",
        "same_gate_and_trainer_relative",
        "opponent_pagerank",
    }
)
FEATURE_NAMES = frozenset(FEATURE_COLUMNS) | _EXPLICIT_FEATURE_NAMES

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
    feature_name: str, column_types: Mapping[str, pa.DataType] | None = None
) -> dict[str, pa.DataType]:
    """Resolve registered or explicitly supplied scalar value-column types."""
    _validate_feature_name(feature_name)
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


def table_column_types(table: IntermediateFeatureTable) -> dict[str, pa.DataType]:
    """Return and validate the value-column schema declared by a feature table."""
    feature_name = _resolve_feature_name(table, None)
    if feature_name in FEATURE_COLUMNS:
        return feature_column_types(feature_name)
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
        return feature_column_types(feature_name, types)
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid feature column types metadata") from exc


def build_feature_table(
    feature_name: str,
    rows: list[FeatureTableRow],
    *,
    column_types: Mapping[str, pa.DataType] | None = None,
) -> IntermediateFeatureTable:
    """Build a middle table without inferring value-column types or dropping rows."""
    types = feature_column_types(feature_name, column_types)
    for row in rows:
        if not isinstance(row, FeatureTableRow):
            raise TypeError("rows must contain FeatureTableRow values")
        if set(row.values) != set(types):
            raise ValueError("row values must match the declared feature columns")
        for name, value_type in types.items():
            value = row.values[name]
            if value is None:
                continue
            valid = (
                isinstance(value, bool)
                if value_type == pa.bool_()
                else isinstance(value, str)
                if value_type == pa.string()
                else isinstance(value, int) and not isinstance(value, bool)
                if value_type == pa.int64()
                else isinstance(value, (int, float)) and not isinstance(value, bool)
            )
            if not valid:
                raise ValueError(f"value for {name!r} does not match declared type {value_type}")
    schema = pa.schema(
        [
            pa.field("race_id", pa.string(), nullable=False),
            pa.field("horse_id", pa.string(), nullable=False),
            pa.field("freeze_at", TIMESTAMP_TYPE, nullable=False),
            pa.field("available_at", TIMESTAMP_TYPE),
            *[pa.field(name, value_type) for name, value_type in types.items()],
        ],
        metadata=_contract_metadata(feature_name, types),
    )
    records = [
        {
            "race_id": row.race_id,
            "horse_id": row.horse_id,
            "freeze_at": row.freeze_at,
            "available_at": row.available_at,
            **row.values,
        }
        for row in rows
    ]
    table = pa.Table.from_pylist(records, schema=schema)
    return validate_feature_table(table, feature_name)


def validate_feature_table(
    table: IntermediateFeatureTable,
    feature_name: str | None = None,
    *,
    expected_freeze_at: datetime | None = None,
) -> IntermediateFeatureTable:
    """Validate columns, explicit types, keys, missingness and temporal availability."""
    if not isinstance(table, pa.Table):
        raise TypeError("table must be a pyarrow.Table")
    feature_name = _resolve_feature_name(table, feature_name)
    types = table_column_types(table)
    expected_columns = (*BASE_COLUMNS, *types)
    if tuple(table.column_names) != expected_columns:
        raise ValueError(f"feature table columns for {feature_name!r} must be {expected_columns!r}")
    expected_types = {
        "race_id": pa.string(),
        "horse_id": pa.string(),
        "freeze_at": TIMESTAMP_TYPE,
        "available_at": TIMESTAMP_TYPE,
        **types,
    }
    for name, expected in expected_types.items():
        if table.schema.field(name).type != expected:
            raise ValueError(f"feature table column {name!r} must have type {expected}")
    metadata = table.schema.metadata or {}
    for metadata_key, value in _contract_metadata(feature_name, types).items():
        if metadata.get(metadata_key) != value:
            raise ValueError(f"invalid feature table metadata for {feature_name!r}")
    freeze_limit = (
        None
        if expected_freeze_at is None
        else normalize_timestamp(expected_freeze_at, "expected_freeze_at")
    )
    keys: set[tuple[str, str]] = set()
    for index in range(table.num_rows):
        race_id = table["race_id"][index].as_py()
        horse_id = table["horse_id"][index].as_py()
        if not isinstance(race_id, str) or not race_id:
            raise ValueError(f"race_id must be a non-empty string at row {index}")
        if not isinstance(horse_id, str) or not horse_id:
            raise ValueError(f"horse_id must be a non-empty string at row {index}")
        key = (race_id, horse_id)
        if key in keys:
            raise ValueError(f"duplicate feature key: {key!r}")
        keys.add(key)
        freeze_at = table["freeze_at"][index].as_py()
        if not isinstance(freeze_at, datetime):
            raise ValueError(f"freeze_at must be non-null at row {index}")
        freeze_at = normalize_timestamp(freeze_at, "freeze_at")
        if freeze_limit is not None and freeze_at != freeze_limit:
            raise ValueError("freeze_at does not match the expected freeze_at")
        available_at = table["available_at"][index].as_py()
        if available_at is not None:
            if not isinstance(available_at, datetime):
                raise ValueError("available_at must be a timestamp or null")
            available_at = normalize_timestamp(available_at, "available_at")
            if available_at > freeze_at:
                raise ValueError("available_at must not be after freeze_at")
        for name in types:
            value = table[name][index].as_py()
            if value is not None and available_at is None:
                raise ValueError(f"non-missing {name} requires available_at")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError(f"{name} must be finite or null")
    return table


def write_feature_table(
    table: IntermediateFeatureTable, path: str | Path, feature_name: str | None = None
) -> None:
    """Validate and save one feature table with its explicit schema metadata."""
    resolved = _resolve_feature_name(table, feature_name)
    types = (
        feature_column_types(resolved) if resolved in FEATURE_COLUMNS else table_column_types(table)
    )
    table = table.replace_schema_metadata(_contract_metadata(resolved, types))
    validate_feature_table(table, resolved)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, destination)


def read_feature_table(
    path: str | Path, feature_name: str | None = None
) -> IntermediateFeatureTable:
    """Read and validate an explicitly saved feature table."""
    return validate_feature_table(pq.read_table(Path(path)), feature_name)


def validate_common_row(
    race_id: str,
    horse_id: str,
    freeze_at: datetime,
    available_at: datetime | None,
    value: object,
    value_column: str,
) -> tuple[datetime, datetime | None]:
    """Validate identifiers and value availability before table construction."""
    if not isinstance(race_id, str) or not race_id:
        raise ValueError("race_id must be a non-empty string")
    if not isinstance(horse_id, str) or not horse_id:
        raise ValueError("horse_id must be a non-empty string")
    freeze_at = normalize_timestamp(freeze_at, "freeze_at")
    available_at = (
        None if available_at is None else normalize_timestamp(available_at, "available_at")
    )
    if value is not None and available_at is None:
        raise ValueError(f"non-missing {value_column} requires available_at")
    if available_at is not None and available_at > freeze_at:
        raise ValueError("available_at must not be after freeze_at")
    return freeze_at, available_at


def _validate_feature_name(feature_name: str) -> None:
    if not isinstance(feature_name, str) or not _FEATURE_NAME_PATTERN.fullmatch(feature_name):
        raise ValueError("feature_name must be a non-empty snake_case string")
    if feature_name not in FEATURE_COLUMNS and feature_name not in _EXPLICIT_FEATURE_NAMES:
        raise ValueError(f"unsupported feature_name: {feature_name!r}")


def _resolve_feature_name(table: IntermediateFeatureTable, feature_name: str | None) -> str:
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
    _validate_feature_name(feature_name)
    return feature_name


def feature_column_type(feature_name: str, column_name: str) -> pa.DataType:
    """Return the registered type of an existing fixed-schema value column."""
    types = feature_column_types(feature_name)
    if column_name not in types:
        raise ValueError(f"unsupported feature column: {column_name!r}")
    return types[column_name]


def _contract_metadata(
    feature_name: str, column_types: Mapping[str, pa.DataType]
) -> dict[bytes, bytes]:
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


save_feature_table = write_feature_table
load_feature_table = read_feature_table
write_intermediate_table = write_feature_table
read_intermediate_table = read_feature_table
