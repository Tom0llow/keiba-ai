"""Build the jockey performance intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from features.contracts.rows import FeatureTableRow
from features.contracts.types import FeatureDefinition, FeatureValuesInput
from features.generation.base import FeatureBuilder
from features.generation.normalization import normalize_feature_inputs
from features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class JockeyPerformanceInput(FeatureValuesInput):
    """Provide explicit jockey performance values and source evidence."""


class JockeyPerformanceBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "jockey_performance"
    definition: FeatureDefinition

    def __init__(self, definition: FeatureDefinition) -> None:
        super().__init__(definition)
        self.definition = definition

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_jockey_performance(records, self.definition)


def build_jockey_performance(
    records: Sequence[JockeyPerformanceInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return JockeyPerformanceBuilder(definition).build(records, column_types=column_types)


def _normalize_jockey_performance(
    records: Sequence[FeatureValuesInput],
    definition: FeatureDefinition,
) -> list[FeatureTableRow]:
    return normalize_feature_inputs(records, definition.feature_id, JockeyPerformanceInput)
