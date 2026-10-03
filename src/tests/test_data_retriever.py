"""Tests for the public race-data retrieval facade."""

from pathlib import Path
from unittest.mock import Mock, patch

from data.data_retriever import DataRetriever


def test_retrieve_historical_delegates_to_historical_retriever(tmp_path: Path) -> None:
    executable = tmp_path / "JVLinkToSQLite.exe"
    executable.write_bytes(b"")
    database = tmp_path / "race.db"
    historical_setting = tmp_path / "historical.xml"
    historical_setting.write_text("<setting />", encoding="utf-8")
    odds_setting = tmp_path / "historical-odds.xml"
    odds_setting.write_text("<setting />", encoding="utf-8")
    latest_setting = tmp_path / "latest.xml"
    latest_setting.write_text("<setting />", encoding="utf-8")

    with (
        patch("data.data_retriever.HistoricalRetriever") as historical_type,
        patch("data.data_retriever.LatestRetriever"),
    ):
        historical = Mock()
        historical.retrieve.return_value = 42
        historical_type.return_value = historical
        retriever = DataRetriever(
            executable=executable,
            database=database,
            historical_setting=historical_setting,
            historical_odds_setting=odds_setting,
            latest_setting=latest_setting,
        )

        assert retriever.retrieve_historical() == 42

    historical.retrieve.assert_called_once_with(
        historical_setting.resolve(),
        odds_setting.resolve(),
    )


def test_retrieve_latest_delegates_to_latest_retriever(tmp_path: Path) -> None:
    executable = tmp_path / "JVLinkToSQLite.exe"
    executable.write_bytes(b"")
    database = tmp_path / "race.db"
    historical_setting = tmp_path / "historical.xml"
    odds_setting = tmp_path / "historical-odds.xml"
    latest_setting = tmp_path / "latest.xml"
    for setting in (historical_setting, odds_setting, latest_setting):
        setting.write_text("<setting />", encoding="utf-8")

    with (
        patch("data.data_retriever.HistoricalRetriever"),
        patch("data.data_retriever.LatestRetriever") as latest_type,
    ):
        latest = Mock()
        latest_type.return_value = latest
        retriever = DataRetriever(
            executable=executable,
            database=database,
            historical_setting=historical_setting,
            historical_odds_setting=odds_setting,
            latest_setting=latest_setting,
            timeout_seconds=30.0,
        )
        retriever.retrieve_latest()

    latest.retrieve.assert_called_once_with(latest_setting.resolve())
