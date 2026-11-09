"""Compose and structurally validate reference-datamart build settings."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

_CALCULATION_KEYS = {
    "rule_id",
    "history_start",
    "lag_count",
    "count_window",
    "days_window",
    "half_life_days",
    "condition_keys",
    "condition_window_order",
    "smoothing_alpha",
    "minimum_count",
    "partial_rank",
    "tie_policy",
    "metric",
    "metric_direction",
    "class_order",
    "style_window",
    "style_minimum_count",
    "leader_threshold",
    "front_threshold",
    "pedigree_include_self",
    "workout_distance_m",
    "workout_section_distance_m",
    "market_anchor_seconds",
    "market_max_age_seconds",
    "market_version_tolerance_seconds",
    "graph_days",
    "graph_half_life_days",
    "graph_edge_rule",
    "graph_base_weight",
    "graph_damping",
    "graph_tolerance",
    "graph_max_iterations",
}
_REFERENCE_RULE_KEYS = {
    "source_rule_id",
    "schedule_basis",
    "reception_basis",
    "card_basis",
    "pedigree_basis",
    "workout_basis",
    "parameter_basis",
    "coverage_scope",
    "exception_policy",
    "class_policy",
    "freeze_offset_seconds",
    "minimum_supported_year",
    "venues",
    "result_delay_days",
}


def load_reference_datamart_config(
    config_dir: Path, *, config_name: str = "build", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Return a resolved config with exact required keys and ordered ISO dates."""
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict) or set(raw) != {
        "processed_root",
        "snapshot_id",
        "target_start",
        "target_end",
        "calculation_settings",
        "reference_rules",
    }:
        raise ValueError("reference datamart config has missing or unsupported keys")
    if (
        not isinstance(raw["processed_root"], str)
        or not raw["processed_root"]
        or (raw["snapshot_id"] is not None and not isinstance(raw["snapshot_id"], str))
        or not isinstance(raw["calculation_settings"], dict)
        or set(raw["calculation_settings"]) != _CALCULATION_KEYS
        or not isinstance(raw["reference_rules"], dict)
        or set(raw["reference_rules"]) != _REFERENCE_RULE_KEYS
    ):
        raise ValueError("reference datamart config types or nested keys are invalid")
    target_start = _iso_date(raw["target_start"], "target_start")
    target_end = _iso_date(raw["target_end"], "target_end")
    history_start = _iso_date(
        cast(dict[str, object], raw["calculation_settings"])["history_start"],
        "calculation_settings.history_start",
    )
    if target_start > target_end:
        raise ValueError("target_start must not be later than target_end")
    if history_start > target_start:
        raise ValueError("history_start must not be later than target_start")
    return cast(dict[str, object], raw)


def _iso_date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must be an ISO date")
    return parsed
