"""Tests for the public race-data retrieval facade."""

from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from configuration.data_paths import DataPaths
from jra_van_retriever.config.profiles import JVLinkConfig, JVLinkProfile, RaceDayOddsProfile
from jra_van_retriever.retriever import DataRetriever


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
        patch("jra_van_retriever.retriever.HistoricalRetriever") as historical_type,
        patch("jra_van_retriever.retriever.LatestRetriever") as latest_type,
        patch("jra_van_retriever.retriever.RealtimeRetriever") as realtime_type,
        patch("jra_van_retriever.retriever.OddsArchive"),
        patch("jra_van_retriever.retriever.JVLinkSettingBuilder"),
    ):
        historical = Mock()
        historical.retrieve_basic.return_value = None
        historical_type.return_value = historical
        latest = Mock()
        latest_type.return_value = latest
        realtime = Mock()
        realtime.retrieve.return_value = 15
        realtime_type.return_value = realtime
        retriever = DataRetriever(paths=paths, jvlink=jvlink)

        retriever.retrieve_historical_basic()
        historical.retrieve.return_value = 7
        assert retriever.retrieve_historical() == 7
        retriever.retrieve_latest()
        inserted = retriever.retrieve_realtime(
            race_date=date(2026, 10, 4),
            jyo_code="05",
            kaiji="04",
            nichiji="08",
            race_number="11",
        )

    assert inserted == 15
    historical.retrieve_basic.assert_called_once_with()
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


def test_race_day_odds_uses_a_dedicated_runner_with_the_profile_timeout(tmp_path: Path) -> None:
    seed = tmp_path / "setting.xml"
    seed.write_text("<setting />", encoding="utf-8")
    paths = DataPaths(tmp_path / "raw" / "race.db", tmp_path / "processed", tmp_path / "runtime")
    profile = _profile()
    race_day_odds = RaceDayOddsProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"}),
        execution_timeout_seconds=77,
    )
    jvlink = JVLinkConfig(
        tmp_path / "JVLinkToSQLite.exe",
        seed,
        profile,
        profile,
        profile,
        profile,
        profile,
        race_day_odds=race_day_odds,
    )

    retriever = DataRetriever(
        paths=paths, jvlink=jvlink, timeout_seconds=45.0, validate_executable=False
    )

    assert retriever._race_day_odds is not None
    assert retriever._race_day_odds._runner._timeout_seconds == 77.0
    assert retriever._latest._runner._timeout_seconds == 45.0
    assert retriever._race_day_odds._runner is not retriever._latest._runner
