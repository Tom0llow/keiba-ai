"""Tests for ADR-043 and ADR-044 backtest input shaping."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from models.probability.market_blend import market_log_probabilities
from models.serialization.betting_inputs import (
    PL_BLEND_COLUMNS,
    PL_PREDICTION_COLUMNS,
    blend_training_races,
    freeze_quotes,
    race_entrants,
    race_predictions,
)
from models.serialization.final_odds_observations import ObservationHold, race_freeze
from tests.betting_fixtures import (
    HORSES,
    horse_id,
    o1_row,
    prediction_rows,
    ra_row,
    race_id,
    se_rows,
)

RACE = race_id(2025)
FREEZE = datetime(2025, 6, 15, 6, 25, tzinfo=UTC)


def test_race_predictions_never_project_results() -> None:
    assert "finish_position" not in PL_PREDICTION_COLUMNS
    assert "score" not in PL_PREDICTION_COLUMNS


def test_race_predictions_select_the_variant_and_graded_races() -> None:
    rows = [
        *prediction_rows(RACE),
        *prediction_rows(RACE, variant="without_market"),
        *prediction_rows(race_id(2025, 2), graded=False),
    ]

    predictions = race_predictions(rows, variant="all_columns", test_years=(2025,))

    assert set(predictions) == {RACE}
    (prediction,) = predictions.values()
    assert prediction.test_year == 2025
    assert [horse.horse_id for horse in prediction.horses] == [horse_id(RACE, h) for h in HORSES]
    assert prediction.horses[0].p_top3 == 0.75


def test_race_predictions_do_not_depend_on_finish_positions() -> None:
    rows = prediction_rows(RACE)
    shuffled = [{**row, "finish_position": 9 - int(str(row["finish_position"]))} for row in rows]

    assert race_predictions(rows, variant="all_columns", test_years=(2025,)) == race_predictions(
        shuffled, variant="all_columns", test_years=(2025,)
    )


def _with(index: int, **fields: object) -> list[dict[str, object]]:
    rows = prediction_rows(RACE)
    rows[index] = {**rows[index], **fields}
    return rows


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (_with(0, p_win=math.nan), "finite p_win"),
        (_with(0, p_top3=math.inf), "finite p_top3"),
        (_with(0, p_win=1.5), "p_win between zero and one"),
        (_with(1, p_top2=0.1), "p_win <= p_top2 <= p_top3"),
        (_with(0, p_win=0.39), "p_win must sum to 1"),
        (_with(0, test_year=2024), "not the race's test year"),
        (_with(1, horse_id=horse_id(RACE, "01")), "unique"),
        (_with(0, temperature=0.0), "temperature must be positive"),
        (_with(0, in_jra_flat_graded_stakes=None), "boolean"),
        (prediction_rows(RACE)[:2], "at least three horses"),
    ],
)
def test_race_predictions_reject_invalid_rows(rows: list[dict[str, object]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        race_predictions(rows, variant="all_columns", test_years=(2025,))


def test_race_predictions_reject_a_missing_variant_and_unconfigured_years() -> None:
    with pytest.raises(ValueError, match="no rows for variant"):
        race_predictions(prediction_rows(RACE), variant="other", test_years=(2025,))
    with pytest.raises(ValueError, match="not the race's test year"):
        race_predictions(prediction_rows(RACE), variant="all_columns", test_years=(2024,))


def test_freeze_quotes_use_latest_o1_and_return_every_horse() -> None:
    rows = [o1_row(RACE, clock="1524"), o1_row(RACE, clock="1526", win_codes=("0099",) * 8)]

    quotes = freeze_quotes(
        RACE, rows, race_freeze(RACE, [ra_row(RACE)]), max_publication_age_seconds=600
    )

    assert quotes.age_seconds == 60
    assert set(quotes.win) == set(HORSES)
    assert quotes.win["01"] == 3.0
    assert quotes.place["03"] == pytest.approx(math.sqrt(12.0))


def test_freeze_quotes_return_both_place_bounds_without_changing_the_mid() -> None:
    row = o1_row(RACE)
    row["OddsFukusyoInfo1OddsHigh"] = None
    row["OddsFukusyoInfo2OddsLow"] = None
    row["OddsFukusyoInfo4OddsLow"], row["OddsFukusyoInfo4OddsHigh"] = "0012", "0036"

    quotes = freeze_quotes(RACE, [row], FREEZE, max_publication_age_seconds=600)

    assert (quotes.place_low["01"], quotes.place_high["01"]) == (1.1, 1.5)
    assert quotes.place["01"] == pytest.approx(math.sqrt(1.1 * 1.5))
    assert (quotes.place_low["02"], quotes.place_high["02"], quotes.place["02"]) == (
        1.5,
        None,
        None,
    )
    assert (quotes.place_low["03"], quotes.place_high["03"], quotes.place["03"]) == (
        None,
        None,
        None,
    )
    assert (quotes.place_low["05"], quotes.place_high["05"]) == (1.2, 3.6)


def _blend_rows(race: str, **changes: object) -> list[dict[str, object]]:
    rows = [{name: row[name] for name in PL_BLEND_COLUMNS} for row in prediction_rows(race)]
    for name, value in changes.items():
        horse, column = name.split("__")
        rows[int(horse) - 1][column] = value
    return rows


def test_blend_training_races_split_years_and_count_exclusions() -> None:
    first, second = race_id(2024), race_id(2025)
    rows = [
        *_blend_rows(first),
        *_blend_rows(race_id(2024, 2), **{"03__market_win_odds": None}),
        *_blend_rows(race_id(2024, 3), **{"05__p_win": 0.0}),
        *_blend_rows(race_id(2024, 4), **{"02__finish_position": 1}),
        *_blend_rows(second),
        *[{**row, "variant": "ignored"} for row in _blend_rows(race_id(2025, 2))],
        *[{**row, "variant": "without_market"} for row in _blend_rows(race_id(2025, 3))],
    ]

    training = blend_training_races(rows, variant="all_columns", test_years=(2024, 2025))

    assert [len(training.races[year]) for year in (2024, 2025)] == [1, 1]
    assert training.excluded[2024] == {
        "market_incomplete": 1,
        "zero_probability": 1,
        "winner_count": 1,
    }
    assert training.excluded[2025] == {
        "market_incomplete": 0,
        "zero_probability": 0,
        "winner_count": 0,
    }
    (race,) = training.races[2024]
    assert race.winner == 0
    assert race.log_p_win[1] == pytest.approx(math.log(0.2))
    odds = [
        int(code) / 10 for code in ("0030", "0060", "0080", "0080", "0200", "0200", "0200", "0200")
    ]
    assert race.log_q == pytest.approx(market_log_probabilities(odds))


def test_blend_training_races_reject_unconfigured_years_and_repeated_horses() -> None:
    rows = _blend_rows(RACE)
    with pytest.raises(ValueError, match="not the race's test year"):
        blend_training_races(rows, variant="all_columns", test_years=(2024,))
    with pytest.raises(ValueError, match="unique"):
        blend_training_races([*rows, rows[0]], variant="all_columns", test_years=(2025,))
    with pytest.raises(ValueError, match="no rows for variant"):
        blend_training_races(rows, variant="other", test_years=(2025,))


def test_the_blend_projection_reads_only_the_fit_columns() -> None:
    assert PL_BLEND_COLUMNS == (
        "variant",
        "test_year",
        "race_id",
        "horse_id",
        "p_win",
        "market_win_odds",
        "finish_position",
    )


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([o1_row(RACE, clock="1526")], "no_publication"),
        ([o1_row(RACE, clock="1514")], "stale_publication"),
        (
            [o1_row(RACE, clock="1524"), o1_row(RACE, clock="1524", win_codes=("0099",) * 8)],
            "conflicting_publication",
        ),
    ],
)
def test_freeze_quotes_hold_with_adr042_reasons(rows: list[dict[str, object]], reason: str) -> None:
    with pytest.raises(ObservationHold) as raised:
        freeze_quotes(RACE, rows, FREEZE, max_publication_age_seconds=600)

    assert raised.value.reason == reason


def test_race_entrants_map_horse_numbers_to_permanent_ids() -> None:
    entrants = race_entrants(RACE, [*se_rows(RACE), *se_rows(RACE), *se_rows(race_id(2025, 2))])

    assert entrants == {horse: horse_id(RACE, horse) for horse in HORSES}


def test_race_entrants_hold_missing_and_duplicate_entrants() -> None:
    with pytest.raises(ObservationHold) as missing:
        race_entrants(RACE, se_rows(race_id(2025, 2)))
    duplicate = se_rows(RACE)
    duplicate[1] = {**duplicate[1], "KettoNum": duplicate[0]["KettoNum"]}
    with pytest.raises(ObservationHold) as mismatch:
        race_entrants(RACE, duplicate)

    assert missing.value.reason == "no_entrants"
    assert mismatch.value.reason == "entrant_mismatch"


def test_non_finite_or_non_positive_market_odds_make_a_blend_race_market_incomplete() -> None:
    rows = [
        *_blend_rows(race_id(2025, 1), **{"03__market_win_odds": math.nan}),
        *_blend_rows(race_id(2025, 2), **{"04__market_win_odds": math.inf}),
        *_blend_rows(race_id(2025, 3), **{"05__market_win_odds": 0.0}),
    ]

    training = blend_training_races(rows, variant="all_columns", test_years=(2025,))

    assert training.races[2025] == ()
    assert training.excluded[2025]["market_incomplete"] == 3
    with pytest.raises(ValueError, match="numeric market_win_odds"):
        blend_training_races(
            _blend_rows(race_id(2025), **{"03__market_win_odds": "3.0"}),
            variant="all_columns",
            test_years=(2025,),
        )
