"""Tests for ADR-044's estimation methods, flat scoring and rolling selection.

``tests/data/betting_backtest_adr043_scenario.json`` is the ADR-043 (format version 1)
result of the shared scenario, written by the code at commit ``f4931af`` before ADR-044.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import cast
from unittest.mock import patch

import pyarrow as pa
import pytest

from models.betting.policy import BetCandidate, BettingPolicy
from models.experiments import betting_backtest as backtest
from models.experiments.betting_backtest import (
    METHODS,
    BettingBacktest,
    BettingBacktestSettings,
    GradedRaceInput,
    Method,
    bets_table,
    races_table,
    run_betting_backtest,
)
from models.market.place_width_correction import place_width
from models.probability.market_blend import (
    BlendRace,
    blend_probabilities,
    market_log_probabilities,
)
from models.serialization.betting_inputs import BlendTraining, freeze_quotes, race_predictions
from models.serialization.final_odds_observations import HitObservation
from tests.betting_fixtures import hr_row, o1_row, prediction_rows, ra_row, race_id, se_rows
from tests.betting_scenario import (
    scenario_hits,
    scenario_hr_rows,
    scenario_o1_rows,
    scenario_race_ids,
)

FROZEN = Path(__file__).parents[1] / "data" / "betting_backtest_adr043_scenario.json"
NO_EXCLUSIONS = {"market_incomplete": 0, "zero_probability": 0, "winner_count": 0}


def _settings(test_years: Sequence[int], **fields: object) -> BettingBacktestSettings:
    values: dict[str, object] = {
        "test_years": tuple(test_years),
        "policy": BettingPolicy(),
        "train_start_year": 2023,
        "max_publication_age_seconds": 600,
        "place_bands": (1.0,),
        "quantiles": (0.1, 0.5, 0.9),
        "min_hits": 1,
        "graded_shrinkage_k": 2,
        "bootstrap_resamples": 20,
        "bootstrap_seed": 0,
        "bootstrap_confidence": 0.95,
        "blend_min_races": 20,
        "blend_tolerance": 1e-10,
        "blend_max_iterations": 100,
        "place_width_bands": (1.0, 1.5, 2.0, 3.0, 5.0),
    }
    values.update(fields)
    return BettingBacktestSettings(**values)  # type: ignore[arg-type]


def _blend_races(year: int, count: int = 60, *, flip: bool = False) -> tuple[BlendRace, ...]:
    """Return races whose winners favour the market; ``flip`` makes the outsider win."""
    generator = Random(year)
    races: list[BlendRace] = []
    for _ in range(count):
        a = _log_softmax([generator.gauss(0.0, 1.0) for _ in range(8)])
        b = _log_softmax([generator.gauss(0.0, 1.0) + 0.5 * value for value in a])
        weights = [math.exp(0.3 * x + 0.9 * y) for x, y in zip(a, b, strict=True)]
        winner = generator.choices(range(8), weights=weights)[0]
        if flip:
            winner = min(range(8), key=lambda index: b[index])
        races.append(BlendRace(tuple(a), tuple(b), winner))
    return tuple(races)


def _log_softmax(values: list[float]) -> list[float]:
    peak = max(values)
    total = math.log(sum(math.exp(value - peak) for value in values)) + peak
    return [value - total for value in values]


def _training(years: Sequence[int], **overrides: tuple[BlendRace, ...]) -> BlendTraining:
    return BlendTraining(
        races={year: overrides.get(str(year), _blend_races(year)) for year in years},
        excluded={year: dict(NO_EXCLUSIONS) for year in years},
    )


def _scenario(
    test_years: Sequence[int] = (2024, 2025),
    *,
    blend: BlendTraining | None = None,
    hits: Sequence[HitObservation] | None = None,
    hr: Mapping[str, list[dict[str, object]]] | None = None,
    predictions: Sequence[Mapping[str, object]] | None = None,
    settings: BettingBacktestSettings | None = None,
) -> BettingBacktest:
    chosen = settings or _settings(test_years)
    races: list[GradedRaceInput] = []
    for year in test_years:
        payouts = {**scenario_hr_rows(year), **(hr or {})}
        o1 = scenario_o1_rows(year)
        for race in scenario_race_ids(year):
            races.append(
                GradedRaceInput(race, [ra_row(race)], o1[race], se_rows(race), payouts[race])
            )
    rows = predictions or [
        row
        for year in test_years
        for race in scenario_race_ids(year)
        for row in prediction_rows(race)
    ]
    return run_betting_backtest(
        settings=chosen,
        graded_races=races,
        predictions=race_predictions(rows, variant="all_columns", test_years=chosen.test_years),
        target_hold_stages={},
        training_hits=hits
        if hits is not None
        else [
            *scenario_hits(2023),
            *(item for year in test_years for item in scenario_hits(year, 1.2)),
        ],
        blend_training=blend or _training(test_years),
        graded_race_ids=frozenset(),
        config={},
        inputs={},
        provenance={},
    )


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def _method_year(result: BettingBacktest, method: str, year: int) -> Mapping[str, object]:
    methods = _mapping(result.report["methods"])
    return _mapping(_mapping(_mapping(methods[method])["years"])[str(year)])


def test_the_current_method_reproduces_the_frozen_adr043_result() -> None:
    expected = json.loads(FROZEN.read_text(encoding="utf-8"))

    result = _scenario()

    pl_mid = _mapping(_mapping(result.report["methods"])["pl_mid"])
    for year in ("2024", "2025"):
        values = _method_year(result, "pl_mid", int(year))
        assert values["policy"] == expected["years"][year]
        counts = dict(_mapping(values["counts"]))
        assert counts.pop("place_width_invalid") == 0
        assert counts == expected["counts"][year]
    assert pl_mid["all_available_years"] == expected["all_test_years"]
    # Without earlier comparison years the selected path is the current method.
    assert result.report["years"] == expected["years"]
    assert result.report["all_test_years"] == expected["all_test_years"]
    assert [
        {
            **{k: v for k, v in row.items() if k != "method"},
            "freeze_at": cast(datetime, row["freeze_at"]).isoformat(),
        }
        for row in result.bets
    ] == expected["bets"]
    assert [
        {
            **{k: v for k, v in row.items() if k != "method"},
            "freeze_at": cast(datetime, row["freeze_at"]).isoformat(),
        }
        for row in result.races
    ] == expected["races"]
    assert {row["method"] for row in result.bets} == {"pl_mid"}


def test_the_first_year_has_no_blend_and_its_methods_are_unavailable() -> None:
    result = _scenario()

    first = _method_year(result, "blend_width", 2024)
    assert first["available"] is False
    assert (first["counts"], first["flat"], first["policy"]) == (None, None, None)
    assert first["blend"] == {
        "alpha": None,
        "beta": None,
        "races": 0,
        "excluded": NO_EXCLUSIONS,
        "failure": "insufficient_races",
    }
    second = _method_year(result, "blend_mid", 2025)
    assert second["available"] is True
    blend = _mapping(second["blend"])
    assert blend["races"] == 60
    assert blend["failure"] is None
    assert _method_year(result, "pl_width", 2024)["blend"] is None
    blend_mid = _mapping(_mapping(result.report["methods"])["blend_mid"])
    assert blend_mid["available_years"] == [2025]
    common = _mapping(result.report["common_years"])
    assert common["years"] == [2025]


def test_a_year_with_too_few_blend_races_is_unavailable() -> None:
    result = _scenario(blend=_training((2024, 2025), **{"2024": _blend_races(2024, 5)}))

    blend = _mapping(_method_year(result, "blend_mid", 2025)["blend"])
    assert (blend["races"], blend["failure"]) == (5, "insufficient_races")
    assert _mapping(result.report["common_years"]) == {
        "years": [],
        "selected": None,
        "methods": dict.fromkeys(METHODS),
    }


def test_blended_probabilities_replace_the_pl_marginals_only_for_blend_methods() -> None:
    result = _scenario()

    pl_flat = _mapping(_method_year(result, "pl_mid", 2025)["flat"])
    blend_flat = _mapping(_method_year(result, "blend_mid", 2025)["flat"])
    assert pl_flat != blend_flat


def _selection_results(
    flats: Mapping[str, Mapping[int, tuple[int, int] | None]],
) -> dict[str, dict[int, backtest._MethodYear]]:
    results: dict[str, dict[int, backtest._MethodYear]] = {}
    for method in METHODS:
        results[method] = {}
        for year, totals in flats.get(method, {}).items():
            if totals is None:
                continue
            receipt, stake = totals
            flat = backtest._Flat(stake // 100, 0, stake, receipt)
            results[method][year] = backtest._MethodYear(backtest._YearCounts(), flat, ())
    return results


def test_selection_uses_only_earlier_years_that_every_method_covers() -> None:
    flats = {
        "pl_mid": {2016: (100, 100), 2017: (80, 100), 2018: (90, 100), 2019: (0, 100)},
        "blend_mid": {2016: None, 2017: (120, 100), 2018: (70, 100), 2019: (900, 100)},
        "pl_width": {2016: (500, 100), 2017: (90, 100), 2018: (80, 100), 2019: (0, 100)},
        "blend_width": {2016: None, 2017: (60, 100), 2018: (60, 100), 2019: (0, 100)},
    }

    selection = backtest._selection(
        _selection_results(flats),  # type: ignore[arg-type]
        (2016, 2017, 2018, 2019),
    )

    assert selection[2016] == ("pl_mid", ())
    assert selection[2017] == ("pl_mid", ())
    assert selection[2018] == ("blend_mid", (2017,))
    # 2017-2018: pl_mid 170, blend_mid 190, pl_width 170; 2019 itself is never used.
    assert selection[2019] == ("blend_mid", (2017, 2018))


def test_selection_ties_go_to_the_earlier_method_and_unbought_methods_are_skipped() -> None:
    flats = {
        "pl_mid": {2016: (0, 0), 2017: (0, 0), 2018: (0, 0)},
        "blend_mid": {2016: (150, 100), 2017: (0, 0), 2018: (0, 0)},
        "pl_width": {2016: (300, 200), 2017: (0, 0), 2018: (0, 0)},
        "blend_width": {2016: (100, 100), 2017: (0, 0), 2018: (0, 0)},
    }

    selection = backtest._selection(
        _selection_results(flats),  # type: ignore[arg-type]
        (2016, 2017, 2018),
    )

    # blend_mid 150/100 and pl_width 300/200 tie; pl_mid bought nothing.
    assert selection[2017] == ("blend_mid", (2016,))
    assert selection[2018] == ("blend_mid", (2016, 2017))


def test_selection_falls_back_when_nothing_was_bought_or_the_choice_is_unavailable() -> None:
    nothing = {method: {2016: (0, 0)} for method in METHODS}
    unavailable = {
        "pl_mid": {2016: (100, 100), 2017: (100, 100)},
        "blend_mid": {2016: (200, 100), 2017: None},
        "pl_width": {2016: (100, 100), 2017: (100, 100)},
        "blend_width": {2016: (100, 100), 2017: (100, 100)},
    }

    assert backtest._selection(_selection_results(nothing), (2016, 2017))[2017] == (  # type: ignore[arg-type]
        "pl_mid",
        (2016,),
    )
    assert backtest._selection(_selection_results(unavailable), (2016, 2017))[2017] == (  # type: ignore[arg-type]
        "pl_mid",
        (2016,),
    )


def test_the_selected_path_is_the_chosen_methods_yearly_result() -> None:
    years = (2024, 2025, 2026)
    result = _scenario(years)

    selection = _mapping(result.report["selection"])
    for year in years:
        method = cast(str, _mapping(selection[str(year)])["method"])
        values = _method_year(result, method, year)
        assert _mapping(result.report["years"])[str(year)] == values["policy"]
        assert _mapping(result.report["counts"])[str(year)] == values["counts"]
        assert {row["method"] for row in result.bets if row["test_year"] == year} <= {method}
        assert {row["method"] for row in result.races if row["test_year"] == year} <= {method}
    flat_rates = _mapping(_mapping(selection["2026"])["flat_recovery_rate"])
    for method in METHODS:
        flat = _mapping(_method_year(result, method, 2025)["flat"])
        assert flat_rates[method] == flat["recovery_rate"]
    assert _mapping(selection["2026"])["comparison_years"] == [2025]


def test_later_results_never_change_earlier_fits_flat_results_or_selections() -> None:
    years = (2024, 2025, 2026)
    later = race_id(2026, 1)
    base = _scenario(years)
    changed = _scenario(
        years,
        blend=_training(years, **{"2026": _blend_races(2026, flip=True)}),
        hits=[
            *scenario_hits(2023),
            *scenario_hits(2024, 1.2),
            *scenario_hits(2025, 1.2),
            *scenario_hits(2026, 3.0),
        ],
        hr={later: [hr_row(later, win=(("05", 2_000),))]},
    )

    for method in METHODS:
        for year in (2024, 2025):
            assert _method_year(base, method, year) == _method_year(changed, method, year)
    assert base.report["selection"] == changed.report["selection"]
    for year in years:
        assert [
            {k: v for k, v in row.items() if k not in ("payout_yen", "refund_yen", "receipt_yen")}
            for row in base.bets
            if row["test_year"] == year
        ] == [
            {k: v for k, v in row.items() if k not in ("payout_yen", "refund_yen", "receipt_yen")}
            for row in changed.bets
            if row["test_year"] == year
        ]


def test_a_years_flat_result_uses_fits_from_before_that_year_only() -> None:
    years = (2024, 2025, 2026)
    base = _scenario(years)
    changed = _scenario(
        years,
        blend=_training(years, **{"2025": _blend_races(2025, flip=True)}),
        hits=[*scenario_hits(2023), *scenario_hits(2024, 1.2), *scenario_hits(2025, 3.0)],
    )

    for method in METHODS:
        assert (
            _method_year(base, method, 2025)["flat"] == _method_year(changed, method, 2025)["flat"]
        )
    assert (
        _method_year(base, "blend_mid", 2026)["blend"]
        != _method_year(changed, "blend_mid", 2026)["blend"]
    )


def test_flat_scoring_buys_one_unit_even_when_the_kelly_stake_is_zero_and_counts_refunds() -> None:
    race = race_id(2025)
    freeze = datetime(2025, 6, 15, 6, 25, tzinfo=UTC)
    candidates = [
        # R 1.10 at odds 1,000: the Kelly stake floors to zero yen under the policy.
        BetCandidate(race, freeze, "win", "04", 0.0011, 1_000.0, 1_000.0),
        BetCandidate(race, freeze, "place", "03", 0.5, 3.0, 3.0),
        BetCandidate(race, freeze, "win", "05", 0.5, 3.0, 3.0),
        BetCandidate(race, freeze, "win", "02", 0.1, 3.0, 3.0),
        # R 1.05 is below the policy's 1.10, and odds of 1.0 never pay more than the stake.
        BetCandidate(race, freeze, "win", "06", 0.35, 3.0, 3.0),
        BetCandidate(race, freeze, "place", "07", 1.0, 1.0, 1.0),
    ]
    hr = {race: [hr_row(race, HenkanUma4="1", HenkanFlag0="1")]}

    flat = backtest._flat(candidates, hr, BettingPolicy())

    # 04 (no payout), 03 place (350) and 05 refunded (100); 02, 06 and 07 are not eligible.
    assert (flat.bets, flat.hits, flat.stake_yen, flat.receipt_yen) == (3, 1, 300, 450)


def test_flat_scoring_stops_on_a_race_that_cannot_be_settled() -> None:
    race = race_id(2025)
    freeze = datetime(2025, 6, 15, 6, 25, tzinfo=UTC)
    candidate = BetCandidate(race, freeze, "win", "01", 0.5, 3.0, 3.0)

    with pytest.raises(ValueError, match="cannot be settled"):
        backtest._flat([candidate], {race: [hr_row(race, TokubaraiFlag0="1")]}, BettingPolicy())


def test_blend_methods_hold_races_with_missing_market_odds_or_a_zero_probability() -> None:
    first, second = scenario_race_ids(2025)[:2]
    missing = o1_row(
        first, win_codes=("0030", "0060", "0080", "0080", "0200", "0200", "0200", "----")
    )
    zero = prediction_rows(second)
    zero[0]["p_win"], zero[7]["p_win"] = 0.45, 0.0
    rows = [
        *(row for race in scenario_race_ids(2024) for row in prediction_rows(race)),
        *prediction_rows(first, market={"08": None}),
        *zero,
        *prediction_rows(scenario_race_ids(2025)[2]),
    ]
    races: list[GradedRaceInput] = []
    for year in (2024, 2025):
        payouts = scenario_hr_rows(year)
        o1 = {**scenario_o1_rows(year), first: [missing]}
        races.extend(
            GradedRaceInput(race, [ra_row(race)], o1[race], se_rows(race), payouts[race])
            for race in scenario_race_ids(year)
        )
    settings = _settings((2024, 2025))
    result = run_betting_backtest(
        settings=settings,
        graded_races=races,
        predictions=race_predictions(rows, variant="all_columns", test_years=settings.test_years),
        target_hold_stages={},
        training_hits=[*scenario_hits(2023), *scenario_hits(2024, 1.2)],
        blend_training=_training((2024, 2025)),
        graded_race_ids=frozenset(),
        config={},
        inputs={},
        provenance={},
    )

    blend_counts = _mapping(_method_year(result, "blend_mid", 2025)["counts"])
    assert blend_counts["holds"] == {
        "blend_market_incomplete": 1,
        "blend_zero_probability": 1,
        "stale_publication": 1,
    }
    pl_counts = _mapping(_method_year(result, "pl_mid", 2025)["counts"])
    assert pl_counts["holds"] == {"stale_publication": 1}


def test_width_methods_skip_and_count_place_quotes_with_a_high_bound_below_the_low() -> None:
    first = scenario_race_ids(2025)[0]
    inverted = o1_row(first)
    inverted["OddsFukusyoInfo2OddsLow"], inverted["OddsFukusyoInfo2OddsHigh"] = "0040", "0030"
    races: list[GradedRaceInput] = []
    for year in (2024, 2025):
        payouts = scenario_hr_rows(year)
        o1 = scenario_o1_rows(year)
        if year == 2025:
            o1[first] = [inverted]
        races.extend(
            GradedRaceInput(race, [ra_row(race)], o1[race], se_rows(race), payouts[race])
            for race in scenario_race_ids(year)
        )
    settings = _settings((2024, 2025))
    result = run_betting_backtest(
        settings=settings,
        graded_races=races,
        predictions=race_predictions(
            [
                row
                for year in (2024, 2025)
                for race in scenario_race_ids(year)
                for row in prediction_rows(race)
            ],
            variant="all_columns",
            test_years=settings.test_years,
        ),
        target_hold_stages={},
        training_hits=[*scenario_hits(2023), *scenario_hits(2024, 1.2)],
        blend_training=_training((2024, 2025)),
        graded_race_ids=frozenset(),
        config={},
        inputs={},
        provenance={},
    )

    assert _mapping(_method_year(result, "pl_width", 2025)["counts"])["place_width_invalid"] == 1
    assert _mapping(_method_year(result, "pl_mid", 2025)["counts"])["place_width_invalid"] == 0


def test_a_place_mid_hit_without_its_place_low_partner_is_rejected() -> None:
    hits = [hit for hit in scenario_hits(2023) if hit.bet_type == "place_mid"]

    with pytest.raises(ValueError, match="has no place_low"):
        _scenario(hits=[*hits, *scenario_hits(2024, 1.2)])


def test_the_report_key_tree_and_table_schemas_follow_adr044() -> None:
    result = _scenario()

    assert _mapping(result.report["estimation"]) == {
        "methods": list(METHODS),
        "blend_min_races": 20,
        "blend_tolerance": 1e-10,
        "blend_max_iterations": 100,
        "place_width_bands": [1.0, 1.5, 2.0, 3.0, 5.0],
    }
    assert set(_mapping(_mapping(result.report["selection"])["2025"])) == {
        "method",
        "comparison_years",
        "flat_recovery_rate",
    }
    assert set(_mapping(result.report["common_years"])) == {"years", "selected", "methods"}
    method = _mapping(_mapping(result.report["methods"])["blend_mid"])
    assert set(method) == {"years", "available_years", "all_available_years"}
    assert set(_method_year(result, "blend_mid", 2025)) == {
        "available",
        "blend",
        "counts",
        "flat",
        "policy",
    }
    assert set(_mapping(_method_year(result, "pl_mid", 2025)["flat"])) == {
        "bets",
        "hits",
        "stake_yen",
        "receipt_yen",
        "recovery_rate",
    }
    assert json.loads(json.dumps(result.report)) == result.report
    assert bets_table(result).schema.field("method").type == pa.string()
    assert bets_table(result).schema.names[-1] == "method"
    assert races_table(result).schema.names[-1] == "method"


def _forced(selection: Mapping[int, str]) -> object:
    """Return a ``_selection`` replacement that keeps comparison years but forces methods."""
    original = backtest._selection

    def choose(results: object, test_years: Sequence[int]) -> object:
        chosen = original(results, test_years)  # type: ignore[arg-type]
        return {
            year: (selection.get(year, method), years) for year, (method, years) in chosen.items()
        }

    return choose


@pytest.mark.parametrize("method", ["blend_mid", "pl_width", "blend_width"])
def test_a_selected_non_baseline_method_supplies_that_years_report_and_rows(method: str) -> None:
    with patch.object(backtest, "_selection", side_effect=_forced({2025: method})):
        result = _scenario(hits=_varied_hits())

    values = _method_year(result, method, 2025)
    baseline = _method_year(result, "pl_mid", 2025)
    assert values["policy"] != baseline["policy"]
    assert _mapping(result.report["years"])["2025"] == values["policy"]
    assert _mapping(result.report["counts"])["2025"] == values["counts"]
    assert (
        _mapping(result.report["years"])["2024"] == _method_year(result, "pl_mid", 2024)["policy"]
    )
    policy = _mapping(values["policy"])
    rows_2025 = [row for row in result.bets if row["test_year"] == 2025]
    assert rows_2025
    assert {row["method"] for row in rows_2025} == {method}
    assert sum(cast(int, row["stake_yen"]) for row in rows_2025) == policy["stake_yen"]
    assert {row["method"] for row in result.races if row["test_year"] == 2025} == {method}
    assert {row["method"] for row in result.bets if row["test_year"] == 2024} == {"pl_mid"}
    stakes = [cast(int, row["stake_yen"]) for row in result.bets]
    assert _mapping(result.report["all_test_years"])["stake_yen"] == sum(stakes)
    common = _mapping(result.report["common_years"])
    assert common["years"] == [2025]
    assert _mapping(common["selected"])["stake_yen"] == policy["stake_yen"]


def _varied_hits() -> list[HitObservation]:
    """Return place hits whose width bands have different final-to-freeze ratios."""
    ratios = {"01": 1.0, "02": 1.5, "03": 0.6}
    hits: list[HitObservation] = []
    for year in (2023, 2024, 2025):
        for hit in scenario_hits(year):
            hits.append(
                HitObservation(
                    hit.race_id,
                    hit.bet_type,
                    hit.combination,
                    hit.freeze_odds,
                    hit.final_odds * ratios[hit.combination],
                    hit.publication_age_seconds,
                )
            )
    return hits


def test_each_method_uses_its_own_probabilities_and_place_odds() -> None:
    settings = _settings((2024, 2025))
    hits = _varied_hits()
    estimators = backtest._year_estimators(
        2025,
        settings,
        hits,
        backtest._width_observations(hits),
        _training((2024, 2025)),
        frozenset(),
    )
    race_id_2025 = scenario_race_ids(2025)[0]
    race = GradedRaceInput(
        race_id_2025,
        [ra_row(race_id_2025)],
        [o1_row(race_id_2025)],
        se_rows(race_id_2025),
        [hr_row(race_id_2025)],
    )
    prediction = race_predictions(
        prediction_rows(race_id_2025), variant="all_columns", test_years=(2025,)
    )[race_id_2025]

    candidates = {
        method: backtest._race_candidates(race, prediction, method, estimators, settings)[0]
        for method in METHODS
    }

    def by_key(method: Method) -> dict[tuple[str, str], BetCandidate]:
        return {(item.bet_type, item.horse_number): item for item in candidates[method]}

    quotes = freeze_quotes(
        race_id_2025,
        race.o1_rows,
        datetime(2025, 6, 15, 6, 25, tzinfo=UTC),
        max_publication_age_seconds=600,
    )
    fit = estimators.blend
    assert fit.alpha is not None
    assert fit.beta is not None
    win, _, top3 = blend_probabilities(
        [math.log(horse.p_win) for horse in prediction.horses],
        market_log_probabilities(
            [cast(float, horse.market_win_odds) for horse in prediction.horses]
        ),
        alpha=fit.alpha,
        beta=fit.beta,
    )
    for (bet_type, number), mid_item in by_key("pl_mid").items():
        width_item = by_key("pl_width")[(bet_type, number)]
        blend_item = by_key("blend_mid")[(bet_type, number)]
        blend_width_item = by_key("blend_width")[(bet_type, number)]
        index = int(number) - 1
        assert width_item.probability == mid_item.probability
        assert blend_item.probability == blend_width_item.probability
        expected = win[index] if bet_type == "win" else top3[index]
        assert blend_item.probability == pytest.approx(expected)
        assert blend_item.probability != pytest.approx(mid_item.probability)
        assert blend_item.estimated_odds == mid_item.estimated_odds
        assert blend_width_item.estimated_odds == width_item.estimated_odds
        if bet_type == "place":
            width = place_width(
                cast(float, quotes.place_low[number]), cast(float, quotes.place_high[number])
            )
            assert width is not None
            assert width_item.estimated_odds == estimators.width.estimate(
                mid_item.freeze_odds, width
            )
    assert any(
        by_key("pl_width")[key].estimated_odds != pytest.approx(item.estimated_odds)
        for key, item in by_key("pl_mid").items()
        if key[0] == "place"
    )


def test_the_flat_recovery_rate_pools_every_comparison_year() -> None:
    years = (2024, 2025, 2026, 2027)
    result = _scenario(years)

    selection = _mapping(_mapping(result.report["selection"])["2027"])
    assert selection["comparison_years"] == [2025, 2026]
    rates = _mapping(selection["flat_recovery_rate"])
    for method in METHODS:
        flats = [_mapping(_method_year(result, method, year)["flat"]) for year in (2025, 2026)]
        receipt = sum(cast(int, flat["receipt_yen"]) for flat in flats)
        stake = sum(cast(int, flat["stake_yen"]) for flat in flats)
        assert stake > 0
        assert rates[method] == receipt / stake
