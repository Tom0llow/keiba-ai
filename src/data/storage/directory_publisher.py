"""Publish one completed directory and remove private staging on every failure."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def publish_directory(output: Path) -> Iterator[Path]:
    """Yield same-parent staging, then expose it with one directory rename."""
    parent = output.parent
    if output.exists() or output.is_symlink():
        raise ValueError("output must be a new non-symbolic-link path")
    if not parent.is_dir():
        raise ValueError("output parent directory must already exist")
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent))
    try:
        if staging.resolve().parent != parent.resolve():
            raise ValueError("staging directory escaped the output parent")
        yield staging
        if output.exists() or output.is_symlink():
            raise ValueError("output appeared before publication")
        staging.rename(output)
    except BaseException as exc:
        if staging.exists():
            if staging.resolve().parent != parent.resolve():
                raise RuntimeError("refusing to remove staging outside the output parent") from exc
            shutil.rmtree(staging)
        raise
