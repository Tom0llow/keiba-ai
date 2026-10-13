"""Read UTF-8 JSON objects without CLI or feature-specific validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast


def read_json(path: Path) -> dict[str, object]:
    """Read a UTF-8 JSON object without converting its values.

    Raises:
        OSError: If the file cannot be read.
        UnicodeDecodeError: If the file is not valid UTF-8.
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the JSON root is not an object.
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input JSON must be an object")
    return cast(dict[str, object], value)
