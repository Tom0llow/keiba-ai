"""Build the within race relative intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues, Evidence
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.generation.statistics import mean, relative_values
from make_features.recent_stability import metric_history
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class WithinRaceRelativeInput(FeatureValuesInput):
    """Provide explicit within race relative values and source evidence."""


class WithinRaceRelativeBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "within_race_relative"
    input_type = WithinRaceRelativeInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_within_race_relative(records)


def build_within_race_relative(
    records: Sequence[WithinRaceRelativeInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return WithinRaceRelativeBuilder(definition).build(records, column_types=column_types)


def _normalize_within_race_relative(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_within_race_relative(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Compare pre-race metric means within the complete frozen horse set."""
    values: list[float | None] = []
    dependencies: list[Evidence] = []
    ids = [r.horse_id for r in context.source.card.runners]
    for identity in ids:
        history, evidence = metric_history(context, identity)
        values.append(mean(history))
        dependencies.extend(evidence)
    result = relative_values(
        values,
        ids.index(horse_id),
        higher=context.parameters.metric_direction == "higher",
        partial=context.parameters.partial_rank,
    )
    return context.result(
        {f"relative_{context.parameters.metric}_{key}": value for key, value in result.items()},
        extra=dependencies,
        reasons={
            f"relative_{context.parameters.metric}_{key}": "missing_own_history_metric"
            if values[ids.index(horse_id)] is None
            else "incomplete_field"
            if not context.parameters.partial_rank and None in values
            else "constant_or_singleton_field"
            for key, value in result.items()
            if value is None
        },
    )
