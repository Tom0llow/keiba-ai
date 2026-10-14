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
        return f"{self.race_date:%Y%m%d}{self.jyo_code}{self.kaiji}{self.nichiji}{self.race_number}"

    def __str__(self) -> str:
        return (
            f"{self.race_date:%Y-%m-%d}/"
            f"{self.jyo_code}/{self.kaiji}/{self.nichiji}/{self.race_number}"
        )


def race_key_from_row(row: tuple[str, str, str, str, str, str]) -> RaceKey:
    """Convert a raw race-key row without opening an acquisition store."""
    year, month_day, jyo_code, kaiji, nichiji, race_number = row
    if not (year.isdigit() and len(year) == 4 and month_day.isdigit() and len(month_day) == 4):
        raise ValueError(f"invalid race date components: {year!r}, {month_day!r}")

    try:
        race_date = date(int(year), int(month_day[:2]), int(month_day[2:]))
    except ValueError as exc:
        raise ValueError(f"invalid race date components: {year!r}, {month_day!r}") from exc

    components = {
        "idJyoCD": jyo_code,
        "idKaiji": kaiji,
        "idNichiji": nichiji,
        "idRaceNum": race_number,
    }
    for name, value in components.items():
        if not isinstance(value, str) or not value.isdigit() or len(value) != 2:
            raise ValueError(f"invalid {name}: {value!r}")

    return RaceKey(race_date, jyo_code, kaiji, nichiji, race_number)
