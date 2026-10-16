"""Build the market characteristics intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import pyarrow as pa

from features.contracts.rows import FeatureTableRow
from features.contracts.types import (
    FeatureAudit,
    FeatureBatchInput,
    FeatureDefinition,
    FeatureGroupInput,
    FeatureScalar,
    FeatureValuesInput,
    _violation,
)
from features.generation.base import RegisteredFeatureBuilder
from features.generation.normalization import normalize_audited_feature_inputs
from features.tables.schema import IntermediateFeatureTable
from features.validation.values import feature_values_equal


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


_ALLOWED_MARKET_FIELD_NAMES = frozenset(
    {
        "marketlogoddschange",
        "marketoddsratio",
        "marketpairsupporti",
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
