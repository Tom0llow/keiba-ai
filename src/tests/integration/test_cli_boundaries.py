"""Tests for CLI composition, independent imports and shared input contracts."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer

from cli.json_io import exit_input_error, parse_json_inputs, read_json_object


@pytest.mark.parametrize(
    "module", ["jra_van_retriever", "preprocessor", "make_features", "make_datamart", "models"]
)
def test_functional_cli_import_does_not_load_sibling_clis_or_start_application(module: str) -> None:
    script = """
import importlib
import sys

name = sys.argv[1]
importlib.import_module("cli." + name)
siblings = {"jra_van_retriever", "preprocessor", "make_features", "make_datamart", "models"} - {name}
assert not {"cli." + sibling for sibling in siblings} & sys.modules.keys()
assert "main" not in sys.modules
assert "lightgbm" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script, module],
        cwd=Path(__file__).resolve().parents[3] / "src",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("error_type", [TypeError, ValueError])
def test_shared_json_parser_preserves_validation_message_and_cause(
    tmp_path: Path, error_type: type[Exception]
) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"value": 2}', encoding="utf-8")
    error = error_type("invalid feature value")

    def reject(payload: dict[str, object]) -> None:
        assert payload == {"value": 2}
        raise error

    with pytest.raises(typer.BadParameter, match=r"^invalid feature value$") as caught:
        parse_json_inputs(path, reject)
    assert caught.value.__cause__ is error


def test_shared_json_parser_does_not_run_parser_before_successful_read(tmp_path: Path) -> None:
    parser = Mock()
    with pytest.raises(typer.BadParameter, match=r"^cannot read input JSON:") as caught:
        parse_json_inputs(tmp_path / "missing.json", parser)
    assert isinstance(caught.value.__cause__, FileNotFoundError)
    parser.assert_not_called()


@pytest.mark.parametrize(
    ("contents", "cause_type", "prefix"),
    [
        (b"\xff", UnicodeDecodeError, "cannot read input JSON:"),
        (b"{", json.JSONDecodeError, "cannot read input JSON:"),
        (b"[]", ValueError, "input JSON must be an object"),
    ],
)
def test_shared_json_reader_preserves_existing_input_error_categories(
    tmp_path: Path, contents: bytes, cause_type: type[Exception], prefix: str
) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(contents)
    with pytest.raises(typer.BadParameter) as caught:
        read_json_object(path)
    assert str(caught.value).startswith(prefix)
    assert isinstance(caught.value.__cause__, cause_type)


def test_shared_json_exit_writes_context_and_original_error_before_exit(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    error = ValueError("invalid model input")
    with pytest.raises(typer.Exit) as caught:
        exit_input_error(path, error, schema_id="schema-v1", audit={"valid": False})
    assert caught.value.exit_code == 1
    assert caught.value.__cause__ is error
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_id": "schema-v1",
        "audit": {"valid": False},
        "error": {"type": "input", "message": "invalid model input"},
    }


def test_shared_json_exit_keeps_physical_write_failure_visible(tmp_path: Path) -> None:
    parent = tmp_path / "parent-file"
    parent.write_text("file", encoding="utf-8")
    with pytest.raises(FileExistsError):
        exit_input_error(parent / "result.json", ValueError("invalid input"))
