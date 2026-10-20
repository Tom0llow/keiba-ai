"""Translate generic JSON input and output failures at the CLI boundary."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import typer

from data.loader.read_json import read_json
from data.saver.write_json import write_json


def parse_json_inputs[T](path: Path, parser: Callable[[dict[str, object]], T]) -> T:
    """Parse JSON input and preserve the existing CLI validation error contract."""
    payload = read_json_object(path)
    try:
        return parser(payload)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def read_json_object(path: Path) -> dict[str, object]:
    """Read an object and translate physical or top-level JSON input errors."""
    try:
        return read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"cannot read input JSON: {exc}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def input_error_payload(error: Exception) -> dict[str, str]:
    """Return the structured input error used by model commands."""
    return {"type": "input", "message": str(error)}


def exit_input_error(output_path: Path, error: Exception, **context: object) -> NoReturn:
    """Write the existing structured input error and exit with code one."""
    write_json(output_path, {**context, "error": input_error_payload(error)})
    raise typer.Exit(code=1) from error
