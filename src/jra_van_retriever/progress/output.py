"""Regenerate historical-odds JSON and TOML reports from committed progress."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from jra_van_retriever.progress.state import WeeklyBatchResult

if TYPE_CHECKING:
    from jra_van_retriever.progress.ledger import ProgressLedger


def result_payload(result: WeeklyBatchResult) -> dict[str, object]:
    """Return the stable metrics persisted in run reports."""
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


def write_summary(
    result: WeeklyBatchResult,
    ledger: ProgressLedger,
    *,
    runtime_dir: Path,
    last_year: int,
    data_specs: frozenset[str],
    effective_year: int | None = None,
    phase: str | None = None,
    publication_state: str | None = None,
) -> None:
    """Regenerate derived artifacts from committed ledger state."""
    _, publications, state_revision = ledger.read()
    progress_path = runtime_dir / "historical-odds-progress.json"
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
            payload = result_payload(result) | {
                "ledger": str(ledger.path),
                "plan_only": result.plan_only,
                "state_revision": state_revision,
            }
    else:
        payload = result_payload(result) | {
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
        effective = runtime_dir / "historical-odds-effective.toml"
        year = effective_year or result.year or last_year
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
            f"data_specs = {json.dumps(sorted(data_specs))}\n",
        )
        if result.run_id is not None:
            atomic_write(
                runtime_dir / "historical-odds-runs" / f"{result.run_id}.json",
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            )


def atomic_write(path: Path, content: str) -> None:
    """Replace one derived artifact after its complete contents are durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
