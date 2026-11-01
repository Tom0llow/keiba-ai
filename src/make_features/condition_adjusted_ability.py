"""Build the condition adjusted ability intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues, Evidence
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext, historical_as_of
from make_features.generation.statistics import mean, std, summaries
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class ConditionAdjustedAbilityInput(FeatureValuesInput):
    """Provide explicit condition adjusted ability values and source evidence."""


class ConditionAdjustedAbilityBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "condition_adjusted_ability"
    input_type = ConditionAdjustedAbilityInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_condition_adjusted_ability(records)


def build_condition_adjusted_ability(
    records: Sequence[ConditionAdjustedAbilityInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return ConditionAdjustedAbilityBuilder(definition).build(records, column_types=column_types)


def _normalize_condition_adjusted_ability(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def adjusted_history(
    context: CalculationContext, horse_id: str, *, count: bool = True
) -> tuple[list[float | None], list[float | None], list[int], tuple[Evidence, ...]]:
    """Fit each past-start reference strictly before that start, excluding itself."""
    cache_key = (horse_id, count)
    if cache_key in context.adjusted_histories:
        return context.adjusted_histories[cache_key]
    times: list[float | None] = []
    speeds: list[float | None] = []
    counts: list[int] = []
    dependencies: list[Evidence] = []
    for race, runner in context.history(horse_id, count=count):
        if race.started_at not in context.baseline_races:
            context.baseline_races[race.started_at] = historical_as_of(
                context.source, context.parameters, race.started_at, race.started_at
            )
        baseline = context.baseline_races[race.started_at]
        matched = [
            r for r in baseline if context.condition_matches(r.conditions, race.conditions) is True
        ]
        unknown = any(
            context.condition_matches(r.conditions, race.conditions) is None for r in baseline
        )
        winners = [next(r for r in prior.runners if r.finish == 1) for prior in matched]
        clocks = [r.elapsed_sec for r in winners]
        velocities = [
            prior.conditions.distance_m / r.elapsed_sec if r.elapsed_sec else None
            for prior, r in zip(matched, winners, strict=True)
        ]
        clock_mean, clock_std = mean(clocks), std(clocks)
        velocity_mean, velocity_std = mean(velocities), std(velocities)
        clock = runner.elapsed_sec
        speed = race.conditions.distance_m / clock if clock else None
        times.append(
            (clock_mean - clock) / clock_std
            if not unknown and clock is not None and clock_mean is not None and clock_std
            else None
        )
        speeds.append(
            (speed - velocity_mean) / velocity_std
            if not unknown and speed is not None and velocity_mean is not None and velocity_std
            else None
        )
        counts.append(len(matched))
        dependencies.extend(r.evidence for r in baseline)
    context.adjusted_histories[cache_key] = times, speeds, counts, tuple(dependencies)
    return context.adjusted_histories[cache_key]


def calculate_condition_adjusted_ability(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Calculate as-of winner-standardized clock and speed advantages."""
    times, speeds, counts, dependencies = adjusted_history(context, horse_id)
    starts = context.history(horse_id)
    values: dict[str, FeatureScalar] = {}
    for name, measurements in (("time", times), ("velocity", speeds)):
        summary = summaries(
            measurements,
            [s[0].started_at for s in starts],
            context.cutoff,
            context.parameters.half_life_days,
        )
        values[f"past_condition_{name}_advantage"] = measurements[0] if measurements else None
        values[f"past_ability_{name}_mean"] = summary["mean"]
        values[f"past_ability_{name}_ewma"] = summary["ewma"]
    values["past_condition_reference_count"] = counts[0] if counts else 0
    for index in range(context.parameters.count_window):
        values[f"past_condition_reference_count_lag{index + 1}"] = (
            counts[index] if index < len(counts) else None
        )
    reasons = {
        key: "window_contains_undefined_adjustment"
        for key, value in values.items()
        if value is None
    }
    for name in ("time", "velocity"):
        key = f"past_condition_{name}_advantage"
        if values[key] is None:
            reasons[key] = _latest_adjustment_reason(context, horse_id, velocity=name == "velocity")
    for index in range(context.parameters.count_window):
        key = f"past_condition_reference_count_lag{index + 1}"
        if values[key] is None:
            reasons[key] = "no_history_at_lag"
    return context.result(
        values,
        extra=dependencies,
        reasons=reasons,
    )


def _latest_adjustment_reason(context: CalculationContext, horse_id: str, *, velocity: bool) -> str:
    starts = context.history(horse_id)
    if not starts:
        return "no_history"
    race, runner = starts[0]
    if runner.elapsed_sec is None:
        return runner.missing_reasons["elapsed_sec"]
    baseline = context.baseline_races[race.started_at]
    matches = [context.condition_matches(r.conditions, race.conditions) for r in baseline]
    if None in matches:
        return "unknown_reference_condition"
    matched = [r for r, match in zip(baseline, matches, strict=True) if match]
    if not matched:
        return "no_prior_condition_reference"
    if len(matched) < 2:
        return "insufficient_reference_count"
    measurements = []
    for prior in matched:
        clock = next(r.elapsed_sec for r in prior.runners if r.finish == 1)
        if clock is None:
            return "unmeasured_reference_clock"
        measurements.append(prior.conditions.distance_m / clock if velocity else clock)
    return "zero_variance_reference" if std(measurements) == 0 else "undefined_adjustment"
