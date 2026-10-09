"""Run one manual, year-scoped historical odds acquisition batch."""

from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data.race_key import RaceKey
from data.retriever.acquisition_lock import AcquisitionLock
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
    ) -> WeeklyBatchResult:
        """Run at most one year, or return a read-only plan when requested."""
        now = self._clock()
        effective_cutoff = cutoff or (now.date() - timedelta(days=1))
        if plan_only:
            snapshot = read_raw_snapshot(
                self._database, self._odds_profile, self._batch, effective_cutoff
            )
            return self._plan(snapshot, effective_cutoff)

        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.ledger
        with AcquisitionLock(self._database, self.ledger_path, allow_unresolved=recover) as lock:
            lock.bind()
            recovery_snapshot: RawSnapshot | None = None
            if recover and self.ledger_path.exists():
                self._assert_runner_stopped()
                recovery_snapshot = read_raw_snapshot(
                    self._database, self._odds_profile, self._batch, effective_cutoff
                )
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
            snapshot = read_raw_snapshot(
                self._database, self._odds_profile, self._batch, effective_cutoff
            )
            adopted_races: dict[str, int] = {}
            if not self.ledger_path.exists():
                ledger.bootstrap(snapshot, now)
            else:
                adopted_races = ledger.reconcile(snapshot, now)
            states, publications, _ = ledger.read()
            year = self._select_year(states, snapshot.races, effective_cutoff, publications)
            if year is None:
                result = WeeklyBatchResult("up_to_date", None, None, 0, 0, 0, 0, {})
                self._write_summary(result, ledger)
                return result

            races = self._races_for_year(states, snapshot.races, year)
            run_id = uuid.uuid4().hex
            ledger.start_run(run_id, year, effective_cutoff, now, races, {"status": "running"})
            requested_races = 0
            requested_specs = 0
            failed_specs = 0
            new_rows: dict[str, int] = dict.fromkeys(self._odds_profile.realtime_data_specs, 0)
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
                    returncode: int | None = None
                    try:
                        self._runner.execute(setting_path, skip_last_modified_update=True)
                        archived = self._archive.archive_request(key, specs)
                        for spec, value in archived.items():
                            if value.acquired:
                                results[spec] = ("acquired", value.reason, value.after_rows)
                                new_rows[spec] += value.inserted_rows
                            else:
                                results[spec] = ("failed", value.reason, value.after_rows)
                    except JVLinkToSQLiteError as exc:
                        returncode = exc.returncode
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
                    failed_specs += sum(state == "failed" for state, _, _ in results.values())
                    ledger.finish_request(key, results, now, recovered=True, returncode=returncode)
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
                "failed" if failed_specs else ("completed" if pending_after == 0 else "up_to_date")
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
            )
            ledger.finish_run(run_id, self._result_payload(result), self._clock())
            self._write_summary(result, ledger)
            return result

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

    def mark_publication(self, year: int, state: str) -> None:
        """Record the outcome of complete-Parquet publication."""
        ledger = ProgressLedger(self.ledger_path, self._database, self._odds_profile, self._batch)
        with AcquisitionLock(self._database, self.ledger_path) as lock:
            lock.bind()
            self.mark_publication_locked(ledger, year, state)

    def mark_publication_locked(self, ledger: ProgressLedger, year: int, state: str) -> None:
        """Record publication while the caller owns the common acquisition lock."""
        ledger.publication(year, state)

    def _plan(self, snapshot: RawSnapshot, cutoff: date) -> WeeklyBatchResult:
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
                    (
                        "acquired"
                        if snapshot.counts.get((key.race_id, spec), 0)
                        else (
                            "provider_missing"
                            if key <= self._batch.accept_existing_gaps_through
                            else "pending"
                        )
                    ),
                    (
                        "initial_archive_observed"
                        if snapshot.counts.get((key.race_id, spec), 0)
                        else (
                            "user_accepted_existing_gaps"
                            if key <= self._batch.accept_existing_gaps_through
                            else "unrequested"
                        )
                    ),
                    snapshot.counts.get((key.race_id, spec), 0),
                    snapshot.counts.get((key.race_id, spec), 0),
                )
                for key in snapshot.races
                for spec in self._odds_profile.realtime_data_specs
            }
            adopted_races = dict.fromkeys(sorted(self._odds_profile.realtime_data_specs), 0)
            publications = None
        year = self._select_year(states, snapshot.races, cutoff, publications)
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
        }

    def _write_summary(self, result: WeeklyBatchResult, ledger: ProgressLedger) -> None:
        _, _, state_revision = ledger.read()
        payload = self._result_payload(result) | {
            "ledger": str(ledger.path),
            "plan_only": result.plan_only,
            "state_revision": state_revision,
        }
        atomic_write(
            self._runtime_dir / "historical-odds-progress.json",
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        if not result.plan_only:
            effective = self._runtime_dir / "historical-odds-effective.toml"
            year = result.year if result.year is not None else self._batch.last_year
            atomic_write(
                effective,
                "[execution]\n"
                "schema_version = 1\n"
                f"state_revision = {state_revision}\n"
                f"year = {year}\n"
                f"start_date = {year:04d}-01-01\n"
                f"end_date_exclusive = {year + 1:04d}-01-01\n"
                f'phase = "{result.status}"\n'
                "skip_acquired = true\n"
                "skip_provider_missing = true\n"
                f"data_specs = {json.dumps(sorted(self._odds_profile.realtime_data_specs))}\n",
            )
            if result.run_id is not None:
                atomic_write(
                    self._runtime_dir / "historical-odds-runs" / f"{result.run_id}.json",
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                )
