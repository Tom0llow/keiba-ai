"""Validate datamart schemas, keys, timestamps and missing values."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from math import isfinite

import pyarrow as pa

from make_datamart.tables.schema import (
    datamart_column_types,
    datamart_feature_names,
    expected_column_types,
)
from make_features.validation.availability import normalize_timestamp


def validate_datamart(table: pa.Table, *, registered_names: Sequence[str] = ()) -> None:
    """Require the existing datamart schema, key and availability contract."""
    if not isinstance(table, pa.Table):
        raise TypeError("table must be a pyarrow.Table")
    metadata = table.schema.metadata or {}
    if metadata.get(b"keiba_ai.table_kind") != b"datamart":
        raise ValueError("datamart metadata is missing or invalid")
    feature_names = datamart_feature_names(metadata, registered_names=registered_names)
    value_types = datamart_column_types(metadata, feature_names, registered_names=registered_names)
    expected_types = expected_column_types(feature_names, value_types)
    expected_columns = list(expected_types)
    if table.column_names != expected_columns:
        raise ValueError(
            f"datamart columns must be {expected_columns!r}, got {table.column_names!r}"
        )

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
            for column_name in value_types[feature_name]:
                value = table[column_name][row_index].as_py()
                if value is not None and normalized_available_at is None:
                    raise ValueError(f"non-missing {column_name} requires available_at")
                if isinstance(value, float) and not isfinite(value):
                    raise ValueError(f"{column_name} must be finite or null")
