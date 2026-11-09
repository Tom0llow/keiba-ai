"""Assemble a chronological reference-feature datamart without performing physical I/O.

The caller reads the fixed snapshot one calendar year at a time and supplies each
target date's market rows through a callback. Every history race is normalized
once, every target is normalized and calculated once in ``(freeze_at, race_id)``
order, and only the projected rows of the current year are kept.
"""

from __future__ import annotations

from bisect import insort
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import groupby
from math import isfinite, isnan
from typing import cast

from make_features.catalog.registry import FeatureRegistry
from make_features.contracts.observations import (
    CalculatedValues,
    HistoricalRace,
    ObservationInput,
    PedigreeObservation,
    Workout,
)
from make_features.generation.calculate import (
    FeatureCalculationValueError,
    calculate_reference_context,
)
from make_features.generation.chronological import (
    ChronologicalHistory,
    ChronologicalInvariantError,
    HistoryView,
    WorkoutIndex,
    WorkoutView,
    shared_context,
)
from make_features.real_market import JST, canonical_hash, timestamp
from make_features.reference_raw import (
    CARD_RA_COLUMNS,
    CARD_SE_COLUMNS,
    identifier,
    positive_integer,
    race_identity,
    validate_reference_projections,
    workout,
)
from make_features.reference_rules import validate_reference_rules
from make_features.reference_snapshot import (
    ReferenceTargetSources,
    normalize_reference_history,
    normalize_reference_target,
    reference_label,
    reference_manifests,
    reference_parameters,
    reference_pedigree,
)
from make_features.serialization.observations import normalized_payload
from models.dataset.calculated import CalculationContract, NumericColumn, closed_numeric_columns
from models.serialization.reference import REFERENCE_LABEL_ASSURANCE, reference_assurance

type MarketRows = Callable[[date], tuple[Sequence[dict[str, object]], Sequence[dict[str, object]]]]
_AMBIGUOUS_PEDIGREE = "ambiguous_or_missing_race_row"


@dataclass(frozen=True)
class ReferenceYearOutput:
    """Hold one calendar year's projected horse rows, race rows and holds."""

    year: int
    rows: tuple[dict[str, object], ...]
    races: tuple[dict[str, object], ...]
    held: tuple[dict[str, object], ...]
    target_races: int


class ReferenceDatamartBuilder:
    """Advance one shared history index year by year and calculate targets once."""

    def __init__(
        self,
        *,
        settings: Mapping[str, object],
        rules: Mapping[str, object],
        registry: FeatureRegistry,
        target_start: date,
        target_end: date,
        snapshot: Mapping[str, object],
        pedigree_rows: Sequence[dict[str, object]],
    ) -> None:
        self.rules = validate_reference_rules(rules)
        self.parameters, self._start = reference_parameters(dict(settings), self.rules)
        history_start = self._start.date()
        if not history_start <= target_start <= target_end:
            raise ValueError("history_start <= target_start <= target_end is required")
        self.settings = dict(settings)
        self.registry = registry
        self.target_start = target_start
        self.target_end = target_end
        self.columns: tuple[NumericColumn, ...] = closed_numeric_columns(self.settings)
        self.contract = CalculationContract.reference(
            self.parameters, self.rules, [column.name for column in self.columns]
        )
        self.available_at_groups: tuple[str, ...] = tuple(registry.names)
        self._snapshot = dict(snapshot)
        self._history = ChronologicalHistory(self.parameters)
        self._workouts = WorkoutIndex(self.parameters)
        self._um: dict[str, list[dict[str, object]]] = {}
        for row in pedigree_rows:
            horse = identifier(row, "KettoNum")
            if horse is not None:
                self._um.setdefault(horse, []).append(row)
        self._pedigrees: dict[str, PedigreeObservation] = {}
        self._pedigree_errors: dict[str, str] = {}
        self._next_year = history_start.year

    @property
    def years(self) -> range:
        """Return every calendar year the caller must supply, history years first."""
        return range(self._start.year, self.target_end.year + 1)

    def target_years(self) -> range:
        """Return the calendar years that receive a partition."""
        return range(self.target_start.year, self.target_end.year + 1)

    def add_year(
        self,
        year: int,
        *,
        ra_rows: Sequence[dict[str, object]],
        se_rows: Sequence[dict[str, object]],
        workout_rows: Sequence[tuple[str, dict[str, object]]],
        markets: MarketRows,
    ) -> ReferenceYearOutput:
        """Index one year of history, then calculate that year's targets by date.

        ``ra_rows`` and ``se_rows`` hold the history projections of every race in the
        year that lies inside history_start..target_end. ``workout_rows`` holds
        ``(kind, row)`` pairs for the sessions the year's targets may use, hc before wc
        and each in physical source order.
        """
        if year != self._next_year:
            raise ValueError(f"years must be supplied in order; expected {self._next_year}")
        self._next_year += 1
        validate_reference_projections(
            {
                "history_ra": list(ra_rows),
                "history_se": list(se_rows),
                "target_ra": [],
                "target_se": [],
                "label_ra": [],
                "label_se": [],
            }
        )
        races, held = normalize_reference_history(ra_rows, se_rows, rules=self.rules)
        held_rows = [_with_stage(item, "history_result") for item in held]
        for row in se_rows:
            horse = identifier(row, "KettoNum")
            if horse is not None:
                self._ensure_pedigree(horse)
        self._history.append(races)
        if year < self.target_start.year:
            return ReferenceYearOutput(year, (), (), tuple(held_rows), 0)
        self._workouts.load(tuple(workout(row, kind=kind) for kind, row in workout_rows))
        targets = self._targets(ra_rows, se_rows, held_rows)
        rows: list[dict[str, object]] = []
        race_rows: list[dict[str, object]] = []
        for day, group in groupby(targets, key=lambda target: target[0]):
            day_targets = list(group)
            view = self._history.view(day, self._pedigrees)
            workout_view = self._workouts.view(day)
            o1_rows, o2_rows = markets(day)
            o1, o2 = _by_race(o1_rows), _by_race(o2_rows)
            row_hash = _RowHashes()
            for _, manifest, target_ra, target_se in day_targets:
                identity = cast(str, manifest["race_id"])
                outcome = self._target(
                    manifest,
                    target_ra,
                    target_se,
                    o1.get(identity, []),
                    o2.get(identity, []),
                    view,
                    workout_view,
                    row_hash,
                )
                if isinstance(outcome, dict):
                    held_rows.append(outcome)
                    continue
                target_rows, race = outcome
                rows.extend(target_rows)
                race_rows.append(race)
        return ReferenceYearOutput(
            year, tuple(rows), tuple(race_rows), tuple(held_rows), len(targets)
        )

    def manifest(
        self,
        *,
        snapshot: Mapping[str, object],
        provenance: Mapping[str, object],
        preparation_config: Mapping[str, object],
    ) -> dict[str, object]:
        """Return the semantic manifest; the writer adds held-race and partition entries."""
        if self._next_year != self.target_end.year + 1:
            raise ValueError("every history and target year must be supplied before the manifest")
        if snapshot.get("tables") != self._snapshot.get("tables"):
            raise ValueError("snapshot table identities changed during the build")
        return {
            "format": "reference_feature_datamart",
            "format_version": 1,
            "implementation": "snapshot_reference_21_groups_v1",
            "verification": "build_time_audit_no_read_recomputation_v1",
            "contract": self.contract.as_metadata(),
            "columns": [
                {
                    "name": column.name,
                    "group": column.group,
                    "column": column.column,
                    "meaning": column.meaning,
                    "unit": column.unit,
                }
                for column in self.columns
            ],
            "available_at_groups": list(self.available_at_groups),
            "feature_definitions": normalized_payload(self.registry.definitions),
            "target_period": {
                "start": self.target_start.isoformat(),
                "end": self.target_end.isoformat(),
            },
            "snapshot": dict(snapshot),
            "assurance": reference_assurance(self.rules),
            "label": {
                "kind": "reference_result_v1",
                "assurance": REFERENCE_LABEL_ASSURANCE,
                "label_boundary_meaning": "declared_usable_after",
                "result_delay_days": self.rules["result_delay_days"],
            },
            "provenance": dict(provenance),
            "preparation_config": dict(preparation_config),
        }

    def _ensure_pedigree(self, horse: str) -> None:
        if horse in self._pedigrees or horse in self._pedigree_errors:
            return
        try:
            pedigree = reference_pedigree(horse, self._um.get(horse, []), start=self._start)
        except ValueError as exc:
            self._pedigree_errors[horse] = str(exc)
            return
        self._history.register(pedigree.evidence)
        self._pedigrees[horse] = pedigree

    def _targets(
        self,
        ra_rows: Sequence[dict[str, object]],
        se_rows: Sequence[dict[str, object]],
        held: list[dict[str, object]],
    ) -> list[tuple[date, dict[str, object], list[dict[str, object]], list[dict[str, object]]]]:
        first = self.target_start.strftime("%Y%m%d")
        last = self.target_end.strftime("%Y%m%d")
        ra_by_race: dict[str, list[dict[str, object]]] = {}
        for row in ra_rows:
            identity = race_identity(row)
            if first <= identity[:8] <= last:
                ra_by_race.setdefault(identity, []).append(row)
        se_by_race: dict[str, list[dict[str, object]]] = {}
        for row in se_rows:
            identity = race_identity(row)
            if identity in ra_by_race:
                se_by_race.setdefault(identity, []).append(row)
        targets = []
        offset = cast(int, self.rules["freeze_offset_seconds"])
        for identity, candidates in sorted(ra_by_race.items()):
            try:
                (manifest,) = reference_manifests(candidates, freeze_offset_seconds=offset)
            except ValueError as exc:
                held.append(_hold(identity, "target_pre_freeze", str(exc)))
                continue
            day = datetime.strptime(identity[:8], "%Y%m%d").date()
            if timestamp(manifest["freeze_at"]).astimezone(JST).date() != day:
                held.append(
                    _hold(identity, "target_pre_freeze", "freeze falls on a different JST date")
                )
                continue
            targets.append((day, manifest, candidates, se_by_race.get(identity, [])))
        return sorted(
            targets,
            key=lambda target: (target[0], timestamp(target[1]["freeze_at"]), target[1]["race_id"]),
        )

    def _target(
        self,
        manifest: dict[str, object],
        target_ra: Sequence[dict[str, object]],
        target_se: Sequence[dict[str, object]],
        o1: Sequence[dict[str, object]],
        o2: Sequence[dict[str, object]],
        view: HistoryView,
        workout_view: WorkoutView,
        row_hash: Callable[[dict[str, object]], str],
    ) -> dict[str, object] | tuple[list[dict[str, object]], dict[str, object]]:
        identity = cast(str, manifest["race_id"])
        populations: list[tuple[str, ...]] = []

        def history_for(scheduled: datetime, freeze: datetime) -> tuple[HistoricalRace, ...]:
            # Shared views expose the exact prefix the per-race filter selects.
            if scheduled.astimezone(JST).date() != view.day:
                raise ChronologicalInvariantError("target date differs from its chronological view")
            return view.races

        def population_for(
            available: tuple[HistoricalRace, ...], card: Sequence[str]
        ) -> tuple[str, ...]:
            merged = list(view.history_horses_sorted())
            known = set(merged) if len(card) else set()
            for horse in card:
                if horse not in known:
                    insort(merged, horse)
                    known.add(horse)
            population = tuple(merged)
            populations.append(population)
            return population

        def pedigrees_for(population: tuple[str, ...]) -> tuple[PedigreeObservation, ...]:
            # The per-race path fails on the first ambiguous master row of its population;
            # shared contexts then read pedigrees from the build-wide mapping instead.
            if any(horse in self._pedigree_errors for horse in card_horses) or (
                view.history_contains_any(self._pedigree_errors)
            ):
                raise ValueError(_AMBIGUOUS_PEDIGREE)
            return ()

        def sessions_for(scheduled: datetime, freeze: datetime) -> tuple[Workout, ...]:
            # Shared contexts select each target's freeze window from the date view.
            return ()

        card_horses = [
            horse for row in target_se if (horse := identifier(row, "KettoNum")) is not None
        ]
        for horse in card_horses:
            self._ensure_pedigree(horse)
        sources = ReferenceTargetSources(
            [{k: row.get(k) for k in CARD_RA_COLUMNS} for row in target_ra],
            [{k: row.get(k) for k in CARD_SE_COLUMNS} for row in target_se],
            o1,
            o2,
            target_ra,
            target_se,
            history_for,
            population_for,
            pedigrees_for,
            sessions_for,
            row_hash,
        )
        try:
            observation, _ = normalize_reference_target(
                manifest,
                sources,
                rules=self.rules,
                parameters=self.parameters,
                start=self._start,
                snapshot=self._snapshot,
                include_labels=False,
            )
        except ChronologicalInvariantError:
            raise
        except ValueError as exc:
            return _hold(identity, "target_pre_freeze", str(exc))
        try:
            context = shared_context(
                observation, view=view, workouts=workout_view, population=populations[-1]
            )
        except ChronologicalInvariantError:
            raise
        except ValueError as exc:
            # Per-target selections, such as two market anchors resolving to one
            # publication, hold the race; history and evidence invariants stay fatal.
            return _hold(identity, "target_pre_freeze", str(exc))
        # Pre-freeze checks run first so they are never counted as outcome holds.
        mapping = {runner.horse_number: runner.horse_id for runner in observation.card.runners}
        try:
            label = reference_label(mapping, target_ra, target_se, rules=self.rules)
        except ChronologicalInvariantError:
            raise
        except ValueError as exc:
            return _hold(identity, "target_outcome", str(exc))
        try:
            calculated = calculate_reference_context(context, registry=self.registry)
        except FeatureCalculationValueError as exc:
            return _hold(identity, "calculation", f"{exc.feature_name}: {exc}")
        return self._project(observation, calculated.manifests, label, view)

    def _project(
        self,
        observation: ObservationInput,
        manifests: Sequence[Mapping[str, CalculatedValues]],
        label: Mapping[str, object],
        view: HistoryView,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        card = observation.card
        if len(manifests) != len(card.runners):
            raise ValueError("calculation output does not cover the complete target field")
        raw = cast(Mapping[str, object], label["raw"])
        finishes = {
            cast(str, identifier(row, "KettoNum")): cast(int, positive_integer(row, "KakuteiJyuni"))
            for row in cast(Sequence[dict[str, object]], raw["se"])
        }
        if set(finishes) != set(card.expected_horse_ids):
            raise ValueError("label does not cover the complete frozen target field")
        ids = {
            name: self.registry.by_name(name).definition.feature_id
            for name in self.available_at_groups
        }
        rows: list[dict[str, object]] = []
        for runner, manifest in zip(card.runners, manifests, strict=True):
            row: dict[str, object] = {
                "race_id": card.race_id,
                "horse_id": runner.horse_id,
                "scheduled_start_at": card.scheduled_start_at,
                "freeze_at": observation.freeze_at,
            }
            for column in self.columns:
                group = manifest[ids[column.group]]
                if column.column not in group.values:
                    raise ValueError(f"closed numeric calculation column is missing: {column.name}")
                row[column.name] = _number(group.values[column.column], column.name)
            for name in self.available_at_groups:
                group = manifest[ids[name]]
                available = max(evidence.available_at for evidence in group.dependencies)
                if available > observation.freeze_at:
                    raise ValueError("calculated group is available only after freeze_at")
                row[f"{name}__available_at"] = available
            row["finish_position"] = finishes[runner.horse_id]
            rows.append(row)
        mapping = {runner.horse_number: runner.horse_id for runner in card.runners}
        race = {
            "race_id": card.race_id,
            "scheduled_start_at": card.scheduled_start_at,
            "freeze_at": observation.freeze_at,
            "field_size": len(card.runners),
            "label_usable_after": timestamp(label["usable_after"]),
            "result_delay_days": label["result_delay_days"],
            "label_raw_sha256": label["raw_sha256"],
            "horse_mapping_sha256": canonical_hash(mapping),
            "history_usable_through": view.usable_through,
        }
        return rows, race


class _RowHashes:
    """Hash each market row of one date once; rows stay alive for that date."""

    def __init__(self) -> None:
        self._hashes: dict[int, tuple[dict[str, object], str]] = {}

    def __call__(self, row: dict[str, object]) -> str:
        cached = self._hashes.get(id(row))
        if cached is not None and cached[0] is row:
            return cached[1]
        digest = canonical_hash(row)
        self._hashes[id(row)] = (row, digest)
        return digest


def _number(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or type(value) not in (int, float):
        raise ValueError(f"reference datamart numeric column requires a number or null: {name}")
    number = float(cast(float, value))
    if isnan(number):
        return None
    if not isfinite(number):
        raise ValueError(f"reference datamart rejects an infinite value: {name}")
    return number


def _by_race(rows: Sequence[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        result.setdefault(race_identity(row), []).append(row)
    return result


def _hold(race_id: str, stage: str, reason: str) -> dict[str, object]:
    return {
        "race_id": race_id,
        "role": "target",
        "stage": stage,
        "reason": reason,
        "whole_race": True,
    }


def _with_stage(item: Mapping[str, object], stage: str) -> dict[str, object]:
    return {
        "race_id": item["race_id"],
        "role": item["role"],
        "stage": stage,
        "reason": item["reason"],
        "whole_race": True,
    }


def workout_window(
    target_year: int, *, target_start: date, target_end: date, days_window: int
) -> tuple[date, date] | None:
    """Return the inclusive session-date range one target year can read, if any."""
    first = max(date(target_year, 1, 1), target_start)
    last = min(date(target_year, 12, 31), target_end)
    if first > last:
        return None
    return first - timedelta(days=days_window + 1), last - timedelta(days=1)
