"""Compose Hydra feature parameters without executing configured objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf


def load_feature_calculation_config(
    config_dir: Path,
    *,
    config_name: str = "calculate",
    overrides: Sequence[str] = (),
) -> Mapping[str, object]:
    """Resolve mandatory mappings; feature boundaries own typed conversion."""
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir.resolve())):
        config = compose(config_name=config_name, overrides=list(overrides))
        resolved = OmegaConf.to_container(config, resolve=True, throw_on_missing=True)
    if not isinstance(resolved, Mapping) or set(resolved) != {"parameters"}:
        raise ValueError("calculation configuration requires only a parameters mapping")
    parameters = resolved["parameters"]
    if not isinstance(parameters, Mapping):
        raise ValueError("calculation parameters must be a mapping")
    return cast(Mapping[str, object], parameters)
