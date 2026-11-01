"""Compose explicit published-market snapshot preparation settings with Hydra."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf


def load_real_market_config(
    config_dir: Path, *, config_name: str = "prepare", overrides: Sequence[str] = ()
) -> dict[str, object]:
    """Resolve required values without reading source tables or importing models."""
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        value = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(value, dict) or set(value) != {
        "processed_root",
        "snapshot_id",
        "parameters",
        "labels",
    }:
        raise ValueError(
            "real market config requires processed_root, snapshot_id, parameters and labels"
        )
    if (
        not isinstance(value["processed_root"], str)
        or not value["processed_root"]
        or (value["snapshot_id"] is not None and not isinstance(value["snapshot_id"], str))
        or not isinstance(value["parameters"], dict)
        or (value["labels"] is not None and not isinstance(value["labels"], dict))
    ):
        raise ValueError("invalid real market configuration types")
    return cast(dict[str, object], value)
