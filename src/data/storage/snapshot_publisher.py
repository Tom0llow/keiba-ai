"""Publish completed processed versions with an atomic CURRENT replacement."""

import os
import time
import uuid
from pathlib import Path

# A reader that has CURRENT open blocks os.replace on Windows (no FILE_SHARE_DELETE).
# Readers hold it for well under a millisecond, so a short bounded retry suffices.
_REPLACE_ATTEMPTS = 20
_REPLACE_RETRY_SECONDS = 0.05


def publish_snapshot(staging: Path, versions: Path, pointer: Path, version_id: str) -> None:
    """Make a completed directory visible, then atomically select it."""
    staging.rename(versions / version_id)
    publish_pointer(pointer, version_id)


def publish_pointer(path: Path, value: str) -> None:
    """Atomically replace CURRENT, retaining its previous value on failure.

    A replacement refused while a reader has CURRENT open is retried briefly; the
    temporary file is removed when every attempt fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(f"{value}\n", encoding="utf-8")
    try:
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_RETRY_SECONDS)
    finally:
        temporary.unlink(missing_ok=True)
