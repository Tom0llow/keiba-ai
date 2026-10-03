"""Tests for the public race-data retrieval facade."""

from pathlib import Path
from unittest.mock import Mock, patch

from data.config import RetrievalPaths
from data.data_retriever import DataRetriever
from data.retriever.setting import JVLinkConfig, JVLinkProfile


def _profile() -> JVLinkProfile:
    return JVLinkProfile(False, False, False, frozenset(), frozenset(), frozenset())


def test_facade_constructs_retrievers_and_delegates(tmp_path: Path) -> None:
    executable = tmp_path / "JVLinkToSQLite.exe"
    executable.write_bytes(b"")
    seed = tmp_path / "setting.xml"
    seed.write_text("<setting />", encoding="utf-8")
    database = tmp_path / "raw" / "race.db"
    runtime = tmp_path / "runtime"
    paths = RetrievalPaths(database, runtime)
    profile = _profile()
    jvlink = JVLinkConfig(executable, seed, profile, profile, profile)

    with (
        patch("data.data_retriever.HistoricalRetriever") as historical_type,
        patch("data.data_retriever.LatestRetriever") as latest_type,
        patch("data.data_retriever.JVLinkSettingBuilder"),
    ):
        historical = Mock()
        historical.retrieve.return_value = 42
        historical_type.return_value = historical
        latest = Mock()
        latest_type.return_value = latest
        retriever = DataRetriever(paths=paths, jvlink=jvlink)

        assert retriever.retrieve_historical() == 42
        retriever.retrieve_latest()

    historical.retrieve.assert_called_once_with()
    latest.retrieve.assert_called_once_with()
    assert database.parent.is_dir()
    assert runtime.is_dir()
