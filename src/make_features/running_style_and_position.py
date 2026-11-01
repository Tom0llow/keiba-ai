"""Build the running style and position intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.generation.statistics import mean, relative, std
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


def calculate_running_style_and_position(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Calculate historical corner positions and gains with actual field sizes."""
    starts = context.history(horse_id, count=False)
    positions = [
        relative(r.corner4, len(race.runners)) if r.corner4 is not None else None
        for race, r in starts
    ]
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    for index in range(context.parameters.lag_count):
        start = starts[index] if index < len(starts) else None
        corner = start[1].corner4 if start else None
        gain = corner - start[1].finish if corner is not None and start else None
        values[f"past_corner4_relative_lag{index + 1}"] = (
            positions[index] if index < len(positions) else None
        )
        values[f"past_corner4_to_finish_gain_lag{index + 1}"] = gain
        values[f"past_corner4_to_finish_relative_gain_lag{index + 1}"] = (
            gain / (len(start[0].runners) - 1)
            if gain is not None and start and len(start[0].runners) > 1
            else None
        )
        for key in (
            f"past_corner4_relative_lag{index + 1}",
            f"past_corner4_to_finish_gain_lag{index + 1}",
            f"past_corner4_to_finish_relative_gain_lag{index + 1}",
        ):
            if values[key] is None:
                reasons[key] = (
                    "no_history_at_lag"
                    if start is None
                    else start[1].missing_reasons.get("corner4", "singleton_field")
                )
    window = positions[: context.parameters.count_window]
    values.update(
        past_corner4_relative_mean=mean(window),
        past_corner4_relative_std=std(window),
        past_corner4_valid_count=sum(x is not None for x in window),
    )
    reasons.update(
        {
            key: "no_history"
            if not starts
            else "window_contains_unmeasured_position"
            if any(x is None for x in window)
            else "insufficient_observations"
            for key, value in values.items()
            if value is None and key not in reasons
        }
    )
    return context.result(values, reasons=reasons)
