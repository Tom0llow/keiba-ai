"""Load filesystem paths shared by race-data retrieval workflows."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RetrievalPaths:
    """Configured locations required by race-data acquisition."""

    raw_db: Path
    jvlink_runtime_dir: Path

    @classmethod
    def from_toml(cls, config_path: Path) -> RetrievalPaths:
        """Read retrieval paths from the shared data configuration."""
        resolved = config_path.expanduser().resolve()
        with resolved.open("rb") as config_file:
            config = tomllib.load(config_file)
        paths = config.get("paths")
        if not isinstance(paths, dict):
            raise ValueError("config must contain a [paths] section")
        return cls(
            raw_db=_resolve_path(resolved, paths, "raw_db"),
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
