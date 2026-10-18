"""Write JSON-compatible values as standard UTF-8 JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from math import isnan
from pathlib import Path


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Write UTF-8 result JSON, converting missing NaN values to null."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _json_safe(value: object) -> object:
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
