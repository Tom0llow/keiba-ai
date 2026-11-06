"""Build the hill and wood workouts intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues, Workout
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import JST, CalculationContext
from make_features.generation.statistics import mean
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class HillAndWoodWorkoutsInput(FeatureValuesInput):
    """Provide explicit hill and wood workouts values and source evidence."""


class HillAndWoodWorkoutsBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "hill_and_wood_workouts"
    input_type = HillAndWoodWorkoutsInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_hill_and_wood_workouts(records)


def build_hill_and_wood_workouts(
    records: Sequence[HillAndWoodWorkoutsInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return HillAndWoodWorkoutsBuilder(definition).build(records, column_types=column_types)


def _normalize_hill_and_wood_workouts(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def _workout_clock(workout: Workout, distance: int) -> float | None:
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


def _workout_key(workout: Workout) -> tuple[str, str, str | None, str | None]:
    return (
        workout.kind,
        workout.facility,
        workout.course,
        workout.turn,
    )


def calculate_hill_and_wood_workouts(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Calculate distance-specific workouts, excluding each reference session itself."""
    coverage = context.require_coverage("workouts")
    p = context.parameters
    left = context.cutoff - timedelta(days=p.days_window)
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    dependencies = [coverage.evidence]
    for kind in ("hc", "wc"):
        sessions = sorted(
            [
                w
                for w in context.workouts
                if w.horse_id == horse_id
                and w.kind == kind
                and left <= w.evidence.event_at <= context.cutoff
            ],
            key=lambda w: w.evidence.event_at,
            reverse=True,
        )
        latest = sessions[0] if sessions else None
        if len(sessions) > 1 and sessions[0].evidence.event_at == sessions[1].evidence.event_at:
            raise ValueError("workout order is ambiguous at the same event timestamp")
        clocks = [_workout_clock(w, p.workout_distance_m) for w in sessions]
        row: dict[str, FeatureScalar] = {
            "workout_count": len(sessions),
            "clock_mean_sec": mean(clocks),
            "clock_best_sec": min(x for x in clocks if x is not None)
            if clocks and all(x is not None for x in clocks)
            else None,
            "last_clock_sec": clocks[0] if clocks else None,
            "last_section_sec": None,
            "finish_accel_sec": None,
            "self_clock_diff_sec": None,
            "same_day_course_diff_sec": None,
            "self_reference_count": 0,
            "same_day_reference_count": 0,
        }
        dependencies.extend(w.evidence for w in sessions)
        if latest:
            sections = latest.sections
            row["last_section_sec"] = (
                sections[-1].seconds
                if sections[-1].distance_m == p.workout_section_distance_m
                else None
            )
            if (
                len(sections) > 1
                and sections[-2].distance_m
                == sections[-1].distance_m
                == p.workout_section_distance_m
                and sections[-2].seconds is not None
                and sections[-1].seconds is not None
            ):
                row["finish_accel_sec"] = sections[-2].seconds - sections[-1].seconds
            same_key = [w for w in context.workouts if _workout_key(w) == _workout_key(latest)]
            reference = [
                w
                for w in same_key
                if w.horse_id == horse_id and left <= w.evidence.event_at < latest.evidence.event_at
            ]
            peers = [
                w
                for w in same_key
                if w.horse_id != horse_id
                and w.evidence.event_at.astimezone(JST).date()
                == latest.evidence.event_at.astimezone(JST).date()
            ]
            clock = _workout_clock(latest, p.workout_distance_m)
            for prefix, group in (("self", reference), ("same_day", peers)):
                average = mean([_workout_clock(w, p.workout_distance_m) for w in group])
                row[f"{prefix}_reference_count"] = len(group)
                name = "self_clock_diff_sec" if prefix == "self" else "same_day_course_diff_sec"
                row[name] = (
                    clock - average
                    if clock is not None and average is not None and len(group) >= p.minimum_count
                    else None
                )
                dependencies.extend(w.evidence for w in group)
        values.update({f"{kind}_{key}": value for key, value in row.items()})
        reasons.update(
            {
                f"{kind}_{key}": "no_workout_history"
                if not sessions
                else "no_or_insufficient_self_reference"
                if key == "self_clock_diff_sec"
                else "no_or_insufficient_same_day_reference"
                if key == "same_day_course_diff_sec"
                else "unmeasured_or_incompatible_section_distance"
                for key, value in row.items()
                if value is None
            }
        )
    return context.result(values, extra=dependencies, reasons=reasons)
