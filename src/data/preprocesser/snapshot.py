"""Publish atomic processed Parquet snapshots and race-scoped realtime views."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from data.preprocesser.read_sqlite import SQLiteReader
from data.race_key import RaceKey

_REALTIME_TABLES = (
    "ARCHIVE_O1_ODDS_TANFUKUWAKU",
    "ARCHIVE_O2_ODDS_UMAREN",
)
_RACE_FILTER = (
    "idYear = ? AND idMonthDay = ? AND idJyoCD = ? AND "
    "idKaiji = ? AND idNichiji = ? AND idRaceNum = ?"
)


class SnapshotPublisher:
    """Convert raw SQLite state into atomically published Parquet artifacts."""

    def __init__(self, reader: SQLiteReader, processed_dir: Path) -> None:
        self._reader = reader
        self._processed_dir = processed_dir.expanduser().resolve()

    def rebuild(self) -> dict[str, int]:
        """Create and atomically publish a complete processed snapshot."""
        snapshots = self._processed_dir / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        snapshot_id = uuid.uuid4().hex
        staging = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}-", dir=snapshots))
        try:
            with self._reader.snapshot() as connection:
                counts = {
                    name: self._reader.export_table(
                        connection,
                        name,
                        staging / f"{name}.parquet",
                    )
                    for name in self._reader.list_tables(connection)
                }
            published = snapshots / snapshot_id
            staging.rename(published)
            self._publish_pointer(self._processed_dir / "CURRENT", snapshot_id)
            return counts
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def update_race(self, race_key: RaceKey) -> dict[str, int]:
        """Publish race-scoped realtime Parquet files for one prediction target."""
        race_root = self._processed_dir / "realtime" / race_key.race_id
        versions = race_root / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        version_id = uuid.uuid4().hex
        staging = Path(tempfile.mkdtemp(prefix=f".{version_id}-", dir=versions))
        parameters = (
            f"{race_key.race_date:%Y}",
            f"{race_key.race_date:%m%d}",
            race_key.jyo_code,
            race_key.kaiji,
            race_key.nichiji,
            race_key.race_number,
        )
        try:
            with self._reader.snapshot() as connection:
                counts = {
                    name: self._reader.export_table(
                        connection,
                        name,
                        staging / f"{name}.parquet",
                        where=_RACE_FILTER,
                        parameters=parameters,
                    )
                    for name in _REALTIME_TABLES
                }
            published = versions / version_id
            staging.rename(published)
            self._publish_pointer(race_root / "CURRENT", version_id)
            return counts
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _publish_pointer(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(f"{value}\n", encoding="utf-8")
        os.replace(temporary, path)
