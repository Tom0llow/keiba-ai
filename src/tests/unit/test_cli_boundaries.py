"""Tests for CLI composition, independent imports and shared input contracts."""

from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

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
