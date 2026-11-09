"""Share one validated chronological reference history across many target races.

The per-race reference path rebuilds and rescans the complete history for every
target. This module keeps one ascending history array instead. Reference result
boundaries are JST midnights, so the history visible to every target on one JST
date is a prefix of that array, and the as-of population of an earlier start is a
shorter prefix. Every view below is a prefix, a slice of a prefix, or an index
over a prefix, ordered exactly as the per-race contexts order the same starts.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import cast

from make_features.contracts.observations import (
    CalculatedValues,
    CalculationParameters,
    Conditions,
    Evidence,
    HistoricalRace,
    MarketObservation,
    ObservationInput,
    PedigreeObservation,
    ReferenceEvidence,
    Workout,
)
from make_features.contracts.types import FeatureScalar
from make_features.generation.observations import (
    JST,
    BaselineStatistics,
    CalculationContext,
    Start,
    WorkoutKey,
    baseline_statistics,
    workout_clock,
    workout_key,
)
from make_features.validation.observations import (
    aware,
    select_versions,
    validate_card,
    validate_evidence,
    validate_evidence_version,
    validate_parameters,
    validate_race,
    validate_sections,
)


class ChronologicalInvariantError(ValueError):
    """Report a leakage-sensitive history, workout or evidence invariant violation."""


def evidence_extrema(evidence: Sequence[Evidence]) -> tuple[Evidence, ...]:
    """Keep only evidence that attains the maximum available_at and event_at clocks."""
    if not evidence:
        return ()
    unique = {
        (item.source, item.observation_id, item.version, item.content_hash): item
        for item in evidence
    }
    values = tuple(unique.values())
    available = max(values, key=lambda item: item.available_at)
    event = max(values, key=lambda item: item.event_at)
    return tuple(
        sorted(
            {available, event}, key=lambda item: (item.source, item.observation_id, item.version)
        )
    )


class ChronologicalHistory:
    """Validate each history race once and expose day prefixes in start order."""

    def __init__(self, parameters: CalculationParameters) -> None:
        validate_parameters(parameters)
        self._parameters = parameters
        self._versions: dict[tuple[str, str, int], Evidence] = {}
        validate_evidence_version(parameters.evidence, self._versions)
        self._races: list[HistoricalRace] = []
        self._ids: set[str] = set()
        self._usable: list[datetime] = []
        self._max_available: list[Evidence] = []
        self._max_event: list[Evidence] = []
        self._condition_positions: dict[tuple[object, ...], list[int]] = {}
        self._unknown_positions: list[int] = []
        self._baselines: dict[tuple[int, tuple[object, ...]], BaselineStatistics] = {}
        self._advanced = 0
        self._generation = 0
        self._by_horse: dict[str, list[Start]] = {}
        self._history_horses: set[str] = set()
        self._view_day: date | None = None

    @property
    def parameters(self) -> CalculationParameters:
        """Return the validated calculation parameters shared by every view."""
        return self._parameters

    def register(self, evidence: Evidence) -> None:
        """Validate evidence once and reject conflicting versions across the whole build."""
        try:
            validate_evidence_version(evidence, self._versions)
        except ValueError as exc:
            raise ChronologicalInvariantError(str(exc)) from exc

    def append(self, races: Sequence[HistoricalRace]) -> None:
        """Add normalized history after every race already indexed, in start order."""
        for race in sorted(races, key=lambda item: (item.started_at, item.race_id)):
            evidence = race.evidence
            if not isinstance(evidence, ReferenceEvidence):
                raise ChronologicalInvariantError(
                    "chronological history requires reference evidence"
                )
            aware(race.started_at, "historical started_at")
            if race.race_id in self._ids:
                raise ChronologicalInvariantError(f"duplicate historical race: {race.race_id}")
            if self._races and (race.started_at, race.race_id) <= (
                self._races[-1].started_at,
                self._races[-1].race_id,
            ):
                raise ChronologicalInvariantError("history must be appended in start order")
            started = race.started_at.astimezone(JST)
            usable = evidence.usable_after.astimezone(JST)
            if started.date() < self._parameters.history_start:
                raise ChronologicalInvariantError("history starts before history_start")
            if usable.timetz().replace(tzinfo=None) != time.min or usable.date() <= started.date():
                raise ChronologicalInvariantError(
                    "reference history must become usable at a later JST midnight"
                )
            if evidence.event_at > evidence.usable_after:
                raise ChronologicalInvariantError("history event follows its use boundary")
            if self._usable and evidence.usable_after < self._usable[-1]:
                raise ChronologicalInvariantError("history use boundaries must follow start order")
            validate_race(race)
            self.register(evidence)
            position = len(self._races)
            self._races.append(race)
            self._ids.add(race.race_id)
            self._usable.append(evidence.usable_after)
            previous_available = self._max_available[-1] if self._max_available else evidence
            previous_event = self._max_event[-1] if self._max_event else evidence
            self._max_available.append(
                evidence
                if evidence.available_at > previous_available.available_at
                else previous_available
            )
            self._max_event.append(
                evidence if evidence.event_at > previous_event.event_at else previous_event
            )
            key = self._condition_key(race.conditions)
            if any(value is None for value in key):
                self._unknown_positions.append(position)
            else:
                self._condition_positions.setdefault(key, []).append(position)

    def view(self, day: date, pedigrees: Mapping[str, PedigreeObservation]) -> HistoryView:
        """Return the history usable on one JST date; dates must not move backwards."""
        if self._view_day is not None and day < self._view_day:
            raise ChronologicalInvariantError("history views must advance in date order")
        self._view_day = day
        midnight = datetime.combine(day, time.min, JST)
        prefix = bisect_right(self._usable, midnight)
        for race in self._races[self._advanced : prefix]:
            for runner in race.runners:
                self._by_horse.setdefault(runner.horse_id, []).append((race, runner))
                self._history_horses.add(runner.horse_id)
        self._advanced = max(self._advanced, prefix)
        self._generation += 1
        races = tuple(reversed(self._races[:prefix]))
        if races:
            last = races[0]
            if (
                last.started_at.astimezone(JST).date() >= day
                or last.evidence.available_at > midnight
                or races[-1].started_at.astimezone(JST).date() < self._parameters.history_start
            ):
                raise ChronologicalInvariantError("history prefix crosses its date boundary")
        return HistoryView(self, day, prefix, races, self._generation, pedigrees)

    def baseline_statistics(self, cutoff: datetime, conditions: Conditions) -> BaselineStatistics:
        """Summarize the as-of reference population of an earlier start without materializing it."""
        prefix = bisect_right(self._usable, cutoff)
        if (
            prefix
            and self._races[prefix - 1].started_at.astimezone(JST).date()
            >= cutoff.astimezone(JST).date()
        ):
            raise ChronologicalInvariantError("baseline prefix crosses its start date")
        key = self._condition_key(conditions)
        cache_key = (prefix, key)
        cached = self._baselines.get(cache_key)
        if cached is not None:
            return cached
        if any(value is None for value in key):
            matched: list[HistoricalRace] = []
            unknown = prefix > 0
        else:
            positions = self._condition_positions.get(key, [])
            stop = bisect_left(positions, prefix)
            matched = [self._races[position] for position in reversed(positions[:stop])]
            unknown = bool(self._unknown_positions) and self._unknown_positions[0] < prefix
        dependencies = (
            evidence_extrema((self._max_available[prefix - 1], self._max_event[prefix - 1]))
            if prefix
            else ()
        )
        summary = baseline_statistics(matched, unknown=unknown, dependencies=dependencies)
        self._baselines[cache_key] = summary
        return summary

    def _condition_key(self, conditions: Conditions) -> tuple[object, ...]:
        return tuple(getattr(conditions, key) for key in self._parameters.condition_keys)

    def _check_generation(self, generation: int) -> None:
        if generation != self._generation:
            raise ChronologicalInvariantError("a history view was used after a later date")


class _DescendingStarts(Mapping[str, tuple[Start, ...]]):
    """Expose ascending per-horse lists as most-recent-first tuples for one view."""

    def __init__(self, history: ChronologicalHistory, generation: int) -> None:
        self._history = history
        self._generation = generation
        self._cache: dict[str, tuple[Start, ...]] = {}

    def __getitem__(self, key: str) -> tuple[Start, ...]:
        self._history._check_generation(self._generation)
        cached = self._cache.get(key)
        if cached is None:
            cached = tuple(reversed(self._history._by_horse[key]))
            self._cache[key] = cached
        return cached

    def __iter__(self) -> Iterator[str]:
        self._history._check_generation(self._generation)
        return iter(self._history._by_horse)

    def __len__(self) -> int:
        return len(self._history._by_horse)


@dataclass
class HistoryView:
    """Hold the history, windows and caches shared by every target on one JST date."""

    history: ChronologicalHistory
    day: date
    prefix: int
    races: tuple[HistoricalRace, ...]
    generation: int
    pedigrees: Mapping[str, PedigreeObservation]
    by_horse: Mapping[str, tuple[Start, ...]] = field(init=False)
    adjusted_histories: dict[
        tuple[str, bool],
        tuple[list[float | None], list[float | None], list[int], tuple[Evidence, ...]],
    ] = field(default_factory=dict)
    _windows: dict[int, tuple[Start, ...]] = field(default_factory=dict)
    _jockeys: dict[str, tuple[Start, ...]] | None = None
    _trainers: dict[str, tuple[Start, ...]] | None = None
    _parents: dict[tuple[str, str], tuple[Start, ...]] = field(default_factory=dict)
    _matching: dict[tuple[object, ...], tuple[Start, ...] | None] = field(default_factory=dict)
    _priors: dict[tuple[int, int], tuple[Sequence[Start], float | None]] = field(
        default_factory=dict
    )
    _missing_parents: dict[str, dict[str, int]] = field(default_factory=dict)
    _shared: dict[str, object] = field(default_factory=dict)
    _pedigree_evidence: tuple[Evidence, ...] | None = None
    _pedigrees_complete: bool | None = None
    _horses_sorted: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        self.by_horse = _DescendingStarts(self.history, self.generation)

    @property
    def dependency_maxima(self) -> tuple[Evidence, ...]:
        """Return the evidence attaining the history maxima of this prefix."""
        if not self.prefix:
            return ()
        index = self.prefix - 1
        return evidence_extrema(
            (self.history._max_available[index], self.history._max_event[index])
        )

    @property
    def usable_through(self) -> datetime | None:
        """Return the latest declared use boundary of this prefix."""
        return self.history._usable[self.prefix - 1] if self.prefix else None

    def window(self, days: int | None) -> tuple[Start, ...]:
        """Return starts within a half-open JST day window, most recent race first."""
        size = days or self.history.parameters.days_window
        cached = self._windows.get(size)
        if cached is None:
            self.history._check_generation(self.generation)
            left = self.day - timedelta(days=size)
            starts: list[Start] = []
            for race in self.races:
                started = race.started_at.astimezone(JST).date()
                if started < left:
                    break
                if started < self.day:
                    starts.extend((race, runner) for runner in race.runners)
            cached = tuple(starts)
            self._windows[size] = cached
        return cached

    @property
    def population(self) -> tuple[Start, ...]:
        """Return the configured rolling population."""
        return self.window(None)

    def jockey_window(self, identity: str) -> tuple[Start, ...]:
        """Return population starts ridden by one jockey."""
        if self._jockeys is None:
            self._jockeys = _index(self.population, lambda start: start[1].jockey_id)
        return self._jockeys.get(identity, ())

    def trainer_window(self, identity: str) -> tuple[Start, ...]:
        """Return population starts trained by one trainer."""
        if self._trainers is None:
            self._trainers = _index(self.population, lambda start: start[1].trainer_id)
        return self._trainers.get(identity, ())

    def parent_window(self, parent: str, identity: str) -> tuple[Start, ...]:
        """Return population starts whose normalized parent matches."""
        key = (parent, identity)
        cached = self._parents.get(key)
        if cached is None:
            cached = tuple(
                start
                for start in self.population
                if (pedigree := self.pedigrees.get(start[1].horse_id)) is not None
                and getattr(pedigree, parent) == identity
            )
            self._parents[key] = cached
        return cached

    def matching_population(
        self, context: CalculationContext, conditions: Conditions
    ) -> tuple[Start, ...] | None:
        """Cache condition matching of the shared population for one card condition."""
        key = tuple(getattr(conditions, name) for name in self.history.parameters.condition_keys)
        if key not in self._matching:
            self._matching[key] = CalculationContext.matching_starts(context, self.population)
        return self._matching[key]

    def population_prior(
        self, context: CalculationContext, population: Sequence[Start] | None, upper: int
    ) -> float | None:
        """Cache priors of the shared population objects, keeping each object alive."""
        if not population:
            return None
        key = (id(population), upper)
        cached = self._priors.get(key)
        if cached is not None and cached[0] is population:
            return cached[1]
        value = CalculationContext.population_prior(context, population, upper)
        self._priors[key] = (population, value)
        return value

    def unknown_parent(self, parent: str, horse_id: str, *, include_self: bool) -> bool:
        """Count window starts without a normalized parent once per parent kind."""
        counts = self._missing_parents.get(parent)
        if counts is None:
            counts = {}
            for _, runner in self.population:
                if getattr(self.pedigrees[runner.horse_id], parent) is None:
                    counts[runner.horse_id] = counts.get(runner.horse_id, 0) + 1
            self._missing_parents[parent] = counts
        total = sum(counts.values())
        return total > (0 if include_self else counts.get(horse_id, 0))

    def shared(self, key: str, compute: Callable[[], object]) -> object:
        """Compute a date-only value once; failures are not cached."""
        if key not in self._shared:
            self._shared[key] = compute()
        return self._shared[key]

    def pedigree_evidence(self) -> tuple[Evidence, ...]:
        """Summarize the clocks of every pedigree observation the views can read."""
        if self._pedigree_evidence is None:
            self._pedigree_evidence = evidence_extrema(
                tuple(pedigree.evidence for pedigree in self.pedigrees.values())
            )
        return self._pedigree_evidence

    def history_pedigrees_complete(self) -> bool:
        """Return whether every history horse has a normalized pedigree."""
        if self._pedigrees_complete is None:
            self.history._check_generation(self.generation)
            self._pedigrees_complete = self.history._history_horses <= self.pedigrees.keys()
        return self._pedigrees_complete

    def history_contains_any(self, horses: Iterable[str]) -> bool:
        """Return whether any given horse has a start in this history prefix."""
        self.history._check_generation(self.generation)
        return any(horse in self.history._history_horses for horse in horses)

    def history_horses_sorted(self) -> tuple[str, ...]:
        """Return the permanent IDs of every history horse in sorted order."""
        if self._horses_sorted is None:
            self.history._check_generation(self.generation)
            self._horses_sorted = tuple(sorted(self.history._history_horses))
        return self._horses_sorted


def _index(
    starts: Sequence[Start], identity: Callable[[Start], str | None]
) -> dict[str, tuple[Start, ...]]:
    result: dict[str, list[Start]] = {}
    for start in starts:
        value = identity(start)
        if value:
            result.setdefault(value, []).append(start)
    return {key: tuple(value) for key, value in result.items()}


class WorkoutIndex:
    """Hold validated workouts in source order and serve one JST date at a time."""

    def __init__(self, parameters: CalculationParameters) -> None:
        self._parameters = parameters
        self._workouts: list[Workout] = []
        self._dates: list[date] = []
        self._order: list[int] = []

    def load(self, workouts: Sequence[Workout]) -> None:
        """Replace the loaded sessions; input order is hc then wc in physical row order.

        Version conflicts are checked within the load. Session observation IDs contain the
        session date, so sessions of different years cannot conflict, and they are not kept
        in the build-wide evidence registry.
        """
        latest = datetime.max.replace(tzinfo=JST)
        chosen = select_versions(workouts, lambda w: w.evidence.observation_id, latest)
        for workout in chosen:
            if (
                workout.kind not in {"hc", "wc"}
                or not workout.sections
                or not workout.facility
                or (
                    (not workout.course or not workout.turn)
                    and not (
                        workout.kind == "hc" and workout.course is None and workout.turn is None
                    )
                )
            ):
                raise ValueError(
                    "workout requires hc/wc, facility, course, turn and measured sections"
                )
            validate_sections(workout.sections)
        self._workouts = list(chosen)
        self._dates = [w.evidence.event_at.astimezone(JST).date() for w in self._workouts]

    def view(self, day: date) -> WorkoutView:
        """Return sessions dated in [day - days_window, day) and usable before that day."""
        left = day - timedelta(days=self._parameters.days_window)
        midnight = datetime.combine(day, time.min, JST)
        selected = [
            workout
            for workout, workout_day in zip(self._workouts, self._dates, strict=True)
            if left <= workout_day < day
        ]
        if any(w.evidence.available_at > midnight for w in selected):
            raise ChronologicalInvariantError(
                "workout view contains a session usable after its date"
            )
        return WorkoutView(tuple(selected))


@dataclass
class WorkoutView:
    """Index one date's candidate sessions; targets still apply their own freeze window."""

    sessions: tuple[Workout, ...]
    by_horse_kind: dict[tuple[str, str], tuple[Workout, ...]] = field(init=False)
    by_key_horse: dict[tuple[WorkoutKey, str], tuple[Workout, ...]] = field(init=False)
    by_key_day: dict[tuple[WorkoutKey, date], tuple[Workout, ...]] = field(init=False)
    _clocks: dict[tuple[int, int], tuple[Workout, float | None]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        horse_kind: dict[tuple[str, str], list[Workout]] = {}
        key_horse: dict[tuple[WorkoutKey, str], list[Workout]] = {}
        key_day: dict[tuple[WorkoutKey, date], list[Workout]] = {}
        for workout in self.sessions:
            key = workout_key(workout)
            horse_kind.setdefault((workout.horse_id, workout.kind), []).append(workout)
            key_horse.setdefault((key, workout.horse_id), []).append(workout)
            key_day.setdefault((key, workout.evidence.event_at.astimezone(JST).date()), []).append(
                workout
            )
        self.by_horse_kind = {key: tuple(value) for key, value in horse_kind.items()}
        self.by_key_horse = {key: tuple(value) for key, value in key_horse.items()}
        self.by_key_day = {key: tuple(value) for key, value in key_day.items()}

    def clock(self, workout: Workout, distance: int) -> float | None:
        """Compute each session clock once per date, keeping the session alive."""
        key = (id(workout), distance)
        cached = self._clocks.get(key)
        if cached is not None and cached[0] is workout:
            return cached[1]
        value = workout_clock(workout, distance)
        self._clocks[key] = (workout, value)
        return value


@dataclass(frozen=True)
class SharedCalculationContext(CalculationContext):
    """Answer the per-race context questions from shared chronological views."""

    view: HistoryView | None = field(default=None, compare=False, repr=False)
    workout_view: WorkoutView | None = field(default=None, compare=False, repr=False)

    @property
    def _history_view(self) -> HistoryView:
        if self.view is None:
            raise ChronologicalInvariantError("shared context requires a history view")
        self.view.history._check_generation(self.view.generation)
        return self.view

    @property
    def _workouts(self) -> WorkoutView:
        if self.workout_view is None:
            raise ChronologicalInvariantError("shared context requires a workout view")
        return self.workout_view

    @property
    def population(self) -> tuple[Start, ...]:
        """Return the shared rolling population."""
        return self._history_view.population

    def window_starts(self, days: int | None = None) -> tuple[Start, ...]:
        """Return the shared day window."""
        return self._history_view.window(days)

    def jockey_window(self, identity: str) -> tuple[Start, ...]:
        """Return the shared rider window."""
        return self._history_view.jockey_window(identity)

    def trainer_window(self, identity: str) -> tuple[Start, ...]:
        """Return the shared trainer window."""
        return self._history_view.trainer_window(identity)

    def parent_window(self, parent: str, identity: str) -> tuple[Start, ...]:
        """Return the shared parent window."""
        return self._history_view.parent_window(parent, identity)

    def matching_starts(self, starts: Sequence[Start]) -> tuple[Start, ...] | None:
        """Reuse condition matching of the shared population per card condition."""
        view = self._history_view
        if starts is view.population:
            return view.matching_population(self, self.source.card.conditions)
        return super().matching_starts(starts)

    def pedigrees_cover_population(self) -> bool:
        """Check history horses once per date and card horses per target."""
        return (
            self._history_view.history_pedigrees_complete()
            and set(self.source.card.expected_horse_ids) <= self.pedigrees.keys()
        )

    def pedigree_evidence(self) -> tuple[Evidence, ...]:
        """Return the pedigree clock maxima."""
        return self._history_view.pedigree_evidence()

    def population_prior(self, population: Sequence[Start] | None, upper: int) -> float | None:
        """Return the cached prior of a shared population object."""
        return self._history_view.population_prior(self, population, upper)

    def population_unknown_parent(self, parent: str, horse_id: str) -> bool:
        """Return the cached unknown-parent check of the shared window."""
        return self._history_view.unknown_parent(
            parent, horse_id, include_self=self.parameters.pedigree_include_self
        )

    def day_shared[T](self, key: str, compute: Callable[[], T]) -> T:
        """Share a date-only value across every target of the view's date."""
        return cast(T, self._history_view.shared(key, compute))

    def _left(self) -> datetime:
        return self.cutoff - timedelta(days=self.parameters.days_window)

    def workout_sessions(self, horse_id: str, kind: str) -> tuple[Workout, ...]:
        """Return one horse's sessions inside this target's freeze window."""
        left = self._left()
        return tuple(
            w
            for w in self._workouts.by_horse_kind.get((horse_id, kind), ())
            if w.evidence.event_at >= left
        )

    def workout_key_horse(self, key: WorkoutKey, horse_id: str) -> tuple[Workout, ...]:
        """Return one horse's comparable sessions inside this target's freeze window."""
        left = self._left()
        return tuple(
            w
            for w in self._workouts.by_key_horse.get((key, horse_id), ())
            if w.evidence.event_at >= left
        )

    def workout_key_day(self, key: WorkoutKey, day: date) -> tuple[Workout, ...]:
        """Return one date's comparable sessions inside this target's freeze window."""
        left = self._left()
        return tuple(
            w for w in self._workouts.by_key_day.get((key, day), ()) if w.evidence.event_at >= left
        )

    def workout_clock(self, workout: Workout, distance: int) -> float | None:
        """Return the date-cached session clock."""
        return self._workouts.clock(workout, distance)

    def history_missing_reasons(self) -> dict[str, dict[str, str]]:
        """Datamart contexts do not persist per-runner history missing reasons."""
        return {}

    def baseline_statistics(
        self, started_at: datetime, conditions: Conditions
    ) -> BaselineStatistics:
        """Return the build-wide as-of baseline summary."""
        return self._history_view.history.baseline_statistics(started_at, conditions)

    def result(
        self,
        values: Mapping[str, FeatureScalar],
        *,
        extra: Sequence[Evidence] = (),
        reasons: Mapping[str, str] | None = None,
        diagnostics: Mapping[str, FeatureScalar] | None = None,
        include_history: bool = True,
    ) -> CalculatedValues:
        """Keep the same dependency clock maxima without enumerating the whole history."""
        evidence = [self.source.card.evidence, self.parameters.evidence]
        if include_history and "history" in self.coverage:
            evidence.append(self.coverage["history"].evidence)
        if include_history:
            evidence.extend(self._history_view.dependency_maxima)
        evidence.extend(extra)
        missing = {key: "undefined_statistic" for key, value in values.items() if value is None}
        if reasons:
            missing.update(reasons)
        return CalculatedValues(
            dict(values),
            evidence_extrema(evidence),
            (),
            missing,
            dict(diagnostics or {}),
        )


def shared_context(
    source: ObservationInput,
    *,
    view: HistoryView,
    workouts: WorkoutView,
    population: tuple[str, ...],
) -> SharedCalculationContext:
    """Validate one target and connect it to the shared views of its JST date."""
    history = view.history
    parameters = history.parameters
    day = source.card.scheduled_start_at.astimezone(JST).date()
    if day != view.day or source.freeze_at.astimezone(JST).date() != day:
        raise ChronologicalInvariantError("target freeze and start must fall on the view date")
    # Evidence that becomes usable after the freeze is a leakage invariant, never a hold.
    late = [
        name
        for name, items in (
            ("card", (source.card.evidence,)),
            ("parameters", (parameters.evidence,)),
            ("coverage", tuple(c.evidence for c in source.coverage)),
            (
                "market",
                tuple(e for m in source.markets for e in (m.evidence, m.pair_evidence)),
            ),
            ("pedigree", view.pedigree_evidence()),
        )
        if any(e.available_at > source.freeze_at or e.event_at > source.freeze_at for e in items)
    ]
    if late:
        raise ChronologicalInvariantError(
            "evidence is usable only after freeze_at: " + ", ".join(late)
        )
    validate_card(source.card, source.freeze_at)
    if view.usable_through is not None and view.usable_through > source.freeze_at:
        raise ChronologicalInvariantError("history is usable only after the target freeze")
    coverage = {
        c.kind: c for c in select_versions(source.coverage, lambda c: c.kind, source.freeze_at)
    }
    for kind, covered in coverage.items():
        aware(covered.start_at, f"{kind} coverage start_at")
        aware(covered.end_at, f"{kind} coverage end_at")
        if kind not in {"history", "workouts", "pedigree", "market"}:
            raise ValueError(f"unsupported coverage kind: {kind}")
        if not covered.scope or covered.start_at > covered.end_at:
            raise ValueError(f"invalid {kind} coverage scope or interval")
        required_start = datetime.combine(parameters.history_start, time.min, JST)
        if kind == "market":
            required_start = source.freeze_at - timedelta(
                seconds=parameters.market_anchor_seconds + parameters.market_max_age_seconds
            )
        elif kind == "workouts":
            required_start = source.freeze_at - timedelta(days=parameters.days_window)
        if covered.start_at > required_start or covered.end_at < source.freeze_at:
            raise ValueError(f"{kind} coverage must span history_start through freeze_at")
        # The population object was built from this date's history horses plus the card.
        complete = (
            covered.horse_ids is population
            if kind in {"history", "pedigree"}
            else set(source.card.expected_horse_ids) <= set(covered.horse_ids)
        )
        if not complete:
            raise ValueError(
                f"{kind} coverage does not cover the complete required horse population"
            )
        history.register(covered.evidence)
    history.register(source.card.evidence)
    markets: tuple[MarketObservation, ...] = tuple(
        m for m in source.markets if m.race_id == source.card.race_id
    )
    select_versions(markets, lambda m: m.evidence.observation_id, source.freeze_at)
    for market in markets:
        for item in (market.evidence, market.pair_evidence):
            validate_evidence(item)
            history.register(item)
    return SharedCalculationContext(
        source,
        parameters,
        view.races,
        view.by_horse,
        coverage,
        workouts.sessions,
        view.pedigrees,
        markets,
        adjusted_histories=view.adjusted_histories,
        view=view,
        workout_view=workouts,
    )
