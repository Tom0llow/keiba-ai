"""Reject incomplete or ambiguous normalized evidence before numerical work."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from itertools import pairwise
from math import isfinite
from typing import Protocol

from make_features.contracts.observations import (
    LAST3F_DISTANCE_M,
    CalculationParameters,
    Conditions,
    Evidence,
    HistoricalRace,
    RaceCard,
    ReferenceEvidence,
    Section,
    SourceEvidence,
)


class Evidenced(Protocol):
    """Expose the source reference carried by a normalized observation."""

    @property
    def evidence(self) -> Evidence: ...


def aware(value: datetime, name: str) -> None:
    """Require an explicit timezone, without guessing a calendar interpretation."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} requires a timezone-aware timestamp")


def reject_reference(value: object) -> None:
    """Keep every existing strict entry point closed to assumed clocks."""
    if isinstance(value, ReferenceEvidence):
        raise ValueError("reference evidence requires the explicit reference calculation path")
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            reject_reference(getattr(value, field.name))
    elif isinstance(value, Mapping):
        for item in value.values():
            reject_reference(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            reject_reference(item)


def publication_clock(value: Evidence) -> datetime:
    """Require a real publication clock for market age and synchronization checks."""
    if value.published_at is None:
        raise ValueError("market requires an actual published_at clock")
    return value.published_at


def validate_evidence(value: Evidence) -> None:
    """Validate a supplied source declaration; do not certify external reception."""
    if not isinstance(value, (SourceEvidence, ReferenceEvidence)):
        raise ValueError("SourceEvidence is required; source reception cannot be inferred")
    for name in ("observation_id", "source", "content_hash"):
        if not isinstance(getattr(value, name), str) or not getattr(value, name).strip():
            raise ValueError(f"source evidence requires {name}")
    if len(value.content_hash) != 64 or any(
        c not in "0123456789abcdef" for c in value.content_hash
    ):
        raise ValueError("source evidence content_hash requires lowercase SHA-256")
    if type(value.version) is not int or value.version < 1:
        raise ValueError("source evidence version must be a positive integer")
    if isinstance(value, ReferenceEvidence):
        aware(value.event_at, "reference event_at")
        aware(value.usable_after, "reference usable_after")
        if (
            value.received_at is not None
            or not value.basis.strip()
            or not value.event_time_basis.strip()
            or value.event_at > value.usable_after
        ):
            raise ValueError("reference evidence requires explicit bases and a valid use boundary")
        if value.published_at is not None:
            aware(value.published_at, "reference actual published_at")
            if value.event_at > value.published_at or value.published_at > value.usable_after:
                raise ValueError(
                    "reference actual publication cannot precede event or follow usability"
                )
        return
    for name in ("published_at", "received_at", "event_at"):
        aware(getattr(value, name), f"source evidence {name}")
    if value.event_at > value.published_at or value.event_at > value.received_at:
        raise ValueError("source event_at cannot follow publication; scheduled start is separate")


def validate_evidence_version(
    source: Evidence, versions: dict[tuple[str, str, int], Evidence]
) -> None:
    """Validate and register evidence in the caller's shared source-version index."""
    validate_evidence(source)
    reference = (source.source, source.observation_id, source.version)
    if versions.setdefault(reference, source) != source:
        raise ValueError("conflicting source version across calculation dependencies or labels")


def select_versions[T: Evidenced](
    records: Sequence[T], key: Callable[[T], str], cutoff: datetime
) -> tuple[T, ...]:
    """Select the latest uniquely ordered available version for each logical key."""
    versions: dict[str, dict[int, T]] = {}
    seen: dict[tuple[str, int], T] = {}
    observation_keys: dict[str, str] = {}
    for record in records:
        evidence = record.evidence
        validate_evidence(evidence)
        if evidence.available_at > cutoff or evidence.event_at > cutoff:
            continue
        logical_key = key(record)
        previous_key = observation_keys.setdefault(evidence.observation_id, logical_key)
        if previous_key != logical_key:
            raise ValueError("observation_id references conflicting logical records")
        version_key = (logical_key, evidence.version)
        if version_key in seen and seen[version_key] != record:
            raise ValueError(f"conflicting source version for {logical_key!r}")
        seen[version_key] = record
        available = versions.setdefault(logical_key, {})
        if (
            available
            and evidence.observation_id != next(iter(available.values())).evidence.observation_id
        ):
            raise ValueError(f"ambiguous observation IDs for {logical_key!r}")
        available[evidence.version] = record
    chosen = []
    for logical_key, available in versions.items():
        ordered = [available[version] for version in sorted(available)]
        for older, newer in pairwise(ordered):
            if (newer.evidence.published_at or newer.evidence.available_at) <= (
                older.evidence.published_at or older.evidence.available_at
            ):
                raise ValueError(f"ambiguous revision order for {logical_key!r}")
        chosen.append(ordered[-1])
    return tuple(chosen)


def validate_conditions(conditions: Conditions) -> None:
    """Validate normalized units without interpreting category strings."""
    if type(conditions.distance_m) is not int or conditions.distance_m <= 0:
        raise ValueError("normalized distance_m must be a positive integer")
    for name in ("surface", "venue", "course", "going", "class_code"):
        value = getattr(conditions, name)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"normalized {name} must be a nonempty category or null")


def validate_card(card: RaceCard, freeze_at: datetime) -> None:
    """Require the full active field and evidence known before its scheduled start."""
    validate_evidence(card.evidence)
    aware(freeze_at, "freeze_at")
    aware(card.scheduled_start_at, "scheduled_start_at")
    if not card.race_id or not card.complete or not card.runners:
        raise ValueError("a complete nonempty frozen RaceCard is required")
    if card.evidence.available_at > freeze_at or freeze_at >= card.scheduled_start_at:
        raise ValueError("RaceCard must be received by freeze_at before scheduled_start_at")
    validate_conditions(card.conditions)
    _field(tuple(r.horse_id for r in card.runners), card.expected_horse_ids)
    numbers = [runner.horse_number for runner in card.runners]
    if any(not number for number in numbers) or len(numbers) != len(set(numbers)):
        raise ValueError("frozen horse numbers must be nonempty and unique")
    for runner in card.runners:
        if runner.active is not True:
            raise ValueError("cancelled/unresolved entrants require an explicit policy")
        for name in ("gate", "age_years"):
            value = getattr(runner, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"card {name} must be a positive integer or null")
        _positive(runner.carried_weight_kg, "carried_weight_kg")


def _field(ids: tuple[str, ...], expected: tuple[str, ...]) -> None:
    if (
        not expected
        or any(not i for i in ids)
        or len(ids) != len(set(ids))
        or len(expected) != len(set(expected))
        or set(ids) != set(expected)
    ):
        raise ValueError("complete field does not match its unique expected horse set")


def validate_sections(sections: tuple[Section, ...]) -> None:
    """Require explicit positive distances and measured positive section durations."""
    for section in sections:
        if type(section.distance_m) is not int or section.distance_m <= 0:
            raise ValueError("section distance_m must be a positive integer")
        _positive(section.seconds, "section seconds")


def _positive(value: float | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be finite and positive or null")


def validate_race(race: HistoricalRace) -> None:
    """Reject unconfirmed, tied, cancelled or incomplete normal-result populations."""
    aware(race.started_at, "historical started_at")
    if race.started_at > race.evidence.event_at or not race.complete:
        raise ValueError("historical race requires completed full-result evidence")
    validate_conditions(race.conditions)
    _field(tuple(r.horse_id for r in race.runners), race.expected_horse_ids)
    if any(type(r.finish) is not int for r in race.runners) or sorted(
        r.finish for r in race.runners
    ) != list(range(1, len(race.runners) + 1)):
        raise ValueError("normal complete results require unique contiguous finish ranks")
    validate_sections(race.sections)
    if race.sections and sum(s.distance_m for s in race.sections) != race.conditions.distance_m:
        raise ValueError("race section distances must sum to normalized race distance")
    _positive(race.race_last3f_sec, "race_last3f_sec")
    _distance(race.race_last3f_distance_m, "race_last3f_distance_m")
    if race.race_last3f_sec is not None and race.race_last3f_distance_m != LAST3F_DISTANCE_M:
        raise ValueError(f"race last3f measurement distance must be {LAST3F_DISTANCE_M} metres")
    for runner in race.runners:
        if runner.status != "normal":
            raise ValueError("non-normal historical result requires an explicit exception policy")
        for name in ("elapsed_sec", "last3f_sec", "body_weight_kg", "carried_weight_kg"):
            _positive(getattr(runner, name), name)
        if runner.signed_gap_sec is not None and not isfinite(runner.signed_gap_sec):
            raise ValueError("signed_gap_sec must be finite or null")
        _distance(runner.last3f_distance_m, "runner last3f_distance_m")
        if runner.last3f_sec is not None and runner.last3f_distance_m != LAST3F_DISTANCE_M:
            raise ValueError(
                f"runner last3f measurement distance must be {LAST3F_DISTANCE_M} metres"
            )
        if runner.corner4 is not None and (
            type(runner.corner4) is not int or not 1 <= runner.corner4 <= len(race.runners)
        ):
            raise ValueError("corner4 must be within the historical field")
        for name in (
            "elapsed_sec",
            "signed_gap_sec",
            "last3f_sec",
            "last3f_distance_m",
            "corner4",
            "body_weight_kg",
            "carried_weight_kg",
            "jockey_id",
            "trainer_id",
        ):
            if getattr(runner, name) is None and not runner.missing_reasons.get(name):
                raise ValueError(f"historical {runner.horse_id} missing {name} requires a reason")


def _distance(value: int | None, name: str) -> None:
    if value is not None and (type(value) is not int or value <= 0):
        raise ValueError(f"{name} must be positive metres or null")


def validate_parameters(p: CalculationParameters) -> None:
    """Reject missing/unknown business choices and invalid numerical controls."""
    validate_evidence(p.evidence)
    if not p.rule_id:
        raise ValueError("calculation rule_id is required")
    for name in (
        "lag_count",
        "count_window",
        "days_window",
        "minimum_count",
        "style_window",
        "style_minimum_count",
        "workout_distance_m",
        "workout_section_distance_m",
        "market_anchor_seconds",
        "market_max_age_seconds",
        "graph_days",
        "graph_max_iterations",
    ):
        if type(getattr(p, name)) is not int or getattr(p, name) < 1:
            raise ValueError(f"{name} must be an explicit positive integer")
    if (
        type(p.market_version_tolerance_seconds) is not int
        or p.market_version_tolerance_seconds < 0
    ):
        raise ValueError("market_version_tolerance_seconds must be nonnegative")
    for name in ("half_life_days", "graph_tolerance"):
        if (
            isinstance(getattr(p, name), bool)
            or not isfinite(getattr(p, name))
            or getattr(p, name) <= 0
        ):
            raise ValueError(f"{name} must be finite and positive")
    if (
        isinstance(p.smoothing_alpha, bool)
        or not isfinite(p.smoothing_alpha)
        or p.smoothing_alpha < 0
    ):
        raise ValueError("smoothing_alpha must be nonnegative; zero explicitly disables smoothing")
    if p.graph_half_life_days is not None and (
        not isfinite(p.graph_half_life_days) or p.graph_half_life_days <= 0
    ):
        raise ValueError("graph_half_life_days must be positive or explicitly null")
    if (
        not 0 < p.graph_damping < 1
        or not 0 <= p.leader_threshold <= 1
        or not 0 <= p.front_threshold <= 1
    ):
        raise ValueError("invalid damping or style threshold")
    if p.style_minimum_count > p.style_window:
        raise ValueError("style_minimum_count cannot exceed style_window")
    if (
        not p.condition_keys
        or len(set(p.condition_keys)) != len(p.condition_keys)
        or set(p.condition_keys)
        - {"distance_m", "surface", "venue", "course", "going", "class_code"}
    ):
        raise ValueError("condition_keys must name unique normalized condition attributes")
    choices = (
        (p.condition_window_order, {"filter_then_window", "window_then_filter"}),
        (p.tie_policy, {"competition"}),
        (
            p.metric,
            {
                "elapsed_sec",
                "velocity_mps",
                "last3f_sec",
                "finish_relative",
                "condition_time_advantage",
            },
        ),
        (p.metric_direction, {"higher", "lower"}),
        (p.graph_edge_rule, {"all_pairs", "winner_only"}),
        (p.graph_base_weight, {"inverse_field_minus_one", "unit"}),
    )
    if any(value not in allowed for value, allowed in choices):
        raise ValueError("unsupported calculation parameter option")
    if type(p.partial_rank) is not bool or type(p.pedigree_include_self) is not bool:
        raise ValueError("partial_rank and pedigree_include_self must be boolean")
    if len(p.class_order) != len(set(p.class_order)) or not p.class_order:
        raise ValueError("class_order requires explicit unique class codes, from low to high")
