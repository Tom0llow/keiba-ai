"""Compose and structurally validate saved PL-variant comparison settings."""

from __future__ import annotations

import re
from collections.abc import Sequence
from math import isfinite
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

_KEYS = {
    "evaluation_path",
    "pl_report_sha256",
    "pl_predictions_sha256",
    "processed_root",
    "comparisons",
    "bootstrap",
}
_COMPARISON_KEYS = {"candidate", "baseline"}
_BOOTSTRAP_KEYS = {"resamples", "seed", "confidence"}
_SHA256 = re.compile(r"[0-9a-f]{64}")


def load_pl_comparison_config(
    config_dir: Path, *, config_name: str = "compare", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Return a resolved config with exact keys and valid comparison settings."""
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    return validate_pl_comparison_config(raw)


def validate_pl_comparison_config(raw: object) -> dict[str, object]:
    """Return ``raw`` after checking all input-independent comparison settings."""
    if not isinstance(raw, dict) or set(raw) != _KEYS:
        raise ValueError("PL comparison config has missing or unsupported keys")
    values = cast(dict[str, object], raw)
    for name in ("evaluation_path", "processed_root"):
        if not isinstance(values[name], str) or not values[name]:
            raise ValueError(f"{name} must be a nonempty string")
    for name in ("pl_report_sha256", "pl_predictions_sha256"):
        value = values[name]
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    _comparisons(values["comparisons"])
    _bootstrap(values["bootstrap"])
    return values


def _comparisons(value: object) -> None:
    """Reject empty, duplicate, or self-comparison requests before inputs are read."""
    if not isinstance(value, list) or not value:
        raise ValueError("comparisons must be a nonempty list")
    pairs: set[tuple[str, str]] = set()
    for comparison in value:
        if not isinstance(comparison, dict) or set(comparison) != _COMPARISON_KEYS:
            raise ValueError("each comparison must contain candidate and baseline")
        candidate = comparison["candidate"]
        baseline = comparison["baseline"]
        if (
            not isinstance(candidate, str)
            or not candidate
            or not isinstance(baseline, str)
            or not baseline
        ):
            raise ValueError("comparison variants must be nonempty strings")
        if candidate == baseline:
            raise ValueError("comparison candidate and baseline must differ")
        pair = (candidate, baseline)
        if pair in pairs:
            raise ValueError("comparison pairs must be unique")
        pairs.add(pair)


def _bootstrap(value: object) -> None:
    """Reject invalid paired-bootstrap parameters."""
    if not isinstance(value, dict) or set(value) != _BOOTSTRAP_KEYS:
        raise ValueError("bootstrap must contain resamples, seed and confidence")
    if _integer(value["resamples"], "bootstrap.resamples") < 1:
        raise ValueError("bootstrap.resamples must be a positive integer")
    if _integer(value["seed"], "bootstrap.seed") < 0:
        raise ValueError("bootstrap.seed must be a non-negative integer")
    confidence = _number(value["confidence"], "bootstrap.confidence")
    if not 0.0 < confidence < 1.0:
        raise ValueError("bootstrap.confidence must be between zero and one")


def _integer(value: object, name: str) -> int:
    """Return an integer external value without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    """Return one finite numeric external value without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)
