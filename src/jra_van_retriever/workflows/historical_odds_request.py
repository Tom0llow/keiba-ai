"""Execute and classify one durable historical odds acquisition request."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
    JVLinkToSQLiteRunner,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive, RequestedArchiveResult
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkProfile
from jra_van_retriever.progress.ledger import ProgressLedger
from jra_van_retriever.progress.state import (
    WeeklyBatchResult as WeeklyBatchResult,
)
from jra_van_retriever.workflows.historical_odds_recovery import HistoricalOddsRecovery


@dataclass(frozen=True)
class _RequestOutcome:
    results: dict[str, tuple[str, str, int]]
    returncode: int | None
    api_results: dict[str, tuple[str, int]]
    inserted_rows: dict[str, int] = field(default_factory=dict)

    @property
    def failed_specs(self) -> frozenset[str]:
        return frozenset(spec for spec, (state, _, _) in self.results.items() if state == "failed")


def _classify_request(
    execution: JVLinkExecutionResult | None,
    archived: dict[str, RequestedArchiveResult],
) -> _RequestOutcome:
    """Classify saved rows without inferring provider gaps from empty staging."""
    api_results: dict[str, tuple[str, int]] = getattr(execution, "api_results", {})
    no_data_specs: frozenset[str] = getattr(execution, "no_data_specs", frozenset())
    fatal_specs: frozenset[str] = getattr(execution, "fatal_specs", frozenset())
    results: dict[str, tuple[str, str, int]] = {}
    inserted_rows: dict[str, int] = {}
    for spec, value in archived.items():
        if spec in fatal_specs:
            results[spec] = ("failed", "jvlink_error", value.after_rows)
        elif value.acquired:
            results[spec] = ("acquired", value.reason, value.after_rows)
            inserted_rows[spec] = value.inserted_rows
        elif value.reason == "jvopen_no_data" and spec in no_data_specs:
            results[spec] = ("provider_missing", value.reason, 0)
        elif value.reason == "jvopen_no_data":
            results[spec] = ("failed", "empty_response_unverified", 0)
        else:
            results[spec] = ("failed", value.reason, value.after_rows)
    return _RequestOutcome(
        results,
        getattr(execution, "process_returncode", None),
        {spec: api_results[spec] for spec in archived if spec in api_results},
        inserted_rows,
    )


class HistoricalOddsRequestExecutor:
    """Own subprocess execution and requested archive/ledger transitions."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        profile: JVLinkProfile,
        recovery: HistoricalOddsRecovery,
    ) -> None:
        self._runner = runner
        self._setting_builder = setting_builder
        self._archive = archive
        self._odds_profile = profile
        self._recovery = recovery

    def run(
        self,
        ledger: ProgressLedger,
        run_id: str,
        key: RaceKey,
        specs: frozenset[str],
        counts: dict[str, int],
        now: datetime,
        setting_path: Path,
    ) -> _RequestOutcome:
        """Commit request intent before staging changes and its outcome afterward."""
        ledger.request(run_id, key, specs, counts, now)
        self._recovery.quarantine_and_reset(ledger, run_id, key, specs)
        profile = replace(self._odds_profile, realtime_data_specs=specs)
        self._setting_builder.build(profile, setting_path, race_key=key)
        outcome = self._execute_request(key, specs, counts, setting_path)
        failed = outcome.failed_specs
        if failed:
            self._recovery.quarantine_and_reset(
                ledger, run_id, key, failed, label=f"{run_id}-{key.race_id}"
            )
        successful = specs - failed
        if successful:
            self._archive.reset_staging(successful)
        ledger.finish_request(
            key,
            outcome.results,
            now,
            recovered=True,
            returncode=outcome.returncode,
            api_results=outcome.api_results,
        )
        return outcome

    def _execute_request(
        self,
        key: RaceKey,
        specs: frozenset[str],
        counts: dict[str, int],
        setting_path: Path,
    ) -> _RequestOutcome:
        try:
            execution = self._runner.execute(setting_path, skip_last_modified_update=True)
            archived = self._archive.archive_request(key, specs)
            return _classify_request(execution, archived)
        except JVLinkToSQLiteError as exc:
            return _RequestOutcome(
                {spec: ("failed", "jvlink_error", counts[spec]) for spec in specs},
                exc.returncode,
                exc.api_results,
            )
