"""Build the same gate and trainer relative intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.condition_adjusted_ability import adjusted_history
from make_features.contracts.observations import CalculatedValues, Evidence
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.generation.statistics import mean
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class SameGateAndTrainerRelativeInput(FeatureValuesInput):
    """Provide explicit same gate and trainer relative values and source evidence."""


class SameGateAndTrainerRelativeBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "same_gate_and_trainer_relative"
    input_type = SameGateAndTrainerRelativeInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_same_gate_and_trainer_relative(records)


def build_same_gate_and_trainer_relative(
    records: Sequence[SameGateAndTrainerRelativeInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return SameGateAndTrainerRelativeBuilder(definition).build(records, column_types=column_types)


def _normalize_same_gate_and_trainer_relative(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_same_gate_and_trainer_relative(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Compare pre-race corrected ability with explicitly identified stable peers."""
    runners = context.source.card.runners
    target = context.runner(horse_id)
    abilities: dict[str, float | None] = {}
    dependencies: list[Evidence] = []
    for runner in runners:
        time, _, _, evidence = adjusted_history(context, runner.horse_id)
        abilities[runner.horse_id] = mean(time)
        dependencies.extend(evidence)
    values: dict[str, FeatureScalar] = {}
    reasons: dict[str, str] = {}
    for name, attribute in (("same_gate", "gate"), ("same_trainer", "trainer_id")):
        identity = getattr(target, attribute)
        unknown_peer = any(
            r.horse_id != horse_id and getattr(r, attribute) is None for r in runners
        )
        if identity is None or unknown_peer:
            values.update(
                {
                    f"{name}_{key}": None
                    for key in ("peer_count", "known_peer_count", "ability_diff", "ability_rank")
                }
            )
            reasons.update(
                {
                    f"{name}_{key}": "unknown_frozen_group_code"
                    if identity is None
                    else "unknown_peer_frozen_group_code"
                    for key in ("peer_count", "known_peer_count", "ability_diff", "ability_rank")
                }
            )
            continue
        group = [r for r in runners if getattr(r, attribute) == identity]
        peers = [abilities[r.horse_id] for r in group if r.horse_id != horse_id]
        known = [x for x in peers if x is not None]
        own = abilities[horse_id]
        allowed = context.parameters.partial_rank or len(known) == len(peers)
        values[f"{name}_peer_count"] = len(peers)
        values[f"{name}_known_peer_count"] = len(known)
        values[f"{name}_ability_diff"] = (
            own - sum(known) / len(known) if own is not None and known and allowed else None
        )
        values[f"{name}_ability_rank"] = (
            float(1 + sum(x > own for x in known)) if own is not None and allowed else None
        )
        reasons.update(
            {
                f"{name}_{key}": "missing_own_past_ability"
                if own is None
                else "no_known_peers"
                if not known
                else "incomplete_peer_abilities"
                for key in ("ability_diff", "ability_rank")
                if values[f"{name}_{key}"] is None
            }
        )
    return context.result(values, extra=dependencies, reasons=reasons)
