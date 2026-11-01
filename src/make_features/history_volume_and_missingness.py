"""Build the history volume and missingness intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.condition_adjusted_ability import adjusted_history
from make_features.contracts.observations import CalculatedValues, Evidence
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class HistoryVolumeAndMissingnessInput(FeatureValuesInput):
    """Provide explicit history volume and missingness values and source evidence."""


class HistoryVolumeAndMissingnessBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "history_volume_and_missingness"
    input_type = HistoryVolumeAndMissingnessInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_history_volume_and_missingness(records)


def build_history_volume_and_missingness(
    records: Sequence[HistoryVolumeAndMissingnessInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return HistoryVolumeAndMissingnessBuilder(definition).build(records, column_types=column_types)


def _normalize_history_volume_and_missingness(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_history_volume_and_missingness(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Distinguish observed absence, incomplete collection and unmeasured values."""
    coverage = context.coverage.get("history")
    if coverage is None:
        raise ValueError("history coverage evidence is required even for missing history")
    starts = context.by_horse.get(horse_id, ())
    condition = context.matching_starts(starts)
    metric = context.parameters.metric
    valid: int | None
    dependencies: tuple[Evidence, ...] = ()
    if metric == "condition_time_advantage":
        if coverage.complete:
            measurements, _, _, dependencies = adjusted_history(context, horse_id, count=False)
            valid = sum(value is not None for value in measurements)
        else:
            valid = None
    elif metric == "finish_relative":
        valid = sum(len(race.runners) > 1 for race, _ in starts)
    elif metric == "last3f_sec":
        valid = sum(runner.last3f_sec is not None for _, runner in starts)
    else:
        valid = sum(runner.elapsed_sec is not None for _, runner in starts)
    values: dict[str, FeatureScalar] = {
        "past_observed_start_count": len(starts),
        "condition_observed_start_count": len(condition) if condition is not None else None,
        "past_metric_valid_count": valid,
        "history_complete": coverage.complete,
        "is_first_observed_start": not starts,
        "is_first_condition": not condition
        if coverage.complete and condition is not None
        else None,
        "has_metric_history": valid > 0 if valid is not None else None,
        "past_missing_reason": "not_collected"
        if not coverage.complete
        else "no_history"
        if not starts
        else "unmeasured"
        if valid is None or valid < len(starts)
        else "none",
    }
    return context.result(
        values,
        extra=dependencies,
        reasons={
            key: "incomplete_history" if not coverage.complete else "unknown_condition"
            for key, value in values.items()
            if value is None
        },
        diagnostics={
            "metric": metric,
            "first_condition_scope": coverage.scope,
            "history_start": context.parameters.history_start.isoformat(),
        },
    )
