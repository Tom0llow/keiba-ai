"""Build the past lap and running style intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from features.common.base import FeatureBuilder
from features.common.feature_table import FeatureTableRow, IntermediateFeatureTable
from features.common.normalization import normalize_feature_inputs
from features.common.types import FeatureGroupSpec, FeatureValuesInput

SPEC = FeatureGroupSpec("F18", "past_lap_and_running_style")


@dataclass(frozen=True, slots=True, kw_only=True)
class PastLapAndRunningStyleInput(FeatureValuesInput):
    """Provide explicit past lap and running style values and source evidence."""


class PastLapAndRunningStyleBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = SPEC.label

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_past_lap_and_running_style(records)


def build_past_lap_and_running_style(
    records: Sequence[PastLapAndRunningStyleInput], *, column_types: Mapping[str, pa.DataType]
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return PastLapAndRunningStyleBuilder().build(records, column_types=column_types)


def _normalize_past_lap_and_running_style(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_feature_inputs(records, SPEC.feature_id, PastLapAndRunningStyleInput)
