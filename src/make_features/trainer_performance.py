"""Build the trainer performance intermediate feature rows and tables."""

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
class TrainerPerformanceInput(FeatureValuesInput):
    """Provide explicit trainer performance values and source evidence."""


class TrainerPerformanceBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "trainer_performance"
    input_type = TrainerPerformanceInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_trainer_performance(records)


def build_trainer_performance(
    records: Sequence[TrainerPerformanceInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return TrainerPerformanceBuilder(definition).build(records, column_types=column_types)


def _normalize_trainer_performance(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_trainer_performance(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Count each horse start under its trainer at that historical start."""
    context.require_coverage("history")
    identity = context.runner(horse_id).trainer_id
    starts = context.trainer_window(identity) if identity else ()
    values: dict[str, FeatureScalar] = {}
    for label, group in (
        ("trainer", starts if identity else None),
        ("trainer_condition", context.matching_starts(starts) if identity else None),
    ):
        values.update(
            {
                f"{label}_{key}": value
                for key, value in context.performance(
                    group, conditioned=label.endswith("_condition")
                ).items()
            }
        )
    if any(r.trainer_id is None for _, r in context.population):
        values = dict.fromkeys(values)
    return context.result(
        values,
        reasons={
            key: "unknown_trainer_in_frozen_or_historical_observation"
            if identity is None or any(r.trainer_id is None for _, r in context.population)
            else "no_trainer_or_condition_history"
            for key, value in values.items()
            if value is None
        },
    )
