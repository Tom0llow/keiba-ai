"""Provide the public orchestration API for JRA-VAN race-data retrieval."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import TypeVar

from configuration.data_paths import DataPaths
from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionLock
from jra_van_retriever.acquisition.jvlink_runner import JVLinkToSQLiteRunner
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkConfig, JVLinkProfile
from jra_van_retriever.config.validation import validate_historical_odds_batch
from jra_van_retriever.workflows.historical_basic import HistoricalBasicRetriever
from jra_van_retriever.workflows.historical_odds import (
    WeeklyBatchResult,
    WeeklyHistoricalOddsRetriever,
)
from jra_van_retriever.workflows.historical_odds_legacy import LegacyHistoricalOddsRetriever
from jra_van_retriever.workflows.latest import LatestRetriever
from jra_van_retriever.workflows.realtime import RealtimeRetriever

T = TypeVar("T")


class HistoricalRetriever:
    """Preserve the existing combined base-and-odds Python retrieval API."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        database: Path,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        historical_profile: JVLinkProfile,
        odds_profile: JVLinkProfile,
    ) -> None:
        self._basic = HistoricalBasicRetriever(
            runner, database, setting_builder, historical_profile
        )
        self._odds = LegacyHistoricalOddsRetriever(
            runner, database, setting_builder, archive, odds_profile
        )

    def retrieve_basic(self) -> None:
        """Run only the historical base workflow."""
        self._basic.retrieve_basic()

    def retrieve(self) -> int:
        """Run base then odds using the existing combined temporary lifecycle."""
        with tempfile.TemporaryDirectory(prefix="keiba-ai-historical-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            self._basic.retrieve_into(temporary_path)
            return self._odds.retrieve_into(temporary_path)

    def iter_race_keys(self, *, start_date: date) -> Iterator[RaceKey]:
        """Yield odds race keys after closing the source observation connection."""
        yield from self._odds.iter_race_keys(start_date=start_date)


class JraVanRetriever:
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
    ) -> JraVanRetriever:
        """Construct the retriever from repository TOML configuration."""
        return cls(
            paths=DataPaths.from_toml(data_config),
            jvlink=JVLinkConfig.from_toml(jvlink_config),
            timeout_seconds=timeout_seconds,
            create_runtime=create_runtime,
            validate_executable=validate_executable,
        )

    def retrieve_historical_basic(self, publisher: Callable[[], object] | None = None) -> None:
        """Retrieve configured historical base data and optionally publish under the lock."""
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
            self._historical.retrieve_basic()
            if publisher is not None:
                publisher()

    def retrieve_historical(self) -> int:
        """Keep the legacy combined retrieval API for existing Python callers."""
        with AcquisitionLock(self._raw_db, self._ledger_path) as lock:
            lock.bind()
            return self._historical.retrieve()

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


# Keep the existing documented acquisition API name at its new owning module.
DataRetriever = JraVanRetriever
