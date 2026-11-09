"""Build the pedigree suitability intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext, Start
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class PedigreeSuitabilityInput(FeatureValuesInput):
    """Provide explicit pedigree suitability values and source evidence."""


class PedigreeSuitabilityBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "pedigree_suitability"
    input_type = PedigreeSuitabilityInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_pedigree_suitability(records)


def build_pedigree_suitability(
    records: Sequence[PedigreeSuitabilityInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return PedigreeSuitabilityBuilder(definition).build(records, column_types=column_types)


def _normalize_pedigree_suitability(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_pedigree_suitability(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Aggregate normalized parent-linked offspring starts under explicit self policy."""
    coverage = context.require_coverage("pedigree")
    context.require_coverage("history")
    if not context.pedigrees_cover_population():
        raise ValueError(
            "pedigree coverage claims complete but normalized horse mappings are absent"
        )
    target = context.pedigrees.get(horse_id)
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    for parent in ("sire", "broodmare_sire"):
        identity = getattr(target, parent) if target else None
        # The rolling window of all matching history equals the matching window population.
        selected: list[Start] = (
            [
                start
                for start in context.parent_window(parent, identity)
                if context.parameters.pedigree_include_self or start[1].horse_id != horse_id
            ]
            if identity is not None
            else []
        )
        unknown_parent = identity is None or context.population_unknown_parent(parent, horse_id)
        starts = context.matching_starts(context.rolling(selected)) if not unknown_parent else None
        values.update(
            {
                f"{parent}_condition_{key}": value
                for key, value in context.performance(starts, conditioned=True).items()
            }
        )
        values[f"{parent}_condition_offspring_count"] = (
            len({s[1].horse_id for s in starts}) if starts is not None else None
        )
        reasons.update(
            {
                key: "unknown_normalized_parent"
                if unknown_parent
                else "unknown_condition"
                if starts is None
                else "no_condition_offspring_history"
                if not starts
                else "undefined_prior"
                for key, value in values.items()
                if key.startswith(parent) and value is None
            }
        )
    return context.result(
        values,
        extra=[coverage.evidence, *context.pedigree_evidence()],
        reasons=reasons,
    )
