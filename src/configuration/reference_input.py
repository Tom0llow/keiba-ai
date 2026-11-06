"""Compose all-group snapshot reference settings without runtime data access."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf


def load_reference_input_config(
    config_dir: Path, *, config_name: str = "prepare", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Require explicit source policies, numeric projection and calculation settings."""
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        raw = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(raw, dict) or set(raw) != {
        "processed_root",
        "snapshot_id",
        "calculation_settings",
        "reference_rules",
        "selected_columns",
        "include_labels",
    }:
        raise ValueError(
            "reference config requires snapshot, settings, rules, columns and explicit label mode"
        )
    if (
        not isinstance(raw["processed_root"], str)
        or not raw["processed_root"]
        or (raw["snapshot_id"] is not None and not isinstance(raw["snapshot_id"], str))
        or not isinstance(raw["calculation_settings"], dict)
        or not isinstance(raw["reference_rules"], dict)
        or not isinstance(raw["selected_columns"], list)
        or not raw["selected_columns"]
        or any(not isinstance(c, str) for c in raw["selected_columns"])
        or type(raw["include_labels"]) is not bool
    ):
        raise ValueError("invalid reference configuration types")
    return cast(dict[str, object], raw)
