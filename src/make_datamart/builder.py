"""Read intermediate feature Parquet files and build an ordered datamart."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from math import isfinite
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from features.feature_table import (
    BASE_COLUMNS,
    FEATURE_COLUMNS,
    TIMESTAMP_TYPE,
    IntermediateFeatureTable,
    feature_column_type,
    normalize_timestamp,
    read_feature_table,
    validate_feature_table,
)

FeatureTableSource = str | Path | IntermediateFeatureTable
_DATAMART_FEATURE_NAMES_METADATA = b"keiba_ai.feature_names"


def make_datamart(paths: Sequence[str | Path]) -> pa.Table:
    """Read intermediate Parquet files and left-join them in the given order."""
    if not paths:
        raise ValueError("at least one feature table path is required")
    tables = [read_feature_table(path) for path in paths]
    return join_feature_tables(tables)


def build_datamart(paths: Sequence[str | Path]) -> pa.Table:
    """Build a datamart from intermediate feature Parquet files."""
    return make_datamart(paths)


def write_datamart(table: pa.Table, path: str | Path) -> None:
    """Write a validated datamart to an explicit Parquet path."""
    _validate_datamart(table)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, destination)


def read_datamart(path: str | Path) -> pa.Table:
    """Read and validate a saved datamart Parquet table."""
    table = pq.read_table(Path(path))
    _validate_datamart(table)
    return table


def join_feature_tables(tables: Sequence[IntermediateFeatureTable]) -> pa.Table:
    """Left-join validated feature tables while preserving the first row order."""
    if not tables:
        raise ValueError("at least one feature table is required")
    validated_tables = [validate_feature_table(table) for table in tables]
    feature_names: set[str] = set()
    feature_names_in_order: list[str] = []
    for table in validated_tables:
        feature_name = _feature_name(table)
        if feature_name in feature_names:
            raise ValueError(f"duplicate feature name: {feature_name!r}")
        feature_names.add(feature_name)
        feature_names_in_order.append(feature_name)

    base_table = validated_tables[0]
    base_keys = [_key_from_table(base_table, row_index) for row_index in range(base_table.num_rows)]
    base_key_set = set(base_keys)
    base_indexes = {key: index for index, key in enumerate(base_keys)}
    base_freeze_at = [
        base_table["freeze_at"][row_index].as_py() for row_index in range(base_table.num_rows)
    ]
    row_indexes: dict[str, dict[tuple[str, str], int]] = {}
    for table in validated_tables:
        feature_name = _feature_name(table)
        indexes: dict[tuple[str, str], int] = {}
        for row_index in range(table.num_rows):
            key = _key_from_table(table, row_index)
            if key in indexes:
                raise ValueError(f"duplicate feature key in {feature_name!r}: {key!r}")
            if key not in base_key_set:
                raise ValueError(f"feature table {feature_name!r} contains an extra key: {key!r}")
            indexes[key] = row_index
            if table is not base_table:
                base_row_index = base_indexes[key]
                freeze_at = table["freeze_at"][row_index].as_py()
                if freeze_at != base_freeze_at[base_row_index]:
                    raise ValueError(f"freeze_at mismatch for key {key!r}")
        row_indexes[feature_name] = indexes

    output_names = ["race_id", "horse_id", "freeze_at"]
    output_arrays: list[pa.Array] = [
        base_table["race_id"],
        base_table["horse_id"],
        base_table["freeze_at"],
    ]
    output_schema_fields = [
        base_table.schema.field("race_id"),
        base_table.schema.field("horse_id"),
        base_table.schema.field("freeze_at"),
    ]
    for table in validated_tables:
        feature_name = _feature_name(table)
        indexes = row_indexes[feature_name]
        available_at_name = f"{feature_name}__available_at"
        _ensure_output_column_is_free(output_names, available_at_name)
        available_values = [
            _feature_value(table, indexes, key, "available_at") for key in base_keys
        ]
        available_type = table.schema.field("available_at").type
        output_names.append(available_at_name)
        output_arrays.append(pa.array(available_values, type=available_type))
        output_schema_fields.append(pa.field(available_at_name, available_type))

        for column_name in FEATURE_COLUMNS[feature_name]:
            _ensure_output_column_is_free(output_names, column_name)
            values = [_feature_value(table, indexes, key, column_name) for key in base_keys]
            column_type = table.schema.field(column_name).type
            output_names.append(column_name)
            output_arrays.append(pa.array(values, type=column_type))
            output_schema_fields.append(pa.field(column_name, column_type))

    return pa.Table.from_arrays(
        output_arrays,
        schema=pa.schema(
            output_schema_fields,
            metadata={
                b"keiba_ai.table_kind": b"datamart",
                _DATAMART_FEATURE_NAMES_METADATA: json.dumps(feature_names_in_order).encode(
                    "utf-8"
                ),
            },
        ),
    )


def _feature_name(table: IntermediateFeatureTable) -> str:
    metadata = table.schema.metadata or {}
    raw_name = metadata.get(b"keiba_ai.feature_name")
    if not isinstance(raw_name, bytes):
        raise ValueError("feature table is missing feature_name metadata")
    try:
        return raw_name.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("feature table feature_name metadata is not UTF-8") from exc


def _key_from_table(table: IntermediateFeatureTable, row_index: int) -> tuple[str, str]:
    race_id = table["race_id"][row_index].as_py()
    horse_id = table["horse_id"][row_index].as_py()
    if not isinstance(race_id, str) or not isinstance(horse_id, str):
        raise ValueError("feature table keys must be strings")
    return race_id, horse_id


def _feature_value(
    table: IntermediateFeatureTable,
    indexes: dict[tuple[str, str], int],
    key: tuple[str, str],
    column_name: str,
) -> object:
    row_index = indexes.get(key)
    if row_index is None:
        return None
    return table[column_name][row_index].as_py()


def _ensure_output_column_is_free(output_names: list[str], column_name: str) -> None:
    if column_name in BASE_COLUMNS or column_name in output_names:
        raise ValueError(f"feature column collision: {column_name!r}")


def _validate_datamart(table: pa.Table) -> None:
    if not isinstance(table, pa.Table):
        raise TypeError("table must be a pyarrow.Table")
    metadata = table.schema.metadata or {}
    if metadata.get(b"keiba_ai.table_kind") != b"datamart":
        raise ValueError("datamart metadata is missing or invalid")
    feature_names = _datamart_feature_names(metadata)
    expected_columns = ["race_id", "horse_id", "freeze_at"]
    for feature_name in feature_names:
        expected_columns.append(f"{feature_name}__available_at")
        expected_columns.extend(FEATURE_COLUMNS[feature_name])
    if table.column_names != expected_columns:
        raise ValueError(
            f"datamart columns must be {expected_columns!r}, got {table.column_names!r}"
        )

    expected_types = {
        "race_id": pa.string(),
        "horse_id": pa.string(),
        "freeze_at": TIMESTAMP_TYPE,
    }
    for feature_name in feature_names:
        expected_types[f"{feature_name}__available_at"] = TIMESTAMP_TYPE
        for column_name in FEATURE_COLUMNS[feature_name]:
            expected_types[column_name] = feature_column_type(feature_name, column_name)
    for column_name, expected_type in expected_types.items():
        actual_type = table.schema.field(column_name).type
        if actual_type != expected_type:
            raise ValueError(
                f"datamart column {column_name!r} must have type {expected_type}, got {actual_type}"
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
            raise ValueError(f"datamart contains duplicate key: {key!r}")
        seen_keys.add(key)

        freeze_at = table["freeze_at"][row_index].as_py()
        if not isinstance(freeze_at, datetime):
            raise ValueError(f"freeze_at must be non-null at row {row_index}")
        normalized_freeze_at = normalize_timestamp(freeze_at, "freeze_at")
        for feature_name in feature_names:
            available_at = table[f"{feature_name}__available_at"][row_index].as_py()
            normalized_available_at = (
                None if available_at is None else normalize_timestamp(available_at, "available_at")
            )
            if (
                normalized_available_at is not None
                and normalized_available_at > normalized_freeze_at
            ):
                raise ValueError("available_at must not be after freeze_at")
            for column_name in FEATURE_COLUMNS[feature_name]:
                value = table[column_name][row_index].as_py()
                if value is not None and normalized_available_at is None:
                    raise ValueError(f"non-missing {column_name} requires available_at")
                if (
                    feature_name == "odds_ratio"
                    and value is not None
                    and (not isinstance(value, (int, float)) or not isfinite(float(value)))
                ):
                    raise ValueError("odds_ratio must be finite or null")


def _datamart_feature_names(metadata: dict[bytes, bytes]) -> list[str]:
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
        or any(feature_name not in FEATURE_COLUMNS for feature_name in decoded)
    ):
        raise ValueError("datamart feature_names metadata is invalid")
    return decoded


__all__ = [
    "build_datamart",
    "join_feature_tables",
    "make_datamart",
    "read_datamart",
    "write_datamart",
]
