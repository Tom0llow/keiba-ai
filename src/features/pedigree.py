"""Build the string-valued pedigree intermediate feature table."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from features.feature_table import (
    FeatureTableRow,
    IntermediateFeatureTable,
    build_feature_table,
    validate_common_row,
)


@dataclass(frozen=True, slots=True)
class PedigreeInput:
    """Provide one horse's explicit sire and broodmare sire identifiers."""

    race_id: str
    horse_id: str
    freeze_at: datetime
    available_at: datetime | None
    sire: str | None
    broodmare_sire: str | None


PedigreeRecord = PedigreeInput


def build_pedigree(records: Sequence[PedigreeInput]) -> IntermediateFeatureTable:
    """Build pedigree columns as strings without category encoding."""
    rows: list[FeatureTableRow] = []
    for record in records:
        if not isinstance(record, PedigreeInput):
            raise TypeError("records must contain PedigreeInput values")
        if record.sire is not None and not isinstance(record.sire, str):
            raise TypeError("sire must be a string or None")
        if record.broodmare_sire is not None and not isinstance(record.broodmare_sire, str):
            raise TypeError("broodmare_sire must be a string or None")
        value = record.sire if record.sire is not None else record.broodmare_sire
        freeze_at, available_at = validate_common_row(
            record.race_id,
            record.horse_id,
            record.freeze_at,
            record.available_at,
            value,
            "pedigree",
        )
        if (record.sire is not None or record.broodmare_sire is not None) and available_at is None:
            raise ValueError("non-missing pedigree values require available_at")
        rows.append(
            FeatureTableRow(
                record.race_id,
                record.horse_id,
                freeze_at,
                available_at,
                {"sire": record.sire, "broodmare_sire": record.broodmare_sire},
            )
        )
    return build_feature_table("pedigree", rows)


def build_pedigree_table(records: Sequence[PedigreeInput]) -> IntermediateFeatureTable:
    """Build the pedigree feature table."""
    return build_pedigree(records)


__all__ = [
    "PedigreeInput",
    "PedigreeRecord",
    "build_pedigree",
    "build_pedigree_table",
]
