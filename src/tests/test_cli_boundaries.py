"""Tests for CLI composition, independent imports and shared input contracts."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from cli.json_io import exit_input_error, parse_json_inputs, read_json_object
from main import app, datamart_app, model_app, preprocess_app


def test_application_registers_every_command_once_in_existing_order() -> None:
    assert [group.name for group in app.registered_groups] == ["preprocess", "model", "datamart"]
    assert [command.name for command in preprocess_app.registered_commands] == ["rebuild"]
    assert [command.name for command in model_app.registered_commands] == [
        "walk-forward",
        "audit",
        "features",
        "explanatory-variables",
    ]
    assert [command.name for command in datamart_app.registered_commands] == ["build"]


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
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_shared_data_option_passes_explicit_path_to_public_snapshot_factory(tmp_path: Path) -> None:
    config = tmp_path / "explicit-data.toml"
    builder = Mock()
    builder.rebuild.return_value = {"TABLE": 4}
    with patch(
        "data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=builder
    ) as factory:
        result = CliRunner().invoke(app, ["preprocess", "rebuild", "--data-config", str(config)])
    assert result.exit_code == 0
    assert result.stdout == "processed snapshot published: 1 tables\n"
    factory.assert_called_once_with(config)
    builder.rebuild.assert_called_once_with()


def test_shared_retrieval_options_preserve_explicit_configuration_paths(tmp_path: Path) -> None:
    data_config, jvlink_config = tmp_path / "data.toml", tmp_path / "jvlink.toml"
    retriever, builder = Mock(), Mock()
    builder.update.return_value = {}
    with (
        patch("cli.jra_van_retriever.DataRetriever.from_toml", return_value=retriever) as factory,
        patch(
            "data.storage.snapshot_builder.SnapshotBuilder.from_toml", return_value=builder
        ) as snapshot,
    ):
        result = CliRunner().invoke(
            app,
            [
                "--retrieve",
                "--mode=latest",
                "--data-config",
                str(data_config),
                "--jvlink-config",
                str(jvlink_config),
            ],
        )
    assert result.exit_code == 0
    factory.assert_called_once_with(data_config=data_config, jvlink_config=jvlink_config)
    snapshot.assert_called_once_with(data_config)


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
