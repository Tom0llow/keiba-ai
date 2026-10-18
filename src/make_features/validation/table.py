"""Validate feature table schemas, keys and availability."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import isfinite

import pyarrow as pa

from make_features.tables.schema import (
    BASE_COLUMNS,
    TIMESTAMP_TYPE,
    IntermediateFeatureTable,
    contract_metadata,
    resolve_feature_name,
    table_column_types,
)
from make_features.validation.availability import normalize_timestamp


def validate_feature_table(
    table: IntermediateFeatureTable,
    feature_name: str | None = None,
    *,
    expected_freeze_at: datetime | None = None,
    registered_names: Sequence[str] = (),
) -> IntermediateFeatureTable:
    """Validate columns, explicit types, keys, missingness and temporal availability."""
    if not isinstance(table, pa.Table):
        raise TypeError("table must be a pyarrow.Table")
    feature_name = resolve_feature_name(table, feature_name, registered_names=registered_names)
    types = table_column_types(table, registered_names=registered_names)
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
    for metadata_key, value in contract_metadata(feature_name, types).items():
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
