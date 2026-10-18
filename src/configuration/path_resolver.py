"""Resolve explicitly configured paths beside their configuration file."""

from pathlib import Path


def resolve_path(config_path: Path, value: object, *, field: str) -> Path:
    """Validate a path string and resolve user and relative components."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()
