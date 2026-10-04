"""Orchestrate raw SQLite to processed Parquet preprocessing."""

from __future__ import annotations

from pathlib import Path

from data.config import DataPaths
from data.preprocesser.read_sqlite import SQLiteReader
from data.preprocesser.snapshot import SnapshotPublisher
from data.race_key import RaceKey


class DataPreprocesser:
    """Coordinate complete and race-scoped processed-data publication."""

    def __init__(self, paths: DataPaths) -> None:
        publisher = SnapshotPublisher(SQLiteReader(paths.raw_db), paths.processed_dir)
        self._publisher = publisher

    @classmethod
    def from_toml(cls, config_path: Path) -> DataPreprocesser:
        """Construct the preprocessor from the shared data configuration."""
        return cls(DataPaths.from_toml(config_path))

    def rebuild(self) -> dict[str, int]:
        """Rebuild and publish a complete Parquet snapshot."""
        return self._publisher.rebuild()

    def update(self) -> dict[str, int]:
        """Refresh the complete Parquet snapshot from the latest raw database."""
        return self._publisher.rebuild()

    def update_race(self, race_key: RaceKey) -> dict[str, int]:
        """Publish prediction-time Parquet data for one race."""
        return self._publisher.update_race(race_key)
