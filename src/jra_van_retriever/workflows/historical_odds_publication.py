"""Publish raw-complete historical odds under the common acquisition lock."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from jra_van_retriever.config.profiles import HistoricalOddsBatch, JVLinkProfile
from jra_van_retriever.progress.ledger import LEDGER_FILENAME, ProgressLedger
from jra_van_retriever.progress.output import write_summary
from jra_van_retriever.progress.raw_observation import read_raw_snapshot
from jra_van_retriever.progress.state import (
    WeeklyBatchResult as WeeklyBatchResult,
)
from jra_van_retriever.workflows.historical_odds_plan import plan_snapshot, select_year

T = TypeVar("T")


class HistoricalOddsPublication:
    """Own publication checks, durable outcomes and derived progress refresh."""

    def __init__(
        self,
        database: Path,
        profile: JVLinkProfile,
        batch: HistoricalOddsBatch,
        runtime_dir: Path,
        clock: Callable[[], datetime],
    ) -> None:
        self._database = database
        self._odds_profile = profile
        self._batch = batch
        self._runtime_dir = runtime_dir
        self._clock = clock

    @property
    def ledger_path(self) -> Path:
        """Return the runtime ledger path used by this raw database."""
        return self._runtime_dir / LEDGER_FILENAME

    @property
    def ledger(self) -> ProgressLedger:
        """Return the progress ledger bound to this raw database."""
        return ProgressLedger(self.ledger_path, self._database, self._odds_profile, self._batch)

    def prepare_publication(self, *, cutoff: date | None = None) -> WeeklyBatchResult:
        """Reconcile raw additions and plan the next complete-Parquet publication."""
        now = self._clock()
        effective_cutoff = cutoff or (now.date() - timedelta(days=1))
        if not self.ledger_path.is_file():
            raise AcquisitionBlocked(
                "historical-odds publication requires an existing progress ledger"
            )
        with AcquisitionLock(self._database, self.ledger_path) as lock:
            lock.bind()
            ledger = self.ledger
            return self.prepare_publication_locked(ledger, effective_cutoff, now)

    def prepare_publication_locked(
        self, ledger: ProgressLedger, cutoff: date, now: datetime
    ) -> WeeklyBatchResult:
        """Reconcile and plan publication while the caller owns the common lock."""
        snapshot = read_raw_snapshot(self._database, self._odds_profile, self._batch, cutoff)
        ledger.migrate_legacy_frontier(snapshot, now)
        ledger.reconcile(snapshot, now)
        return plan_snapshot(
            snapshot,
            cutoff,
            self._odds_profile.realtime_data_specs,
            self.ledger if self.ledger_path.exists() else None,
        )

    def verify_publication_locked(self, ledger: ProgressLedger, year: int) -> None:
        """Reject publication when raw data changed or remains incomplete."""
        now = self._clock()
        plan = self.prepare_publication_locked(ledger, now.date() - timedelta(days=1), now)
        if plan.year != year or plan.requested_specs:
            raise AcquisitionBlocked(
                "raw data changed or remains incomplete after publication planning"
            )

    def repair_derived_publication(self) -> None:
        """Regenerate derived publication files from the committed ledger state."""
        if not self.ledger_path.is_file():
            raise AcquisitionBlocked(
                "historical-odds publication requires an existing progress ledger"
            )
        with AcquisitionLock(self._database, self.ledger_path) as lock:
            lock.bind()
            ledger = self.ledger
            _, publications, _ = ledger.read()
            published_years = [
                year for year, publication in publications.items() if publication == "published"
            ]
            year = max(published_years, default=self._batch.last_year)
            result = WeeklyBatchResult("up_to_date", year, None, 0, 0, 0, 0, {})
            self.refresh_derived_after_publication_locked(ledger, result, "published")

    def publish_complete(self, publisher: Callable[[], T]) -> T | None:
        """Publish all raw-complete years in one Parquet rebuild."""
        now = self._clock()
        with AcquisitionLock(self._database, self.ledger_path) as lock:
            lock.bind()
            ledger = self.ledger
            snapshot = read_raw_snapshot(
                self._database,
                self._odds_profile,
                self._batch,
                now.date() - timedelta(days=1),
            )
            ledger.migrate_legacy_frontier(snapshot, now)
            ledger.reconcile(snapshot, now)
            states, publications, _ = ledger.read()
            if any(
                state.state not in {"acquired", "provider_missing"} for state in states.values()
            ):
                raise AcquisitionBlocked("historical odds remain incomplete")
            years = [
                year
                for year, publication in publications.items()
                if publication in {"pending", "failed"}
            ]
            if not years:
                return None
            result = WeeklyBatchResult("up_to_date", None, None, 0, 0, 0, 0, {})
            try:
                published = publisher()
            except BaseException:
                for year in years:
                    ledger.publication(year, "failed")
                self.refresh_derived_after_publication_locked(ledger, result, "failed")
                raise
            for year in years:
                ledger.publication(year, "published")
            self.refresh_derived_after_publication_locked(ledger, result, "published")
            return published

    def mark_published(self, year: int) -> None:
        """Record publication only after the complete snapshot is durable."""
        self.mark_publication(year, "published")

    def mark_publication(self, year: int, state: str) -> None:
        """Record the outcome of complete-Parquet publication."""
        ledger = ProgressLedger(self.ledger_path, self._database, self._odds_profile, self._batch)
        with AcquisitionLock(self._database, self.ledger_path) as lock:
            lock.bind()
            self.mark_publication_locked(ledger, year, state)

    def mark_publication_locked(self, ledger: ProgressLedger, year: int, state: str) -> None:
        """Record publication while the caller owns the common acquisition lock."""
        ledger.publication(year, state)

    def refresh_derived_after_publication_locked(
        self,
        ledger: ProgressLedger,
        result: WeeklyBatchResult,
        publication_state: str,
    ) -> None:
        """Refresh derived progress files after changing a publication state."""
        if publication_state == "published":
            states, publications, _ = ledger.read()
            cutoff = self._clock().date() - timedelta(days=1)
            snapshot = read_raw_snapshot(self._database, self._odds_profile, self._batch, cutoff)
            next_year = select_year(
                self._odds_profile.realtime_data_specs, states, snapshot.races, cutoff, publications
            )
            effective_year = next_year if next_year is not None else self._batch.last_year
            phase = "acquire" if next_year is not None else "idle"
        else:
            effective_year = result.year if result.year is not None else self._batch.last_year
            phase = "failed"
        self._write_summary(
            result,
            ledger,
            effective_year=effective_year,
            phase=phase,
            publication_state=publication_state,
        )

    def _write_summary(
        self,
        result: WeeklyBatchResult,
        ledger: ProgressLedger,
        *,
        effective_year: int | None = None,
        phase: str | None = None,
        publication_state: str | None = None,
    ) -> None:
        write_summary(
            result,
            ledger,
            runtime_dir=self._runtime_dir,
            last_year=self._batch.last_year,
            data_specs=self._odds_profile.realtime_data_specs,
            effective_year=effective_year,
            phase=phase,
            publication_state=publication_state,
        )
