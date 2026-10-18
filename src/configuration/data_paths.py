"""Load filesystem paths shared by race-data workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from configuration.loader import load_toml
from configuration.path_resolver import resolve_path


@dataclass(frozen=True)
class DataPaths:
    """Configured locations for raw, processed, and JVLink runtime data."""

    raw_db: Path
    processed_dir: Path
    jvlink_runtime_dir: Path

    @classmethod
    def from_toml(cls, config_path: Path) -> DataPaths:
        """Read shared paths from TOML and resolve relative paths beside it."""
        resolved = config_path.expanduser().resolve()
        config = load_toml(resolved)
        paths = config.get("paths")
        if not isinstance(paths, dict):
            raise ValueError("config must contain a [paths] section")
        return cls(
            raw_db=resolve_path(resolved, paths.get("raw_db"), field="[paths].raw_db"),
            processed_dir=resolve_path(
                resolved, paths.get("processed_dir"), field="[paths].processed_dir"
            ),
            jvlink_runtime_dir=resolve_path(
                resolved, paths.get("jvlink_runtime_dir"), field="[paths].jvlink_runtime_dir"
            ),
        )
