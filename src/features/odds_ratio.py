"""Build the explicit-odds-ratio intermediate feature table."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, isnan

from features.contracts.rows import FeatureTableRow
from features.generation.base import FeatureBuilder
from features.tables.schema import IntermediateFeatureTable
from features.validation.table import validate_common_row


@dataclass(frozen=True, slots=True)
class OddsRatioInput:
    """Provide one horse's explicit odds and reference odds."""

    race_id: str
    horse_id: str
    freeze_at: datetime
    available_at: datetime | None
    odds: float | None
    reference_odds: float | None


OddsRatioRecord = OddsRatioInput


class OddsRatioBuilder(FeatureBuilder[OddsRatioInput]):
    """Generate normalized rows using the shared intermediate-table builder."""

    feature_name = "odds_ratio"

    def _build_rows(self, records: Sequence[OddsRatioInput]) -> list[FeatureTableRow]:
        rows: list[FeatureTableRow] = []
        for record in records:
            if not isinstance(record, OddsRatioInput):
                raise TypeError("records must contain OddsRatioInput values")
            odds = _normalize_odds(record.odds, "odds")
            reference_odds = _normalize_odds(record.reference_odds, "reference_odds")
            ratio = None if odds is None or reference_odds is None else odds / reference_odds
            if ratio is not None and not isfinite(ratio):
                raise ValueError("odds_ratio must be finite")
            freeze_at, available_at = validate_common_row(
                record.race_id,
                record.horse_id,
                record.freeze_at,
                record.available_at,
                ratio,
                "odds_ratio",
            )
            rows.append(
                FeatureTableRow(
                    record.race_id,
                    record.horse_id,
                    freeze_at,
                    available_at,
                    {"odds_ratio": ratio},
                )
            )
        return rows


def build_odds_ratio(records: Sequence[OddsRatioInput]) -> IntermediateFeatureTable:
    """Build this feature through the shared intermediate-table contract."""
    return OddsRatioBuilder().build(records)


def build_odds_ratio_table(records: Sequence[OddsRatioInput]) -> IntermediateFeatureTable:
    """Build the odds-ratio feature table."""
    return build_odds_ratio(records)


def _normalize_odds(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a positive number or None")
    normalized = float(value)
    if isnan(normalized):
        return None
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} must be positive")
    return normalized


__all__ = [
    "OddsRatioInput",
    "OddsRatioRecord",
    "build_odds_ratio",
    "build_odds_ratio_table",
]
