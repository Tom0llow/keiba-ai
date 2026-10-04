"""Public processed-data loading facade."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa

from data.config import DataPaths
from data.loader.read_parquet import ParquetReader
from data.race_key import RaceKey


class DataLoader:
    """Load processed Parquet for training, analysis, and inference."""

    def __init__(self, paths: DataPaths) -> None:
        self._reader = ParquetReader(paths.processed_dir)

    @classmethod
    def from_toml(cls, config_path: Path) -> DataLoader:
        """Construct the loader from the shared data configuration."""
        return cls(DataPaths.from_toml(config_path))

    def list_tables(self) -> list[str]:
        """List tables in the current complete processed snapshot."""
        return self._reader.list_tables()

    def read_table(self, name: str) -> pa.Table:
        """Read one table from the current complete processed snapshot."""
        return self._reader.read_table(name)

    def iter_batches(
        self,
        name: str,
        *,
        batch_size: int = 1_000,
    ) -> Iterator[pa.RecordBatch]:
        """Iterate one current processed table in bounded batches."""
        return self._reader.iter_batches(name, batch_size=batch_size)

    def read_realtime_table(self, race_key: RaceKey, name: str) -> pa.Table:
        """Read one prediction-time Parquet table for the target race."""
        return self._reader.read_realtime_table(race_key, name)
