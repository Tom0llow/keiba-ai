"""Compose and structurally validate the ADR-043 betting backtest settings."""

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
    "pl_evaluation_path",
    "pl_predictions_sha256",
    "pl_report_sha256",
    "pl_variant",
    "test_years",
    "bet_types",
    "policy",
    "final_odds",
    "bootstrap",
}
_POLICY_KEYS = {
    "min_expected_return",
    "kelly_fraction",
    "bankroll_yen",
    "annual_budget_yen",
    "race_budget_yen",
    "unit_yen",
}
_FINAL_ODDS_KEYS = {
    "train_start_year",
    "max_publication_age_seconds",
    "place_mid_bands",
    "quantiles",
    "min_hits",
    "graded_shrinkage_k",
}
_BOOTSTRAP_KEYS = {"resamples", "seed", "confidence"}
_SHA256 = re.compile(r"[0-9a-f]{64}")


def load_betting_backtest_config(
    config_dir: Path, *, config_name: str = "evaluate", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Return a resolved config with exact keys, valid types and ordered values.

    Every check runs before any input is read.
    """
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict) or set(raw) != _KEYS:
        raise ValueError("betting backtest config has missing or unsupported keys")
    values = cast(dict[str, object], raw)
    for name in ("processed_root", "pl_evaluation_path", "pl_variant"):
        if not isinstance(values[name], str) or not values[name]:
            raise ValueError(f"{name} must be a nonempty string")
    for name in ("pl_predictions_sha256", "pl_report_sha256"):
        value = values[name]
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    test_years = values["test_years"]
    if not isinstance(test_years, list) or not test_years:
        raise ValueError("test_years must be a nonempty list")
    years = [_year(year, "test_years") for year in test_years]
    if any(left >= right for left, right in pairwise(years)):
        raise ValueError("test_years must be strictly increasing")
    if values["bet_types"] != ["win", "place"]:
        raise ValueError("bet_types must be exactly [win, place] (ADR-043)")
    _policy(values["policy"])
    _final_odds(values["final_odds"], years[0])
    _bootstrap(values["bootstrap"])
    return values


def _policy(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _POLICY_KEYS:
        raise ValueError("policy has missing or unsupported keys")
    for name in ("min_expected_return", "kelly_fraction"):
        (number,) = _numbers([value[name]], f"policy.{name}")
        if number <= 0.0:
            raise ValueError(f"policy.{name} must be positive")
    (minimum,) = _numbers([value["min_expected_return"]], "policy.min_expected_return")
    if minimum < 1.0:
        raise ValueError("policy.min_expected_return must be at least 1.0")
    for name in ("bankroll_yen", "annual_budget_yen", "race_budget_yen", "unit_yen"):
        if _integer(value[name], f"policy.{name}") < 1:
            raise ValueError(f"policy.{name} must be a positive integer")
    if cast(int, value["unit_yen"]) % 100 != 0:
        raise ValueError("policy.unit_yen must be a multiple of 100")


def _final_odds(value: object, first_test_year: int) -> None:
    if not isinstance(value, dict) or set(value) != _FINAL_ODDS_KEYS:
        raise ValueError("final_odds has missing or unsupported keys")
    if _year(value["train_start_year"], "final_odds.train_start_year") >= first_test_year:
        raise ValueError("final_odds.train_start_year must be before every test year")
    if _integer(value["max_publication_age_seconds"], "final_odds.max_publication_age_seconds") < 1:
        raise ValueError("final_odds.max_publication_age_seconds must be a positive integer")
    bands = _numbers(value["place_mid_bands"], "final_odds.place_mid_bands")
    if not bands or any(left >= right for left, right in pairwise(bands)) or bands[0] < 1.0:
        raise ValueError("final_odds.place_mid_bands must start at 1.0 and strictly increase")
    quantiles = _numbers(value["quantiles"], "final_odds.quantiles")
    if not quantiles or any(left >= right for left, right in pairwise(quantiles)):
        raise ValueError("final_odds.quantiles must be nonempty and strictly increasing")
    if quantiles[0] < 0.0 or quantiles[-1] > 1.0:
        raise ValueError("final_odds.quantiles must be between zero and one")
    if _integer(value["min_hits"], "final_odds.min_hits") < 1:
        raise ValueError("final_odds.min_hits must be a positive integer")
    if _integer(value["graded_shrinkage_k"], "final_odds.graded_shrinkage_k") < 0:
        raise ValueError("final_odds.graded_shrinkage_k must be a non-negative integer")


def _bootstrap(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _BOOTSTRAP_KEYS:
        raise ValueError("bootstrap must contain resamples, seed and confidence")
    if _integer(value["resamples"], "bootstrap.resamples") < 1:
        raise ValueError("bootstrap.resamples must be a positive integer")
    if _integer(value["seed"], "bootstrap.seed") < 0:
        raise ValueError("bootstrap.seed must be a non-negative integer")
    (confidence,) = _numbers([value["confidence"]], "bootstrap.confidence")
    if not 0.0 < confidence < 1.0:
        raise ValueError("bootstrap.confidence must be between zero and one")


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
