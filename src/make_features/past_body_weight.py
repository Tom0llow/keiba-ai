"""Build the past body weight intermediate feature rows and tables."""

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
from make_features.generation.statistics import mean, std
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class PastBodyWeightInput(FeatureValuesInput):
    """Provide explicit past body weight values and source evidence."""


class PastBodyWeightBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "past_body_weight"
    input_type = PastBodyWeightInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_past_body_weight(records)


def build_past_body_weight(
    records: Sequence[PastBodyWeightInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return PastBodyWeightBuilder(definition).build(records, column_types=column_types)


def _normalize_past_body_weight(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_past_body_weight(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Calculate past measured-weight lags and complete-window spread and ratios."""
    starts = context.history(horse_id, count=False)
    weights = [s[1].body_weight_kg for s in starts[: context.parameters.count_window]]
    latest = starts[0][1].body_weight_kg if starts else None
    previous = starts[1][1].body_weight_kg if len(starts) > 1 else None
    average = mean(weights)
    values: dict[str, FeatureScalar] = {
        "past_weight_lag1_kg": latest,
        "past_weight_delta_last2_kg": latest - previous
        if latest is not None and previous is not None
        else None,
        "past_weight_mean_kg": average,
        "past_weight_std_kg": std(weights),
        "past_weight_vs_mean_kg": latest - average
        if latest is not None and average is not None
        else None,
        "past_weight_ratio_mean": latest / average
        if latest is not None and average is not None and average > 0
        else None,
        "past_weight_valid_count": sum(x is not None for x in weights),
    }
    reasons = {
        key: "no_history"
        if not starts
        else "window_contains_unmeasured_weight"
        if any(x is None for x in weights)
        else "insufficient_weight_observations"
        for key, value in values.items()
        if value is None
    }
    if starts and latest is None:
        reasons["past_weight_lag1_kg"] = starts[0][1].missing_reasons["body_weight_kg"]
    return context.result(values, reasons=reasons)
