"""Define acquisition values and calculate progress without persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from domain.race_key import RaceKey
from retriever.acquisition_lock import AcquisitionBlocked
from retriever.race_key_parser import race_key_from_row
from retriever.setting import HistoricalOddsBatch, JVLinkProfile


@dataclass(frozen=True)
class RawSnapshot:
    """Represent one consistent read-only snapshot of candidates and archive counts."""

    races: tuple[RaceKey, ...]
    counts: dict[tuple[str, str], int]
    schemas: dict[str, str]


@dataclass(frozen=True)
class SpecState:
    """Represent a ledger entry for one race and one odds DataSpec."""

    race_id: str
    data_spec: str
    state: str
    reason: str
    before_rows: int
    after_rows: int
    attempts: int = 0


def race_key_from_id(race_id: str) -> RaceKey:
    """Validate and restore the complete persisted race key."""
    if len(race_id) != 16 or not race_id.isdigit():
        raise AcquisitionBlocked("invalid race_id in progress ledger")
    return race_key_from_row(
        (race_id[:4], race_id[4:8], race_id[8:10], race_id[10:12], race_id[12:14], race_id[14:16])
    )


def policy_hash(profile: JVLinkProfile, batch: HistoricalOddsBatch) -> str:
    """Hash fixed policy without treating generated execution settings as policy."""
    payload = {
        "first_year": batch.first_year,
        "last_year": batch.last_year,
        "years_per_run": batch.years_per_run,
        "race_start_date": str(profile.race_start_date),
        "data_specs": sorted(profile.realtime_data_specs),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _legacy_policy_hash(
    profile: JVLinkProfile, batch: HistoricalOddsBatch, frontier: RaceKey
) -> str:
    """Recreate the removed frontier policy hash for a one-time ledger migration."""
    payload = {
        "first_year": batch.first_year,
        "last_year": batch.last_year,
        "years_per_run": batch.years_per_run,
        "frontier": str(frontier),
        "race_start_date": str(profile.race_start_date),
        "data_specs": sorted(profile.realtime_data_specs),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def reconcile_states(
    states: dict[tuple[str, str], SpecState], snapshot: RawSnapshot, specs: frozenset[str]
) -> tuple[dict[tuple[str, str], SpecState], set[int], dict[str, int]]:
    """Compute reconciliation without writes, including previews."""
    candidate_pairs = {(key.race_id, spec) for key in snapshot.races for spec in specs}
    if states.keys() - candidate_pairs:
        raise AcquisitionBlocked("previously managed race candidates disappeared")
    proposed = dict(states)
    changed_years: set[int] = set()
    adopted = dict.fromkeys(sorted(specs), 0)
    for key in snapshot.races:
        for spec in specs:
            pair = (key.race_id, spec)
            prior = states.get(pair)
            count = snapshot.counts.get(pair, 0)
            if (
                prior is not None
                and prior.state == "acquired"
                and (count == 0 or count < prior.after_rows)
            ):
                raise AcquisitionBlocked(f"acquired archive rows disappeared: {key}/{spec}")
            if count and (prior is None or prior.state != "acquired" or count > prior.after_rows):
                entry = SpecState(
                    key.race_id,
                    spec,
                    "acquired",
                    "external_archive_observed",
                    count,
                    count,
                    prior.attempts if prior else 0,
                )
                adopted[spec] += 1
            elif prior is None:
                entry = SpecState(key.race_id, spec, "pending", "new_candidate", 0, 0)
            else:
                entry = prior
            proposed[pair] = entry
            if entry != prior:
                changed_years.add(key.race_date.year)
    return proposed, changed_years, adopted


def candidate_hash(races: tuple[RaceKey, ...]) -> str:
    """Identify the exact sorted candidate set fixed for a run."""
    return hashlib.sha256("\n".join(key.race_id for key in races).encode()).hexdigest()


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
