"""Compose required numeric projection and calculation settings with Hydra."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf


def load_model_projection_config(
    config_dir: Path, *, config_name: str = "prepare", overrides: Sequence[str] = ()
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    """Resolve mandatory settings without importing model or feature behavior."""
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        resolved = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(resolved, Mapping) or set(resolved) != {"parameters", "selected_columns"}:
        raise ValueError("projection configuration requires parameters and selected_columns")
    parameters, names = resolved["parameters"], resolved["selected_columns"]
    if (
        not isinstance(parameters, Mapping)
        or not isinstance(names, list)
        or not names
        or any(not isinstance(n, str) for n in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError(
            "projection requires explicit parameters and unique ordered selected_columns"
        )
    return cast(Mapping[str, object], parameters), tuple(cast(list[str], names))
