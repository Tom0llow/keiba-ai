"""Load filesystem paths shared by race-data workflows."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        with resolved.open("rb") as config_file:
            config = tomllib.load(config_file)
        paths = config.get("paths")
        if not isinstance(paths, dict):
            raise ValueError("config must contain a [paths] section")
        return cls(
            raw_db=_resolve_path(resolved, paths, "raw_db"),
            processed_dir=_resolve_path(resolved, paths, "processed_dir"),
            jvlink_runtime_dir=_resolve_path(resolved, paths, "jvlink_runtime_dir"),
        )


def _resolve_path(config_path: Path, paths: dict[str, Any], key: str) -> Path:
    value = paths.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"[paths].{key} must be a non-empty string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()
