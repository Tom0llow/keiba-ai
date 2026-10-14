"""Build the opponent pagerank intermediate feature rows and tables."""

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
class OpponentPagerankInput(FeatureValuesInput):
    """Provide explicit opponent pagerank values and source evidence."""


class OpponentPagerankBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "opponent_pagerank"
    definition: FeatureDefinition

    def __init__(self, definition: FeatureDefinition) -> None:
        super().__init__(definition)
        self.definition = definition

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_opponent_pagerank(records, self.definition)


def build_opponent_pagerank(
    records: Sequence[OpponentPagerankInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return OpponentPagerankBuilder(definition).build(records, column_types=column_types)


def _normalize_opponent_pagerank(
    records: Sequence[FeatureValuesInput],
    definition: FeatureDefinition,
) -> list[FeatureTableRow]:
    return normalize_feature_inputs(records, definition.feature_id, OpponentPagerankInput)
