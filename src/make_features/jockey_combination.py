"""Build the jockey combination intermediate feature rows and tables."""

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
class JockeyCombinationInput(FeatureValuesInput):
    """Provide explicit jockey combination values and source evidence."""


class JockeyCombinationBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "jockey_combination"
    input_type = JockeyCombinationInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_jockey_combination(records)


def build_jockey_combination(
    records: Sequence[JockeyCombinationInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return JockeyCombinationBuilder(definition).build(records, column_types=column_types)


def _normalize_jockey_combination(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_jockey_combination(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Calculate combination counts, horse-denominator frequency and rider change."""
    target = context.runner(horse_id)
    all_starts = context.history(horse_id, count=False)
    horse_starts = context.rolling(all_starts)
    horse_assignment_unknown = any(s[1].jockey_id is None for s in horse_starts)
    combination = (
        tuple(s for s in horse_starts if s[1].jockey_id == target.jockey_id)
        if target.jockey_id and not horse_assignment_unknown
        else None
    )
    population = context.population
    pair_assignment_unknown = any(
        r.jockey_id in (None, target.jockey_id)
        and r.trainer_id in (None, target.trainer_id)
        and (r.jockey_id is None or r.trainer_id is None)
        for _, r in population
    )
    pair = (
        context.rolling(
            tuple(
                (race, r)
                for race, r in population
                if r.jockey_id == target.jockey_id and r.trainer_id == target.trainer_id
            )
        )
        if target.jockey_id and target.trainer_id and not pair_assignment_unknown
        else None
    )
    values: dict[str, FeatureScalar] = {}
    for name, starts in (("horse_jockey", combination), ("jockey_trainer", pair)):
        values.update(
            {f"{name}_{key}": value for key, value in context.performance(starts).items()}
        )
    values["horse_jockey_frequency"] = (
        len(combination) / len(horse_starts) if combination is not None and horse_starts else None
    )
    values["jockey_changed_since_previous"] = (
        target.jockey_id != all_starts[0][1].jockey_id
        if target.jockey_id and all_starts and all_starts[0][1].jockey_id
        else None
    )
    return context.result(
        values,
        reasons={
            key: "unknown_jockey_or_trainer"
            if not target.jockey_id or not target.trainer_id
            else "unknown_historical_assignment"
            if (
                (key.startswith("horse_jockey") and horse_assignment_unknown)
                or (key.startswith("jockey_trainer") and pair_assignment_unknown)
            )
            else "no_history"
            if not all_starts
            else "no_prior_combination_or_missing_historical_assignment"
            for key, value in values.items()
            if value is None
        },
    )
