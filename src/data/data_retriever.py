"""Provide the public orchestration API for JRA-VAN race-data retrieval."""

from __future__ import annotations

from pathlib import Path

from data.config import RetrievalPaths
from data.retriever.historical import HistoricalRetriever
from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.latest import LatestRetriever
from data.retriever.setting import JVLinkConfig, JVLinkSettingBuilder


class DataRetriever:
    """Coordinate historical and latest retrieval for one raw race database."""

    def __init__(
        self,
        *,
        paths: RetrievalPaths,
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
        self._historical = HistoricalRetriever(
            runner,
            paths.raw_db,
            builder,
            jvlink.historical,
            jvlink.historical_odds,
        )
        self._latest = LatestRetriever(
            runner,
            builder,
            jvlink.latest,
            paths.jvlink_runtime_dir / "latest.xml",
        )

    @classmethod
    def from_toml(
        cls,
        *,
        data_config: Path,
        jvlink_config: Path,
        timeout_seconds: float | None = None,
    ) -> DataRetriever:
        """Construct the retriever from the repository TOML configuration."""
        return cls(
            paths=RetrievalPaths.from_toml(data_config),
            jvlink=JVLinkConfig.from_toml(jvlink_config),
            timeout_seconds=timeout_seconds,
        )

    def retrieve_historical(self) -> int:
        """Retrieve historical race data and configured time-series odds."""
        return self._historical.retrieve()

    def retrieve_latest(self) -> None:
        """Retrieve the configured latest incremental race data."""
        self._latest.retrieve()
