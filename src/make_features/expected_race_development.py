"""Build the expected race development intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureScalar, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.generation.statistics import relative
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpectedRaceDevelopmentInput(FeatureValuesInput):
    """Provide explicit expected race development values and source evidence."""


class ExpectedRaceDevelopmentBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "expected_race_development"
    input_type = ExpectedRaceDevelopmentInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_expected_race_development(records)


def build_expected_race_development(
    records: Sequence[ExpectedRaceDevelopmentInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return ExpectedRaceDevelopmentBuilder(definition).build(records, column_types=column_types)


def _normalize_expected_race_development(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_expected_race_development(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Infer exclusive styles from past corners and count frozen-field opponents."""
    styles: dict[str, str] = {}
    for runner in context.source.card.runners:
        starts = context.history(runner.horse_id, count=False)[: context.parameters.style_window]
        corners = [r.corner4 for _, r in starts]
        positions = [
            relative(r.corner4, len(race.runners)) if r.corner4 else None for race, r in starts
        ]
        style = "unknown"
        if len(starts) >= context.parameters.style_minimum_count and all(
            p is not None for p in positions
        ):
            leader_share = sum(c == 1 for c in corners) / len(starts)
            if leader_share >= context.parameters.leader_threshold:
                style = "leader"
            elif (
                median([p for p in positions if p is not None])
                <= context.parameters.front_threshold
            ):
                style = "front"
            else:
                style = "other"
        styles[runner.horse_id] = style
    peers = [style for identity, style in styles.items() if identity != horse_id]
    known = sum(style != "unknown" for style in peers)
    values: dict[str, FeatureScalar] = {
        "pre_race_style": styles[horse_id],
        "field_leader_count": list(styles.values()).count("leader"),
        "field_front_count": list(styles.values()).count("front"),
        "style_unknown_count": list(styles.values()).count("unknown"),
        "opponent_leader_count": peers.count("leader"),
        "opponent_front_count": peers.count("front"),
        "opponent_unknown_count": peers.count("unknown"),
        "opponent_known_count": known,
        "opponent_front_share": sum(s in {"leader", "front"} for s in peers) / known
        if known
        else None,
    }
    return context.result(
        values, reasons={"opponent_front_share": "no_known_opponent_styles"} if not known else {}
    )
