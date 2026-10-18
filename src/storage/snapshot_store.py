"""Own processed snapshot layout and CURRENT version resolution."""

import re
from pathlib import Path

from domain.race_key import RaceKey

_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class SnapshotStore:
    """Represent complete and race-scoped versions under one processed root."""

    def __init__(self, processed_dir: Path) -> None:
        self._processed_dir = processed_dir.expanduser().resolve()

    def locations(self, race_key: RaceKey | None = None) -> tuple[Path, Path]:
        """Return version directory and CURRENT pointer for a publication scope."""
        if race_key is None:
            return self._processed_dir / "snapshots", self._processed_dir / "CURRENT"
        race_root = self._processed_dir / "realtime" / race_key.race_id
        return race_root / "versions", race_root / "CURRENT"

    def current_snapshot(self, race_key: RaceKey | None = None) -> Path:
        """Resolve the active complete or race-scoped processed version."""
        versions, pointer = self.locations(race_key)
        if not pointer.is_file():
            raise FileNotFoundError(pointer)
        version_id = pointer.read_text(encoding="utf-8").strip()
        if not version_id:
            raise ValueError(f"empty processed snapshot pointer: {pointer}")
        version = versions / version_id
        if not version.is_dir():
            raise FileNotFoundError(version)
        return version

    def list_tables(self) -> list[str]:
        """Return table names in the currently selected complete version."""
        return sorted(
            path.stem for path in self.current_snapshot().glob("*.parquet") if path.is_file()
        )

    def table_path(self, name: str, race_key: RaceKey | None = None) -> Path:
        """Resolve one table in the selected scope without reading Parquet."""
        if _TABLE_NAME.fullmatch(name) is None:
            raise ValueError(f"invalid table name: {name!r}")
        path = self.current_snapshot(race_key) / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
