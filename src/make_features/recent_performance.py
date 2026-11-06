"""Build the recent performance intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.generation.statistics import rates, relative
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class RecentPerformanceInput(FeatureValuesInput):
    """Provide explicit recent performance values and source evidence."""


class RecentPerformanceBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "recent_performance"
    input_type = RecentPerformanceInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_recent_performance(records)


def build_recent_performance(
    records: Sequence[RecentPerformanceInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return RecentPerformanceBuilder(definition).build(records, column_types=column_types)


def _normalize_recent_performance(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_recent_performance(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Calculate finish lags and actual-denominator rates from selected results."""
    starts = context.history(horse_id, count=False)
    p = context.parameters
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    for index in range(p.lag_count):
        start = starts[index] if index < len(starts) else None
        values[f"past_finish_lag{index + 1}"] = start[1].finish if start else None
        values[f"past_finish_relative_lag{index + 1}"] = (
            relative(start[1].finish, len(start[0].runners)) if start else None
        )
        if start is None:
            reasons[f"past_finish_lag{index + 1}"] = "no_history_at_lag"
        if values[f"past_finish_relative_lag{index + 1}"] is None:
            reasons[f"past_finish_relative_lag{index + 1}"] = (
                "no_history_at_lag" if start is None else "singleton_field"
            )
    for key, value in rates(
        [s[1].finish for s in starts[: p.count_window]], p.minimum_count
    ).items():
        values[f"past_{key}"] = value
    reasons.update(
        {key: "no_history" for key, value in values.items() if value is None and key not in reasons}
    )
    return context.result(values, reasons=reasons)
