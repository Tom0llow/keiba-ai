"""Tests for feature execution JSON serialization."""

import json
from math import isnan
from pathlib import Path

from run.json_output import write_json


def test_write_json_converts_nested_nan_without_mutating_inputs(tmp_path: Path) -> None:
    path = tmp_path / "results" / "generated.json"
    values = [None, float("nan"), 2.0]
    payload = {"name": "競走馬", "record": {"values": values}, "metrics": (float("nan"),)}

    write_json(path, payload)

    output = path.read_text(encoding="utf-8")
    assert output.endswith("\n")
    assert "競走馬" in output
    assert "NaN" not in output
    assert json.loads(output) == {
        "name": "競走馬",
        "record": {"values": [None, None, 2.0]},
        "metrics": [None],
    }
    assert isinstance(values[1], float)
    assert isnan(values[1])
