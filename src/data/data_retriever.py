"""Provide the public orchestration API for JRA-VAN race-data retrieval."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TypeVar

from data.config import DataPaths
from data.race_key import RaceKey
from data.retriever.acquisition_lock import AcquisitionLock
from data.retriever.historical import HistoricalRetriever
from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.latest import LatestRetriever
from data.retriever.odds_archive import OddsArchive
from data.retriever.realtime import RealtimeRetriever
from data.retriever.setting import (
    JVLinkConfig,
    JVLinkSettingBuilder,
    validate_historical_odds_batch,
)
from data.retriever.weekly import WeeklyBatchResult, WeeklyHistoricalOddsRetriever

T = TypeVar("T")


class DataRetriever:
    """Coordinate historical, latest, and prediction-time retrieval."""

    def __init__(
        self,
        *,
        paths: DataPaths,
        jvlink: JVLinkConfig,
        timeout_seconds: float | None = None,
        create_runtime: bool = True,
        validate_executable: bool = True,
    ) -> None:
        if create_runtime:
            paths.jvlink_runtime_dir.mkdir(parents=True, exist_ok=True)
            paths.raw_db.parent.mkdir(parents=True, exist_ok=True)
        self._raw_db = paths.raw_db
        self._ledger_path = paths.jvlink_runtime_dir / "historical-odds-progress.db"
        self._odds_profile = jvlink.historical_odds
        self._odds_batch = jvlink.historical_odds_batch
        runner = JVLinkToSQLiteRunner(
            jvlink.executable,
            paths.raw_db,
            timeout_seconds=timeout_seconds,
            validate_executable=validate_executable,
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
        self._weekly = (
            WeeklyHistoricalOddsRetriever(
                runner,
                paths.raw_db,
                builder,
                archive,
                jvlink.historical_odds,
                jvlink.historical_odds_batch,
                paths.jvlink_runtime_dir,
            )
            if jvlink.historical_odds_batch is not None
            else None
        )

    @classmethod
    def from_toml(
        cls,
        *,
        data_config: Path,
        jvlink_config: Path,
        timeout_seconds: float | None = None,
        create_runtime: bool = True,
        validate_executable: bool = True,
    ) -> DataRetriever:
        """Construct the retriever from repository TOML configuration."""
        return cls(
            paths=DataPaths.from_toml(data_config),
            jvlink=JVLinkConfig.from_toml(jvlink_config),
            timeout_seconds=timeout_seconds,
            create_runtime=create_runtime,
            validate_executable=validate_executable,
        )

    def retrieve_historical_basic(self) -> None:
        """Retrieve configured historical base data."""
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
            self._historical.retrieve_basic()

    def retrieve_historical_odds(
        self,
        *,
        plan_only: bool = False,
        recover: bool = False,
        raw_only: bool = False,
    ) -> WeeklyBatchResult:
        """Run one manual year-scoped historical odds batch."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-odds")
        assert self._odds_batch is not None
        validate_historical_odds_batch(self._odds_profile, self._odds_batch)
        return self._weekly.run(plan_only=plan_only, recover=recover, raw_only=raw_only)

    def confirm_historical_odds_provider_missing(
        self, race_key: RaceKey, specs: frozenset[str]
    ) -> int:
        """Confirm empty-response failures as provider-side gaps."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-odds")
        assert self._odds_batch is not None
        validate_historical_odds_batch(self._odds_profile, self._odds_batch)
        return self._weekly.confirm_provider_missing(race_key, specs)

    def publish_historical_odds(self, publisher: Callable[[], T]) -> T | None:
        """Publish all raw-complete historical odds years in one snapshot."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-odds")
        assert self._odds_batch is not None
        validate_historical_odds_batch(self._odds_profile, self._odds_batch)
        return self._weekly.publish_complete(publisher)

    def retrieve_latest(self) -> None:
        """Retrieve the configured latest incremental race data."""
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
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
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
            return self._realtime.retrieve(
                RaceKey(race_date, jyo_code, kaiji, nichiji, race_number)
            )
