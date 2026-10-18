"""Publish completed processed versions with an atomic CURRENT replacement."""

import os
import uuid
from pathlib import Path


def publish_snapshot(staging: Path, versions: Path, pointer: Path, version_id: str) -> None:
    """Make a completed directory visible, then atomically select it."""
    staging.rename(versions / version_id)
    publish_pointer(pointer, version_id)


def publish_pointer(path: Path, value: str) -> None:
    """Atomically replace CURRENT, retaining its previous value on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(f"{value}\n", encoding="utf-8")
    os.replace(temporary, path)
