"""Build the within race relative intermediate feature rows and tables."""

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
