"""Build the market characteristics intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import combinations
from math import isfinite, log

import pyarrow as pa

from make_features.contracts.observations import CalculatedValues, MarketObservation
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import (
    FeatureAudit,
    FeatureBatchInput,
    FeatureDefinition,
    FeatureGroupInput,
    FeatureScalar,
    FeatureValuesInput,
    _violation,
)
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.normalization import normalize_audited_feature_inputs
from make_features.generation.observations import CalculationContext
from make_features.tables.schema import IntermediateFeatureTable
from make_features.validation.observations import (
    publication_clock,
    select_versions,
    validate_evidence,
)
from make_features.validation.values import feature_values_equal


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketCharacteristicsInput(FeatureValuesInput):
    """Provide explicit market characteristics values and source evidence."""


class MarketCharacteristicsBuilder(RegisteredFeatureBuilder):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = "market_characteristics"
    input_type = MarketCharacteristicsInput

    def audit_batches(
        self, records: Sequence[FeatureBatchInput], audit: FeatureAudit
    ) -> FeatureAudit:
        """Append market-field and race-wide ticket-total checks."""
        return validate_market_batches(records, audit, feature_id=self.definition.feature_id)

    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_market_characteristics(records)


def build_market_characteristics(
    records: Sequence[MarketCharacteristicsInput],
    *,
    definition: FeatureDefinition,
    column_types: Mapping[str, pa.DataType],
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return MarketCharacteristicsBuilder(definition).build(records, column_types=column_types)


def _normalize_market_characteristics(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    return normalize_audited_feature_inputs(records)


def _market_at(context: CalculationContext, anchor: datetime) -> MarketObservation:
    candidates = []
    for market in context.markets:
        validate_evidence(market.pair_evidence)
        if max(market.evidence.available_at, market.pair_evidence.available_at) <= anchor:
            candidates.append(market)
    if not candidates:
        raise ValueError(
            f"market anchor {anchor.isoformat()} has no received normalized observation"
        )
    candidates = list(select_versions(candidates, lambda m: m.evidence.observation_id, anchor))
    candidates.sort(
        key=lambda m: max(publication_clock(m.evidence), publication_clock(m.pair_evidence)),
        reverse=True,
    )
    chosen = candidates[0]
    if len(candidates) > 1 and max(
        publication_clock(chosen.evidence), publication_clock(chosen.pair_evidence)
    ) == max(
        publication_clock(candidates[1].evidence), publication_clock(candidates[1].pair_evidence)
    ):
        raise ValueError("market anchor has ambiguous simultaneous observations")
    if (
        anchor - min(publication_clock(chosen.evidence), publication_clock(chosen.pair_evidence))
    ).total_seconds() > context.parameters.market_max_age_seconds:
        raise ValueError("market anchor observation exceeds explicit maximum age")
    if (
        abs(
            (
                publication_clock(chosen.evidence) - publication_clock(chosen.pair_evidence)
            ).total_seconds()
        )
        > context.parameters.market_version_tolerance_seconds
    ):
        raise ValueError("horse and pair market publication versions are inconsistent")
    return chosen


def _market_values(
    context: CalculationContext, market: MarketObservation, horse_id: str
) -> dict[str, FeatureScalar]:
    target = set(context.source.card.expected_horse_ids)
    quotes = {quote.horse_id: quote for quote in market.horses}
    if (
        len(quotes) != len(market.horses)
        or not set(quotes) <= target
        or len(set(market.sale_horse_ids)) != len(market.sale_horse_ids)
        or not set(market.sale_horse_ids) <= target
    ):
        raise ValueError("market quotes/sale set contain duplicate or unknown horse IDs")
    for quote in market.horses:
        for number in (quote.win, quote.place_low, quote.place_high):
            if number is not None and (not isfinite(number) or number <= 0):
                raise ValueError("market decimal odds must be finite and positive")
        if (
            quote.place_low is not None
            and quote.place_high is not None
            and quote.place_low > quote.place_high
        ):
            raise ValueError("place odds low must not exceed high")
    own = quotes.get(horse_id)
    complete = set(quotes) == target == set(market.sale_horse_ids) and all(
        q.win is not None for q in quotes.values()
    )
    support, rank = None, None
    if complete and own and own.win is not None:
        denominator = sum(1 / q.win for q in quotes.values() if q.win is not None)
        support = (1 / own.win) / denominator
        rank = float(1 + sum(q.win < own.win for q in quotes.values() if q.win is not None))
    all_pairs = {tuple(sorted(pair)) for pair in combinations(target, 2)}
    sale = [tuple(sorted(pair)) for pair in market.sale_pairs]
    pairs = {tuple(sorted(pair.horse_ids)): pair.odds for pair in market.pairs}
    if (
        len(sale) != len(set(sale))
        or len(pairs) != len(market.pairs)
        or not set(sale) <= all_pairs
        or not pairs.keys() <= all_pairs
    ):
        raise ValueError("market contains duplicate, self or unknown horse pairs")
    for odd in pairs.values():
        if odd is not None and (not isfinite(odd) or odd <= 0):
            raise ValueError("pair odds must be finite and positive")
    pair_support = None
    pair_count = sum(horse_id in pair and odds is not None for pair, odds in pairs.items())
    if (
        all_pairs
        and pairs.keys() == all_pairs == set(sale)
        and all(o is not None for o in pairs.values())
    ):
        total = sum(1 / o for o in pairs.values() if o is not None)
        pair_support = sum(
            1 / o for pair, o in pairs.items() if horse_id in pair and o is not None
        ) / (2 * total)
    return {
        "market_win_odds": own.win if own else None,
        "market_place_low": own.place_low if own else None,
        "market_place_high": own.place_high if own else None,
        "market_place_width": own.place_high - own.place_low
        if own and own.place_high is not None and own.place_low is not None
        else None,
        "market_win_support": support,
        "market_win_rank": rank,
        "market_pair_support_i": pair_support,
        "market_pair_known_opponent_count": pair_count,
        "market_complete_win_set": complete,
        "market_complete_pair_set": pairs.keys() == all_pairs == set(sale)
        and all(o is not None for o in pairs.values()),
    }


def calculate_market_characteristics(
    context: CalculationContext, horse_id: str
) -> CalculatedValues:
    """Compare received anchor markets without using final odds or inventing votes."""
    coverage = context.require_coverage("market")
    anchor = context.cutoff - timedelta(seconds=context.parameters.market_anchor_seconds)
    old, current = _market_at(context, anchor), _market_at(context, context.cutoff)
    before, values = (
        _market_values(context, old, horse_id),
        _market_values(context, current, horse_id),
    )
    old_odds, odds = before["market_win_odds"], values["market_win_odds"]
    values["market_odds_ratio"] = (
        odds / old_odds
        if isinstance(odds, (int, float)) and isinstance(old_odds, (int, float))
        else None
    )
    values["market_log_odds_change"] = (
        log(odds / old_odds)
        if isinstance(odds, (int, float)) and isinstance(old_odds, (int, float))
        else None
    )
    old_rank, rank = before["market_win_rank"], values["market_win_rank"]
    values["market_rank_change"] = (
        rank - old_rank if isinstance(rank, float) and isinstance(old_rank, float) else None
    )
    allowed = {"tansyo", "fukusyo", "wakuren", "umaren"}
    if (
        not current.ticket_totals.keys() == old.ticket_totals.keys()
        or current.ticket_totals.keys() - allowed
    ):
        raise ValueError("anchor ticket types must match explicit supported sale totals")
    for kind in current.ticket_totals:
        a, b = old.ticket_totals[kind], current.ticket_totals[kind]
        if type(a) is not int or type(b) is not int or a < 0 or b < a:
            raise ValueError("ticket total decrease/correction requires an explicit policy")
        values[f"ticket_total_{kind}"] = b
        values[f"ticket_total_growth_{kind}"] = b - a
        values[f"ticket_total_growth_rate_{kind}"] = (b - a) / a if a else None
    return context.result(
        values,
        include_history=False,
        reasons={
            key: "zero_anchor_total"
            if key.startswith("ticket_total_growth_rate_")
            else "incomplete_sale_set_or_unpublished_quote"
            for key, value in values.items()
            if value is None
        },
        extra=[
            coverage.evidence,
            old.evidence,
            old.pair_evidence,
            current.evidence,
            current.pair_evidence,
        ],
        diagnostics={
            "anchor0": anchor.isoformat(),
            "anchor1": context.cutoff.isoformat(),
            "observed0": publication_clock(old.evidence).isoformat(),
            "observed1": publication_clock(current.evidence).isoformat(),
            "observed_elapsed_seconds": (
                publication_clock(current.evidence) - publication_clock(old.evidence)
            ).total_seconds(),
        },
    )


_ALLOWED_MARKET_FIELD_NAMES = frozenset(
    {
        "marketlogoddschange",
        "marketoddsratio",
        "marketpairsupporti",
        "marketpairknownopponentcount",
        "marketcompletewinset",
        "marketcompletepairset",
        "marketrankchange",
        "marketplacelow",
        "marketplacehigh",
        "marketplacewidth",
        "marketwinodds",
        "marketwinsupport",
        "marketwinrank",
    }
)
_MARKET_TICKET_TYPES = frozenset({"fukusyo", "tansyo", "umaren", "wakuren"})


def _is_allowed_market_field(field_name: str) -> bool:
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    if normalized in _ALLOWED_MARKET_FIELD_NAMES:
        return True
    return _is_ticket_total_field(field_name)


def _is_ticket_total_field(field_name: str) -> bool:
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    return any(
        normalized
        in {
            f"tickettotal{ticket_type}",
            f"tickettotalgrowth{ticket_type}",
            f"tickettotalgrowthrate{ticket_type}",
        }
        for ticket_type in _MARKET_TICKET_TYPES
    )


def validate_market_batches(
    records: Sequence[FeatureBatchInput], audit: FeatureAudit, *, feature_id: str
) -> FeatureAudit:
    """Check documented market columns and race-wide ticket total consistency."""
    violations = list(audit.violations)
    totals: dict[tuple[str, str], FeatureScalar] = {}
    for row_index, record in enumerate(records):
        if not isinstance(record.groups, Mapping):
            continue
        group = record.groups.get(feature_id)
        if not isinstance(group, FeatureGroupInput) or not isinstance(group.values, Mapping):
            continue
        for field_name, value in group.values.items():
            if not isinstance(field_name, str):
                continue
            if not _is_allowed_market_field(field_name):
                violations.append(
                    _violation(
                        row_index,
                        record.race_id,
                        record.horse_id,
                        feature_id,
                        field_name,
                        f"{feature_id} market field is not allowed",
                    )
                )
            if not _is_ticket_total_field(field_name):
                continue
            key = (record.race_id, field_name)
            if key not in totals:
                totals[key] = value
            elif not feature_values_equal(totals[key], value):
                violations.append(
                    _violation(
                        row_index,
                        record.race_id,
                        record.horse_id,
                        feature_id,
                        field_name,
                        f"{feature_id} ticket total must be identical within a race",
                    )
                )
    return replace(audit, violations=tuple(violations))
