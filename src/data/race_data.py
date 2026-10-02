"""Export SQLite race tables and load their Parquet copies."""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import tomllib
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SOURCE_TYPES = {"TEXT", "DATETIME"}
_TARGET_CELLS_PER_BATCH = 1_000_000
_MAX_ROWS_PER_BATCH = 65_536
_DEFAULT_READ_BATCH_SIZE = 1_000


@dataclass(frozen=True)
class DataPaths:
    """The configured SQLite input and Parquet output locations."""

    raw_db: Path
    processed_dir: Path

    @classmethod
    def from_toml(cls, config_path: Path) -> DataPaths:
        """Read paths from TOML, resolving relative values beside the config file."""
        config_path = config_path.resolve()
        with config_path.open("rb") as config_file:
            config = tomllib.load(config_file)

        paths = config.get("paths")
        if not isinstance(paths, dict):
            raise ValueError("config must contain a [paths] section")

        def resolve_path(key: str) -> Path:
            value = paths.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"[paths].{key} must be a non-empty string")
            path = Path(value)
            return (config_path.parent / path).resolve()

        return cls(raw_db=resolve_path("raw_db"), processed_dir=resolve_path("processed_dir"))


class RaceDataLoader:
    """Read converted race tables from one configured Parquet directory."""

    def __init__(self, paths: DataPaths) -> None:
        self._processed_dir = paths.processed_dir

    def list_tables(self) -> list[str]:
        """Return the available converted table names in sorted order."""
        if not self._processed_dir.is_dir():
            raise FileNotFoundError(self._processed_dir)
        names = [path.stem for path in self._processed_dir.glob("*.parquet") if path.is_file()]
        for name in names:
            _validate_table_name(name)
        return sorted(names)

    def read_table(self, name: str) -> pa.Table:
        """Load one complete table; use iter_batches for large tables."""
        return pq.read_table(self._table_path(name))

    def iter_batches(
        self, name: str, batch_size: int = _DEFAULT_READ_BATCH_SIZE
    ) -> Iterator[pa.RecordBatch]:
        """Yield bounded record batches from a converted table."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        path = self._table_path(name)
        with path.open("rb") as source:
            yield from pq.ParquetFile(source).iter_batches(batch_size=batch_size)

    def _table_path(self, name: str) -> Path:
        _validate_table_name(name)
        path = self._processed_dir / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path


def convert_all_tables(paths: DataPaths) -> dict[str, int]:
    """Export every user table from one SQLite snapshot without replacing output."""
    destination = paths.processed_dir
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)

    with closing(sqlite3.connect(f"{paths.raw_db.resolve().as_uri()}?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only = ON")
        db.execute("BEGIN")
        names = [
            name
            for (name,) in db.execute(
                "SELECT name FROM sqlite_schema WHERE type = ? AND name NOT GLOB ? ORDER BY name",
                ("table", "sqlite_%"),
            )
        ]
        for name in names:
            _validate_table_name(name)

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
        try:
            row_counts = {name: _export_table(db, name, staging) for name in names}
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(destination)
            staging.rename(destination)
        except Exception:
            shutil.rmtree(staging)
            raise

    return row_counts


def _export_table(db: sqlite3.Connection, name: str, staging: Path) -> int:
    quoted_name = f'"{name}"'
    columns = db.execute(f"PRAGMA table_info({quoted_name})").fetchall()
    field_names = [column[1] for column in columns]
    for column in columns:
        if column[2].upper() not in _SOURCE_TYPES:
            raise ValueError(f"unsupported declared type in {name}.{column[1]}")

    shadowed_names = {field_name.casefold() for field_name in field_names}
    rowid_name = next(
        (candidate for candidate in ("rowid", "_rowid_", "oid") if candidate not in shadowed_names),
        None,
    )
    if rowid_name is None:
        raise ValueError(f"no accessible rowid for table {name}")

    schema = pa.schema([pa.field(field_name, pa.string()) for field_name in field_names])
    source_rows = db.execute(f"SELECT * FROM {quoted_name} ORDER BY {rowid_name}")
    if [column[0] for column in source_rows.description] != field_names:
        raise ValueError(f"column mismatch in table {name}")

    parquet_path = staging / f"{name}.parquet"
    row_count = 0
    batch_size = min(_MAX_ROWS_PER_BATCH, max(1, _TARGET_CELLS_PER_BATCH // len(field_names)))
    with pq.ParquetWriter(parquet_path, schema) as writer:
        while rows := source_rows.fetchmany(batch_size):
            values: list[list[str | None]] = [[] for _ in field_names]
            for row in rows:
                for index, value in enumerate(row):
                    if value is not None and not isinstance(value, str):
                        raise TypeError(f"unsupported SQLite value in {name}.{field_names[index]}")
                    values[index].append(value)
            arrays = [pa.array(column, type=pa.string()) for column in values]
            writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
            row_count += len(rows)

    metadata = pq.read_metadata(parquet_path)
    if metadata.num_rows != row_count or not metadata.schema.to_arrow_schema().equals(schema):
        raise ValueError(f"Parquet validation failed for table {name}")
    return row_count


def _validate_table_name(name: str) -> None:
    if _TABLE_NAME.fullmatch(name) is None:
        raise ValueError(f"invalid table name: {name!r}")
