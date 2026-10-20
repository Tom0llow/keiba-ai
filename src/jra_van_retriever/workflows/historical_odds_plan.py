"""Plan year-scoped odds work from raw and committed ledger observations."""

from __future__ import annotations

from datetime import date

from domain.race_key import RaceKey
from jra_van_retriever.progress.ledger import ProgressLedger
from jra_van_retriever.progress.state import (
    RawSnapshot,
    SpecState,
    reconcile_states,
)
from jra_van_retriever.progress.state import (
    WeeklyBatchResult as WeeklyBatchResult,
)


def plan_snapshot(
    snapshot: RawSnapshot,
    cutoff: date,
    data_specs: frozenset[str],
    ledger: ProgressLedger | None,
    *,
    raw_only: bool = False,
) -> WeeklyBatchResult:
    """Observe committed progress and return a read-only year-scoped plan."""
    if ledger is not None:
        states, publications, _ = ledger.read()
        states, _, adopted_races = reconcile_states(states, snapshot, data_specs)
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
            for spec in data_specs
        }
        adopted_races = dict.fromkeys(sorted(data_specs), 0)
        publications = None
    year = select_year(
        data_specs,
        states,
        snapshot.races,
        cutoff,
        None if raw_only else publications,
    )
    races = races_for_year(data_specs, states, snapshot.races, year) if year is not None else ()
    specs = sum(
        1
        for key in races
        for spec in data_specs
        if states[(key.race_id, spec)].state in {"pending", "failed"}
    )
    return WeeklyBatchResult("plan", year, None, len(races), specs, 0, specs, adopted_races, True)


def select_year(
    data_specs: frozenset[str],
    states: dict[tuple[str, str], SpecState],
    races: tuple[RaceKey, ...],
    cutoff: date,
    publications: dict[int, str] | None = None,
) -> int | None:
    """Select the oldest incomplete eligible acquisition or publication year."""
    candidate_years = {key.race_date.year for key in races if key.race_date <= cutoff}
    years = {
        key.race_date.year
        for key in races
        if key.race_date <= cutoff
        and any(
            states.get((key.race_id, spec), SpecState("", "", "pending", "", 0, 0)).state
            not in {"acquired", "provider_missing"}
            for spec in data_specs
        )
    }
    if publications is not None:
        years.update(
            year
            for year, publication in publications.items()
            if publication in {"pending", "failed"} and year in candidate_years
        )
    return min(years) if years else None


def races_for_year(
    data_specs: frozenset[str],
    states: dict[tuple[str, str], SpecState],
    races: tuple[RaceKey, ...],
    year: int | None,
) -> tuple[RaceKey, ...]:
    """Return pending race keys in their existing observation order."""
    if year is None:
        return ()
    return tuple(
        key
        for key in races
        if key.race_date.year == year
        and any(states[(key.race_id, spec)].state in {"pending", "failed"} for spec in data_specs)
    )
