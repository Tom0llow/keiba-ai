"""Calculate stable physical file identities for validated local artifacts."""

import hashlib
from pathlib import Path


def file_sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file's bytes."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
