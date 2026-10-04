"""Read raw SQLite tables and export them to Parquet without domain coercion."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SOURCE_TYPES = {"TEXT", "DATETIME"}
_TARGET_CELLS_PER_BATCH = 1_000_000
_MAX_ROWS_PER_BATCH = 65_536


class SQLiteReader:
    """Own read-only access to the raw JVLinkToSQLite database."""

    def __init__(self, database: Path) -> None:
        self._database = database.expanduser().resolve()

    @contextmanager
    def snapshot(self) -> Iterator[sqlite3.Connection]:
        """Yield one consistent read-only SQLite snapshot."""
        if not self._database.is_file():
            raise FileNotFoundError(self._database)
        connection = sqlite3.connect(f"{self._database.as_uri()}?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            yield connection
        finally:
            connection.close()

    def list_tables(self, connection: sqlite3.Connection) -> list[str]:
        """List user tables from an already-open snapshot."""
        names = [
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = ? AND name NOT GLOB ? ORDER BY name",
                ("table", "sqlite_%"),
            )
        ]
        for name in names:
            _validate_table_name(name)
        return names

    def export_table(
        self,
        connection: sqlite3.Connection,
        name: str,
        destination: Path,
        *,
        where: str | None = None,
        parameters: Sequence[str] = (),
    ) -> int:
        """Export one source table to one validated Parquet file."""
        _validate_table_name(name)
        quoted_name = f'"{name}"'
        columns = connection.execute(f"PRAGMA table_info({quoted_name})").fetchall()
        if not columns:
            raise ValueError(f"missing SQLite table: {name}")
        field_names = [column[1] for column in columns]
        for column in columns:
            if column[2].upper() not in _SOURCE_TYPES:
                raise ValueError(f"unsupported declared type in {name}.{column[1]}")

        shadowed = {field_name.casefold() for field_name in field_names}
        rowid_name = next(
            (
                candidate
                for candidate in ("rowid", "_rowid_", "oid")
                if candidate.casefold() not in shadowed
            ),
            None,
        )
        if rowid_name is None:
            raise ValueError(f"no accessible rowid for table {name}")

        schema = pa.schema([pa.field(field_name, pa.string()) for field_name in field_names])
        query = f"SELECT * FROM {quoted_name}"
        if where is not None:
            query += f" WHERE {where}"
        query += f" ORDER BY {rowid_name}"
        source_rows = connection.execute(query, tuple(parameters))
        if [column[0] for column in source_rows.description] != field_names:
            raise ValueError(f"column mismatch in table {name}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        row_count = 0
        batch_size = min(
            _MAX_ROWS_PER_BATCH,
            max(1, _TARGET_CELLS_PER_BATCH // max(1, len(field_names))),
        )
        with pq.ParquetWriter(destination, schema) as writer:
            while rows := source_rows.fetchmany(batch_size):
                values: list[list[str | None]] = [[] for _ in field_names]
                for row in rows:
                    for index, value in enumerate(row):
                        if value is not None and not isinstance(value, str):
                            raise TypeError(
                                f"unsupported SQLite value in {name}.{field_names[index]}"
                            )
                        values[index].append(value)
                arrays = [pa.array(column, type=pa.string()) for column in values]
                writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
                row_count += len(rows)

        metadata = pq.read_metadata(destination)
        if metadata.num_rows != row_count:
            raise ValueError(f"Parquet row-count validation failed for table {name}")
        if not metadata.schema.to_arrow_schema().equals(schema):
            raise ValueError(f"Parquet schema validation failed for table {name}")
        return row_count


def _validate_table_name(name: str) -> None:
    if _TABLE_NAME.fullmatch(name) is None:
        raise ValueError(f"invalid table name: {name!r}")
