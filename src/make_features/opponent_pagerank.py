"""Build the opponent pagerank intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.tables.schema import IntermediateFeatureTable


@dataclass(frozen=True, slots=True, kw_only=True)
class OpponentPagerankInput(FeatureValuesInput):
    """Provide explicit opponent pagerank values and source evidence."""


class OpponentPagerankBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "opponent_pagerank"
    input_type = OpponentPagerankInput

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_opponent_pagerank(records)


def build_opponent_pagerank(
    records: Sequence[OpponentPagerankInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return OpponentPagerankBuilder(definition).build(records, column_types=column_types)


def _normalize_opponent_pagerank(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def calculate_opponent_pagerank(context: CalculationContext, horse_id: str) -> CalculatedValues:
    """Fit a sparse loser-to-better graph and fail if PageRank does not converge."""
    if horse_id in context.pagerank_results:
        return context.pagerank_results[horse_id]
    context.require_coverage("history")
    p = context.parameters
    starts = context.rolling(
        tuple((race, r) for race in context.races for r in race.runners), p.graph_days
    )
    races = {race.race_id: race for race, _ in starts}
    nodes = sorted({r.horse_id for race in races.values() for r in race.runners})
    edges: dict[str, dict[str, float]] = {node: {} for node in nodes}
    counts = {node: 0 for node in nodes}
    opponents: dict[str, set[str]] = {node: set() for node in nodes}
    for race in races.values():
        size = len(race.runners)
        age = (context.cutoff - race.started_at).total_seconds() / 86400
        weight = 2 ** (-age / p.graph_half_life_days) if p.graph_half_life_days is not None else 1.0
        if weight == 0:
            raise ValueError(
                "graph time decay underflow; choose an explicit supported range/half-life"
            )
        if p.graph_base_weight == "inverse_field_minus_one" and size > 1:
            weight /= size - 1
        for runner in race.runners:
            counts[runner.horse_id] += 1
            opponents[runner.horse_id].update(
                r.horse_id for r in race.runners if r.horse_id != runner.horse_id
            )
            for better in race.runners:
                if better.finish < runner.finish and (
                    p.graph_edge_rule == "all_pairs" or better.finish == 1
                ):
                    adjacent = edges[runner.horse_id]
                    adjacent[better.horse_id] = adjacent.get(better.horse_id, 0.0) + weight
    n = len(nodes)
    distribution = {node: 1 / n for node in nodes}
    residual = 0.0
    iterations = 0
    if nodes:
        for iteration in range(1, p.graph_max_iterations + 1):
            iterations = iteration
            updated = {node: (1 - p.graph_damping) / n for node in nodes}
            dangling = 0.0
            for node in nodes:
                total = sum(edges[node].values())
                if not total:
                    dangling += distribution[node]
                else:
                    for destination, weight in edges[node].items():
                        updated[destination] += (
                            p.graph_damping * distribution[node] * weight / total
                        )
            for node in nodes:
                updated[node] += p.graph_damping * dangling / n
            residual = sum(abs(updated[node] - distribution[node]) for node in nodes)
            distribution = updated
            if residual <= p.graph_tolerance:
                break
        else:
            raise ValueError(
                f"PageRank did not converge after {iterations} iterations; residual={residual}"
            )
    for identity in {horse_id, *context.source.card.expected_horse_ids}:
        context.pagerank_results[identity] = context.result(
            {
                "opponent_graph_score": distribution.get(identity),
                "opponent_graph_known": identity in distribution,
                "opponent_graph_start_count": counts.get(identity, 0),
                "unique_opponent_count": len(opponents.get(identity, set())),
            },
            reasons={"opponent_graph_score": "unknown_horse"}
            if identity not in distribution
            else {},
            diagnostics={
                "node_count": n,
                "edge_count": sum(len(e) for e in edges.values()),
                "iterations": iterations,
                "residual": residual,
                "score_sum": sum(distribution.values()),
                "graph_cutoff": context.cutoff.isoformat(),
            },
        )
    return context.pagerank_results[horse_id]
