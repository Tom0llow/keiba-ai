"""Build the market characteristics intermediate feature rows and tables."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import pyarrow as pa

from features.common.audit import audit_feature_inputs
from features.common.base import FeatureBuilder
from features.common.feature_table import FeatureTableRow, IntermediateFeatureTable
from features.common.normalization import input_batches, normalize_feature_inputs
from features.common.types import (
    FeatureAudit,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureGroupInput,
    FeatureGroupSpec,
    FeatureScalar,
    FeatureValuesInput,
    _violation,
)
from features.common.validation import _feature_values_equal

SPEC = FeatureGroupSpec("F19", "market_characteristics")


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketCharacteristicsInput(FeatureValuesInput):
    """Provide explicit market characteristics values and source evidence."""


class MarketCharacteristicsBuilder(FeatureBuilder[FeatureValuesInput]):
    """Build this feature using its own normalization and shared table contract."""

    feature_name = SPEC.label

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        return _normalize_market_characteristics(records)


def build_market_characteristics(
    records: Sequence[MarketCharacteristicsInput], *, column_types: Mapping[str, pa.DataType]
) -> IntermediateFeatureTable:
    """Build a table using caller-declared column types without inferring rules."""
    return MarketCharacteristicsBuilder().build(records, column_types=column_types)


def _normalize_market_characteristics(
    records: Sequence[FeatureValuesInput],
) -> list[FeatureTableRow]:
    rows = normalize_feature_inputs(records, SPEC.feature_id, MarketCharacteristicsInput)
    batches = input_batches(records, SPEC.feature_id)
    audit = validate_market_batches(
        batches, audit_feature_inputs(batches, required_feature_ids=(SPEC.feature_id,))
    )
    if not audit.valid:
        raise FeatureBuildError(audit)
    return rows


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
    records: Sequence[FeatureBatchInput], audit: FeatureAudit
) -> FeatureAudit:
    """Check documented market columns and race-wide ticket total consistency."""
    violations = list(audit.violations)
    totals: dict[tuple[str, str], FeatureScalar] = {}
    for row_index, record in enumerate(records):
        if not isinstance(record.groups, Mapping):
            continue
        group = record.groups.get("F19")
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
                        "F19",
                        field_name,
                        "F19 market field is not allowed",
                    )
                )
            if not _is_ticket_total_field(field_name):
                continue
            key = (record.race_id, field_name)
            if key not in totals:
                totals[key] = value
            elif not _feature_values_equal(totals[key], value):
                violations.append(
                    _violation(
                        row_index,
                        record.race_id,
                        record.horse_id,
                        "F19",
                        field_name,
                        "F19 ticket total must be identical within a race",
                    )
                )
    return replace(audit, violations=tuple(violations))
