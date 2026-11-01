"""Build the condition suitability intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class ConditionSuitabilityInput(FeatureValuesInput):
    """Provide explicit condition suitability values and source evidence."""


class ConditionSuitabilityBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "condition_suitability"
    input_type = ConditionSuitabilityInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_condition_suitability(records)


def build_condition_suitability(
    records: Sequence[ConditionSuitabilityInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return ConditionSuitabilityBuilder(definition).build(records, column_types=column_types)


def _normalize_condition_suitability(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_condition_suitability(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Calculate exact configured-condition rates without sparse-condition fallback."""
    starts = context.condition_starts(context.history(horse_id, count=False))
    values = {
        f"horse_condition_{key}": value
        for key, value in context.performance(starts, conditioned=True).items()
    }
    return context.result(
        values,
        reasons={
            key: "unknown_condition"
            if starts is None
            else "no_condition_history"
            if not starts
            else "undefined_reference"
            for key, value in values.items()
            if value is None
        },
    )
