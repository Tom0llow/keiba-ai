"""Tests for the Typer retrieval CLI."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from main import app

runner = CliRunner()


def test_historical_cli_uses_default_configs() -> None:
    retriever = Mock()
    retriever.retrieve_historical.return_value = 12
    with patch("main.DataRetriever.from_toml", return_value=retriever) as from_toml:
        result = runner.invoke(app, ["retrieve", "historical"])

    assert result.exit_code == 0
    assert "12 races" in result.stdout
    from_toml.assert_called_once()
    kwargs = from_toml.call_args.kwargs
    assert kwargs["data_config"].as_posix() == "config/data.toml"
    assert kwargs["jvlink_config"].as_posix() == "config/jvlink.toml"


def test_latest_cli_delegates_to_retriever() -> None:
    retriever = Mock()
    with patch("main.DataRetriever.from_toml", return_value=retriever):
        result = runner.invoke(app, ["retrieve", "latest"])

    assert result.exit_code == 0
    retriever.retrieve_latest.assert_called_once_with()
