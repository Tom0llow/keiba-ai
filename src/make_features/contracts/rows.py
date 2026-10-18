"""Represent normalized feature middle rows without storage dependencies."""

from __future__ import annotations

from datetime import datetime


class FeatureTableRow:
    """Represent one normalized middle row independently of feature adoption."""

    __slots__ = ("available_at", "freeze_at", "horse_id", "race_id", "values")

    def __init__(
        self,
        race_id: str,
        horse_id: str,
        freeze_at: datetime,
        available_at: datetime | None,
        values: dict[str, object],
    ) -> None:
        self.race_id = race_id
        self.horse_id = horse_id
        self.freeze_at = freeze_at
        self.available_at = available_at
        self.values = values
