"""Create a small file exclusively, or replace it atomically only when unchanged."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

# A reader that has the file open blocks os.replace on Windows (no FILE_SHARE_DELETE).
# Readers hold it briefly, so the bounded retry of snapshot_publisher.publish_pointer suffices.
_REPLACE_ATTEMPTS = 20
_REPLACE_RETRY_SECONDS = 0.05


def create_file(path: Path, data: bytes) -> None:
    """Write ``data`` to a new file and flush it to disk.

    Raises:
        FileExistsError: If ``path`` already exists; it is left unchanged.
        OSError: If writing fails; the partly written file is removed.
    """
    with open(path, "xb") as handle:
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            path.unlink(missing_ok=True)
            raise


def replace_file_if_unchanged(path: Path, data: bytes, *, expected: bytes) -> None:
    """Atomically replace ``path`` with ``data`` when it still holds ``expected``.

    The new content is flushed to a temporary file beside ``path``. Just before each
    replacement attempt ``path`` is read again; a replacement refused while a reader has
    the file open is retried briefly. The temporary file never remains.

    Raises:
        ValueError: If ``path`` no longer holds ``expected``; it is left unchanged.
        OSError: If writing, reading or every replacement attempt fails.
    """
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporary, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(_REPLACE_ATTEMPTS):
            if _current_bytes(path) != expected:
                raise ValueError(f"{path.name} changed before it could be replaced")
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_RETRY_SECONDS)
    finally:
        temporary.unlink(missing_ok=True)


def _current_bytes(path: Path) -> bytes:
    return path.read_bytes()


__all__ = ["create_file", "replace_file_if_unchanged"]
