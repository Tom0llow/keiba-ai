"""Compose and structurally validate yearly-fold PL evaluation settings."""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise
from math import isfinite
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

_KEYS = {
    "datamart_path",
    "datamart_manifest_sha256",
    "train_start_year",
    "test_years",
    "variants",
    "lightgbm",
    "num_boost_round",
    "early_stopping_rounds",
    "temperature_bounds",
    "probability_chunk_races",
    "bootstrap",
    "probability_bands",
    "odds_bands",
}
_BOOTSTRAP_KEYS = {"resamples", "seed", "confidence"}
_VARIANT_KEYS = {"name", "excluded_columns"}


def load_pl_evaluation_config(
    config_dir: Path, *, config_name: str = "evaluate", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Return a resolved config with exact keys, valid types and ordered bands.

    Column existence is checked by the caller after reading the datamart.
    """
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict) or set(raw) != _KEYS:
        raise ValueError("PL evaluation config has missing or unsupported keys")
    values = cast(dict[str, object], raw)
    if not isinstance(values["datamart_path"], str) or not values["datamart_path"]:
        raise ValueError("datamart_path must be a nonempty string")
    digest = values["datamart_manifest_sha256"]
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("datamart_manifest_sha256 must be a lowercase SHA-256 hex digest")
    _integer(values["train_start_year"], "train_start_year")
    test_years = values["test_years"]
    if not isinstance(test_years, list) or not test_years:
        raise ValueError("test_years must be a nonempty list")
    for year in test_years:
        _integer(year, "test_years")
    if any(left >= right for left, right in pairwise(test_years)):
        raise ValueError("test_years must be strictly increasing")
    _variants(values["variants"])
    lightgbm = values["lightgbm"]
    if not isinstance(lightgbm, dict) or any(not isinstance(key, str) for key in lightgbm):
        raise ValueError("lightgbm must be a mapping with string keys")
    for name in ("num_boost_round", "early_stopping_rounds", "probability_chunk_races"):
        if _integer(values[name], name) < 1:
            raise ValueError(f"{name} must be a positive integer")
    bounds = _numbers(values["temperature_bounds"], "temperature_bounds")
    if len(bounds) != 2 or not 0.0 < bounds[0] < bounds[1]:
        raise ValueError("temperature_bounds must be two increasing positive numbers")
    bootstrap = values["bootstrap"]
    if not isinstance(bootstrap, dict) or set(bootstrap) != _BOOTSTRAP_KEYS:
        raise ValueError("bootstrap must contain resamples, seed and confidence")
    if _integer(bootstrap["resamples"], "bootstrap.resamples") < 1:
        raise ValueError("bootstrap.resamples must be a positive integer")
    if _integer(bootstrap["seed"], "bootstrap.seed") < 0:
        raise ValueError("bootstrap.seed must be a non-negative integer")
    (confidence,) = _numbers([bootstrap["confidence"]], "bootstrap.confidence")
    if not 0.0 < confidence < 1.0:
        raise ValueError("bootstrap.confidence must be between zero and one")
    probability_bands = _bands(values["probability_bands"], "probability_bands")
    if probability_bands[0] != 0.0 or probability_bands[-1] != 1.0:
        raise ValueError("probability_bands must start at zero and end at one")
    if not 0.0 < _bands(values["odds_bands"], "odds_bands")[0] <= 1.0:
        raise ValueError("odds_bands must start above zero and no higher than one")
    return values


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _numbers(value: object, name: str) -> list[float]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of numbers")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(item):
            raise ValueError(f"{name} must contain finite numbers")
        result.append(float(item))
    return result


def _bands(value: object, name: str) -> list[float]:
    bands = _numbers(value, name)
    if len(bands) < 2 or any(left >= right for left, right in pairwise(bands)):
        raise ValueError(f"{name} must contain at least two strictly increasing values")
    return bands


def _variants(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("variants must be a nonempty list")
    names: set[str] = set()
    for variant in value:
        if not isinstance(variant, dict) or set(variant) != _VARIANT_KEYS:
            raise ValueError("each variant must contain name and excluded_columns")
        name = variant["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("variant names must be unique nonempty strings")
        names.add(name)
        excluded = variant["excluded_columns"]
        if (
            not isinstance(excluded, list)
            or any(not isinstance(column, str) or not column for column in excluded)
            or len(set(excluded)) != len(excluded)
        ):
            raise ValueError("variant excluded_columns must be unique nonempty strings")
