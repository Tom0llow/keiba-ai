"""Provide the public orchestration API for JRA-VAN race-data retrieval."""

from __future__ import annotations

from pathlib import Path

from data.retriever.historical import HistoricalRetriever
from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.latest import LatestRetriever


class DataRetriever:
    """Coordinate historical and latest retrieval for one raw race database."""

    def __init__(
        self,
        *,
        executable: Path,
        database: Path,
        historical_setting: Path,
        historical_odds_setting: Path,
        latest_setting: Path,
        timeout_seconds: float | None = None,
    ) -> None:
        """Configure all local paths needed by the retrieval workflow.

        Args:
            executable: Local ``JVLinkToSQLite.exe`` path.
            database: Raw SQLite database to create or update.
            historical_setting: JVLinkToSQLite setting for the base historical load.
            historical_odds_setting: Template containing 0B41 and 0B42 entries.
            latest_setting: Persistent setting for incremental/latest updates.
            timeout_seconds: Optional positive timeout applied to each importer run.
        """
        runner = JVLinkToSQLiteRunner(
            executable,
            database,
            timeout_seconds=timeout_seconds,
        )
        self._historical = HistoricalRetriever(runner, database)
        self._latest = LatestRetriever(runner)
        self._historical_setting = historical_setting.expanduser().resolve()
        self._historical_odds_setting = historical_odds_setting.expanduser().resolve()
        self._latest_setting = latest_setting.expanduser().resolve()

    def retrieve_historical(self) -> int:
        """Retrieve historical race data and all eligible time-series odds."""
        return self._historical.retrieve(
            self._historical_setting,
            self._historical_odds_setting,
        )

    def retrieve_latest(self) -> None:
        """Retrieve the latest incremental race data."""
        self._latest.retrieve(self._latest_setting)
