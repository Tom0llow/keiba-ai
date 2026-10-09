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
    validate_batch_profiles,
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
        self._historical_profile = jvlink.historical
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

    def retrieve_historical(self) -> int:
        """Retrieve historical race data and configured time-series odds."""
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
            return self._historical.retrieve()

    def retrieve_historical_weekly(
        self, *, plan_only: bool = False, recover: bool = False
    ) -> WeeklyBatchResult:
        """Run one manual year-scoped historical odds batch."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-weekly")
        assert self._odds_batch is not None
        validate_batch_profiles(self._historical_profile, self._odds_profile, self._odds_batch)
        return self._weekly.run(plan_only=plan_only, recover=recover)

    def prepare_historical_weekly_publication(self) -> WeeklyBatchResult:
        """Reconcile raw additions and plan one complete-Parquet publication."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-weekly")
        assert self._odds_batch is not None
        validate_batch_profiles(self._historical_profile, self._odds_profile, self._odds_batch)
        return self._weekly.prepare_publication()

    def repair_historical_weekly_derived(self) -> None:
        """Regenerate historical weekly derived files from the committed ledger."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-weekly")
        assert self._odds_batch is not None
        validate_batch_profiles(self._historical_profile, self._odds_profile, self._odds_batch)
        self._weekly.repair_derived_publication()

    def mark_historical_weekly_published(self, year: int) -> None:
        """Record successful complete-Parquet publication for one weekly year."""
        self.mark_historical_weekly_publication(year, "published")

    def mark_historical_weekly_publication(self, year: int, state: str) -> None:
        """Record a successful or failed complete-Parquet publication."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-weekly")
        self._weekly.mark_publication(year, state)

    def confirm_historical_weekly_provider_missing(
        self, race_key: RaceKey, specs: frozenset[str]
    ) -> int:
        """Confirm empty-response failures as provider-side gaps."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-weekly")
        assert self._odds_batch is not None
        validate_batch_profiles(self._historical_profile, self._odds_profile, self._odds_batch)
        return self._weekly.confirm_provider_missing(race_key, specs)

    def publish_historical_weekly(
        self,
        year: int,
        publisher: Callable[[], T],
        *,
        result: WeeklyBatchResult | None = None,
    ) -> T:
        """Publish one completed year and record its state under the raw DB lock."""
        if self._weekly is None:
            raise ValueError("[historical_odds.batch] is required for historical-weekly")
        ledger = self._weekly.ledger
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
            if result is not None and result.year != year:
                raise ValueError("publication result year does not match requested year")
            if result is not None:
                self._weekly.verify_publication_locked(ledger, year)
            try:
                published = publisher()
            except BaseException:
                self._weekly.mark_publication_locked(ledger, year, "failed")
                if result is not None:
                    self._weekly.refresh_derived_after_publication_locked(ledger, result, "failed")
                raise
            self._weekly.mark_publication_locked(ledger, year, "published")
            if result is not None:
                try:
                    self._weekly.refresh_derived_after_publication_locked(
                        ledger, result, "published"
                    )
                except BaseException:
                    self._weekly.mark_publication_locked(ledger, year, "failed")
                    raise
            return published

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
