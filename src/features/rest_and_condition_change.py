"""Build the rest and condition change intermediate feature rows and tables."""

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
class RestAndConditionChangeInput(FeatureValuesInput):
    """Provide explicit rest and condition change values and source evidence."""


class RestAndConditionChangeBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "rest_and_condition_change"
    input_type = RestAndConditionChangeInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_rest_and_condition_change(records)


def build_rest_and_condition_change(
    records: Sequence[RestAndConditionChangeInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return RestAndConditionChangeBuilder(definition).build(records, column_types=column_types)


def _normalize_rest_and_condition_change(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)
