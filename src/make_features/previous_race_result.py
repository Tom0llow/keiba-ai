"""Build the previous-race-result intermediate feature table."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from make_features.contracts.rows import FeatureTableRow
from make_features.generation.base import FeatureBuilder
from make_features.tables.schema import IntermediateFeatureTable
from make_features.validation.table import validate_common_row


@dataclass(frozen=True, slots=True)
class PreviousRaceResultInput:
    """Provide one horse's explicit previous-race result input."""

    race_id: str
    horse_id: str
    freeze_at: datetime
    available_at: datetime | None
    previous_finish_position: int | None


PreviousRaceResultRecord = PreviousRaceResultInput


class PreviousRaceResultBuilder(FeatureBuilder[PreviousRaceResultInput]):
    """Generate normalized rows using the shared intermediate-table builder."""

    feature_name = "previous_race_result"

    def _build_rows(self, records: Sequence[PreviousRaceResultInput]) -> list[FeatureTableRow]:
        rows: list[FeatureTableRow] = []
        for record in records:
            if not isinstance(record, PreviousRaceResultInput):
                raise TypeError("records must contain PreviousRaceResultInput values")
            freeze_at, available_at = validate_common_row(
                record.race_id,
                record.horse_id,
                record.freeze_at,
                record.available_at,
                record.previous_finish_position,
                "previous_race_finish_position",
            )
            if record.previous_finish_position is not None and (
                isinstance(record.previous_finish_position, bool)
                or not isinstance(record.previous_finish_position, int)
            ):
                raise TypeError("previous_finish_position must be an integer or None")
            rows.append(
                FeatureTableRow(
                    record.race_id,
                    record.horse_id,
                    freeze_at,
                    available_at,
                    {"previous_race_finish_position": record.previous_finish_position},
                )
            )
        return rows


def build_previous_race_result(
    records: Sequence[PreviousRaceResultInput],
) -> IntermediateFeatureTable:
    """Build this feature through the shared intermediate-table contract."""
    return PreviousRaceResultBuilder().build(records)


def build_previous_race_result_table(
    records: Sequence[PreviousRaceResultInput],
) -> IntermediateFeatureTable:
    """Build the previous-race-result feature table."""
    return build_previous_race_result(records)


__all__ = [
    "PreviousRaceResultInput",
    "PreviousRaceResultRecord",
    "build_previous_race_result",
    "build_previous_race_result_table",
]
