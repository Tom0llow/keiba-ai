"""Build the past racing ability intermediate feature rows and tables."""

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
from make_features.generation.statistics import relative, relative_values
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class PastRacingAbilityInput(FeatureValuesInput):
    """Provide explicit past racing ability values and source evidence."""


class PastRacingAbilityBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "past_racing_ability"
    input_type = PastRacingAbilityInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_past_racing_ability(records)


def build_past_racing_ability(
    records: Sequence[PastRacingAbilityInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return PastRacingAbilityBuilder(definition).build(records, column_types=column_types)


def _normalize_past_racing_ability(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_past_racing_ability(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Calculate speeds, signed margins and within-past-race closing ranks."""
    starts = context.history(horse_id, count=False)
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    for index in range(context.parameters.lag_count):
        suffix = f"_lag{index + 1}"
        start = starts[index] if index < len(starts) else None
        row: dict[str, FeatureScalar] = {
            key: None
            for key in (
                "elapsed_sec",
                "signed_gap_sec",
                "velocity_mps",
                "last3f_sec",
                "last3f_rank",
                "last3f_relative",
                "last3f_known_count",
            )
        }
        if start:
            race, runner = start
            measured = [r.last3f_sec for r in race.runners]
            compared = relative_values(
                measured,
                race.runners.index(runner),
                higher=False,
                partial=context.parameters.partial_rank,
            )
            row.update(
                elapsed_sec=runner.elapsed_sec,
                signed_gap_sec=runner.signed_gap_sec,
                velocity_mps=race.conditions.distance_m / runner.elapsed_sec
                if runner.elapsed_sec
                else None,
                last3f_sec=runner.last3f_sec,
                last3f_rank=compared["rank"],
                last3f_relative=relative(int(compared["rank"]), int(compared["known_count"]))
                if isinstance(compared["rank"], float) and isinstance(compared["known_count"], int)
                else None,
                last3f_known_count=compared["known_count"],
            )
        values.update({f"past_{key}{suffix}": value for key, value in row.items()})
        for key, value in row.items():
            if value is None:
                source_field = (
                    "elapsed_sec"
                    if key == "velocity_mps"
                    else "last3f_sec"
                    if key.startswith("last3f_")
                    else key
                )
                reasons[f"past_{key}{suffix}"] = (
                    start[1].missing_reasons.get(source_field, "incomplete_comparison_or_singleton")
                    if start
                    else "no_history_at_lag"
                )
    return context.result(values, reasons=reasons)
