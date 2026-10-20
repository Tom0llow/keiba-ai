"""Build processed snapshots from one consistent raw SQLite observation."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from configuration.data_paths import DataPaths
from data.loader.read_parquet import read_parquet_metadata
from data.loader.read_sqlite import SQLiteReader
from data.preprocessor.sqlite_to_arrow import (
    sqlite_arrow_schema,
    sqlite_batch_size,
    sqlite_rows_to_arrow,
)
from data.saver.write_parquet import write_parquet_batches
from data.storage.snapshot_publisher import publish_snapshot
from data.storage.snapshot_store import SnapshotStore
from domain.race_key import RaceKey

_REALTIME_TABLES = ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN")
_RACE_FILTER = (
    "idYear = ? AND idMonthDay = ? AND idJyoCD = ? AND "
    "idKaiji = ? AND idNichiji = ? AND idRaceNum = ?"
)


class SnapshotBuilder:
    """Coordinate reading, pure conversion, writing and completed-version publication."""

    def __init__(self, paths: DataPaths) -> None:
        self._reader = SQLiteReader(paths.raw_db)
        self._store = SnapshotStore(paths.processed_dir)

    @classmethod
    def from_toml(cls, config_path: Path) -> SnapshotBuilder:
        """Construct the builder from the shared data configuration."""
        return cls(DataPaths.from_toml(config_path))

    def rebuild(self) -> dict[str, int]:
        """Build and atomically publish a complete processed snapshot."""
        return self._publish()

    def update(self) -> dict[str, int]:
        """Refresh the complete snapshot from the latest raw database."""
        return self.rebuild()

    def update_race(self, race_key: RaceKey) -> dict[str, int]:
        """Publish prediction-time tables for one target race."""
        return self._publish(race_key)

    def _publish(self, race_key: RaceKey | None = None) -> dict[str, int]:
        versions, pointer = self._store.locations(race_key)
        versions.mkdir(parents=True, exist_ok=True)
        version_id = uuid.uuid4().hex
        staging = Path(tempfile.mkdtemp(prefix=f".{version_id}-", dir=versions))
        parameters = (
            (
                f"{race_key.race_date:%Y}",
                f"{race_key.race_date:%m%d}",
                race_key.jyo_code,
                race_key.kaiji,
                race_key.nichiji,
                race_key.race_number,
            )
            if race_key is not None
            else ()
        )
        try:
            counts: dict[str, int] = {}
            with self._reader.snapshot() as connection:
                selected = (
                    self._reader.list_tables(connection) if race_key is None else _REALTIME_TABLES
                )
                for name in selected:
                    schema = sqlite_arrow_schema(name, self._reader.columns(connection, name))
                    rows = self._reader.iter_rows(
                        connection,
                        name,
                        schema.names,
                        batch_size=sqlite_batch_size(len(schema)),
                        where=_RACE_FILTER if race_key is not None else None,
                        parameters=parameters,
                    )
                    batches = (sqlite_rows_to_arrow(name, schema, batch) for batch in rows)
                    destination = staging / f"{name}.parquet"
                    counts[name] = write_parquet_batches(destination, schema, batches)
                    metadata = read_parquet_metadata(destination)
                    if metadata.num_rows != counts[name]:
                        raise ValueError(f"Parquet row-count validation failed for table {name}")
                    if not metadata.schema.to_arrow_schema().equals(schema):
                        raise ValueError(f"Parquet schema validation failed for table {name}")
            publish_snapshot(staging, versions, pointer, version_id)
            return counts
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise


# Preserve the documented API spelling while naming the actual responsibility.
DataPreprocesser = SnapshotBuilder
