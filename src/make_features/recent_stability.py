"""Build the recent stability intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.condition_adjusted_ability import adjusted_history
from make_features.contracts.observations import CalculatedValues, Evidence
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.generation.statistics import relative, summaries
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class RecentStabilityInput(FeatureValuesInput):
    """Provide explicit recent stability values and source evidence."""


class RecentStabilityBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "recent_stability"
    input_type = RecentStabilityInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_recent_stability(records)


def build_recent_stability(
    records: Sequence[RecentStabilityInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return RecentStabilityBuilder(definition).build(records, column_types=column_types)


def _normalize_recent_stability(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def metric_history(
    context: CalculationContext, horse_id: str
) -> tuple[list[float | None], tuple[Evidence, ...]]:
    """Select one explicitly named metric without mixing units."""
    if context.parameters.metric == "condition_time_advantage":
        time, _, _, dependencies = adjusted_history(context, horse_id)
        return time, dependencies
    values: list[float | None] = []
    for race, runner in context.history(horse_id):
        metric = context.parameters.metric
        if metric == "velocity_mps":
            values.append(
                race.conditions.distance_m / runner.elapsed_sec if runner.elapsed_sec else None
            )
        elif metric == "finish_relative":
            values.append(relative(runner.finish, len(race.runners)))
        elif metric == "elapsed_sec":
            values.append(runner.elapsed_sec)
        else:
            values.append(runner.last3f_sec)
    return values, ()


def calculate_recent_stability(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Calculate complete-window level, spread, elapsed-day decay and trend."""
    values, dependencies = metric_history(context, horse_id)
    starts = context.history(horse_id)
    result = summaries(
        values, [s[0].started_at for s in starts], context.cutoff, context.parameters.half_life_days
    )
    return context.result(
        {f"past_{context.parameters.metric}_{key}": value for key, value in result.items()},
        extra=dependencies,
        reasons={
            f"past_{context.parameters.metric}_{key}": "no_history"
            if not starts
            else "window_contains_missing_measurements"
            if any(value is None for value in values)
            else "insufficient_observations_or_identical_times"
            for key, value in result.items()
            if value is None
        },
        diagnostics={
            "metric": context.parameters.metric,
            "direction": context.parameters.metric_direction,
        },
    )
