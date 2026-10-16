"""Build the history volume and missingness intermediate feature rows and tables."""

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
class HistoryVolumeAndMissingnessInput(FeatureValuesInput):
    """Provide explicit history volume and missingness values and source evidence."""


class HistoryVolumeAndMissingnessBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "history_volume_and_missingness"
    input_type = HistoryVolumeAndMissingnessInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_history_volume_and_missingness(records)


def build_history_volume_and_missingness(
    records: Sequence[HistoryVolumeAndMissingnessInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return HistoryVolumeAndMissingnessBuilder(definition).build(records, column_types=column_types)


def _normalize_history_volume_and_missingness(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)
