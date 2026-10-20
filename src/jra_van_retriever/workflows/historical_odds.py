"""Coordinate bounded historical odds batches and their lifecycle owners."""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkToSQLiteRunner,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import HistoricalOddsBatch, JVLinkProfile
from jra_van_retriever.progress.ledger import LEDGER_FILENAME, ProgressLedger
from jra_van_retriever.progress.output import result_payload, write_summary
from jra_van_retriever.progress.raw_observation import read_raw_snapshot
from jra_van_retriever.progress.state import (
    RawSnapshot,
    SpecState,
    race_key_from_id,
)
from jra_van_retriever.progress.state import (
    WeeklyBatchResult as WeeklyBatchResult,
)
from jra_van_retriever.workflows.historical_odds_plan import (
    plan_snapshot,
    races_for_year,
    select_year,
)
from jra_van_retriever.workflows.historical_odds_publication import HistoricalOddsPublication
from jra_van_retriever.workflows.historical_odds_recovery import HistoricalOddsRecovery
from jra_van_retriever.workflows.historical_odds_request import (
    HistoricalOddsRequestExecutor,
    _RequestOutcome,
)

T = TypeVar("T")


@dataclass
class _BatchMetrics:
    new_rows: dict[str, int]
    new_races: dict[str, int]
    new_provider_missing: dict[str, int]
    requested_races: int = 0
    requested_specs: int = 0
    failed_specs: int = 0

    @classmethod
    def for_specs(cls, specs: frozenset[str]) -> _BatchMetrics:
        return cls(dict.fromkeys(specs, 0), dict.fromkeys(specs, 0), dict.fromkeys(specs, 0))

    def record(self, specs: frozenset[str], outcome: _RequestOutcome) -> None:
        self.requested_races += 1
        self.requested_specs += len(specs)
        self.failed_specs += len(outcome.failed_specs)
        for spec, (state, _, _) in outcome.results.items():
            if state == "acquired":
                self.new_rows[spec] += outcome.inserted_rows[spec]
                self.new_races[spec] += 1
            elif state == "provider_missing":
                self.new_provider_missing[spec] += 1


class WeeklyHistoricalOddsRetriever:
    """Coordinate one bounded historical odds run and its progress ledger."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        database: Path,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        odds_profile: JVLinkProfile,
        batch: HistoricalOddsBatch,
        runtime_dir: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database = database.expanduser().resolve()
        self._odds_profile = odds_profile
        self._batch = batch
        self._runtime_dir = runtime_dir.expanduser().resolve()
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Tokyo")))
        self._recovery = HistoricalOddsRecovery(runner, archive, self._runtime_dir)
        self._requests = HistoricalOddsRequestExecutor(
            runner, setting_builder, archive, odds_profile, self._recovery
        )
        self._publication = HistoricalOddsPublication(
            self._database, odds_profile, batch, self._runtime_dir, self._clock
        )

    @property
    def ledger_path(self) -> Path:
        """Return the runtime ledger path used by this raw database."""
        return self._runtime_dir / LEDGER_FILENAME

    @property
    def ledger(self) -> ProgressLedger:
        """Return the progress ledger bound to this raw database."""
        return ProgressLedger(self.ledger_path, self._database, self._odds_profile, self._batch)

    def run(
        self,
        *,
        plan_only: bool = False,
        cutoff: date | None = None,
        recover: bool = False,
        raw_only: bool = False,
    ) -> WeeklyBatchResult:
        """Run one year, or return a read-only plan when requested.

        When ``raw_only`` is true, publication state does not select another
        year. This lets the caller defer one complete Parquet publication until
        all raw historical odds have been acquired.
        """
        now = self._clock()
        effective_cutoff = cutoff or (now.date() - timedelta(days=1))
        if plan_only:
            snapshot = read_raw_snapshot(
                self._database, self._odds_profile, self._batch, effective_cutoff
            )
            return plan_snapshot(
                snapshot,
                effective_cutoff,
                self._odds_profile.realtime_data_specs,
                self.ledger if self.ledger_path.exists() else None,
                raw_only=raw_only,
            )

        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.ledger
        with AcquisitionLock(self._database, self.ledger_path, allow_unresolved=recover) as lock:
            lock.bind()
            if recover:
                self._recovery.assert_runner_stopped()
            snapshot = read_raw_snapshot(
                self._database, self._odds_profile, self._batch, effective_cutoff
            )
            if self.ledger_path.exists():
                ledger.migrate_legacy_frontier(snapshot, now)
            recovery_snapshot: RawSnapshot | None = None
            if recover and self.ledger_path.exists():
                recovery_snapshot = snapshot
                for run_id, key, specs in ledger.running_requests():
                    self._recovery.quarantine_and_reset(
                        ledger, run_id, key, specs, label=f"{run_id}-{key.race_id}-recovery"
                    )
                    assert recovery_snapshot is not None
                    ledger.recover_running(
                        key,
                        specs,
                        now,
                        {
                            spec: recovery_snapshot.counts.get((key.race_id, spec), 0)
                            for spec in specs
                        },
                    )
            if recover:
                snapshot = read_raw_snapshot(
                    self._database, self._odds_profile, self._batch, effective_cutoff
                )
            adopted_races: dict[str, int] = {}
            if not self.ledger_path.exists():
                ledger.bootstrap(snapshot, now)
            else:
                adopted_races = ledger.reconcile(snapshot, now)
            states, publications, _ = ledger.read()
            year = select_year(
                self._odds_profile.realtime_data_specs,
                states,
                snapshot.races,
                effective_cutoff,
                None if raw_only else publications,
            )
            if year is None:
                result = WeeklyBatchResult("up_to_date", None, None, 0, 0, 0, 0, {})
                self._write_summary(
                    result, ledger, effective_year=self._batch.last_year, phase="idle"
                )
                return result

            races = races_for_year(
                self._odds_profile.realtime_data_specs, states, snapshot.races, year
            )
            run_id = uuid.uuid4().hex
            ledger.start_run(run_id, year, effective_cutoff, now, races, {"status": "running"})
            metrics = _BatchMetrics.for_specs(self._odds_profile.realtime_data_specs)
            with tempfile.TemporaryDirectory(prefix="keiba-ai-weekly-") as temporary_directory:
                setting_path = Path(temporary_directory) / "historical-odds.xml"
                for key in races:
                    specs = frozenset(
                        spec
                        for spec in self._odds_profile.realtime_data_specs
                        if states[(key.race_id, spec)].state in {"pending", "failed"}
                    )
                    if not specs:
                        continue
                    counts = {spec: snapshot.counts.get((key.race_id, spec), 0) for spec in specs}
                    outcome = self._requests.run(
                        ledger, run_id, key, specs, counts, now, setting_path
                    )
                    metrics.record(specs, outcome)
                    for spec, (state, reason, after_rows) in outcome.results.items():
                        prior = states[(key.race_id, spec)]
                        states[(key.race_id, spec)] = SpecState(
                            key.race_id,
                            spec,
                            state,
                            reason,
                            prior.before_rows,
                            after_rows,
                            prior.attempts + 1,
                        )
                    if outcome.failed_specs:
                        break

            states, _, _ = ledger.read()
            pending_after = sum(
                1
                for (race_id, _), state in states.items()
                if race_key_from_id(race_id).race_date.year == year
                and state.state not in {"acquired", "provider_missing"}
            )
            status = (
                "failed"
                if metrics.failed_specs
                else (
                    "completed"
                    if pending_after == 0 and year < effective_cutoff.year
                    else "up_to_date"
                )
            )
            result = WeeklyBatchResult(
                status,
                year,
                run_id,
                metrics.requested_races,
                metrics.requested_specs,
                metrics.failed_specs,
                pending_after,
                adopted_races,
                False,
                metrics.new_rows,
                metrics.new_races,
                metrics.new_provider_missing,
            )
            ledger.finish_run(run_id, result_payload(result), self._clock())
            self._write_summary(result, ledger)
            return result

    def confirm_provider_missing(self, key: RaceKey, specs: frozenset[str]) -> int:
        """Confirm selected empty-response failures as provider-side gaps."""
        now = self._clock()
        cutoff = now.date() - timedelta(days=1)
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.ledger
        with AcquisitionLock(self._database, self.ledger_path) as lock:
            lock.bind()
            snapshot = read_raw_snapshot(self._database, self._odds_profile, self._batch, cutoff)
            ledger.migrate_legacy_frontier(snapshot, now)
            if key not in snapshot.races:
                raise AcquisitionBlocked("provider-missing confirmation targets an unknown race")
            ledger.confirm_provider_missing(
                key,
                specs,
                now,
                {spec: snapshot.counts.get((key.race_id, spec), 0) for spec in specs},
            )
        return len(specs)

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

    def prepare_publication(self, *, cutoff: date | None = None) -> WeeklyBatchResult:
        """Reconcile raw additions and plan the next complete-Parquet publication."""
        return self._publication.prepare_publication(cutoff=cutoff)

    def prepare_publication_locked(
        self, ledger: ProgressLedger, cutoff: date, now: datetime
    ) -> WeeklyBatchResult:
        """Reconcile and plan publication while the caller owns the common lock."""
        return self._publication.prepare_publication_locked(ledger, cutoff, now)

    def verify_publication_locked(self, ledger: ProgressLedger, year: int) -> None:
        """Reject publication when raw data changed or remains incomplete."""
        return self._publication.verify_publication_locked(ledger, year)

    def repair_derived_publication(self) -> None:
        """Regenerate derived publication files from the committed ledger state."""
        return self._publication.repair_derived_publication()

    def publish_complete(self, publisher: Callable[[], T]) -> T | None:
        """Publish all raw-complete years in one Parquet rebuild."""
        return self._publication.publish_complete(publisher)

    def mark_published(self, year: int) -> None:
        """Record publication only after the complete snapshot is durable."""
        return self._publication.mark_published(year)

    def mark_publication(self, year: int, state: str) -> None:
        """Record the outcome of complete-Parquet publication."""
        return self._publication.mark_publication(year, state)

    def mark_publication_locked(self, ledger: ProgressLedger, year: int, state: str) -> None:
        """Record publication while the caller owns the common acquisition lock."""
        return self._publication.mark_publication_locked(ledger, year, state)

    def refresh_derived_after_publication_locked(
        self,
        ledger: ProgressLedger,
        result: WeeklyBatchResult,
        publication_state: str,
    ) -> None:
        """Refresh derived progress files after changing a publication state."""
        return self._publication.refresh_derived_after_publication_locked(
            ledger, result, publication_state
        )
