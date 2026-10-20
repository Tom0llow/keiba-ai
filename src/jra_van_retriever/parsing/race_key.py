"""Convert raw race-key rows at the retrieval boundary."""

from __future__ import annotations

from datetime import date

from domain.race_key import RaceKey


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
