"""Select as-of versions and index the approved historical population."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cached_property
from zoneinfo import ZoneInfo

from make_features.contracts.observations import (
    CalculatedValues,
    CalculationParameters,
    CardRunner,
    Conditions,
    Coverage,
    Evidence,
    HistoricalRace,
    HistoricalRunner,
    MarketObservation,
    ObservationInput,
    PedigreeObservation,
    Workout,
)
from make_features.contracts.types import FeatureScalar
from make_features.generation.statistics import mean, rates, relative, std
from make_features.validation.observations import (
    aware,
    reject_reference,
    select_versions,
    validate_card,
    validate_parameters,
    validate_race,
    validate_sections,
)

JST = ZoneInfo("Asia/Tokyo")
type Start = tuple[HistoricalRace, HistoricalRunner]
type WorkoutKey = tuple[str, str, str | None, str | None]


def workout_key(workout: Workout) -> WorkoutKey:
    """Return the kind, facility, course and turn used to compare workout clocks."""
    return (workout.kind, workout.facility, workout.course, workout.turn)


def workout_clock(workout: Workout, distance: int) -> float | None:
    """Sum the final measured sections covering exactly one distance, or return None."""
    selected = []
    measured_distance = 0
    for section in reversed(workout.sections):
        measured_distance += section.distance_m
        selected.append(section)
        if measured_distance >= distance:
            break
    if measured_distance != distance:
        return None
    values = [section.seconds for section in selected]
    return sum(x for x in values if x is not None) if all(x is not None for x in values) else None


@dataclass(frozen=True, slots=True)
class BaselineStatistics:
    """Summarize condition-matched winner clocks of one as-of reference population."""

    matched_count: int
    unknown: bool
    clock_mean: float | None
    clock_std: float | None
    velocity_mean: float | None
    velocity_std: float | None
    unmeasured_clock: bool
    zero_clock: bool
    dependencies: tuple[Evidence, ...]


def baseline_statistics(
    matched: Sequence[HistoricalRace], *, unknown: bool, dependencies: tuple[Evidence, ...]
) -> BaselineStatistics:
    """Apply the shared winner-clock formulas to an already ordered matched population."""
    winners = [next(r for r in prior.runners if r.finish == 1) for prior in matched]
    clocks = [r.elapsed_sec for r in winners]
    velocities = [
        prior.conditions.distance_m / r.elapsed_sec if r.elapsed_sec else None
        for prior, r in zip(matched, winners, strict=True)
    ]
    return BaselineStatistics(
        len(matched),
        unknown,
        mean(clocks),
        std(clocks),
        mean(velocities),
        std(velocities),
        any(clock is None for clock in clocks),
        any(clock == 0 for clock in clocks if clock is not None),
        dependencies,
    )


@dataclass(frozen=True)
class CalculationContext:
    """Keep selected versions and horse indexes local to one frozen race."""

    source: ObservationInput
    parameters: CalculationParameters
    races: tuple[HistoricalRace, ...]
    by_horse: Mapping[str, tuple[Start, ...]]
    coverage: Mapping[str, Coverage]
    workouts: tuple[Workout, ...]
    pedigrees: Mapping[str, PedigreeObservation]
    markets: tuple[MarketObservation, ...]
    adjusted_histories: dict[
        tuple[str, bool],
        tuple[list[float | None], list[float | None], list[int], tuple[Evidence, ...]],
    ] = field(default_factory=dict, compare=False, repr=False)
    baseline_races: dict[datetime, tuple[HistoricalRace, ...]] = field(
        default_factory=dict, compare=False, repr=False
    )
    pagerank_results: dict[str, CalculatedValues] = field(
        default_factory=dict, compare=False, repr=False
    )
    baseline_summaries: dict[tuple[datetime, Conditions], BaselineStatistics] = field(
        default_factory=dict, compare=False, repr=False
    )

    @cached_property
    def population(self) -> tuple[Start, ...]:
        """Index the shared rolling prior population once per frozen race."""
        return self.rolling(tuple((race, r) for race in self.races for r in race.runners))

    @cached_property
    def by_jockey(self) -> Mapping[str, tuple[Start, ...]]:
        """Index historical riders once rather than scanning per target horse."""
        result: dict[str, list[Start]] = {}
        for race in self.races:
            for runner in race.runners:
                if runner.jockey_id:
                    result.setdefault(runner.jockey_id, []).append((race, runner))
        return {key: tuple(value) for key, value in result.items()}

    @cached_property
    def by_trainer(self) -> Mapping[str, tuple[Start, ...]]:
        """Index historical trainers while counting individual horse starts."""
        result: dict[str, list[Start]] = {}
        for race in self.races:
            for runner in race.runners:
                if runner.trainer_id:
                    result.setdefault(runner.trainer_id, []).append((race, runner))
        return {key: tuple(value) for key, value in result.items()}

    @property
    def cutoff(self) -> datetime:
        """Return the explicit input freeze."""
        return self.source.freeze_at

    def runner(self, horse_id: str) -> CardRunner:
        """Find a target horse exclusively within the frozen card."""
        return next(r for r in self.source.card.runners if r.horse_id == horse_id)

    def history(self, horse_id: str, *, count: bool = True) -> tuple[Start, ...]:
        """Return most-recent-first starts, never filling a measured-value window."""
        self.require_coverage("history")
        starts = self.by_horse.get(horse_id, ())
        return starts[: self.parameters.count_window] if count else starts

    def rolling(self, starts: Sequence[Start], days: int | None = None) -> tuple[Start, ...]:
        """Select a half-open JST calendar-day window."""
        target_date = self.source.card.scheduled_start_at.astimezone(JST).date()
        left = target_date - timedelta(days=days or self.parameters.days_window)
        return tuple(
            s for s in starts if left <= s[0].started_at.astimezone(JST).date() < target_date
        )

    def condition_matches(self, left: Conditions, right: Conditions) -> bool | None:
        """Match configured exact keys, preserving an unknown condition."""
        pairs = [
            (getattr(left, key), getattr(right, key)) for key in self.parameters.condition_keys
        ]
        return (
            None if any(a is None or b is None for a, b in pairs) else all(a == b for a, b in pairs)
        )

    def condition_starts(self, starts: Sequence[Start]) -> tuple[Start, ...] | None:
        """Apply the explicit filter/window order, with no category fallback."""
        p = self.parameters
        if any(getattr(self.source.card.conditions, key) is None for key in p.condition_keys):
            return None
        candidates = (
            starts[: p.count_window] if p.condition_window_order == "window_then_filter" else starts
        )
        # Unknown historical conditions may belong to the requested population.
        matches = [
            self.condition_matches(s[0].conditions, self.source.card.conditions) for s in candidates
        ]
        if None in matches:
            return None
        filtered = tuple(s for s, match in zip(candidates, matches, strict=True) if match)
        return filtered[: p.count_window]

    def matching_starts(self, starts: Sequence[Start]) -> tuple[Start, ...] | None:
        """Filter a population without cutting through simultaneous race starters."""
        if any(
            getattr(self.source.card.conditions, key) is None
            for key in self.parameters.condition_keys
        ):
            return None
        matches = [
            self.condition_matches(s[0].conditions, self.source.card.conditions) for s in starts
        ]
        if None in matches:
            return None
        return tuple(s for s, match in zip(starts, matches, strict=True) if match)

    def require_coverage(self, kind: str) -> Coverage:
        """Reject unavailable coverage instead of treating unseen rows as empty history."""
        coverage = self.coverage.get(kind)
        if coverage is None:
            raise ValueError(f"{kind} coverage evidence is required")
        if not coverage.complete:
            raise ValueError(f"{kind} coverage is incomplete: {coverage.scope}")
        return coverage

    # Overridable accessors. These defaults reproduce the per-race reference behavior;
    # chronological datamart contexts answer the same questions from shared indexes.

    def window_starts(self, days: int | None = None) -> tuple[Start, ...]:
        """Return every eligible prior start inside a JST calendar-day window."""
        return self.rolling(tuple((race, r) for race in self.races for r in race.runners), days)

    def jockey_window(self, identity: str) -> tuple[Start, ...]:
        """Return one rider's starts inside the configured rolling window."""
        return self.rolling(self.by_jockey.get(identity, ()))

    def trainer_window(self, identity: str) -> tuple[Start, ...]:
        """Return one trainer's starts inside the configured rolling window."""
        return self.rolling(self.by_trainer.get(identity, ()))

    def parent_window(self, parent: str, identity: str) -> tuple[Start, ...]:
        """Return rolling-window starts whose normalized parent identity matches."""
        result = []
        for start in self.population:
            pedigree = self.pedigrees.get(start[1].horse_id)
            if pedigree is not None and getattr(pedigree, parent) == identity:
                result.append(start)
        return tuple(result)

    def pedigrees_cover_population(self) -> bool:
        """Return whether every history and card horse has a normalized pedigree."""
        return (
            set(self.by_horse) | set(self.source.card.expected_horse_ids) <= self.pedigrees.keys()
        )

    def pedigree_evidence(self) -> tuple[Evidence, ...]:
        """Return the pedigree evidence a pedigree-based group depends on."""
        return tuple(p.evidence for p in self.pedigrees.values())

    def workout_sessions(self, horse_id: str, kind: str) -> tuple[Workout, ...]:
        """Return one horse's selected sessions of one kind in source order."""
        return tuple(w for w in self.workouts if w.horse_id == horse_id and w.kind == kind)

    def workout_key_horse(self, key: WorkoutKey, horse_id: str) -> tuple[Workout, ...]:
        """Return one horse's selected sessions with one comparison key in source order."""
        return tuple(w for w in self.workouts if workout_key(w) == key and w.horse_id == horse_id)

    def workout_key_day(self, key: WorkoutKey, day: date) -> tuple[Workout, ...]:
        """Return selected sessions with one comparison key on one JST date in source order."""
        return tuple(
            w
            for w in self.workouts
            if workout_key(w) == key and w.evidence.event_at.astimezone(JST).date() == day
        )

    def population_prior(self, population: Sequence[Start] | None, upper: int) -> float | None:
        """Return the share of population starts finishing at or above a place."""
        if not population:
            return None
        return sum(s[1].finish <= upper for s in population) / len(population)

    def population_unknown_parent(self, parent: str, horse_id: str) -> bool:
        """Return whether a window start, other than the horse unless included, lacks a parent."""
        return any(
            getattr(self.pedigrees[runner.horse_id], parent) is None
            for _, runner in self.population
            if self.parameters.pedigree_include_self or runner.horse_id != horse_id
        )

    def day_shared[T](self, key: str, compute: Callable[[], T]) -> T:
        """Compute a value that depends only on the target date's history views."""
        return compute()

    def workout_clock(self, workout: Workout, distance: int) -> float | None:
        """Return one session's clock over the final sections of a distance."""
        return workout_clock(workout, distance)

    def history_missing_reasons(self) -> dict[str, dict[str, str]]:
        """Return the per-runner missing reasons recorded on selected history."""
        return {
            f"{race.race_id}/{runner.horse_id}": dict(runner.missing_reasons)
            for race in self.races
            for runner in race.runners
            if runner.missing_reasons
        }

    def baseline_statistics(
        self, started_at: datetime, conditions: Conditions
    ) -> BaselineStatistics:
        """Summarize the as-of reference population of one prior start, excluding itself."""
        key = (started_at, conditions)
        cached = self.baseline_summaries.get(key)
        if cached is not None:
            return cached
        if started_at not in self.baseline_races:
            self.baseline_races[started_at] = historical_as_of(
                self.source, self.parameters, started_at, started_at
            )
        baseline = self.baseline_races[started_at]
        matches = [self.condition_matches(r.conditions, conditions) for r in baseline]
        summary = baseline_statistics(
            [r for r, match in zip(baseline, matches, strict=True) if match is True],
            unknown=any(match is None for match in matches),
            dependencies=tuple(r.evidence for r in baseline),
        )
        self.baseline_summaries[key] = summary
        return summary

    def performance(
        self, starts: Sequence[Start] | None, *, conditioned: bool = False
    ) -> dict[str, FeatureScalar]:
        """Return raw and smoothed rates with priors fitted only before this row."""
        if starts is None:
            return {
                key: None
                for key in (
                    "start_count",
                    "win_rate",
                    "top3_rate",
                    "small_sample",
                    "relative_finish_mean",
                    "smoothed_win_rate",
                    "smoothed_top3_rate",
                    "prior_win_rate",
                    "prior_top3_rate",
                )
            }
        self.require_coverage("history")
        result = rates([s[1].finish for s in starts], self.parameters.minimum_count)
        result["relative_finish_mean"] = mean(
            [relative(s[1].finish, len(s[0].runners)) for s in starts]
        )
        population = self.matching_starts(self.population) if conditioned else self.population
        n = len(starts)
        alpha = self.parameters.smoothing_alpha
        for name, upper in (("win_rate", 1), ("top3_rate", 3)):
            prior = self.population_prior(population, upper)
            result[f"prior_{name}"] = prior
            result[f"smoothed_{name}"] = (
                (sum(s[1].finish <= upper for s in starts) + alpha * prior) / (n + alpha)
                if n and prior is not None
                else None
            )
            if alpha == 0:
                result[f"smoothed_{name}"] = result[name]
        return result

    def result(
        self,
        values: Mapping[str, FeatureScalar],
        *,
        extra: Sequence[Evidence] = (),
        reasons: Mapping[str, str] | None = None,
        diagnostics: Mapping[str, FeatureScalar] | None = None,
        include_history: bool = True,
    ) -> CalculatedValues:
        """Retain conservative history-population dependencies and specific extras."""
        evidence = [self.source.card.evidence, self.parameters.evidence]
        if include_history and "history" in self.coverage:
            evidence.append(self.coverage["history"].evidence)
        if include_history:
            evidence.extend(r.evidence for r in self.races)
        evidence.extend(extra)
        unique = {(e.source, e.observation_id, e.version, e.content_hash): e for e in evidence}
        missing = {key: "undefined_statistic" for key, value in values.items() if value is None}
        if reasons:
            missing.update(reasons)
        return CalculatedValues(
            dict(values),
            tuple(sorted(unique.values(), key=lambda e: (e.source, e.observation_id, e.version))),
            tuple(r.race_id for r in self.races) if include_history else (),
            missing,
            dict(diagnostics or {}),
        )


def historical_as_of(
    source: ObservationInput, p: CalculationParameters, cutoff: datetime, target_date: datetime
) -> tuple[HistoricalRace, ...]:
    """Select completed versions strictly before the target's JST calendar day."""
    day = target_date.astimezone(JST).date()
    for race in source.history:
        aware(race.started_at, "historical started_at")
    candidates = tuple(
        race
        for race in source.history
        if race.race_id != source.card.race_id
        and p.history_start <= race.started_at.astimezone(JST).date() < day
    )
    selected = select_versions(candidates, lambda race: race.race_id, cutoff)
    for race in selected:
        validate_race(race)
    return tuple(sorted(selected, key=lambda r: (r.started_at, r.race_id), reverse=True))


def prepare_context(
    source: ObservationInput, p: CalculationParameters, *, reference: bool = False
) -> CalculationContext:
    """Validate normalized source declarations without accessing raw/Parquet data."""
    if not reference:
        reject_reference((source, p))
    validate_parameters(p)
    validate_card(source.card, source.freeze_at)
    if p.evidence.available_at > source.freeze_at:
        raise ValueError("parameter selection evidence is later than freeze_at")
    races = historical_as_of(source, p, source.freeze_at, source.card.scheduled_start_at)
    by_horse: dict[str, list[Start]] = {}
    for race in races:
        for runner in race.runners:
            by_horse.setdefault(runner.horse_id, []).append((race, runner))
    coverage = {
        c.kind: c for c in select_versions(source.coverage, lambda c: c.kind, source.freeze_at)
    }
    target_ids = set(source.card.expected_horse_ids)
    population = target_ids | set(by_horse)
    for kind, covered in coverage.items():
        aware(covered.start_at, f"{kind} coverage start_at")
        aware(covered.end_at, f"{kind} coverage end_at")
        if kind not in {"history", "workouts", "pedigree", "market"}:
            raise ValueError(f"unsupported coverage kind: {kind}")
        if not covered.scope or covered.start_at > covered.end_at:
            raise ValueError(f"invalid {kind} coverage scope or interval")
        required_start = datetime.combine(p.history_start, datetime.min.time(), JST)
        if kind == "market":
            required_start = source.freeze_at - timedelta(
                seconds=p.market_anchor_seconds + p.market_max_age_seconds
            )
        elif kind == "workouts":
            required_start = source.freeze_at - timedelta(days=p.days_window)
        if covered.start_at > required_start or covered.end_at < source.freeze_at:
            raise ValueError(f"{kind} coverage must span history_start through freeze_at")
        required = population if kind in {"history", "pedigree"} else target_ids
        if len(set(covered.horse_ids)) != len(covered.horse_ids) or not required <= set(
            covered.horse_ids
        ):
            raise ValueError(
                f"{kind} coverage does not cover the complete required horse population"
            )
    workouts = select_versions(
        source.workouts, lambda w: w.evidence.observation_id, source.freeze_at
    )
    for w in workouts:
        if (
            w.kind not in {"hc", "wc"}
            or not w.sections
            or not w.facility
            or (
                (not w.course or not w.turn)
                and not (reference and w.kind == "hc" and w.course is None and w.turn is None)
            )
        ):
            raise ValueError("workout requires hc/wc, facility, course, turn and measured sections")
        validate_sections(w.sections)
    pedigrees = select_versions(source.pedigrees, lambda x: x.horse_id, source.freeze_at)
    markets = tuple(m for m in source.markets if m.race_id == source.card.race_id)
    select_versions(
        markets,
        lambda m: m.evidence.observation_id,
        source.freeze_at,
    )
    return CalculationContext(
        source,
        p,
        races,
        {h: tuple(s) for h, s in by_horse.items()},
        coverage,
        workouts,
        {x.horse_id: x for x in pedigrees},
        markets,
    )
