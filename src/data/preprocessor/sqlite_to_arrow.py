"""Convert SQLite-derived values to the existing all-string Arrow contract."""

from collections.abc import Sequence

import pyarrow as pa

_SOURCE_TYPES = {"TEXT", "DATETIME"}
_TARGET_CELLS_PER_BATCH = 1_000_000
_MAX_ROWS_PER_BATCH = 65_536


def sqlite_arrow_schema(name: str, columns: Sequence[tuple[str, str]]) -> pa.Schema:
    """Validate source declarations and preserve ordered nullable string fields."""
    for field_name, declared_type in columns:
        if declared_type.upper() not in _SOURCE_TYPES:
            raise ValueError(f"unsupported declared type in {name}.{field_name}")
    return pa.schema([pa.field(field_name, pa.string()) for field_name, _ in columns])


def sqlite_batch_size(column_count: int) -> int:
    """Return the existing bound on batch rows and total source cells."""
    return min(_MAX_ROWS_PER_BATCH, max(1, _TARGET_CELLS_PER_BATCH // max(1, column_count)))


def sqlite_rows_to_arrow(
    name: str, schema: pa.Schema, rows: Sequence[Sequence[object]]
) -> pa.Table:
    """Convert one batch without coercing numeric values, nulls or leading zeros."""
    values: list[list[str | None]] = [[] for _ in schema.names]
    for row in rows:
        for index, value in enumerate(row):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"unsupported SQLite value in {name}.{schema.names[index]}")
            values[index].append(value)
    arrays = [pa.array(column, type=pa.string()) for column in values]
    return pa.Table.from_arrays(arrays, schema=schema)
