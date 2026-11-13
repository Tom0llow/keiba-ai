"""Assemble a chronological reference-feature datamart without performing physical I/O.

The caller reads the fixed snapshot one calendar year at a time and supplies each
target date's market rows through a callback. Every history race is normalized
once, every target is normalized and calculated once in ``(freeze_at, race_id)``
order, and only the projected rows of the current year are kept.

With ``labeled=False`` (ADR-036) the same calculation runs for races that have no
result yet: rows on or after ``target_start`` never enter the history, targets see
only their pre-race card projections, and no label or finishing position is read.
``prepare_targets`` (ADR-037) stops before the market so that each race can be
calculated later, once its post-freeze market has been fetched.
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
from make_features.real_market import JST, canonical_hash, publication, timestamp
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
    card_entrants,
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
MARKET_NOT_OBSERVED_AFTER_FREEZE = "market_not_observed_after_freeze"
# Recent history holds are reported for this many days before the result-delay boundary.
_RECENT_HISTORY_DAYS = 7


@dataclass(frozen=True)
class TargetSchedule:
    """Identify one prepared target race and the clocks its market must follow."""

    race_id: str
    scheduled_start_at: datetime
    freeze_at: datetime


@dataclass(frozen=True)
class TargetResult:
    """Hold one target's projected rows and race row, or its single hold."""

    race_id: str
    rows: tuple[dict[str, object], ...]
    race: dict[str, object] | None
    hold: dict[str, object] | None


class PreparedTargets:
    """Calculate the prepared targets of one label-free date, one race at a time.

    Each race is calculated at most once, in any order and for any subset: a target
    reads only the shared date view, its own card, and its own market rows.
    """

    def __init__(
        self,
        builder: ReferenceDatamartBuilder,
        targets: Sequence[
            tuple[date, dict[str, object], list[dict[str, object]], list[dict[str, object]]]
        ],
        held: Sequence[dict[str, object]],
        views: tuple[HistoryView, WorkoutView] | None,
    ) -> None:
        self._builder = builder
        self._targets = {cast(str, target[1]["race_id"]): target for target in targets}
        self._views = views
        self._row_hash = _RowHashes()
        self._done: set[str] = set()
        self.held: tuple[dict[str, object], ...] = tuple(held)
        self.schedules: tuple[TargetSchedule, ...] = tuple(
            TargetSchedule(
                cast(str, manifest["race_id"]),
                timestamp(manifest["scheduled_start_at"]),
                timestamp(manifest["freeze_at"]),
            )
            for _, manifest, _, _ in targets
        )

    def calculate(
        self,
        race_id: str,
        o1_rows: Sequence[dict[str, object]],
        o2_rows: Sequence[dict[str, object]],
        *,
        observed_through: datetime | None,
    ) -> TargetResult:
        """Calculate one prepared race from its own market rows.

        ``observed_through=None`` requires an O1 publication after freeze (a pinned
        snapshot). A clock states when a fetch of the complete time series started;
        it must not precede freeze, or the race is held as not observed.
        """
        target = self._targets.get(race_id)
        if target is None:
            raise ValueError(f"race is not a prepared target: {race_id}")
        if race_id in self._done:
            raise ValueError(f"prepared target was already calculated: {race_id}")
        if observed_through is not None and observed_through.tzinfo is None:
            raise ValueError("observed_through must be timezone-aware")
        for row in (*o1_rows, *o2_rows):
            if race_identity(row) != race_id:
                raise ValueError(f"market row belongs to another race than {race_id}")
        assert self._views is not None  # targets exist only with their date views
        self._done.add(race_id)
        _, manifest, target_ra, target_se = target
        view, workout_view = self._views
        outcome = self._builder._target(
            manifest,
            target_ra,
            target_se,
            o1_rows,
            o2_rows,
            view,
            workout_view,
            self._row_hash,
            observed_through=observed_through,
        )
        if isinstance(outcome, dict):
            return TargetResult(race_id, (), None, outcome)
        rows, race = outcome
        return TargetResult(race_id, tuple(rows), race, None)


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
        labeled: bool = True,
    ) -> None:
        self.labeled = labeled
        self.rules = validate_reference_rules(rules)
        self.parameters, self._start = reference_parameters(dict(settings), self.rules)
        history_start = self._start.date()
        if not history_start <= target_start <= target_end:
            raise ValueError("history_start <= target_start <= target_end is required")
        if not labeled and target_start != target_end:
            # Earlier target dates' results are history for later ones; without labels the
            # target dates' rows never enter the history, so only one date is equivalent.
            raise ValueError("a builder without labels covers exactly one target date")
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
        self._first_target = target_start.strftime("%Y%m%d")
        self._latest_workouts: dict[str, date | None] = {"hc": None, "wc": None}
        self._card_horses: set[str] = set()
        self._recent_history_holds = 0

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
        held_rows = self._index_year(year, ra_rows, se_rows)
        if year < self.target_start.year:
            return ReferenceYearOutput(year, (), (), tuple(held_rows), 0)
        if not self.labeled:
            return self._label_free_year(
                year, self._prepare(ra_rows, se_rows, workout_rows, held_rows), markets
            )
        targets = self._prepare_inputs(ra_rows, se_rows, workout_rows, held_rows)
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
                    observed_through=None,
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

    def prepare_targets(
        self,
        year: int,
        *,
        ra_rows: Sequence[dict[str, object]],
        se_rows: Sequence[dict[str, object]],
        workout_rows: Sequence[tuple[str, dict[str, object]]],
    ) -> PreparedTargets:
        """Index the target year without reading markets; calculate races later (ADR-037).

        Only a builder without labels prepares targets, and only for its target year,
        after every history year has been supplied through ``add_year``.
        """
        if self.labeled:
            raise ValueError("only a builder without labels prepares targets")
        if year != self.target_end.year:
            raise ValueError(
                f"targets are prepared only for the target year {self.target_end.year}"
            )
        held_rows = self._index_year(year, ra_rows, se_rows)
        return self._prepare(ra_rows, se_rows, workout_rows, held_rows)

    def _label_free_year(
        self, year: int, prepared: PreparedTargets, markets: MarketRows
    ) -> ReferenceYearOutput:
        """Calculate every prepared target from one pinned date of markets, in order."""
        held_rows = list(prepared.held)
        rows: list[dict[str, object]] = []
        race_rows: list[dict[str, object]] = []
        if prepared.schedules:
            o1_rows, o2_rows = markets(self.target_start)
            o1, o2 = _by_race(o1_rows), _by_race(o2_rows)
            for schedule in prepared.schedules:
                result = prepared.calculate(
                    schedule.race_id,
                    o1.get(schedule.race_id, []),
                    o2.get(schedule.race_id, []),
                    observed_through=None,
                )
                if result.hold is not None:
                    held_rows.append(result.hold)
                    continue
                assert result.race is not None
                rows.extend(result.rows)
                race_rows.append(result.race)
        return ReferenceYearOutput(
            year, tuple(rows), tuple(race_rows), tuple(held_rows), len(prepared.schedules)
        )

    def _prepare(
        self,
        ra_rows: Sequence[dict[str, object]],
        se_rows: Sequence[dict[str, object]],
        workout_rows: Sequence[tuple[str, dict[str, object]]],
        held_rows: list[dict[str, object]],
    ) -> PreparedTargets:
        targets = self._prepare_inputs(ra_rows, se_rows, workout_rows, held_rows)
        # Register every card pedigree before the date view exists, so that the view's
        # cached pedigree clocks never depend on which race is calculated first.
        for _, _, _, target_se in targets:
            for row in target_se:
                horse = identifier(row, "KettoNum")
                if horse is not None:
                    self._ensure_pedigree(horse)
        views = (
            (
                self._history.view(self.target_start, self._pedigrees),
                self._workouts.view(self.target_start),
            )
            if targets
            else None
        )
        return PreparedTargets(self, targets, held_rows, views)

    def _prepare_inputs(
        self,
        ra_rows: Sequence[dict[str, object]],
        se_rows: Sequence[dict[str, object]],
        workout_rows: Sequence[tuple[str, dict[str, object]]],
        held_rows: list[dict[str, object]],
    ) -> list[tuple[date, dict[str, object], list[dict[str, object]], list[dict[str, object]]]]:
        """Load the target year's workouts and return its targets in calculation order."""
        sessions = tuple(workout(row, kind=kind) for kind, row in workout_rows)
        for (kind, _), session in zip(workout_rows, sessions, strict=True):
            day = session.evidence.event_at.astimezone(JST).date()
            latest = self._latest_workouts.get(kind)
            if day < self.target_start and (latest is None or day > latest):
                self._latest_workouts[kind] = day
        self._workouts.load(sessions)
        return self._targets(ra_rows, se_rows, held_rows)

    def _index_year(
        self,
        year: int,
        ra_rows: Sequence[dict[str, object]],
        se_rows: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Validate, normalize and index one year of history; return its history holds."""
        if year != self._next_year:
            raise ValueError(f"years must be supplied in order; expected {self._next_year}")
        self._next_year += 1
        # Without labels, rows on or after the first target date are never history: a
        # target date's own unfinished rows must not be held or fail the whole build.
        # Values are unchanged because a target date only sees the earlier prefix.
        history_ra = ra_rows if self.labeled else [r for r in ra_rows if self._before_targets(r)]
        history_se = se_rows if self.labeled else [r for r in se_rows if self._before_targets(r)]
        validate_reference_projections(
            {
                "history_ra": list(history_ra),
                "history_se": list(history_se),
                "target_ra": [],
                "target_se": [],
                "label_ra": [],
                "label_se": [],
            }
        )
        races, held = normalize_reference_history(history_ra, history_se, rules=self.rules)
        held_rows = [_with_stage(item, "history_result") for item in held]
        self._recent_history_holds += sum(1 for item in held if self._recent(item))
        for row in history_se:
            horse = identifier(row, "KettoNum")
            if horse is not None:
                self._ensure_pedigree(horse)
        self._history.append(races)
        return held_rows

    def manifest(
        self,
        *,
        snapshot: Mapping[str, object],
        provenance: Mapping[str, object],
        preparation_config: Mapping[str, object],
    ) -> dict[str, object]:
        """Return the semantic manifest; the writer adds held-race and partition entries."""
        if not self.labeled:
            raise ValueError("a builder without labels writes prediction_manifest instead")
        self._check_complete(snapshot)
        return {
            "format": "reference_feature_datamart",
            "format_version": 1,
            **self._common_manifest(snapshot),
            "label": {
                "kind": "reference_result_v1",
                "assurance": REFERENCE_LABEL_ASSURANCE,
                "label_boundary_meaning": "declared_usable_after",
                "result_delay_days": self.rules["result_delay_days"],
            },
            "provenance": dict(provenance),
            "preparation_config": dict(preparation_config),
        }

    def prediction_manifest(
        self,
        *,
        snapshot: Mapping[str, object],
        provenance: Mapping[str, object],
        preparation_config: Mapping[str, object],
        source_datamart: Mapping[str, object],
        market_source: Mapping[str, object],
    ) -> dict[str, object]:
        """Return the label-free manifest bound to the training datamart (ADR-036).

        ``market_source`` records where the target's market came from (ADR-037).
        """
        if self.labeled:
            raise ValueError("a labeled builder writes manifest instead of prediction_manifest")
        self._check_complete(snapshot)
        return {
            "format": "reference_prediction_features",
            "format_version": 2,
            **self._common_manifest(snapshot),
            "source_datamart": dict(source_datamart),
            "market_source": dict(market_source),
            "freshness": self.freshness(),
            "provenance": dict(provenance),
            "preparation_config": dict(preparation_config),
        }

    def freshness(self) -> dict[str, object]:
        """Return how current the target date's workouts, pedigrees and history are."""
        missing = sorted(horse for horse in self._card_horses if not self._um.get(horse))
        return {
            "latest_workout_date": {
                kind: None if day is None else day.isoformat()
                for kind, day in sorted(self._latest_workouts.items())
            },
            "card_horses": len(self._card_horses),
            "card_horses_without_pedigree_row": len(missing),
            "history_held_recent": self._recent_history_holds,
            "history_held_recent_window_days": _RECENT_HISTORY_DAYS,
        }

    def _check_complete(self, snapshot: Mapping[str, object]) -> None:
        if self._next_year != self.target_end.year + 1:
            raise ValueError("every history and target year must be supplied before the manifest")
        if snapshot.get("tables") != self._snapshot.get("tables"):
            raise ValueError("snapshot table identities changed during the build")

    def _common_manifest(self, snapshot: Mapping[str, object]) -> dict[str, object]:
        return {
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
        }

    def _before_targets(self, row: Mapping[str, object]) -> bool:
        return f"{row.get('idYear')}{row.get('idMonthDay')}" < self._first_target

    def _recent(self, item: Mapping[str, object]) -> bool:
        """Return whether a history hold lies just before the result-delay boundary."""
        try:
            started = datetime.strptime(cast(str, item["race_id"])[:8], "%Y%m%d").date()
        except ValueError:
            return False
        boundary = self.target_start - timedelta(days=cast(int, self.rules["result_delay_days"]))
        return boundary - timedelta(days=_RECENT_HISTORY_DAYS) <= started < self.target_start

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
        ra_by_race, se_by_race = target_rows(
            ra_rows, se_rows, first=self.target_start, last=self.target_end, labeled=self.labeled
        )
        for entrants in se_by_race.values():
            for row in entrants:
                horse = identifier(row, "KettoNum")
                if horse is not None:
                    self._card_horses.add(horse)
        targets = []
        offset = cast(int, self.rules["freeze_offset_seconds"])
        for identity, candidates in sorted(ra_by_race.items()):
            try:
                manifest = target_manifest(candidates, freeze_offset_seconds=offset)
            except ValueError as exc:
                held.append(_hold(identity, "target_pre_freeze", str(exc)))
                continue
            day = datetime.strptime(identity[:8], "%Y%m%d").date()
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
        *,
        observed_through: datetime | None,
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
        if not self.labeled and not _market_complete(
            o1, timestamp(manifest["freeze_at"]), observed_through
        ):
            return _hold(identity, "target_pre_freeze", MARKET_NOT_OBSERVED_AFTER_FREEZE)
        sources = ReferenceTargetSources(
            [{k: row.get(k) for k in CARD_RA_COLUMNS} for row in target_ra],
            [{k: row.get(k) for k in CARD_SE_COLUMNS} for row in target_se],
            o1,
            o2,
            target_ra if self.labeled else (),
            target_se if self.labeled else (),
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
        label: dict[str, object] | None = None
        if self.labeled:
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
        label: Mapping[str, object] | None,
        view: HistoryView,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        card = observation.card
        if len(manifests) != len(card.runners):
            raise ValueError("calculation output does not cover the complete target field")
        finishes: dict[str, int] | None = None
        if label is not None:
            raw = cast(Mapping[str, object], label["raw"])
            finishes = {
                cast(str, identifier(row, "KettoNum")): cast(
                    int, positive_integer(row, "KakuteiJyuni")
                )
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
            if finishes is not None:
                row["finish_position"] = finishes[runner.horse_id]
            rows.append(row)
        mapping = {runner.horse_number: runner.horse_id for runner in card.runners}
        race: dict[str, object] = {
            "race_id": card.race_id,
            "scheduled_start_at": card.scheduled_start_at,
            "freeze_at": observation.freeze_at,
            "field_size": len(card.runners),
        }
        if label is not None:
            race.update(
                label_usable_after=timestamp(label["usable_after"]),
                result_delay_days=label["result_delay_days"],
                label_raw_sha256=label["raw_sha256"],
            )
        race.update(
            horse_mapping_sha256=canonical_hash(mapping),
            history_usable_through=view.usable_through,
        )
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


def _market_complete(
    o1: Sequence[dict[str, object]], freeze: datetime, observed_through: datetime | None
) -> bool:
    """Return whether the market rows hold every publication up to freeze.

    A pinned snapshot has no creation clock, so a later O1 publication proves that its
    latest quote is not silently a pre-freeze value. A time series fetched after
    freeze holds every earlier publication; its start clock is the evidence, because
    0B41 publishes only every five minutes near the start (ADR-037).
    """
    if observed_through is not None:
        return observed_through >= freeze
    return _observed_after(o1, freeze)


def _observed_after(o1: Sequence[dict[str, object]], freeze: datetime) -> bool:
    """Return whether any parsable O1 publication of the race lies after its freeze."""
    for row in o1:
        try:
            if publication(row) > freeze:
                return True
        except ValueError:
            continue
    return False


def _by_race(rows: Sequence[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        result.setdefault(race_identity(row), []).append(row)
    return result


def target_rows(
    ra_rows: Sequence[dict[str, object]],
    se_rows: Sequence[dict[str, object]],
    *,
    first: date,
    last: date,
    labeled: bool,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    """Group the target period's race and runner rows by race ID, in input order.

    Runner rows are kept only for races that have a race row. Without labels each row
    is projected to its pre-race card columns, so result columns cannot reach
    de-duplication, normalization or any calculator.
    """
    start, end = first.strftime("%Y%m%d"), last.strftime("%Y%m%d")
    ra_by_race: dict[str, list[dict[str, object]]] = {}
    for row in ra_rows:
        identity = race_identity(row)
        if start <= identity[:8] <= end:
            ra_by_race.setdefault(identity, []).append(
                row if labeled else {k: row.get(k) for k in CARD_RA_COLUMNS}
            )
    se_by_race: dict[str, list[dict[str, object]]] = {}
    for row in se_rows:
        identity = race_identity(row)
        if identity in ra_by_race:
            se_by_race.setdefault(identity, []).append(
                row if labeled else {k: row.get(k) for k in CARD_SE_COLUMNS}
            )
    return ra_by_race, se_by_race


def target_manifest(
    candidates: Sequence[dict[str, object]], *, freeze_offset_seconds: int
) -> dict[str, object]:
    """Return one target race's stored schedule from its race rows.

    Identical rows count once. Differing rows, an invalid ``HassoTime`` or a freeze on
    another JST date than the date in the race ID raise ``ValueError``, which holds the
    race before freeze.
    """
    (manifest,) = reference_manifests(candidates, freeze_offset_seconds=freeze_offset_seconds)
    day = datetime.strptime(cast(str, manifest["race_id"])[:8], "%Y%m%d").date()
    if timestamp(manifest["freeze_at"]).astimezone(JST).date() != day:
        raise ValueError("freeze falls on a different JST date")
    return manifest


@dataclass(frozen=True)
class TargetCard:
    """One label-free target's stored schedule and horse-number mapping (ADR-039)."""

    race_id: str
    scheduled_start_at: datetime
    freeze_at: datetime
    horse_mapping: Mapping[str, str]


def label_free_target_cards(
    ra_rows: Sequence[dict[str, object]],
    se_rows: Sequence[dict[str, object]],
    *,
    day: date,
    freeze_offset_seconds: int,
) -> tuple[tuple[TargetCard, ...], tuple[dict[str, object], ...]]:
    """Return one date's target schedules and mappings, or their card holds.

    This applies the feature build's own card normalization (``target_rows``,
    ``target_manifest`` and ``card_entrants``) to the stored race and runner rows, so a
    mapping's ``canonical_hash`` equals the published ``horse_mapping_sha256``. Holds use
    the build's ``target_pre_freeze`` stage and reasons. Holds that need markets,
    history or the calculation are not reproduced. Cards are ordered by race ID.
    """
    ra_by_race, se_by_race = target_rows(ra_rows, se_rows, first=day, last=day, labeled=False)
    cards: list[TargetCard] = []
    held: list[dict[str, object]] = []
    for identity, candidates in sorted(ra_by_race.items()):
        try:
            manifest = target_manifest(candidates, freeze_offset_seconds=freeze_offset_seconds)
            _, _, mapping = card_entrants(se_by_race.get(identity, []))
        except ValueError as exc:
            held.append(_hold(identity, "target_pre_freeze", str(exc)))
            continue
        cards.append(
            TargetCard(
                identity,
                timestamp(manifest["scheduled_start_at"]),
                timestamp(manifest["freeze_at"]),
                mapping,
            )
        )
    return tuple(cards), tuple(held)


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
