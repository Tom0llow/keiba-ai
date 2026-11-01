"""Build the basic conditions and weight intermediate feature rows and tables."""

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
class BasicConditionsAndWeightInput(FeatureValuesInput):
    """Provide explicit basic conditions and weight values and source evidence."""


class BasicConditionsAndWeightBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "basic_conditions_and_weight"
    input_type = BasicConditionsAndWeightInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_basic_conditions_and_weight(records)


def build_basic_conditions_and_weight(
    records: Sequence[BasicConditionsAndWeightInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return BasicConditionsAndWeightBuilder(definition).build(records, column_types=column_types)


def _normalize_basic_conditions_and_weight(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_basic_conditions_and_weight(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Retain decoded card values and calculate previous-start weight difference."""
    runner = context.runner(horse_id)
    card = context.source.card
    starts = context.history(horse_id, count=False)
    previous = starts[0][1].carried_weight_kg if starts else None
    values: dict[str, FeatureScalar] = {
        "race_distance_m": card.conditions.distance_m,
        "horse_age_years": runner.age_years,
        "gate_number": runner.gate,
        "horse_number": runner.horse_number,
        "sex": runner.sex,
        "carried_weight_kg": runner.carried_weight_kg,
        "carried_weight_delta_kg": runner.carried_weight_kg - previous
        if runner.carried_weight_kg is not None and previous is not None
        else None,
        "frozen_field_size": len(card.runners),
    }
    values.update(
        {
            key: getattr(card.conditions, key)
            for key in ("surface", "venue", "course", "going", "class_code")
        }
    )
    reasons = {
        key: "unknown_in_frozen_observation" for key, value in values.items() if value is None
    }
    if values["carried_weight_delta_kg"] is None:
        reasons["carried_weight_delta_kg"] = (
            "no_history"
            if not starts
            else starts[0][1].missing_reasons.get(
                "carried_weight_kg", "unknown_frozen_carried_weight"
            )
        )
    return context.result(values, reasons=reasons)
