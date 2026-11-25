"""Recover and execute planned race-day odds captures.

With ``prediction_offset_minutes`` each race also gets a 0B41/0B42 prediction fetch
(ADR-032 Amendment 2). It archives the time series into ``ARCHIVE_O1``/``ARCHIVE_O2``
and, still holding the acquisition lock, hands the race to a publisher so that the
race-day feature command (ADR-037) reads its log and odds from one pinned version.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import (
    AcquisitionBlocked,
    AcquisitionLock,
)
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
    JVLinkToSQLiteRunner,
)
from jra_van_retriever.acquisition.odds_archive import CaptureResult, OddsArchive
from jra_van_retriever.acquisition.setting_xml import (
    JVLinkSettingBuilder,
    verify_realtime_date_key,
    verify_realtime_race_key,
)
from jra_van_retriever.config.profiles import (
    JVLinkProfile,
    RaceDayOddsProfile,
    race_day_tc_profile,
)
from jra_van_retriever.config.validation import (
    validate_race_day_odds_profile,
    validate_race_day_prediction_profile,
    validate_race_day_tc_profile,
)
from jra_van_retriever.progress.raw_observation import read_race_day_races
from jra_van_retriever.workflows.race_day_odds_plan import (
    CapturePlan,
    adopted_starts,
    classify_capture,
    earlier_start_races,
    effective_starts,
    is_capture_late,
    jvlink_agent_down_results,
    plan_captures,
    replan,
)

type RacePublisher = Callable[[RaceKey], object]

_CAPTURE_STATUSES = ("archived", "no_data", "failed", "held", "skipped_late", "interrupted")
_TC_SPECS = frozenset({"0B14"})


class RaceDayOddsSetupError(ValueError):
    """Report a setting error found before the first race-day capture."""


@dataclass(frozen=True)
class CaptureReport:
    """Represent one capture line emitted by the CLI."""

    capture_id: str
    race_key: RaceKey
    offset_minutes: int
    results: dict[str, CaptureResult]


@dataclass(frozen=True)
class RaceDayOddsRunResult:
    """Return emitted captures and the final per-DataSpec status counts."""

    captures: tuple[CaptureReport, ...]
    summary: dict[str, int]
    stop_reason: str | None = None

    @property
    def failed(self) -> bool:
        """Return whether any requested DataSpec failed."""
        return self.summary["failed"] > 0


@dataclass(frozen=True)
class _CaptureStep:
    report: CaptureReport
    stop: bool = False
    stop_reason: str | None = None


@dataclass(frozen=True)
class _TCStep:
    """Represent one time-change check and whether it must stop the day."""

    stop: bool = False
    stop_reason: str | None = None


class RaceDayOddsRetriever:
    """Run one day's captures with explicit clock and sleep boundaries."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        profile: RaceDayOddsProfile,
        database: Path,
        ledger_path: Path,
        runtime_dir: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        prediction_profile: JVLinkProfile | None = None,
        tc_runner: JVLinkToSQLiteRunner | None = None,
    ) -> None:
        validate_race_day_odds_profile(profile)
        if profile.prediction_offset_minutes is not None:
            if prediction_profile is None:
                raise ValueError("race-day prediction fetch requires the realtime-history profile")
            validate_race_day_prediction_profile(prediction_profile)
        self._prediction_profile = prediction_profile
        self._runner = runner
        self._tc_runner = tc_runner or runner
        self._setting_builder = setting_builder
        self._archive = archive
        self._profile = profile
        self._database = database
        self._ledger_path = ledger_path
        self._runtime_dir = runtime_dir
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper
        self._specs = profile.realtime_data_specs
        self._tc_profile = race_day_tc_profile()
        validate_race_day_tc_profile(self._tc_profile)
        self._quarantine_dir = runtime_dir / "race-day-odds-quarantine"

    def retrieve(
        self,
        race_date: date,
        *,
        reporter: Callable[[CaptureReport], None] | None = None,
        recovery_reporter: Callable[[int], None] | None = None,
        publisher: RacePublisher | None = None,
    ) -> RaceDayOddsRunResult:
        """Recover interrupted work, then execute the planned captures in time order.

        Before each time point (``tc_check_lead_seconds`` earlier) a 0B14 check reads
        announced start-time changes; unfinished odds captures move to the changed start,
        and a race announced earlier has its prediction fetch held (ADR-049). A check runs
        only if it can finish (by its timeout) before the next capture; otherwise that time
        point is skipped. Only the lock and recording after a check can add a few seconds.

        ``publisher`` receives the race of every finished or held prediction fetch,
        whatever its status, while the acquisition lock is held; its failure never stops
        the day.
        """
        interrupted = self.recover()
        if recovery_reporter is not None:
            recovery_reporter(interrupted)
        rows = read_race_day_races(self._database, race_date)
        all_plans = plan_captures(
            rows,
            race_date,
            self._profile.offsets_minutes,
            prediction_offset_minutes=self._profile.prediction_offset_minutes,
        )
        key_prefix = (f"{race_date:%Y}", f"{race_date:%m%d}")
        # A restart (the recovery path) must not re-run or re-log finished captures.
        finished = self._archive.finished_capture_keys(key_prefix)
        pending = [
            plan
            for plan in all_plans
            if (plan.race_key.race_id, str(plan.offset_minutes), plan.kind) not in finished
        ]
        card_starts = {plan.race_key.race_id: plan.scheduled_start_at for plan in all_plans}
        reports: list[CaptureReport] = []
        summary = dict.fromkeys(_CAPTURE_STATUSES, 0)
        summary["interrupted"] = interrupted
        stop_reason: str | None = None
        # Time points already covered by a TC check (or a recorded skip); a time point
        # moved by re-planning is examined again (ADR-049).
        checked_time_points: set[datetime] = set()
        notified_earlier: set[str] = set()
        lead = timedelta(seconds=self._profile.tc_check_lead_seconds)
        tc_timeout = timedelta(seconds=self._profile.tc_check_timeout_seconds)
        with tempfile.TemporaryDirectory(prefix="keiba-ai-race-day-odds-") as temporary:
            settings = {
                "capture": Path(temporary) / "race-day-odds.xml",
                "prediction": Path(temporary) / "race-day-prediction.xml",
                "tc": Path(temporary) / "race-day-tc.xml",
            }
            self._verify_setting(settings["capture"], all_plans[0].race_key, "capture")
            if self._profile.prediction_offset_minutes is not None:
                self._verify_setting(settings["prediction"], all_plans[0].race_key, "prediction")
            self._verify_tc_setting(settings["tc"], race_date)
            # A restart restores the changes already accumulated before the interruption.
            effective, pending = self._apply_tc_rows(
                key_prefix,
                card_starts,
                pending,
                notified_earlier,
                publisher,
                previous={},
                reports=reports,
                summary=summary,
                reporter=reporter,
            )
            while pending:
                pending = list(replan(pending, effective))
                plan = pending[0]
                now = self._now()
                # The earliest unchecked time point whose check can still run on time.
                checkable = sorted(
                    candidate.planned_at
                    for candidate in pending
                    if candidate.planned_at not in checked_time_points
                    and now <= candidate.planned_at - lead
                )
                # A later point's check goes first only if it ends by the next capture.
                if checkable and checkable[0] - lead + tc_timeout <= plan.planned_at:
                    time_point_at = checkable[0]
                    # One check covers every time point within the lead window.
                    checked_time_points.update(
                        candidate.planned_at
                        for candidate in pending
                        if time_point_at <= candidate.planned_at <= time_point_at + lead
                    )
                    self._wait_until(time_point_at - lead)
                    tc_step = self._check_tc(race_date, time_point_at, card_starts, settings["tc"])
                    if tc_step.stop:
                        stop_reason = tc_step.stop_reason
                        break
                    effective, pending = self._apply_tc_rows(
                        key_prefix,
                        card_starts,
                        pending,
                        notified_earlier,
                        publisher,
                        previous=effective,
                        reports=reports,
                        summary=summary,
                        reporter=reporter,
                    )
                    continue
                if plan.planned_at not in checked_time_points:
                    # The previous capture overran the lead time; never delay a capture.
                    # Only this time point is skipped; later ones keep their own check.
                    checked_time_points.add(plan.planned_at)
                    self._record_skipped_tc_check(race_date, plan.planned_at, card_starts)
                    continue
                pending.pop(0)
                self._wait_until(plan.planned_at)
                step = self._capture(plan, settings[plan.kind], publisher)
                self._record_steps((step,), reports, summary, reporter)
                if step.stop:
                    stop_reason = step.stop_reason
                    break
        return RaceDayOddsRunResult(tuple(reports), summary, stop_reason)

    def _verify_tc_setting(self, setting_path: Path, race_date: date) -> None:
        """Generate and check the 0B14 date-key XML once before any capture."""
        try:
            self._setting_builder.build(self._tc_profile, setting_path, race_date=race_date)
            verify_realtime_date_key(setting_path, _TC_SPECS, race_date)
        except (OSError, ValueError, ET.ParseError) as exc:
            raise RaceDayOddsSetupError(f"race-day TC check setting is invalid: {exc}") from exc

    def _check_tc(
        self,
        race_date: date,
        time_point_at: datetime,
        card_starts: dict[str, datetime],
        setting_path: Path,
    ) -> _TCStep:
        """Request 0B14 once, archive its TC rows and record the outcome (ADR-049)."""
        started_at: datetime | None = None
        execution: JVLinkExecutionResult | None = None
        try:
            with AcquisitionLock(self._database, self._ledger_path) as lock:
                lock.bind()
                # A previous response must never be read as this one.
                self._archive.reset_tc_staging()
                started_at = self._now()
                failure: str | None = None
                try:
                    execution = self._tc_runner.execute(
                        setting_path, skip_last_modified_update=True
                    )
                except JVLinkToSQLiteError as exc:
                    execution = JVLinkExecutionResult(
                        exc.api_returncodes,
                        fatal_specs=_TC_SPECS,
                        api_results=exc.api_results,
                        fatal_returncodes=exc.fatal_returncodes,
                        process_returncode=exc.returncode,
                    )
                    failure = " ".join(str(exc).split())
                completed_at = self._now()
                agent_down = jvlink_agent_down_results(execution)
                tc_rows = 0
                if agent_down:
                    result, reason = "agent_down", _agent_down_details(agent_down)
                elif failure is not None or "0B14" in execution.fatal_specs:
                    result, reason = "failed", failure or "jvlink_error"
                elif "0B14" in execution.no_data_specs:
                    result, reason = "no_data", "jvopen_no_data"
                else:
                    tc_rows = self._archive.tc_staging_rows()
                    self._archive.archive_tc_info()
                    result, reason = "ok", "tc_rows_archived"
                self._archive.reset_tc_staging()
                self._record_tc_check_outcome(
                    race_date,
                    time_point_at,
                    card_starts,
                    result=result,
                    reason=reason,
                    started_at=started_at,
                    completed_at=completed_at,
                    execution=execution,
                    tc_rows=tc_rows,
                )
        except KeyboardInterrupt:
            raise
        except (AcquisitionBlocked, OSError, ValueError, ET.ParseError, sqlite3.Error) as exc:
            # A failed check keeps the last known plan; it never stops the captures.
            reason = " ".join(str(exc).split()) or type(exc).__name__
            print(f"race-day-odds TC check failed: {reason}", file=sys.stderr)
            if not isinstance(exc, AcquisitionBlocked):
                # The lock was held when the failure happened; record it under the lock.
                self._record_locked(
                    race_date,
                    time_point_at,
                    card_starts,
                    result="failed",
                    reason=reason,
                    started_at=started_at,
                    completed_at=self._now(),
                    execution=execution,
                )
            return _TCStep()
        if result == "agent_down":
            return _TCStep(
                stop=True,
                stop_reason=(
                    f"JV-Link returned {reason} for the TC check; the JVLinkAgent service may "
                    "have stopped; remaining captures were not run"
                ),
            )
        if result == "failed":
            print(f"race-day-odds TC check failed: {reason}", file=sys.stderr)
        return _TCStep()

    def _record_skipped_tc_check(
        self, race_date: date, time_point_at: datetime, card_starts: dict[str, datetime]
    ) -> None:
        """Record a skipped check under the acquisition lock (stderr only without it)."""
        self._record_locked(
            race_date,
            time_point_at,
            card_starts,
            result="skipped",
            reason="no_time_before_time_point",
        )

    def _record_locked(
        self,
        race_date: date,
        time_point_at: datetime,
        card_starts: dict[str, datetime],
        **outcome: object,
    ) -> None:
        try:
            with AcquisitionLock(self._database, self._ledger_path) as lock:
                lock.bind()
                self._record_tc_check_outcome(
                    race_date,
                    time_point_at,
                    card_starts,
                    **outcome,  # type: ignore[arg-type]
                )
        except (AcquisitionBlocked, OSError) as exc:
            print(
                f"race-day-odds TC check {outcome.get('result')} not recorded: {exc}",
                file=sys.stderr,
            )

    def _record_tc_check_outcome(
        self,
        race_date: date,
        time_point_at: datetime,
        card_starts: dict[str, datetime],
        *,
        result: str,
        reason: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        execution: JVLinkExecutionResult | None = None,
        tc_rows: int = 0,
    ) -> None:
        """Persist one TC check (or skip) with the starts adopted after it (best effort)."""
        try:
            rows = self._archive.tc_rows((f"{race_date:%Y}", f"{race_date:%m%d}"))
            self._archive.record_tc_check(
                uuid.uuid4().hex,
                race_date=race_date,
                time_point_at=time_point_at,
                started_at=started_at,
                completed_at=completed_at,
                result=result,
                reason=reason,
                execution=execution,
                tc_rows=tc_rows,
                earlier_start_races=earlier_start_races(rows, card_starts),
                adopted_starts=json.dumps(
                    adopted_starts(rows, card_starts), ensure_ascii=False, sort_keys=True
                ),
            )
        except sqlite3.Error as exc:
            print(f"race-day-odds TC check not recorded: {exc}", file=sys.stderr)

    def _apply_tc_rows(
        self,
        key_prefix: tuple[str, str],
        card_starts: dict[str, datetime],
        pending: list[CapturePlan],
        notified_earlier: set[str],
        publisher: RacePublisher | None,
        *,
        previous: dict[str, datetime],
        reports: list[CaptureReport],
        summary: dict[str, int],
        reporter: Callable[[CaptureReport], None] | None,
    ) -> tuple[dict[str, datetime], list[CapturePlan]]:
        """Return the current changed starts and hold predictions of earlier starts.

        If the accumulated TC rows cannot be read, the last known plan is kept.
        """
        try:
            rows = self._archive.tc_rows(key_prefix)
        except sqlite3.Error as exc:
            print(f"race-day-odds TC rows not read; keeping the plan: {exc}", file=sys.stderr)
            return previous, pending
        effective = effective_starts(rows, card_starts)
        earlier = earlier_start_races(rows, card_starts)
        remaining: list[CapturePlan] = []
        held_steps: list[_CaptureStep] = []
        for plan in pending:
            if plan.kind == "prediction" and plan.race_key.race_id in earlier:
                held_steps.append(self._hold_prediction(plan, publisher))
                continue
            remaining.append(plan)
        held_races = {step.report.race_key.race_id for step in held_steps}
        for race_id in sorted(earlier - notified_earlier):
            notified_earlier.add(race_id)
            action = (
                "prediction fetch held"
                if race_id in held_races
                else "prediction fetch not pending (already fetched, already held or not "
                "planned); nothing withdrawn"
            )
            print(
                f"race-day-odds start moved earlier for race {race_id}: {action}",
                file=sys.stderr,
            )
        self._record_steps(held_steps, reports, summary, reporter)
        return effective, remaining

    def _hold_prediction(self, plan: CapturePlan, publisher: RacePublisher | None) -> _CaptureStep:
        """Record a prediction fetch as held for an earlier start, then publish it."""
        capture_id = uuid.uuid4().hex
        _, specs = self._kind(plan.kind)
        results = {spec: CaptureResult("held", "start_moved_earlier") for spec in sorted(specs)}
        try:
            with AcquisitionLock(self._database, self._ledger_path) as lock:
                lock.bind()
                self._archive.record_held_capture(
                    capture_id,
                    plan.race_key,
                    specs,
                    scheduled_start_at=plan.scheduled_start_at,
                    offset_minutes=plan.offset_minutes,
                    planned_at=plan.planned_at,
                )
                self._publish(plan, capture_id, publisher)
        except KeyboardInterrupt:
            raise
        except (AcquisitionBlocked, OSError, ValueError, sqlite3.Error) as exc:
            print(
                f"race-day-odds capture {capture_id} hold not recorded: {exc}",
                file=sys.stderr,
            )
            results = {
                spec: CaptureResult("failed", "capture_not_recorded") for spec in sorted(specs)
            }
        return _CaptureStep(CaptureReport(capture_id, plan.race_key, plan.offset_minutes, results))

    def _record_steps(
        self,
        steps: tuple[_CaptureStep, ...] | list[_CaptureStep],
        reports: list[CaptureReport],
        summary: dict[str, int],
        reporter: Callable[[CaptureReport], None] | None,
    ) -> None:
        for step in steps:
            reports.append(step.report)
            for result in step.report.results.values():
                summary[result.status] += 1
            if reporter is not None:
                reporter(step.report)

    def _verify_setting(self, setting_path: Path, race_key: RaceKey, kind: str) -> None:
        """Generate and check the execution XML once before any capture is recorded."""
        profile, specs = self._kind(kind)
        try:
            self._setting_builder.build(profile, setting_path, race_key=race_key)
            verify_realtime_race_key(setting_path, specs, race_key)
        except (OSError, ValueError, ET.ParseError) as exc:
            raise RaceDayOddsSetupError(
                f"race-day-odds execution setting is invalid: {exc}"
            ) from exc

    def recover(self) -> int:
        """Quarantine staging of unfinished captures and mark them interrupted.

        Returns the number of capture rows marked interrupted.
        """
        with AcquisitionLock(
            self._database,
            self._ledger_path,
            allow_unresolved_capture=True,
        ) as lock:
            lock.bind()
            self._runner.assert_not_running()
            specs = self._archive.running_capture_specs()
            if not specs:
                return 0
            artifacts = self._archive.quarantine_capture_staging(
                specs,
                self._quarantine_dir,
                f"startup-recovery-{uuid.uuid4().hex}",
            )
            if artifacts:
                self._archive.append_capture_reason_for_running(
                    _evidence_reason("recovery_quarantined", artifacts)
                )
            self._archive.reset_capture_staging(specs)
            return self._archive.interrupt_running_captures(self._now(), "interrupted_recovery")

    def _kind(self, kind: str) -> tuple[JVLinkProfile, frozenset[str]]:
        if kind == "prediction":
            assert self._prediction_profile is not None  # checked in __init__
            return self._prediction_profile, self._prediction_profile.realtime_data_specs
        return self._profile, self._specs

    def _capture(
        self, plan: CapturePlan, setting_path: Path, publisher: RacePublisher | None
    ) -> _CaptureStep:
        capture_id = uuid.uuid4().hex
        begin_committed = False
        profile, specs = self._kind(plan.kind)
        try:
            with AcquisitionLock(self._database, self._ledger_path) as lock:
                lock.bind()
                if plan.kind == "prediction":
                    # The time series must come from this fetch alone (ADR-037).
                    self._runner.assert_not_running()
                if is_capture_late(
                    plan.planned_at,
                    self._now(),
                    self._profile.late_tolerance_seconds,
                ):
                    self._archive.record_skipped_capture(
                        capture_id,
                        plan.race_key,
                        specs,
                        scheduled_start_at=plan.scheduled_start_at,
                        offset_minutes=plan.offset_minutes,
                        planned_at=plan.planned_at,
                        effective_start_at=plan.effective_start_at,
                    )
                    self._publish(plan, capture_id, publisher)
                    return _CaptureStep(
                        CaptureReport(
                            capture_id,
                            plan.race_key,
                            plan.offset_minutes,
                            {
                                spec: CaptureResult("skipped_late", "late_tolerance_exceeded")
                                for spec in sorted(specs)
                            },
                        )
                    )

                # A setting error must not leave a running capture that stops the day.
                self._setting_builder.build(
                    profile,
                    setting_path,
                    race_key=plan.race_key,
                )
                self._archive.begin_capture(
                    capture_id,
                    plan.race_key,
                    specs,
                    scheduled_start_at=plan.scheduled_start_at,
                    offset_minutes=plan.offset_minutes,
                    planned_at=plan.planned_at,
                    effective_start_at=plan.effective_start_at,
                )
                begin_committed = True
                artifacts = self._archive.quarantine_capture_staging(
                    specs,
                    self._quarantine_dir,
                    f"{capture_id}-pre-request",
                )
                # Record the evidence before the staging rows are deleted.
                if artifacts:
                    self._archive.append_capture_reason(
                        capture_id, _evidence_reason("preexisting_staging", artifacts)
                    )
                self._archive.reset_capture_staging(specs)
                started_at = self._now()
                self._archive.mark_capture_started(capture_id, started_at)
                try:
                    execution = self._runner.execute(setting_path, skip_last_modified_update=True)
                except JVLinkToSQLiteError as exc:
                    execution = JVLinkExecutionResult(
                        exc.api_returncodes,
                        fatal_specs=specs,
                        api_results=exc.api_results,
                        fatal_returncodes=exc.fatal_returncodes,
                        process_returncode=exc.returncode,
                    )
                completed_at = self._now()
                results = self._archive.finish_capture(
                    capture_id,
                    plan.race_key,
                    specs,
                    execution,
                    completed_at=completed_at,
                    quarantine_directory=self._quarantine_dir,
                    quarantine_label=capture_id,
                    classifier=classify_capture,
                )
                self._publish(plan, capture_id, publisher)
                agent_down_results = jvlink_agent_down_results(execution)
                stop_reason = None
                if agent_down_results:
                    details = _agent_down_details(agent_down_results)
                    stop_reason = (
                        f"JV-Link returned {details}; the JVLinkAgent service may have stopped; "
                        "remaining captures were not run"
                    )
                return _CaptureStep(
                    CaptureReport(capture_id, plan.race_key, plan.offset_minutes, results),
                    stop=stop_reason is not None,
                    stop_reason=stop_reason,
                )
        except KeyboardInterrupt:
            raise
        except (
            AcquisitionBlocked,
            JVLinkToSQLiteError,
            OSError,
            ValueError,
            ET.ParseError,
            sqlite3.Error,
        ) as exc:
            print(
                f"race-day-odds capture {capture_id} failed before completion: {exc}",
                file=sys.stderr,
            )
            results = {
                spec: CaptureResult("failed", "capture_not_recorded") for spec in sorted(specs)
            }
            if begin_committed:
                results = self._incomplete_results(capture_id, specs)
            return _CaptureStep(
                CaptureReport(capture_id, plan.race_key, plan.offset_minutes, results),
                stop=begin_committed,
            )

    def _publish(self, plan: CapturePlan, capture_id: str, publisher: RacePublisher | None) -> None:
        """Publish a finished prediction fetch's race; a failure is logged, never fatal."""
        if plan.kind != "prediction" or publisher is None:
            return
        try:
            publisher(plan.race_key)
        except Exception as exc:
            # Any publication error leaves the archived rows; the feature command then
            # holds the race at its deadline. The day's remaining captures continue.
            reason = f"publish_failed: {exc}"
            print(f"race-day-odds capture {capture_id} {reason}", file=sys.stderr)
            try:
                self._archive.append_finished_capture_reason(capture_id, reason)
            except sqlite3.Error as log_error:
                print(
                    f"race-day-odds capture {capture_id} reason not recorded: {log_error}",
                    file=sys.stderr,
                )

    def _incomplete_results(
        self, capture_id: str, specs: frozenset[str]
    ) -> dict[str, CaptureResult]:
        """Report committed specs as persisted and the rest as incomplete."""
        try:
            persisted = self._archive.capture_statuses(capture_id)
        except sqlite3.Error:
            persisted = {}
        results: dict[str, CaptureResult] = {}
        for spec in sorted(specs):
            status, reason = persisted.get(spec, ("running", ""))
            if status == "running":
                results[spec] = CaptureResult("failed", "capture_incomplete")
            else:
                results[spec] = CaptureResult(status, reason)
        return results

    def _wait_until(self, planned_at: datetime) -> None:
        while (seconds := (planned_at - self._now()).total_seconds()) > 0:
            self._sleeper(seconds)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("race-day odds clock must be timezone-aware")
        return value.astimezone(UTC)


def _agent_down_details(results: dict[str, tuple[str, int]]) -> str:
    return ", ".join(
        f"{data_spec} {api} {returncode}" for data_spec, (api, returncode) in results.items()
    )


def _evidence_reason(prefix: str, artifacts: list[dict[str, object]]) -> str:
    if not artifacts:
        return prefix
    return f"{prefix}: {json.dumps(artifacts, ensure_ascii=False, sort_keys=True)}"
