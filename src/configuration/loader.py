"""Read TOML without applying feature-specific configuration contracts."""

import tomllib
from pathlib import Path
from typing import Any


def load_toml(path: Path) -> dict[str, Any]:
    """Read an explicit TOML path, preserving filesystem and parser errors."""
    with path.open("rb") as source:
        return tomllib.load(source)
