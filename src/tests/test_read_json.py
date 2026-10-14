"""Tests for the reusable UTF-8 JSON object loader."""

import json
from math import isnan
from pathlib import Path
from typing import cast

import pytest

from utils.loader.read_json import read_json


def test_read_json_preserves_utf8_and_nested_values(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    payload = {"name": "競走馬", "records": [{"value": None, "enabled": True, "count": 2}]}
    source = json.dumps(payload, ensure_ascii=False)
    path.write_text(source, encoding="utf-8")

    assert read_json(path) == payload
    assert path.read_text(encoding="utf-8") == source


def test_read_json_accepts_empty_object(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")

    assert read_json(path) == {}


def test_read_json_preserves_nan_for_the_execution_boundary(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"value": NaN, "missing": null}', encoding="utf-8")

    payload = read_json(path)

    assert isnan(cast(float, payload["value"]))
    assert payload["missing"] is None


def test_read_json_raises_file_not_found_with_the_input_path(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError) as error:
        read_json(path)

    assert error.value.filename == str(path)


def test_read_json_propagates_file_read_errors(tmp_path: Path) -> None:
    with pytest.raises((IsADirectoryError, PermissionError)) as error:
        read_json(tmp_path)

    assert error.value.filename == str(tmp_path)


def test_read_json_raises_unicode_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(b"\xff")

    with pytest.raises(UnicodeDecodeError) as error:
        read_json(path)

    assert error.value.encoding == "utf-8"
    assert error.value.object == b"\xff"


def test_read_json_raises_json_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError) as error:
        read_json(path)

    assert error.value.doc == "{"
    assert error.value.pos == 1


@pytest.mark.parametrize("source", ["[]", "[{}]", "null", '"value"', "1", "1.5", "true"])
def test_read_json_rejects_non_object_roots(tmp_path: Path, source: str) -> None:
    path = tmp_path / "input.json"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=r"^input JSON must be an object$"):
        read_json(path)
