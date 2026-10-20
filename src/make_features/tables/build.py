"""Construct intermediate tables from normalized feature rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pyarrow as pa

from make_features.contracts.rows import FeatureTableRow as FeatureTableRow
from make_features.tables.schema import (
    TIMESTAMP_TYPE,
    IntermediateFeatureTable,
    contract_metadata,
    feature_column_types,
)
from make_features.validation.table import validate_feature_table


def build_feature_table(
    feature_name: str,
    rows: list[FeatureTableRow],
    *,
    column_types: Mapping[str, pa.DataType] | None = None,
    registered_names: Sequence[str] = (),
) -> IntermediateFeatureTable:
    """Build a middle table without inferring value-column types or dropping rows."""
    types = feature_column_types(feature_name, column_types, registered_names=registered_names)
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
        metadata=contract_metadata(feature_name, types),
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
    return validate_feature_table(table, feature_name, registered_names=registered_names)
