"""Tests for the Typer data CLI."""

from datetime import date
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from data.race_key import RaceKey
from main import app

runner = CliRunner()


def test_historical_cli_retrieves_then_rebuilds_processed_data() -> None:
    retriever = Mock()
    retriever.retrieve_historical.return_value = 12
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    with (
        patch("main.DataRetriever.from_toml", return_value=retriever) as from_toml,
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=historical"])

    assert result.exit_code == 0
    assert "12 races" in result.stdout
    retriever.retrieve_historical.assert_called_once_with()
    preprocesser.rebuild.assert_called_once_with()
    kwargs = from_toml.call_args.kwargs
    assert kwargs["data_config"].as_posix() == "config/data.toml"
    assert kwargs["jvlink_config"].as_posix() == "config/jvlink.toml"


def test_latest_cli_retrieves_then_refreshes_processed_data() -> None:
    retriever = Mock()
    preprocesser = Mock()
    preprocesser.update.return_value = {"NL_RA_RACE": 100}
    with (
        patch("main.DataRetriever.from_toml", return_value=retriever),
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=latest"])

    assert result.exit_code == 0
    retriever.retrieve_latest.assert_called_once_with()
    preprocesser.update.assert_called_once_with()


def test_realtime_cli_retrieves_then_publishes_race_parquet() -> None:
    retriever = Mock()
    retriever.retrieve_realtime.return_value = 17
    preprocesser = Mock()
    preprocesser.update_race.return_value = {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 10,
        "ARCHIVE_O2_ODDS_UMAREN": 7,
    }
    with (
        patch("main.DataRetriever.from_toml", return_value=retriever),
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(
            app,
            [
                "--retrieve",
                "--mode=realtime",
                "--date",
                "2026-10-04",
                "--jyo",
                "05",
                "--kaiji",
                "04",
                "--nichiji",
                "08",
                "--race",
                "11",
            ],
        )

    assert result.exit_code == 0
    assert "17 rows" in result.stdout
    retriever.retrieve_realtime.assert_called_once_with(
        race_date=date(2026, 10, 4),
        jyo_code="05",
        kaiji="04",
        nichiji="08",
        race_number="11",
    )
    preprocesser.update_race.assert_called_once_with(
        RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    )


def test_realtime_cli_uses_race_config_when_options_are_omitted() -> None:
    retriever = Mock()
    retriever.retrieve_realtime.return_value = 17
    preprocesser = Mock()
    preprocesser.update_race.return_value = {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 10,
        "ARCHIVE_O2_ODDS_UMAREN": 7,
    }
    race_key = RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    with (
        patch("main.JVLinkConfig.from_toml", return_value=Mock(realtime_race=race_key)),
        patch("main.DataRetriever.from_toml", return_value=retriever),
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=realtime"])

    assert result.exit_code == 0
    retriever.retrieve_realtime.assert_called_once_with(
        race_date=date(2026, 10, 4),
        jyo_code="05",
        kaiji="04",
        nichiji="08",
        race_number="11",
    )
    preprocesser.update_race.assert_called_once_with(race_key)


def test_retrieve_subcommand_is_removed() -> None:
    result = runner.invoke(app, ["retrieve", "historical"])

    assert result.exit_code == 2


def test_preprocess_rebuild_can_run_without_retrieval() -> None:
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    with patch("main.DataPreprocesser.from_toml", return_value=preprocesser):
        result = runner.invoke(app, ["preprocess", "rebuild"])

    assert result.exit_code == 0
    preprocesser.rebuild.assert_called_once_with()
