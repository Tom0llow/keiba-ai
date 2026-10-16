"""Build the condition adjusted ability intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from features.contracts.rows import FeatureTableRow
from features.contracts.types import FeatureDefinition, FeatureValuesInput
from features.generation.base import RegisteredFeatureBuilder
from features.generation.normalization import normalize_audited_feature_inputs
from features.tables.schema import IntermediateFeatureTable


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
