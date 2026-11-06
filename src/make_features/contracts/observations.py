"""Define normalized observations; timestamps are supplied evidence, never inferred.

All distances are metres, durations seconds, weights kilograms and odds decimal.
Identifiers and already decoded categories retain their source meaning. A source
hash identifies the original observation, not a proof of historical reception.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from make_features.contracts.types import FeatureScalar

LAST3F_DISTANCE_M = 600


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    """Identify one version of a logical source observation and its actual clocks."""

    observation_id: str
    source: str
    version: int
    content_hash: str
    published_at: datetime
    received_at: datetime
    event_at: datetime

    @property
    def available_at(self) -> datetime:
        """Return the later of publication and actual reception."""
        return max(self.published_at, self.received_at)


@dataclass(frozen=True, slots=True)
class ReferenceEvidence:
    """Keep assumed usability separate from actual publication and reception clocks."""

    observation_id: str
    source: str
    version: int
    content_hash: str
    published_at: datetime | None
    received_at: datetime | None
    event_at: datetime
    usable_after: datetime
    basis: str
    event_time_basis: str

    @property
    def available_at(self) -> datetime:
        """Return the declared reference-use boundary, never an observed receipt."""
        return self.usable_after


type Evidence = SourceEvidence | ReferenceEvidence


@dataclass(frozen=True, slots=True)
class CalculationDependencyGroup:
    """Retain the existing serialized evidence manifest for one calculated group."""

    rule_id: str
    sources: tuple[Evidence, ...]
    historical_race_ids: tuple[str, ...]
    missing_reasons: Mapping[str, str]
    diagnostics: Mapping[str, FeatureScalar]


@dataclass(frozen=True, slots=True)
class CalculationDependencyRecord:
    """Bind each dependency group to its frozen race and horse identity."""

    race_id: str
    horse_id: str
    groups: Mapping[str, CalculationDependencyGroup]


@dataclass(frozen=True, slots=True)
class Conditions:
    """Provide decoded conditions without inventing ordered category codes."""

    distance_m: int
    surface: str | None
    venue: str | None
    course: str | None
    going: str | None
    class_code: str | None


@dataclass(frozen=True, slots=True)
class CardRunner:
    """Describe a frozen entrant without any target result fields."""

    horse_id: str
    horse_number: str
    gate: int | None
    age_years: int | None
    sex: str | None
    carried_weight_kg: float | None
    jockey_id: str | None
    trainer_id: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class RaceCard:
    """Hold one complete frozen card; evidence.event_at is the card observation."""

    race_id: str
    scheduled_start_at: datetime
    conditions: Conditions
    runners: tuple[CardRunner, ...]
    expected_horse_ids: tuple[str, ...]
    complete: bool
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Section:
    """Represent an explicitly measured distance section in chronological order."""

    distance_m: int
    seconds: float | None


@dataclass(frozen=True, slots=True)
class HistoricalRunner:
    """Provide normal results; measured last3f_sec always covers the final 600 m."""

    horse_id: str
    finish: int
    status: str
    jockey_id: str | None
    trainer_id: str | None
    elapsed_sec: float | None
    signed_gap_sec: float | None
    last3f_sec: float | None
    last3f_distance_m: int | None
    corner4: int | None
    body_weight_kg: float | None
    carried_weight_kg: float | None
    missing_reasons: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class HistoricalRace:
    """Hold complete normal results; measured race_last3f_sec covers the final 600 m."""

    race_id: str
    started_at: datetime
    conditions: Conditions
    runners: tuple[HistoricalRunner, ...]
    expected_horse_ids: tuple[str, ...]
    complete: bool
    sections: tuple[Section, ...]
    race_last3f_sec: float | None
    race_last3f_distance_m: int | None
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Coverage:
    """Declare an audited population/time range, including genuinely empty sets.

    Kinds are history, workouts, pedigree and market. Horse IDs describe the
    population covered by the declaration, not only the observed rows.
    """

    kind: str
    start_at: datetime
    end_at: datetime
    horse_ids: tuple[str, ...]
    complete: bool
    scope: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Workout:
    """Describe one hill/wood session with distance-labelled measured sections."""

    horse_id: str
    kind: str
    facility: str
    course: str | None
    turn: str | None
    sections: tuple[Section, ...]
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class PedigreeObservation:
    """Supply normalized father and maternal-father IDs with their source version."""

    horse_id: str
    sire: str | None
    broodmare_sire: str | None
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class HorseOdds:
    """Associate decimal quotes with horse IDs, independently of slot order."""

    horse_id: str
    win: float | None
    place_low: float | None
    place_high: float | None


@dataclass(frozen=True, slots=True)
class PairOdds:
    """Provide one unordered horse pair and its decimal quote."""

    horse_ids: tuple[str, str]
    odds: float | None


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """Hold one synchronized market observation and its explicit sale sets."""

    race_id: str
    horses: tuple[HorseOdds, ...]
    pairs: tuple[PairOdds, ...]
    sale_horse_ids: tuple[str, ...]
    sale_pairs: tuple[tuple[str, str], ...]
    ticket_totals: Mapping[str, int]
    evidence: Evidence
    pair_evidence: Evidence


@dataclass(frozen=True, slots=True)
class CalculationParameters:
    """Require all business choices explicitly; none is an operational default."""

    rule_id: str
    evidence: Evidence
    history_start: date
    lag_count: int
    count_window: int
    days_window: int
    half_life_days: float
    condition_keys: tuple[str, ...]
    condition_window_order: str
    smoothing_alpha: float
    minimum_count: int
    partial_rank: bool
    tie_policy: str
    metric: str
    metric_direction: str
    class_order: tuple[str, ...]
    style_window: int
    style_minimum_count: int
    leader_threshold: float
    front_threshold: float
    pedigree_include_self: bool
    workout_distance_m: int
    workout_section_distance_m: int
    market_anchor_seconds: int
    market_max_age_seconds: int
    market_version_tolerance_seconds: int
    graph_days: int
    graph_half_life_days: float | None
    graph_edge_rule: str
    graph_base_weight: str
    graph_damping: float
    graph_tolerance: float
    graph_max_iterations: int


@dataclass(frozen=True, slots=True)
class ObservationInput:
    """Supply normalized immutable source versions, keeping target results separate."""

    freeze_at: datetime
    card: RaceCard
    history: tuple[HistoricalRace, ...]
    coverage: tuple[Coverage, ...]
    workouts: tuple[Workout, ...]
    pedigrees: tuple[PedigreeObservation, ...]
    markets: tuple[MarketObservation, ...]


@dataclass(frozen=True, slots=True)
class CalculatedValues:
    """Retain calculated scalars and every selected observation dependency."""

    values: Mapping[str, FeatureScalar]
    dependencies: tuple[Evidence, ...]
    historical_race_ids: tuple[str, ...]
    missing_reasons: Mapping[str, str]
    diagnostics: Mapping[str, FeatureScalar]
