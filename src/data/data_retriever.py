"""Provide the public orchestration API for JRA-VAN race-data retrieval."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from data.config import DataPaths
from data.race_key import RaceKey
from data.retriever.historical import HistoricalRetriever
from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.latest import LatestRetriever
from data.retriever.odds_archive import OddsArchive
from data.retriever.realtime import RealtimeRetriever
from data.retriever.setting import JVLinkConfig, JVLinkSettingBuilder


class DataRetriever:
    """Coordinate historical, latest, and prediction-time retrieval."""

    def __init__(
        self,
        *,
        paths: DataPaths,
        jvlink: JVLinkConfig,
        timeout_seconds: float | None = None,
    ) -> None:
        paths.jvlink_runtime_dir.mkdir(parents=True, exist_ok=True)
        paths.raw_db.parent.mkdir(parents=True, exist_ok=True)
        runner = JVLinkToSQLiteRunner(
            jvlink.executable,
            paths.raw_db,
            timeout_seconds=timeout_seconds,
        )
        builder = JVLinkSettingBuilder(jvlink.seed_setting)
        archive = OddsArchive(paths.raw_db)
        self._historical = HistoricalRetriever(
            runner,
            paths.raw_db,
            builder,
            archive,
            jvlink.historical,
            jvlink.historical_odds,
        )
        self._latest = LatestRetriever(
            runner,
            builder,
            jvlink.latest,
            paths.jvlink_runtime_dir / "latest.xml",
        )
        self._realtime = RealtimeRetriever(
            runner,
            builder,
            archive,
            jvlink.realtime_history,
            jvlink.realtime_current,
        )

    @classmethod
    def from_toml(
        cls,
        *,
        data_config: Path,
        jvlink_config: Path,
        timeout_seconds: float | None = None,
    ) -> DataRetriever:
        """Construct the retriever from repository TOML configuration."""
        return cls(
            paths=DataPaths.from_toml(data_config),
            jvlink=JVLinkConfig.from_toml(jvlink_config),
            timeout_seconds=timeout_seconds,
        )

    def retrieve_historical(self) -> int:
        """Retrieve historical race data and configured time-series odds."""
        return self._historical.retrieve()

    def retrieve_latest(self) -> None:
        """Retrieve the configured latest incremental race data."""
        self._latest.retrieve()

    def retrieve_realtime(
        self,
        *,
        race_date: date,
        jyo_code: str,
        kaiji: str,
        nichiji: str,
        race_number: str,
    ) -> int:
        """Retrieve prediction-time O1/O2 odds for one target race."""
        return self._realtime.retrieve(
            RaceKey(race_date, jyo_code, kaiji, nichiji, race_number)
        )
