"""Share command-line option contracts, input parsing and error exits."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from data_loader.read_json import read_json
from data_saver.write_json import write_json

DataConfigOption = Annotated[
    Path,
    typer.Option("--data-config", help="Path to the shared data TOML configuration."),
]


JVLinkConfigOption = Annotated[
    Path,
    typer.Option("--jvlink-config", help="Path to the JVLink retrieval profile TOML."),
]


def _parse_inputs[T](path: Path, parser: Callable[[dict[str, object]], T]) -> T:
    payload = _read_json_object(path)
    try:
        return parser(payload)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        return read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"cannot read input JSON: {exc}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def input_error_payload(error: Exception) -> dict[str, str]:
    """Return the structured input error used by model commands."""
    return {"type": "input", "message": str(error)}


def _exit_input_error(output_path: Path, error: Exception, **context: object) -> NoReturn:
    write_json(output_path, {**context, "error": input_error_payload(error)})
    raise typer.Exit(code=1) from error
