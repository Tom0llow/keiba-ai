"""Join validated feature tables into an ordered datamart without I/O."""

from __future__ import annotations

from collections.abc import Sequence

import pyarrow as pa

from make_datamart.tables.schema import contract_metadata, expected_column_types
from make_features.tables.schema import IntermediateFeatureTable, table_column_types
from make_features.validation.table import validate_feature_table


def join_feature_tables(
    tables: Sequence[IntermediateFeatureTable], *, registered_names: Sequence[str] = ()
) -> pa.Table:
    """Left-join validated feature tables while preserving the first row order."""
    if not tables:
        raise ValueError("at least one feature table is required")
    validated_tables = [
        validate_feature_table(table, registered_names=registered_names) for table in tables
    ]
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

    value_types = {
        _feature_name(table): table_column_types(table, registered_names=registered_names)
        for table in validated_tables
    }
    expected_column_types(feature_names_in_order, value_types)
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
        available_values = [
            _feature_value(table, indexes, key, "available_at") for key in base_keys
        ]
        available_type = table.schema.field("available_at").type
        output_arrays.append(pa.array(available_values, type=available_type))
        output_schema_fields.append(pa.field(available_at_name, available_type))

        for column_name in value_types[feature_name]:
            values = [_feature_value(table, indexes, key, column_name) for key in base_keys]
            column_type = table.schema.field(column_name).type
            output_arrays.append(pa.array(values, type=column_type))
            output_schema_fields.append(pa.field(column_name, column_type))

    metadata = contract_metadata(feature_names_in_order, value_types)
    return pa.Table.from_arrays(
        output_arrays,
        schema=pa.schema(
            output_schema_fields,
            metadata=metadata,
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
