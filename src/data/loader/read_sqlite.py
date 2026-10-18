"""Read raw SQLite tables through one read-only transaction."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class SQLiteReader:
    """Own read-only access to a SQLite database and bounded row cursors."""

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
                "SELECT name FROM sqlite_schema WHERE type = ? AND name NOT GLOB ? ORDER BY name",
                ("table", "sqlite_%"),
            )
        ]
        for name in names:
            _validate_table_name(name)
        return names

    def columns(self, connection: sqlite3.Connection, name: str) -> tuple[tuple[str, str], ...]:
        """Return ordered column names and declared SQLite types."""
        _validate_table_name(name)
        columns = connection.execute(f'PRAGMA table_info("{name}")').fetchall()
        if not columns:
            raise ValueError(f"missing SQLite table: {name}")
        return tuple((column[1], column[2]) for column in columns)

    def iter_rows(
        self,
        connection: sqlite3.Connection,
        name: str,
        field_names: Sequence[str],
        *,
        batch_size: int,
        where: str | None = None,
        parameters: Sequence[str] = (),
    ) -> Iterator[list[tuple[object, ...]]]:
        """Yield rowid-ordered batches using an internal SQL predicate."""
        _validate_table_name(name)
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        shadowed = {field_name.casefold() for field_name in field_names}
        rowid_name = next(
            (candidate for candidate in ("rowid", "_rowid_", "oid") if candidate not in shadowed),
            None,
        )
        if rowid_name is None:
            raise ValueError(f"no accessible rowid for table {name}")
        query = f'SELECT * FROM "{name}"'
        if where is not None:
            query += f" WHERE {where}"
        query += f" ORDER BY {rowid_name}"
        source_rows = connection.execute(query, tuple(parameters))
        if [column[0] for column in source_rows.description] != list(field_names):
            raise ValueError(f"column mismatch in table {name}")
        while rows := source_rows.fetchmany(batch_size):
            yield rows


def _validate_table_name(name: str) -> None:
    if _TABLE_NAME.fullmatch(name) is None:
        raise ValueError(f"invalid table name: {name!r}")
