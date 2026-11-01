"""Build the past lap and running style intermediate feature rows and tables."""

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
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class PastLapAndRunningStyleInput(FeatureValuesInput):
    """Provide explicit past lap and running style values and source evidence."""


class PastLapAndRunningStyleBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "past_lap_and_running_style"
    input_type = PastLapAndRunningStyleInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_past_lap_and_running_style(records)


def build_past_lap_and_running_style(
    records: Sequence[PastLapAndRunningStyleInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return PastLapAndRunningStyleBuilder(definition).build(records, column_types=column_types)


def _normalize_past_lap_and_running_style(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_past_lap_and_running_style(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Split past race sections only at a measured halfway distance boundary."""
    starts = context.history(horse_id, count=False)
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    for index in range(context.parameters.lag_count):
        row: dict[str, FeatureScalar] = {
            "race_early_velocity_mps": None,
            "race_late_velocity_mps": None,
            "pace_velocity_gap_mps": None,
            "last3f_vs_race_sec": None,
        }
        if index < len(starts):
            race, runner = starts[index]
            cumulative = 0
            boundary = None
            for i, section in enumerate(race.sections):
                cumulative += section.distance_m
                if 2 * cumulative == race.conditions.distance_m:
                    boundary = i + 1
            if boundary is not None and all(s.seconds is not None for s in race.sections):
                early_seconds = sum(
                    s.seconds for s in race.sections[:boundary] if s.seconds is not None
                )
                late_seconds = sum(
                    s.seconds for s in race.sections[boundary:] if s.seconds is not None
                )
                if early_seconds > 0 and late_seconds > 0:
                    early = (race.conditions.distance_m / 2) / early_seconds
                    late = (race.conditions.distance_m / 2) / late_seconds
                    row.update(
                        race_early_velocity_mps=early,
                        race_late_velocity_mps=late,
                        pace_velocity_gap_mps=early - late,
                    )
            else:
                reasons[f"past_race_early_velocity_mps_lag{index + 1}"] = (
                    "unmeasured_or_no_exact_halfway_boundary"
                )
            if (
                runner.last3f_sec is not None
                and race.race_last3f_sec is not None
                and runner.last3f_distance_m == race.race_last3f_distance_m
                and runner.last3f_distance_m is not None
            ):
                row["last3f_vs_race_sec"] = runner.last3f_sec - race.race_last3f_sec
            else:
                reasons[f"past_last3f_vs_race_sec_lag{index + 1}"] = (
                    "unmeasured_or_incompatible_closing_distance"
                )
        values.update({f"past_{key}_lag{index + 1}": value for key, value in row.items()})
        for key, value in row.items():
            if value is None and f"past_{key}_lag{index + 1}" not in reasons:
                reasons[f"past_{key}_lag{index + 1}"] = (
                    "no_history_at_lag"
                    if index >= len(starts)
                    else "unmeasured_or_no_exact_halfway_boundary"
                )
    return context.result(values, reasons=reasons)
