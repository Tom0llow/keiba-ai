"""Publish atomic processed Parquet snapshots and race-scoped realtime views."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from domain.race_key import RaceKey
from preprocesser.read_sqlite import SQLiteReader

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
        return self._publish(self._processed_dir / "snapshots", self._processed_dir / "CURRENT")

    def update_race(self, race_key: RaceKey) -> dict[str, int]:
        """Publish race-scoped realtime Parquet files for one prediction target."""
        race_root = self._processed_dir / "realtime" / race_key.race_id
        parameters = (
            f"{race_key.race_date:%Y}",
            f"{race_key.race_date:%m%d}",
            race_key.jyo_code,
            race_key.kaiji,
            race_key.nichiji,
            race_key.race_number,
        )
        return self._publish(
            race_root / "versions",
            race_root / "CURRENT",
            tables=_REALTIME_TABLES,
            where=_RACE_FILTER,
            parameters=parameters,
        )

    def _publish(
        self,
        versions: Path,
        pointer: Path,
        *,
        tables: tuple[str, ...] | None = None,
        where: str | None = None,
        parameters: tuple[str, ...] = (),
    ) -> dict[str, int]:
        versions.mkdir(parents=True, exist_ok=True)
        version_id = uuid.uuid4().hex
        staging = Path(tempfile.mkdtemp(prefix=f".{version_id}-", dir=versions))
        try:
            with self._reader.snapshot() as connection:
                selected = self._reader.list_tables(connection) if tables is None else tables
                counts = {
                    name: self._reader.export_table(
                        connection,
                        name,
                        staging / f"{name}.parquet",
                        where=where,
                        parameters=parameters,
                    )
                    for name in selected
                }
            published = versions / version_id
            staging.rename(published)
            self._publish_pointer(pointer, version_id)
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
