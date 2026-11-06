"""Record source and environment identity without invoking Git commands."""

from __future__ import annotations

import hashlib
import platform
from importlib.metadata import version
from pathlib import Path

from models.experiments.inputs import file_sha256


def experiment_provenance() -> dict[str, object]:
    """Return source-file digests, locked environment hash and installed versions."""
    root = Path(__file__).resolve().parents[3]
    paths = sorted((root / "src").rglob("*.py"))
    paths.extend(sorted((root / "configs" / "experiments").rglob("*.yaml")))
    paths.extend([root / "pyproject.toml", root / "uv.lock"])
    manifest = {path.relative_to(root).as_posix(): file_sha256(path) for path in paths}
    identity = "\n".join(f"{name}:{digest}" for name, digest in sorted(manifest.items()))
    return {
        "source_sha256": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "source_files": manifest,
        "python": platform.python_version(),
        "dependencies": {
            name: version(name)
            for name in ("hydra-core", "omegaconf", "mlflow", "lightgbm", "scikit-learn", "pyarrow")
        },
        "uv_lock_sha256": manifest["uv.lock"],
    }
