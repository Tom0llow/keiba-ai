"""Build the rest and condition change intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import JST, CalculationContext
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class RestAndConditionChangeInput(FeatureValuesInput):
    """Provide explicit rest and condition change values and source evidence."""


class RestAndConditionChangeBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "rest_and_condition_change"
    input_type = RestAndConditionChangeInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_rest_and_condition_change(records)


def build_rest_and_condition_change(
    records: Sequence[RestAndConditionChangeInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return RestAndConditionChangeBuilder(definition).build(records, column_types=column_types)


def _normalize_rest_and_condition_change(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_rest_and_condition_change(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Calculate calendar-day rest and changes against the actual previous start."""
    starts = context.history(horse_id, count=False)
    target = context.source.card
    values: dict[str, FeatureScalar] = {
        "days_since_previous_start": None,
        "starts_in_window_days": len(context.rolling(starts)),
        "distance_delta_m": None,
        "surface_changed": None,
        "class_transition": None,
    }
    if starts:
        previous = starts[0][0]
        values["days_since_previous_start"] = (
            target.scheduled_start_at.astimezone(JST).date()
            - previous.started_at.astimezone(JST).date()
        ).days
        values["distance_delta_m"] = target.conditions.distance_m - previous.conditions.distance_m
        if target.conditions.surface is not None and previous.conditions.surface is not None:
            values["surface_changed"] = target.conditions.surface != previous.conditions.surface
        old, new = previous.conditions.class_code, target.conditions.class_code
        classes = context.parameters.class_order
        if old in classes and new in classes:
            delta = classes.index(new) - classes.index(old)
            values["class_transition"] = "up" if delta > 0 else "down" if delta < 0 else "same"
    return context.result(
        values,
        reasons={
            key: "no_history" if not starts else "unknown_condition_or_class_mapping"
            for key, value in values.items()
            if value is None
        },
    )
