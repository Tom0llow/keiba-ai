"""Shared race identity used across retrieval, preprocessing, and loading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, order=True)
class RaceKey:
    """Represent the five components that uniquely identify one JRA race."""

    race_date: date
    jyo_code: str
    kaiji: str
    nichiji: str
    race_number: str

    def __post_init__(self) -> None:
        for name, value in (
            ("jyo_code", self.jyo_code),
            ("kaiji", self.kaiji),
            ("nichiji", self.nichiji),
            ("race_number", self.race_number),
        ):
            if not value.isdigit() or len(value) != 2:
                raise ValueError(f"{name} must be a two-digit string: {value!r}")

    @property
    def race_id(self) -> str:
        """Return a stable filesystem-safe identifier for this race."""
        return (
            f"{self.race_date:%Y%m%d}"
            f"{self.jyo_code}{self.kaiji}{self.nichiji}{self.race_number}"
        )

    def __str__(self) -> str:
        return (
            f"{self.race_date:%Y-%m-%d}/"
            f"{self.jyo_code}/{self.kaiji}/{self.nichiji}/{self.race_number}"
        )
