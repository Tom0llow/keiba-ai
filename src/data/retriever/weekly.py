"""Run one manual, year-scoped historical odds acquisition batch."""

from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

from data.race_key import RaceKey
from data.retriever.acquisition_lock import AcquisitionBlocked, AcquisitionLock
from data.retriever.jvlinktosqlite import JVLinkToSQLiteError, JVLinkToSQLiteRunner
from data.retriever.odds_archive import OddsArchive
from data.retriever.progress import (
    LEDGER_FILENAME,
    ProgressLedger,
    RawSnapshot,
    SpecState,
    atomic_write,
    race_key_from_id,
    read_raw_snapshot,
    reconcile_states,
)
from data.retriever.setting import HistoricalOddsBatch, JVLinkProfile, JVLinkSettingBuilder

T = TypeVar("T")


@dataclass(frozen=True)
class WeeklyBatchResult:
    """Summarize one invocation without conflating requests and saved rows."""

    status: str
    year: int | None
    run_id: str | None
    requested_races: int
    requested_specs: int
    failed_specs: int
    pending_after: int
    adopted_races: dict[str, int]
    plan_only: bool = False
    new_rows: dict[str, int] = field(default_factory=dict)
    new_races: dict[str, int] = field(default_factory=dict)
    new_provider_missing: dict[str, int] = field(default_factory=dict)


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
        self._runner = runner
        self._database = database.expanduser().resolve()
        self._setting_builder = setting_builder
        self._archive = archive
        self._odds_profile = odds_profile
        self._batch = batch
        self._runtime_dir = runtime_dir.expanduser().resolve()
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Tokyo")))

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
            return self._plan(snapshot, effective_cutoff, raw_only=raw_only)

        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.ledger
        with AcquisitionLock(self._database, self.ledger_path, allow_unresolved=recover) as lock:
            lock.bind()
            if recover:
                self._assert_runner_stopped()
            snapshot = read_raw_snapshot(
                self._database, self._odds_profile, self._batch, effective_cutoff
            )
            if self.ledger_path.exists():
                ledger.migrate_legacy_frontier(snapshot, now)
            recovery_snapshot: RawSnapshot | None = None
            if recover and self.ledger_path.exists():
                recovery_snapshot = snapshot
                for run_id, key, specs in ledger.running_requests():
                    self._quarantine_and_reset(
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
            year = self._select_year(
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

            races = self._races_for_year(states, snapshot.races, year)
            run_id = uuid.uuid4().hex
            ledger.start_run(run_id, year, effective_cutoff, now, races, {"status": "running"})
            requested_races = 0
            requested_specs = 0
            failed_specs = 0
            new_rows: dict[str, int] = dict.fromkeys(self._odds_profile.realtime_data_specs, 0)
            new_races: dict[str, int] = dict.fromkeys(self._odds_profile.realtime_data_specs, 0)
            new_provider_missing: dict[str, int] = dict.fromkeys(
                self._odds_profile.realtime_data_specs, 0
            )
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
                    requested_races += 1
                    requested_specs += len(specs)
                    counts = {spec: snapshot.counts.get((key.race_id, spec), 0) for spec in specs}
                    ledger.request(run_id, key, specs, counts, now)
                    self._quarantine_and_reset(ledger, run_id, key, specs)
                    profile = replace(self._odds_profile, realtime_data_specs=specs)
                    self._setting_builder.build(profile, setting_path, race_key=key)
                    results: dict[str, tuple[str, str, int]] = {}
                    process_returncode: int | None = None
                    api_results: dict[str, tuple[str, int]] = {}
                    try:
                        execution = self._runner.execute(
                            setting_path, skip_last_modified_update=True
                        )
                        process_returncode = getattr(execution, "process_returncode", None)
                        execution_api_results: dict[str, tuple[str, int]] = getattr(
                            execution, "api_results", {}
                        )
                        no_data_specs: frozenset[str] = getattr(
                            execution, "no_data_specs", frozenset()
                        )
                        fatal_specs: frozenset[str] = getattr(execution, "fatal_specs", frozenset())
                        archived = self._archive.archive_request(key, specs)
                        for spec, value in archived.items():
                            if spec in fatal_specs:
                                results[spec] = ("failed", "jvlink_error", value.after_rows)
                                if spec in execution_api_results:
                                    api_results[spec] = execution_api_results[spec]
                            elif value.acquired:
                                results[spec] = ("acquired", value.reason, value.after_rows)
                                new_rows[spec] += value.inserted_rows
                                new_races[spec] += 1
                                if spec in execution_api_results:
                                    api_results[spec] = execution_api_results[spec]
                            elif value.reason == "jvopen_no_data" and spec in no_data_specs:
                                results[spec] = ("provider_missing", value.reason, 0)
                                new_provider_missing[spec] += 1
                                if spec in execution_api_results:
                                    api_results[spec] = execution_api_results[spec]
                            elif value.reason == "jvopen_no_data":
                                results[spec] = ("failed", "empty_response_unverified", 0)
                                if spec in execution_api_results:
                                    api_results[spec] = execution_api_results[spec]
                            else:
                                results[spec] = ("failed", value.reason, value.after_rows)
                                if spec in execution_api_results:
                                    api_results[spec] = execution_api_results[spec]
                    except JVLinkToSQLiteError as exc:
                        process_returncode = exc.returncode
                        api_results = exc.api_results
                        results = {spec: ("failed", "jvlink_error", counts[spec]) for spec in specs}
                    except BaseException:
                        # Keep running rows unresolved so the common lock refuses
                        # another writer until the operator has inspected staging.
                        raise
                    failed = frozenset(
                        spec for spec, (state, _, _) in results.items() if state == "failed"
                    )
                    if failed:
                        self._quarantine_and_reset(
                            ledger, run_id, key, failed, label=f"{run_id}-{key.race_id}"
                        )
                    successful = specs - failed
                    if successful:
                        self._archive.reset_staging(successful)
                    failed_specs += sum(state == "failed" for state, _, _ in results.values())
                    ledger.finish_request(
                        key,
                        results,
                        now,
                        recovered=True,
                        returncode=process_returncode,
                        api_results=api_results,
                    )
                    for spec, (state, reason, after_rows) in results.items():
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
                    if failed:
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
                if failed_specs
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
                requested_races,
                requested_specs,
                failed_specs,
                pending_after,
                adopted_races,
                False,
                new_rows,
                new_races,
                new_provider_missing,
            )
            ledger.finish_run(run_id, self._result_payload(result), self._clock())
            self._write_summary(result, ledger)
            return result

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
        return self._plan(snapshot, cutoff)

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

    def _assert_runner_stopped(self) -> None:
        checker = getattr(self._runner, "assert_not_running", None)
        if checker is None:
            raise JVLinkToSQLiteError("recovery requires a runner process-state check")
        checker()

    def _quarantine_and_reset(
        self,
        ledger: ProgressLedger,
        run_id: str,
        key: RaceKey,
        specs: frozenset[str],
        *,
        label: str | None = None,
    ) -> None:
        """Preserve pre-existing staging evidence before clearing requested tables."""
        recovery_dir = self._runtime_dir / "historical-odds-recovery"
        artifacts = self._archive.quarantine_staging(
            specs, recovery_dir, label or f"{run_id}-{key.race_id}-pre-request"
        )
        if artifacts:
            ledger.record_quarantine(run_id, artifacts)
        self._archive.reset_staging(specs)

    def mark_published(self, year: int) -> None:
        """Record publication only after the complete snapshot is durable."""
        self.mark_publication(year, "published")

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
            next_year = self._select_year(states, snapshot.races, cutoff, publications)
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

    def _plan(
        self, snapshot: RawSnapshot, cutoff: date, *, raw_only: bool = False
    ) -> WeeklyBatchResult:
        if self.ledger_path.exists():
            ledger = ProgressLedger(
                self.ledger_path, self._database, self._odds_profile, self._batch
            )
            states, publications, _ = ledger.read()
            states, _, adopted_races = reconcile_states(
                states, snapshot, self._odds_profile.realtime_data_specs
            )
        else:
            states = {
                (key.race_id, spec): SpecState(
                    key.race_id,
                    spec,
                    "acquired" if snapshot.counts.get((key.race_id, spec), 0) else "pending",
                    (
                        "initial_archive_observed"
                        if snapshot.counts.get((key.race_id, spec), 0)
                        else "unrequested"
                    ),
                    snapshot.counts.get((key.race_id, spec), 0),
                    snapshot.counts.get((key.race_id, spec), 0),
                )
                for key in snapshot.races
                for spec in self._odds_profile.realtime_data_specs
            }
            adopted_races = dict.fromkeys(sorted(self._odds_profile.realtime_data_specs), 0)
            publications = None
        year = self._select_year(
            states,
            snapshot.races,
            cutoff,
            None if raw_only else publications,
        )
        races = self._races_for_year(states, snapshot.races, year) if year is not None else ()
        specs = sum(
            1
            for key in races
            for spec in self._odds_profile.realtime_data_specs
            if states[(key.race_id, spec)].state in {"pending", "failed"}
        )
        return WeeklyBatchResult(
            "plan", year, None, len(races), specs, 0, specs, adopted_races, True
        )

    def _select_year(
        self,
        states: dict[tuple[str, str], SpecState],
        races: tuple[RaceKey, ...],
        cutoff: date,
        publications: dict[int, str] | None = None,
    ) -> int | None:
        candidate_years = {key.race_date.year for key in races if key.race_date <= cutoff}
        years = {
            key.race_date.year
            for key in races
            if key.race_date <= cutoff
            and any(
                states.get((key.race_id, spec), SpecState("", "", "pending", "", 0, 0)).state
                not in {"acquired", "provider_missing"}
                for spec in self._odds_profile.realtime_data_specs
            )
        }
        if publications is not None:
            years.update(
                year
                for year, publication in publications.items()
                if publication in {"pending", "failed"} and year in candidate_years
            )
        return min(years) if years else None

    def _races_for_year(
        self, states: dict[tuple[str, str], SpecState], races: tuple[RaceKey, ...], year: int | None
    ) -> tuple[RaceKey, ...]:
        if year is None:
            return ()
        return tuple(
            key
            for key in races
            if key.race_date.year == year
            and any(
                states[(key.race_id, spec)].state in {"pending", "failed"}
                for spec in self._odds_profile.realtime_data_specs
            )
        )

    def _result_payload(self, result: WeeklyBatchResult) -> dict[str, object]:
        return {
            "status": result.status,
            "year": result.year,
            "run_id": result.run_id,
            "requested_races": result.requested_races,
            "requested_specs": result.requested_specs,
            "failed_specs": result.failed_specs,
            "pending_after": result.pending_after,
            "adopted_races": result.adopted_races,
            "new_rows": result.new_rows,
            "new_races": result.new_races,
            "new_provider_missing": result.new_provider_missing,
        }

    def _write_summary(
        self,
        result: WeeklyBatchResult,
        ledger: ProgressLedger,
        *,
        effective_year: int | None = None,
        phase: str | None = None,
        publication_state: str | None = None,
    ) -> None:
        _, publications, state_revision = ledger.read()
        progress_path = self._runtime_dir / "historical-odds-progress.json"
        if not result.plan_only and result.run_id is None and result.year is not None:
            try:
                existing = json.loads(progress_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
                existing = None
            if isinstance(existing, dict) and existing.get("year") == result.year:
                payload = existing
                payload["publication"] = publication_state or publications.get(result.year)
                payload["state_revision"] = state_revision
            else:
                payload = self._result_payload(result) | {
                    "ledger": str(ledger.path),
                    "plan_only": result.plan_only,
                    "state_revision": state_revision,
                }
        else:
            payload = self._result_payload(result) | {
                "ledger": str(ledger.path),
                "plan_only": result.plan_only,
                "state_revision": state_revision,
            }
        if publication_state is not None:
            payload["publication"] = publication_state
        elif result.year is not None:
            payload["publication"] = publications.get(result.year)
        atomic_write(
            progress_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        if not result.plan_only:
            effective = self._runtime_dir / "historical-odds-effective.toml"
            year = effective_year or result.year or self._batch.last_year
            effective_phase = phase or result.status
            atomic_write(
                effective,
                "[execution]\n"
                "schema_version = 1\n"
                f"state_revision = {state_revision}\n"
                f"year = {year}\n"
                f"start_date = {year:04d}-01-01\n"
                f"end_date_exclusive = {year + 1:04d}-01-01\n"
                f'phase = "{effective_phase}"\n'
                "skip_acquired = true\n"
                "skip_provider_missing = true\n"
                f"data_specs = {json.dumps(sorted(self._odds_profile.realtime_data_specs))}\n",
            )
            if result.run_id is not None:
                atomic_write(
                    self._runtime_dir / "historical-odds-runs" / f"{result.run_id}.json",
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                )
