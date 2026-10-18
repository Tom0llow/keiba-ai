"""Build the running style and position intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class RunningStyleAndPositionInput(FeatureValuesInput):
    """Provide explicit running style and position values and source evidence."""


class RunningStyleAndPositionBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "running_style_and_position"
    input_type = RunningStyleAndPositionInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_running_style_and_position(records)


def build_running_style_and_position(
    records: Sequence[RunningStyleAndPositionInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return RunningStyleAndPositionBuilder(definition).build(records, column_types=column_types)


def _normalize_running_style_and_position(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)
