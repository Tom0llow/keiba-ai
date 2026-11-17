"""A two-year graded-race scenario shared by the ADR-043 and ADR-044 backtest tests.

Test years 2024 and 2025 have three graded races each: the fixture race, a race won by
horse 02 with a refund on horse 05, and a race held for a stale publication. Place hits
come from 2023 (identity) and 2024 (ratio 1.2), each with its ``place_low`` partner.
"""

from __future__ import annotations

from models.serialization.final_odds_observations import HitObservation
from tests.betting_fixtures import hr_row, o1_row, race_id

PLACE_HITS = ((1, 1.5, 1.2), (2, 3.0, 2.0), (3, 6.0, 3.0))


def scenario_race_ids(year: int) -> tuple[str, str, str]:
    """Return the scenario's three graded race IDs of one year."""
    return race_id(year, 1), race_id(year, 2), race_id(year, 3)


def scenario_hr_rows(year: int) -> dict[str, list[dict[str, object]]]:
    """Return each scenario race's payout rows."""
    first, second, third = scenario_race_ids(year)
    return {
        first: [hr_row(first)],
        second: [
            hr_row(
                second,
                win=(("02", 600),),
                place=(("02", 200), ("03", 400), ("04", 300)),
                HenkanUma4="1",
                HenkanFlag0="1",
            )
        ],
        third: [hr_row(third)],
    }


def scenario_o1_rows(year: int) -> dict[str, list[dict[str, object]]]:
    """Return each scenario race's O1 rows; the third race's publication is stale."""
    first, second, third = scenario_race_ids(year)
    return {
        first: [o1_row(first)],
        second: [o1_row(second)],
        third: [o1_row(third, clock="1514")],
    }


def scenario_hits(year: int, ratio: float = 1.0) -> list[HitObservation]:
    """Return a year's place hits (``place_mid`` and ``place_low``) of one non-graded race."""
    race = race_id(year, 90)
    hits: list[HitObservation] = []
    for number, mid, low in PLACE_HITS:
        combination = f"{number:02d}"
        hits.append(HitObservation(race, "place_mid", combination, mid, mid * ratio, 60))
        hits.append(HitObservation(race, "place_low", combination, low, mid * ratio, 60))
    return hits
