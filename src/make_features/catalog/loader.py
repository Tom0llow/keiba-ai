"""Read the declarative feature catalog without importing implementations."""

from __future__ import annotations

import re
from pathlib import Path

from configuration.loader import load_toml
from make_features.contracts.types import FeatureDefinition

_FEATURE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def load_feature_definitions(path: str | Path) -> tuple[FeatureDefinition, ...]:
    """Read ordered unique feature IDs and names from an explicit TOML path."""
    payload = load_toml(Path(path))
    if set(payload) != {"features"}:
        raise ValueError("feature config must contain only a features list")
    raw_features = payload["features"]
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError("features must be a non-empty list")
    definitions = []
    ids: set[str] = set()
    names: set[str] = set()
    for index, entry in enumerate(raw_features):
        if not isinstance(entry, dict) or set(entry) != {"id", "name"}:
            raise ValueError(f"features[{index}] requires only id and name")
        feature_id, name = entry["id"], entry["name"]
        if (
            not isinstance(feature_id, str)
            or not feature_id.strip()
            or feature_id != feature_id.strip()
        ):
            raise ValueError(f"features[{index}].id must be a non-empty trimmed string")
        if not isinstance(name, str) or not _FEATURE_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"features[{index}].name must be a snake_case string")
        if feature_id in ids:
            raise ValueError(f"duplicate feature id: {feature_id!r}")
        if name in names:
            raise ValueError(f"duplicate feature name: {name!r}")
        ids.add(feature_id)
        names.add(name)
        definitions.append(FeatureDefinition(feature_id, name))
    return tuple(definitions)
