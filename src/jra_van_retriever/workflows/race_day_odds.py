"""Recover and execute planned race-day odds captures."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import RaceDayOddsProfile
from jra_van_retriever.config.validation import validate_race_day_odds_profile
from jra_van_retriever.progress.raw_observation import read_race_day_races
from jra_van_retriever.workflows.race_day_odds_plan import (
    CapturePlan,
    classify_capture,
    is_capture_late,
    plan_captures,
)

_CAPTURE_STATUSES = ("archived", "no_data", "failed", "skipped_late", "interrupted")


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

    @property
    def failed(self) -> bool:
        """Return whether any requested DataSpec failed."""
        return self.summary["failed"] > 0


@dataclass(frozen=True)
class _CaptureStep:
    report: CaptureReport
    stop: bool = False


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
    ) -> None:
        validate_race_day_odds_profile(profile)
        self._runner = runner
        self._setting_builder = setting_builder
        self._archive = archive
        self._profile = profile
        self._database = database
        self._ledger_path = ledger_path
        self._runtime_dir = runtime_dir
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper
        self._specs = profile.realtime_data_specs
        self._quarantine_dir = runtime_dir / "race-day-odds-quarantine"

    def retrieve(
        self,
        race_date: date,
        *,
        reporter: Callable[[CaptureReport], None] | None = None,
        recovery_reporter: Callable[[int], None] | None = None,
    ) -> RaceDayOddsRunResult:
        """Recover interrupted work, then execute every planned capture in order."""
        interrupted = self._recover()
        if recovery_reporter is not None:
            recovery_reporter(interrupted)
        rows = read_race_day_races(self._database, race_date)
        plans = plan_captures(rows, race_date, self._profile.offsets_minutes)
        # A restart (the recovery path) must not re-run or re-log finished captures.
        finished = self._archive.finished_capture_keys((f"{race_date:%Y}", f"{race_date:%m%d}"))
        plans = tuple(
            plan
            for plan in plans
            if (plan.race_key.race_id, str(plan.offset_minutes)) not in finished
        )
        reports: list[CaptureReport] = []
        summary = dict.fromkeys(_CAPTURE_STATUSES, 0)
        summary["interrupted"] = interrupted
        with tempfile.TemporaryDirectory(prefix="keiba-ai-race-day-odds-") as temporary:
            setting_path = Path(temporary) / "race-day-odds.xml"
            for plan in plans:
                self._wait_until(plan.planned_at)
                step = self._capture(plan, setting_path)
                reports.append(step.report)
                for result in step.report.results.values():
                    summary[result.status] += 1
                if reporter is not None:
                    reporter(step.report)
                if step.stop:
                    break
        return RaceDayOddsRunResult(tuple(reports), summary)

    def _recover(self) -> int:
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

    def _capture(self, plan: CapturePlan, setting_path: Path) -> _CaptureStep:
        capture_id = uuid.uuid4().hex
        begin_committed = False
        try:
            with AcquisitionLock(self._database, self._ledger_path) as lock:
                lock.bind()
                if is_capture_late(
                    plan.planned_at,
                    self._now(),
                    self._profile.late_tolerance_seconds,
                ):
                    self._archive.record_skipped_capture(
                        capture_id,
                        plan.race_key,
                        self._specs,
                        scheduled_start_at=plan.scheduled_start_at,
                        offset_minutes=plan.offset_minutes,
                        planned_at=plan.planned_at,
                    )
                    return _CaptureStep(
                        CaptureReport(
                            capture_id,
                            plan.race_key,
                            plan.offset_minutes,
                            {
                                spec: CaptureResult("skipped_late", "late_tolerance_exceeded")
                                for spec in sorted(self._specs)
                            },
                        )
                    )

                self._archive.begin_capture(
                    capture_id,
                    plan.race_key,
                    self._specs,
                    scheduled_start_at=plan.scheduled_start_at,
                    offset_minutes=plan.offset_minutes,
                    planned_at=plan.planned_at,
                )
                begin_committed = True
                artifacts = self._archive.quarantine_capture_staging(
                    self._specs,
                    self._quarantine_dir,
                    f"{capture_id}-pre-request",
                )
                # Record the evidence before the staging rows are deleted.
                if artifacts:
                    self._archive.append_capture_reason(
                        capture_id, _evidence_reason("preexisting_staging", artifacts)
                    )
                self._archive.reset_capture_staging(self._specs)
                self._setting_builder.build(
                    self._profile,
                    setting_path,
                    race_key=plan.race_key,
                )
                started_at = self._now()
                self._archive.mark_capture_started(capture_id, started_at)
                try:
                    execution = self._runner.execute(setting_path, skip_last_modified_update=True)
                except JVLinkToSQLiteError as exc:
                    execution = JVLinkExecutionResult(
                        exc.api_returncodes,
                        fatal_specs=self._specs,
                        api_results=exc.api_results,
                        fatal_returncodes=exc.fatal_returncodes,
                        process_returncode=exc.returncode,
                    )
                completed_at = self._now()
                results = self._archive.finish_capture(
                    capture_id,
                    plan.race_key,
                    self._specs,
                    execution,
                    completed_at=completed_at,
                    quarantine_directory=self._quarantine_dir,
                    quarantine_label=capture_id,
                    classifier=classify_capture,
                )
                return _CaptureStep(
                    CaptureReport(capture_id, plan.race_key, plan.offset_minutes, results)
                )
        except KeyboardInterrupt:
            raise
        except (AcquisitionBlocked, OSError, ValueError, sqlite3.Error) as exc:
            print(
                f"race-day-odds capture {capture_id} failed before completion: {exc}",
                file=sys.stderr,
            )
            results = {
                spec: CaptureResult("failed", "capture_not_recorded")
                for spec in sorted(self._specs)
            }
            if begin_committed:
                results = self._incomplete_results(capture_id)
            return _CaptureStep(
                CaptureReport(capture_id, plan.race_key, plan.offset_minutes, results),
                stop=begin_committed,
            )

    def _incomplete_results(self, capture_id: str) -> dict[str, CaptureResult]:
        """Report committed specs as persisted and the rest as incomplete."""
        try:
            persisted = self._archive.capture_statuses(capture_id)
        except sqlite3.Error:
            persisted = {}
        results: dict[str, CaptureResult] = {}
        for spec in sorted(self._specs):
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


def _evidence_reason(prefix: str, artifacts: list[dict[str, object]]) -> str:
    if not artifacts:
        return prefix
    return f"{prefix}: {json.dumps(artifacts, ensure_ascii=False, sort_keys=True)}"
