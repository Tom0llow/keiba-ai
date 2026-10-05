"""Tests for the public race-data retrieval facade."""

from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from data.config import DataPaths
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
    processed = tmp_path / "processed"
    runtime = tmp_path / "runtime"
    paths = DataPaths(database, processed, runtime)
    profile = _profile()
    jvlink = JVLinkConfig(executable, seed, profile, profile, profile, profile, profile)

    with (
        patch("data.data_retriever.HistoricalRetriever") as historical_type,
        patch("data.data_retriever.LatestRetriever") as latest_type,
        patch("data.data_retriever.RealtimeRetriever") as realtime_type,
        patch("data.data_retriever.OddsArchive"),
        patch("data.data_retriever.JVLinkSettingBuilder"),
    ):
        historical = Mock()
        historical.retrieve.return_value = 42
        historical_type.return_value = historical
        latest = Mock()
        latest_type.return_value = latest
        realtime = Mock()
        realtime.retrieve.return_value = 15
        realtime_type.return_value = realtime
        retriever = DataRetriever(paths=paths, jvlink=jvlink)

        assert retriever.retrieve_historical() == 42
        retriever.retrieve_latest()
        inserted = retriever.retrieve_realtime(
            race_date=date(2026, 10, 4),
            jyo_code="05",
            kaiji="04",
            nichiji="08",
            race_number="11",
        )

    assert inserted == 15
    historical.retrieve.assert_called_once_with()
    latest.retrieve.assert_called_once_with()
    realtime.retrieve.assert_called_once()
    race_key = realtime.retrieve.call_args.args[0]
    assert race_key.race_date == date(2026, 10, 4)
    assert race_key.jyo_code == "05"
    assert race_key.kaiji == "04"
    assert race_key.nichiji == "08"
    assert race_key.race_number == "11"
    assert database.parent.is_dir()
    assert runtime.is_dir()
