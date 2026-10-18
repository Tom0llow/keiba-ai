"""Preserve interrupted acquisition evidence before resetting staging."""

from __future__ import annotations

from pathlib import Path

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkToSQLiteError,
    JVLinkToSQLiteRunner,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.progress.ledger import ProgressLedger
from jra_van_retriever.progress.state import (
    WeeklyBatchResult as WeeklyBatchResult,
)


class HistoricalOddsRecovery:
    """Own runner-state inspection and staging evidence lifecycle."""

    def __init__(
        self, runner: JVLinkToSQLiteRunner, archive: OddsArchive, runtime_dir: Path
    ) -> None:
        self._runner = runner
        self._archive = archive
        self._runtime_dir = runtime_dir

    def assert_runner_stopped(self) -> None:
        """Fail closed unless the runner can verify that no acquisition is active."""
        checker = getattr(self._runner, "assert_not_running", None)
        if checker is None:
            raise JVLinkToSQLiteError("recovery requires a runner process-state check")
        checker()

    def quarantine_and_reset(
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
