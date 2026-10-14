"""Build the recent performance intermediate feature rows and tables."""

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
class RecentPerformanceInput(FeatureValuesInput):
    """Provide explicit recent performance values and source evidence."""


class RecentPerformanceBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "recent_performance"
    definition: FeatureDefinition

    def __init__(self, definition: FeatureDefinition) -> None:
        super().__init__(definition)
        self.definition = definition

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_recent_performance(records, self.definition)


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
    definition: FeatureDefinition,
) -> list[FeatureTableRow]:
    return normalize_feature_inputs(records, definition.feature_id, RecentPerformanceInput)
