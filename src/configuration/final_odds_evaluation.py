"""Compose and structurally validate final-odds correction evaluation settings."""

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
    "processed_root",
    "snapshot_id",
    "train_start_year",
    "test_years",
    "max_publication_age_seconds",
    "bands",
    "quantiles",
    "min_hits",
    "graded_shrinkage_k",
    "bootstrap",
}
_BET_TYPES = {"win", "place_low", "place_mid", "quinella"}
_BOOTSTRAP_KEYS = {"resamples", "seed", "confidence"}


def load_final_odds_evaluation_config(
    config_dir: Path, *, config_name: str = "evaluate", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Return a resolved config with exact keys, valid types and ordered values.

    Every check runs before any processed data is read.
    """
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict) or set(raw) != _KEYS:
        raise ValueError("final odds evaluation config has missing or unsupported keys")
    values = cast(dict[str, object], raw)
    if not isinstance(values["processed_root"], str) or not values["processed_root"]:
        raise ValueError("processed_root must be a nonempty string")
    snapshot_id = values["snapshot_id"]
    if snapshot_id is not None and (
        not isinstance(snapshot_id, str) or re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id) is None
    ):
        raise ValueError("snapshot_id must be null or a snapshot directory name")
    train_start_year = _year(values["train_start_year"], "train_start_year")
    test_years = values["test_years"]
    if not isinstance(test_years, list) or not test_years:
        raise ValueError("test_years must be a nonempty list")
    years = [_year(year, "test_years") for year in test_years]
    if any(left >= right for left, right in pairwise(years)):
        raise ValueError("test_years must be strictly increasing")
    if years[0] <= train_start_year:
        raise ValueError("every test year must be after train_start_year")
    if _integer(values["max_publication_age_seconds"], "max_publication_age_seconds") < 1:
        raise ValueError("max_publication_age_seconds must be a positive integer")
    bands = values["bands"]
    if not isinstance(bands, dict) or set(bands) != _BET_TYPES:
        raise ValueError("bands must contain exactly win, place_low, place_mid and quinella")
    for name, edges in bands.items():
        numbers = _numbers(edges, f"bands.{name}")
        if not numbers or any(left >= right for left, right in pairwise(numbers)):
            raise ValueError(f"bands.{name} must be nonempty and strictly increasing")
        if numbers[0] < 1.0:
            raise ValueError(f"bands.{name} must start at 1.0 or higher")
    quantiles = _numbers(values["quantiles"], "quantiles")
    if not quantiles or any(left >= right for left, right in pairwise(quantiles)):
        raise ValueError("quantiles must be nonempty and strictly increasing")
    if quantiles[0] < 0.0 or quantiles[-1] > 1.0:
        raise ValueError("quantiles must be between zero and one")
    if _integer(values["min_hits"], "min_hits") < 1:
        raise ValueError("min_hits must be a positive integer")
    if _integer(values["graded_shrinkage_k"], "graded_shrinkage_k") < 0:
        raise ValueError("graded_shrinkage_k must be a non-negative integer")
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
    return values


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _year(value: object, name: str) -> int:
    year = _integer(value, name)
    if not 1000 <= year <= 9999:
        raise ValueError(f"{name} must contain four-digit years")
    return year


def _numbers(value: object, name: str) -> list[float]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of numbers")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(item):
            raise ValueError(f"{name} must contain finite numbers")
        result.append(float(item))
    return result
