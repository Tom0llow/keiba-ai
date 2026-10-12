"""Build the history volume and missingness intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from features.common.base import FeatureBuilder
from features.common.feature_table import FeatureTableRow, IntermediateFeatureTable
from features.common.normalization import normalize_feature_inputs
from features.common.types import FeatureGroupSpec, FeatureValuesInput

SPEC = FeatureGroupSpec("F15", "history_volume_and_missingness")


@dataclass(frozen=True, slots=True, kw_only=True)
class HistoryVolumeAndMissingnessInput(FeatureValuesInput):
    """Provide explicit history volume and missingness values and source evidence."""


class HistoryVolumeAndMissingnessBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = SPEC.label

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_history_volume_and_missingness(records)


def build_history_volume_and_missingness(
    records: Sequence[HistoryVolumeAndMissingnessInput], *, column_types: Mapping[str, pa.DataType]
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return HistoryVolumeAndMissingnessBuilder().build(records, column_types=column_types)


def _normalize_history_volume_and_missingness(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_feature_inputs(records, SPEC.feature_id, HistoryVolumeAndMissingnessInput)
