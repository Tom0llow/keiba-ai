"""Compose and structurally validate final PL training settings (ADR-038)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from math import isfinite
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

_KEYS = {
    "datamart_path",
    "datamart_manifest_sha256",
    "train_start_year",
    "valid_year",
    "variant",
    "lightgbm",
    "num_boost_round",
    "early_stopping_rounds",
    "temperature_bounds",
}
_VARIANT_KEYS = {"name", "excluded_columns"}


def load_pl_training_config(
    config_dir: Path, *, config_name: str = "train", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Return a resolved config with exact keys and valid types.

    Years against the datamart period, column names and reserved LightGBM keys are
    checked by the caller once the pinned datamart manifest is read.
    """
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict) or set(raw) != _KEYS:
        raise ValueError("PL training config has missing or unsupported keys")
    values = cast(dict[str, object], raw)
    if not isinstance(values["datamart_path"], str) or not values["datamart_path"]:
        raise ValueError("datamart_path must be a nonempty string")
    digest = values["datamart_manifest_sha256"]
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("datamart_manifest_sha256 must be a lowercase SHA-256 hex digest")
    for name in ("train_start_year", "valid_year", "num_boost_round", "early_stopping_rounds"):
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    variant = values["variant"]
    if not isinstance(variant, dict) or set(variant) != _VARIANT_KEYS:
        raise ValueError("variant must contain name and excluded_columns")
    if not isinstance(variant["name"], str) or not variant["name"]:
        raise ValueError("variant name must be a nonempty string")
    excluded = variant["excluded_columns"]
    if (
        not isinstance(excluded, list)
        or any(not isinstance(column, str) or not column for column in excluded)
        or len(set(excluded)) != len(excluded)
    ):
        raise ValueError("variant excluded_columns must be unique nonempty strings")
    lightgbm = values["lightgbm"]
    if not isinstance(lightgbm, dict) or any(not isinstance(key, str) for key in lightgbm):
        raise ValueError("lightgbm must be a mapping with string keys")
    bounds = values["temperature_bounds"]
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(item)
            for item in bounds
        )
        or not 0.0 < bounds[0] < bounds[1]
    ):
        raise ValueError("temperature_bounds must be two increasing positive numbers")
    return values
