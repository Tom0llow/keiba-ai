"""Build the opponent pagerank intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from features.common.base import FeatureBuilder
from features.common.feature_table import FeatureTableRow, IntermediateFeatureTable
from features.common.normalization import normalize_feature_inputs
from features.common.types import FeatureGroupSpec, FeatureValuesInput

SPEC = FeatureGroupSpec("F21", "opponent_pagerank")


@dataclass(frozen=True, slots=True, kw_only=True)
class OpponentPagerankInput(FeatureValuesInput):
    """Provide explicit opponent pagerank values and source evidence."""


class OpponentPagerankBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = SPEC.label

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_opponent_pagerank(records)


def build_opponent_pagerank(
    records: Sequence[OpponentPagerankInput], *, column_types: Mapping[str, pa.DataType]
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return OpponentPagerankBuilder().build(records, column_types=column_types)


def _normalize_opponent_pagerank(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_feature_inputs(records, SPEC.feature_id, OpponentPagerankInput)
