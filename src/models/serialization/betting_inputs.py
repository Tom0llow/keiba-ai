"""Shape ADR-043 backtest inputs: PL predictions, entrants and freeze-time O1 quotes.

Every function is pure. Payout parsing and the freeze-time O1 row selection are shared
with ADR-042 (``final_odds_observations``), so both evaluations read the market and the
settlement the same way.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from make_features.real_market import canonical_hash
from make_features.reference_raw import CARD_SE_COLUMNS, race_identity
from make_features.reference_snapshot import card_entrants
from models.market.place_width_correction import recover_place_high
from models.probability.market_blend import BlendRace, market_log_probabilities
from models.serialization.final_odds_observations import (
    ObservationHold,
    freeze_row,
    o1_quotes,
)

SE_TABLE = "NL_SE_RACE_UMA"
SE_COLUMNS = CARD_SE_COLUMNS
# ``finish_position`` and ``score`` are never read: the backtest must not see results.
PL_PREDICTION_COLUMNS = (
    "variant",
    "test_year",
    "race_id",
    "horse_id",
    "temperature",
    "p_win",
    "p_top2",
    "p_top3",
    "market_win_odds",
    "in_jra_flat_graded_stakes",
)
# ADR-044: the blend is fitted on earlier years' winners, so this second projection reads
# ``finish_position``; ``run_betting_backtest`` passes a year's fit only earlier years.
PL_BLEND_COLUMNS = (
    "variant",
    "test_year",
    "race_id",
    "horse_id",
    "p_win",
    "market_win_odds",
    "finish_position",
)
BLEND_EXCLUSIONS = ("market_incomplete", "zero_probability", "winner_count")
_SUM_TOLERANCE = 1e-6
_ORDER_TOLERANCE = 1e-12


@dataclass(frozen=True)
class HorsePrediction:
    """Hold one horse's calibrated PL marginals and the market odds the model saw."""

    horse_id: str
    p_win: float
    p_top2: float
    p_top3: float
    market_win_odds: float | None


@dataclass(frozen=True)
class RacePrediction:
    """Hold one graded test race's predictions from the ADR-035 yearly fold."""

    race_id: str
    test_year: int
    horses: tuple[HorsePrediction, ...]


@dataclass(frozen=True)
class FreezeQuotes:
    """Hold the freeze-time win and ``place_mid`` quotes of every O1 horse.

    ``win`` keeps every horse number of the selected publication; a horse without a
    valid quote maps to ``None``, as in ``latest_o1``'s complete horse set.
    """

    age_seconds: int
    win: Mapping[str, float | None]
    place: Mapping[str, float | None]
    place_low: Mapping[str, float | None]
    place_high: Mapping[str, float | None]


@dataclass(frozen=True)
class BlendTraining:
    """Hold every test year's races usable for the blend fit and the excluded counts."""

    races: Mapping[int, tuple[BlendRace, ...]]
    excluded: Mapping[int, Mapping[str, int]]


def race_predictions(
    rows: Sequence[Mapping[str, object]], *, variant: str, test_years: Collection[int]
) -> dict[str, RacePrediction]:
    """Return the graded races' predictions of one variant, after strict checks.

    Rows of other variants are ignored. Only rows flagged as
    ``jra_flat_graded_stakes_v1`` are returned.

    Raises:
        ValueError: If the variant has no rows; a column is missing or has the wrong type;
            ``test_year`` is not a configured year or differs from the race's year; a
            horse appears twice in a race; a race has fewer than three horses; a
            probability is not finite in [0, 1]; ``p_win <= p_top2 <= p_top3`` fails; the
            race sums differ from 1, 2 and 3; or the temperature is not positive.
    """
    selected = [row for row in rows if row.get("variant") == variant]
    if not selected:
        raise ValueError(f"PL predictions have no rows for variant {variant!r}")
    years = set(test_years)
    by_race: dict[str, list[Mapping[str, object]]] = {}
    for row in selected:
        graded = row.get("in_jra_flat_graded_stakes")
        if not isinstance(graded, bool):
            raise ValueError("PL predictions require a boolean in_jra_flat_graded_stakes")
        if graded:
            race_id = row.get("race_id")
            if not isinstance(race_id, str) or re.fullmatch(r"[0-9]{16}", race_id) is None:
                raise ValueError("PL predictions require 16-digit race IDs")
            by_race.setdefault(race_id, []).append(row)
    return {race_id: _race(race_id, items, years) for race_id, items in sorted(by_race.items())}


def freeze_quotes(
    race_id: str,
    o1_rows: Sequence[Mapping[str, object]],
    freeze: datetime,
    *,
    max_publication_age_seconds: int,
) -> FreezeQuotes:
    """Return the freeze-time O1 quotes by ADR-042 Decision 2's rules.

    Raises:
        ObservationHold: With ADR-042's reasons when there is no publication at or
            before freeze, rows conflict, the clock or a quote is invalid, or the
            publication is older than ``max_publication_age_seconds``.
    """
    row, age = freeze_row(race_id, o1_rows, freeze)
    if age > max_publication_age_seconds:
        raise ObservationHold("stale_publication", f"{race_id}: {age} seconds old")
    quotes = o1_quotes(row)
    low = {horse: odds for horse, (odds, _) in quotes["place_low"].items()}
    mid = {horse: odds for horse, (odds, _) in quotes["place_mid"].items()}
    high: dict[str, float | None] = {}
    for horse, odds in mid.items():
        lower = low.get(horse)
        high[horse] = None if odds is None or lower is None else recover_place_high(lower, odds)
    return FreezeQuotes(
        age_seconds=age,
        win={horse: odds for horse, (odds, _) in quotes["win"].items()},
        place=mid,
        place_low=low,
        place_high=high,
    )


def blend_training_races(
    rows: Sequence[Mapping[str, object]], *, variant: str, test_years: Collection[int]
) -> BlendTraining:
    """Return each test year's races for the ADR-044 blend fit, with excluded counts.

    A race is excluded, in this order, when a horse lacks positive finite market odds
    (``market_incomplete``), a horse has ``p_win <= 0`` (``zero_probability``), or not
    exactly one horse finished first (``winner_count``). Horses are ordered by ID.

    Raises:
        ValueError: If the variant has no rows, a value has the wrong type, a race ID is
            invalid, a test year is not configured or differs from the race's year, or a
            horse appears twice in a race.
    """
    selected = [row for row in rows if row.get("variant") == variant]
    if not selected:
        raise ValueError(f"PL predictions have no rows for variant {variant!r}")
    years = set(test_years)
    by_race: dict[str, list[Mapping[str, object]]] = {}
    for row in selected:
        race_id = row.get("race_id")
        if not isinstance(race_id, str) or re.fullmatch(r"[0-9]{16}", race_id) is None:
            raise ValueError("PL predictions require 16-digit race IDs")
        test_year = row.get("test_year")
        if isinstance(test_year, bool) or not isinstance(test_year, int):
            raise ValueError("PL predictions require an integer test_year")
        if test_year not in years or test_year != int(race_id[:4]):
            raise ValueError(f"{race_id}: test_year {test_year} is not the race's test year")
        by_race.setdefault(race_id, []).append(row)
    races: dict[int, list[BlendRace]] = {year: [] for year in sorted(years)}
    excluded = {year: dict.fromkeys(BLEND_EXCLUSIONS, 0) for year in sorted(years)}
    for race_id, items in sorted(by_race.items()):
        year = int(race_id[:4])
        reason, race = _blend_race(race_id, items)
        if race is None:
            excluded[year][cast(str, reason)] += 1
        else:
            races[year].append(race)
    return BlendTraining(
        races={year: tuple(values) for year, values in races.items()},
        excluded=excluded,
    )


def _blend_race(
    race_id: str, rows: Sequence[Mapping[str, object]]
) -> tuple[str | None, BlendRace | None]:
    horses: dict[str, tuple[float, float | None, int]] = {}
    for row in rows:
        horse_id = row.get("horse_id")
        if not isinstance(horse_id, str) or not horse_id or horse_id in horses:
            raise ValueError(f"{race_id}: horse_id must be unique non-empty strings")
        finish = row.get("finish_position")
        if isinstance(finish, bool) or not isinstance(finish, int):
            raise ValueError(f"{race_id}: finish_position must be an integer")
        market = row.get("market_win_odds")
        if market is not None and (isinstance(market, bool) or not isinstance(market, int | float)):
            raise ValueError("PL predictions require numeric market_win_odds")
        horses[horse_id] = (
            _probability(row.get("p_win"), "p_win"),
            # A missing or non-finite market makes the race market_incomplete, not an error.
            None if market is None or not math.isfinite(market) else float(market),
            finish,
        )
    ordered = [horses[horse_id] for horse_id in sorted(horses)]
    odds: list[float] = []
    for _, market, _ in ordered:
        if market is None or market <= 0.0:
            return "market_incomplete", None
        odds.append(market)
    if any(p_win <= 0.0 for p_win, _, _ in ordered):
        return "zero_probability", None
    winners = [index for index, (_, _, finish) in enumerate(ordered) if finish == 1]
    if len(winners) != 1 or len(ordered) < 2:
        return "winner_count", None
    return None, BlendRace(
        tuple(math.log(p_win) for p_win, _, _ in ordered),
        market_log_probabilities(odds),
        winners[0],
    )


def race_entrants(race_id: str, se_rows: Sequence[Mapping[str, object]]) -> dict[str, str]:
    """Map one race's stored entrants from horse number to permanent horse ID.

    Identical rows count once. The mapping is the one the datamart and the race-day
    prediction use (``card_entrants``).

    Raises:
        ObservationHold: ``no_entrants`` without rows, or ``entrant_mismatch`` when a
            horse number or permanent ID is missing or appears twice.
    """
    unique = {canonical_hash(dict(row)): row for row in se_rows if race_identity(row) == race_id}
    if not unique:
        raise ObservationHold("no_entrants", race_id)
    try:
        _, _, mapping = card_entrants(list(unique.values()))
    except ValueError as exc:
        raise ObservationHold("entrant_mismatch", f"{race_id}: {exc}") from exc
    return mapping


def _race(race_id: str, rows: Sequence[Mapping[str, object]], years: set[int]) -> RacePrediction:
    year = int(race_id[:4])
    horses: list[HorsePrediction] = []
    seen: set[str] = set()
    for row in rows:
        test_year = row.get("test_year")
        if isinstance(test_year, bool) or not isinstance(test_year, int):
            raise ValueError("PL predictions require an integer test_year")
        if test_year not in years or test_year != year:
            raise ValueError(f"{race_id}: test_year {test_year} is not the race's test year")
        horse_id = row.get("horse_id")
        if not isinstance(horse_id, str) or not horse_id or horse_id in seen:
            raise ValueError(f"{race_id}: horse_id must be unique non-empty strings")
        seen.add(horse_id)
        temperature = _real(row.get("temperature"), "temperature")
        if temperature <= 0.0:
            raise ValueError(f"{race_id}: temperature must be positive")
        p_win, p_top2, p_top3 = (
            _probability(row.get(name), name) for name in ("p_win", "p_top2", "p_top3")
        )
        if p_win > p_top2 + _ORDER_TOLERANCE or p_top2 > p_top3 + _ORDER_TOLERANCE:
            raise ValueError(f"{race_id}: probabilities must satisfy p_win <= p_top2 <= p_top3")
        market = row.get("market_win_odds")
        horses.append(
            HorsePrediction(
                horse_id,
                p_win,
                p_top2,
                p_top3,
                None if market is None else _real(market, "market_win_odds"),
            )
        )
    if len(horses) < 3:
        raise ValueError(f"{race_id}: PL predictions require at least three horses")
    for name, expected in (("p_win", 1.0), ("p_top2", 2.0), ("p_top3", 3.0)):
        total = math.fsum(getattr(horse, name) for horse in horses)
        if abs(total - expected) > _SUM_TOLERANCE:
            raise ValueError(f"{race_id}: {name} must sum to {expected:g} within the race")
    return RacePrediction(race_id, year, tuple(sorted(horses, key=lambda h: h.horse_id)))


def _real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"PL predictions require a finite {name}")
    return float(value)


def _probability(value: object, name: str) -> float:
    number = _real(value, name)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"PL predictions require {name} between zero and one")
    return number


__all__ = [
    "BLEND_EXCLUSIONS",
    "PL_BLEND_COLUMNS",
    "PL_PREDICTION_COLUMNS",
    "SE_COLUMNS",
    "SE_TABLE",
    "BlendTraining",
    "FreezeQuotes",
    "HorsePrediction",
    "RacePrediction",
    "blend_training_races",
    "freeze_quotes",
    "race_entrants",
    "race_predictions",
]
