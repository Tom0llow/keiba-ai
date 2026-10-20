"""Verify declarative registrations reach audit, generation and saved contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from main import app


@pytest.mark.parametrize("command", [[], ["model"], ["model", "explanatory-variables"]])
def test_help_never_loads_feature_config(command: list[str]) -> None:
    with patch(
        "cli.make_features.load_feature_definitions",
        side_effect=AssertionError("unexpected config read"),
    ) as loader:
        result = CliRunner().invoke(app, [*command, "--help"])
    assert result.exit_code == 0
    loader.assert_not_called()
