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
from jra_van_retriever.acquisition.setting_xml import (
    JVLinkSettingBuilder,
    verify_realtime_race_key,
)
from jra_van_retriever.config.profiles import JVLinkProfile, RaceDayOddsProfile
from jra_van_retriever.config.validation import (
    validate_race_day_odds_profile,
    validate_race_day_prediction_profile,
)
from jra_van_retriever.progress.raw_observation import read_race_day_races
from jra_van_retriever.workflows.race_day_odds_plan import (
    CapturePlan,
    classify_capture,
    is_capture_late,
    plan_captures,
)

type RacePublisher = Callable[[RaceKey], object]

_CAPTURE_STATUSES = ("archived", "no_data", "failed", "skipped_late", "interrupted")


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
        prediction_profile: JVLinkProfile | None = None,
    ) -> None:
        validate_race_day_odds_profile(profile)
        if profile.prediction_offset_minutes is not None:
            if prediction_profile is None:
                raise ValueError("race-day prediction fetch requires the realtime-history profile")
            validate_race_day_prediction_profile(prediction_profile)
        self._prediction_profile = prediction_profile
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
        publisher: RacePublisher | None = None,
    ) -> RaceDayOddsRunResult:
        """Recover interrupted work, then execute every planned capture in order.

        ``publisher`` receives the race of every finished prediction fetch, whatever its
        status, while the acquisition lock is held; its failure never stops the day.
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
        # A restart (the recovery path) must not re-run or re-log finished captures.
        finished = self._archive.finished_capture_keys((f"{race_date:%Y}", f"{race_date:%m%d}"))
        plans = tuple(
            plan
            for plan in all_plans
            if (plan.race_key.race_id, str(plan.offset_minutes), plan.kind) not in finished
        )
        reports: list[CaptureReport] = []
        summary = dict.fromkeys(_CAPTURE_STATUSES, 0)
        summary["interrupted"] = interrupted
        with tempfile.TemporaryDirectory(prefix="keiba-ai-race-day-odds-") as temporary:
            settings = {
                "capture": Path(temporary) / "race-day-odds.xml",
                "prediction": Path(temporary) / "race-day-prediction.xml",
            }
            self._verify_setting(settings["capture"], all_plans[0].race_key, "capture")
            if self._profile.prediction_offset_minutes is not None:
                self._verify_setting(settings["prediction"], all_plans[0].race_key, "prediction")
            for plan in plans:
                self._wait_until(plan.planned_at)
                step = self._capture(plan, settings[plan.kind], publisher)
                reports.append(step.report)
                for result in step.report.results.values():
                    summary[result.status] += 1
                if reporter is not None:
                    reporter(step.report)
                if step.stop:
                    break
        return RaceDayOddsRunResult(tuple(reports), summary)

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
                return _CaptureStep(
                    CaptureReport(capture_id, plan.race_key, plan.offset_minutes, results)
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


def _evidence_reason(prefix: str, artifacts: list[dict[str, object]]) -> str:
    if not artifacts:
        return prefix
    return f"{prefix}: {json.dumps(artifacts, ensure_ascii=False, sort_keys=True)}"
