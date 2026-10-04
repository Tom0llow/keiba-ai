"""Read processed Parquet snapshots for training and inference."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

_DEFAULT_BATCH_SIZE = 1_000


class ParquetReader:
    """Read tables from the currently published processed snapshot."""

    def __init__(self, processed_dir: Path) -> None:
        self._processed_dir = processed_dir.expanduser().resolve()

    def current_snapshot(self) -> Path:
        """Resolve the snapshot selected by the processed ``CURRENT`` pointer."""
        current = self._processed_dir / "CURRENT"
        if not current.is_file():
            raise FileNotFoundError(current)
        snapshot_id = current.read_text(encoding="utf-8").strip()
        if not snapshot_id:
            raise ValueError(f"empty processed snapshot pointer: {current}")
        snapshot = self._processed_dir / "snapshots" / snapshot_id
        if not snapshot.is_dir():
            raise FileNotFoundError(snapshot)
        return snapshot

    def list_tables(self) -> list[str]:
        """Return Parquet table names in the active snapshot."""
        return sorted(path.stem for path in self.current_snapshot().glob("*.parquet") if path.is_file())

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

    def _table_path(self, name: str) -> Path:
        if not name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in name):
            raise ValueError(f"invalid table name: {name!r}")
        path = self.current_snapshot() / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
