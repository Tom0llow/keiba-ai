"""Read processed Parquet snapshots for training and inference."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from data.race_key import RaceKey

_DEFAULT_BATCH_SIZE = 1_000
_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class ParquetReader:
    """Read complete snapshots and race-scoped prediction-time Parquet."""

    def __init__(self, processed_dir: Path) -> None:
        self._processed_dir = processed_dir.expanduser().resolve()

    def current_snapshot(self) -> Path:
        """Resolve the snapshot selected by the processed ``CURRENT`` pointer."""
        return self._resolve_pointer(
            self._processed_dir / "CURRENT",
            self._processed_dir / "snapshots",
        )

    def list_tables(self) -> list[str]:
        """Return Parquet table names in the active complete snapshot."""
        return sorted(
            path.stem for path in self.current_snapshot().glob("*.parquet") if path.is_file()
        )

    def read_table(self, name: str) -> pa.Table:
        """Read one complete processed table."""
        return pq.read_table(self._table_path(name))

    def iter_batches(
        self,
        name: str,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> Iterator[pa.RecordBatch]:
        """Yield bounded batches from one processed table."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        with self._table_path(name).open("rb") as source:
            yield from pq.ParquetFile(source).iter_batches(batch_size=batch_size)

    def read_realtime_table(self, race_key: RaceKey, name: str) -> pa.Table:
        """Read one race-scoped prediction-time table from its active version."""
        _validate_table_name(name)
        race_root = self._processed_dir / "realtime" / race_key.race_id
        version = self._resolve_pointer(race_root / "CURRENT", race_root / "versions")
        path = version / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(path)
        return pq.read_table(path)

    def _table_path(self, name: str) -> Path:
        _validate_table_name(name)
        path = self.current_snapshot() / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    @staticmethod
    def _resolve_pointer(pointer: Path, versions: Path) -> Path:
        if not pointer.is_file():
            raise FileNotFoundError(pointer)
        version_id = pointer.read_text(encoding="utf-8").strip()
        if not version_id:
            raise ValueError(f"empty processed snapshot pointer: {pointer}")
        version = versions / version_id
        if not version.is_dir():
            raise FileNotFoundError(version)
        return version


def _validate_table_name(name: str) -> None:
    if _TABLE_NAME.fullmatch(name) is None:
        raise ValueError(f"invalid table name: {name!r}")
