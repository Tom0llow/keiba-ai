"""Tests for fitting the ADR-045 race-day estimator from a backtest's results."""

from __future__ import annotations

import copy
from fractions import Fraction

import pytest

from models.artifacts.betting_estimator import manifest_from_record
from models.betting.methods import METHODS
from models.betting.policy import BettingPolicy
from models.experiments.betting_backtest import (
    GradedRaceInput,
    fit_year_estimators,
    run_betting_backtest,
    width_observations,
)
from models.experiments.betting_estimator import (
    BacktestResults,
    backtest_results,
    fit_betting_estimator,
)
from models.serialization.betting_inputs import BlendTraining, race_predictions
from tests.betting_estimator_fixtures import (
    SOURCES,
    blend_races,
    blend_training,
    estimator_settings,
    flat_results,
    varied_hits,
)
from tests.betting_fixtures import prediction_rows, ra_row, se_rows
from tests.betting_scenario import scenario_hr_rows, scenario_o1_rows, scenario_race_ids

ODDS = (1.0, 1.2, 1.5, 1.99, 2.0, 2.5, 4.0, 6.0, 30.0)
WIDTHS = (Fraction(1), Fraction(3, 2), Fraction(2), Fraction(5, 2), Fraction(4), Fraction(7))


def test_the_target_year_fit_equals_the_backtest_fit_of_that_year() -> None:
    hits = varied_hits(range(2021, 2025))
    record, fitted = fit_betting_estimator(
        settings=estimator_settings((2023, 2024)),
        results=flat_results((2023, 2024)),
        hits=hits,
        graded_race_ids=frozenset({hits[0].race_id}),
        blend_training=blend_training((2023, 2024)),
        sources=SOURCES,
        provenance={},
    )
    expected = fit_year_estimators(
        2025,
        estimator_settings((2023, 2024, 2025)),
        hits,
        width_observations(hits),
        blend_training((2023, 2024, 2025)),
        frozenset({hits[0].race_id}),
    )

    assert record.target_year == 2025
    assert record.blend.available
    assert (record.blend.alpha, record.blend.beta) == (expected.blend.alpha, expected.blend.beta)
    assert record.blend_excluded == expected.blend_excluded
    for odds in ODDS:
        assert fitted.mid.estimate(odds) == expected.mid.estimate(odds)
        for width in WIDTHS:
            assert fitted.width.estimate(odds, width) == expected.width.estimate(odds, width)


def test_data_from_the_target_year_on_never_changes_the_record() -> None:
    settings = estimator_settings((2023, 2024))
    base_hits = varied_hits(range(2021, 2025))
    later_hits = [*base_hits, *varied_hits((2025, 2026))]
    later_training = BlendTraining(
        races={**blend_training((2023, 2024)).races, 2025: blend_races(99)},
        excluded={year: {"market_incomplete": 9} for year in (2023, 2024, 2025)},
    )
    base_training = BlendTraining(
        races=blend_training((2023, 2024)).races,
        excluded={year: {"market_incomplete": 9} for year in (2023, 2024)},
    )

    def manifest(hits: list, training: BlendTraining) -> dict[str, object]:  # type: ignore[type-arg]
        record, _ = fit_betting_estimator(
            settings=settings,
            results=flat_results((2023, 2024)),
            hits=hits,
            graded_race_ids=frozenset(),
            blend_training=training,
            sources=SOURCES,
            provenance={},
        )
        return manifest_from_record(record)

    assert manifest(later_hits, later_training) == manifest(base_hits, base_training)


def test_the_method_follows_decision_4_and_falls_back_without_a_blend() -> None:
    hits = varied_hits(range(2021, 2025))

    def fit(training: BlendTraining) -> str:
        record, _ = fit_betting_estimator(
            settings=estimator_settings((2023, 2024)),
            results=flat_results((2023, 2024), "blend_mid"),
            hits=hits,
            graded_race_ids=frozenset(),
            blend_training=training,
            sources=SOURCES,
            provenance={},
        )
        return record.method

    assert fit(blend_training((2023, 2024))) == "blend_mid"
    too_few = BlendTraining(races={2023: blend_races(2023, 5)}, excluded={})
    assert fit(too_few) == "pl_mid"


def _report() -> dict[str, object]:
    settings = estimator_settings((2024, 2025), train_start_year=2023, place_bands=(1.0,))
    races = [
        GradedRaceInput(race, [ra_row(race)], scenario_o1_rows(year)[race], se_rows(race), [])
        for year in (2024, 2025)
        for race in scenario_race_ids(year)
    ]
    races = [
        GradedRaceInput(
            race.race_id,
            race.ra_rows,
            race.o1_rows,
            race.se_rows,
            scenario_hr_rows(int(race.race_id[:4]))[race.race_id],
        )
        for race in races
    ]
    rows = [row for year in (2024, 2025) for row in prediction_rows(scenario_race_ids(year)[0])]
    backtest = run_betting_backtest(
        settings=settings,
        graded_races=races,
        predictions=race_predictions(rows, variant="all_columns", test_years=(2024, 2025)),
        target_hold_stages={},
        training_hits=varied_hits((2023, 2024, 2025)),
        blend_training=blend_training((2024, 2025)),
        graded_race_ids=frozenset(),
        config={},
        inputs={},
        provenance={},
    )
    return backtest.report


def test_a_backtest_reports_flat_results_are_read_and_its_selection_checked() -> None:
    report = _report()

    results = backtest_results(report, (2024, 2025))

    for method in METHODS:
        years = report["methods"][method]["years"]  # type: ignore[index]
        for year in (2024, 2025):
            flat = years[str(year)]["flat"]
            if flat is None:
                assert year not in results.flat[method]
            else:
                assert results.flat[method][year] == (flat["receipt_yen"], flat["stake_yen"])


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(format_version=1),
        lambda r: r["methods"].pop("pl_width"),
        lambda r: r["methods"]["pl_mid"]["years"]["2025"].update(available="yes"),
        lambda r: r["methods"]["pl_mid"]["years"]["2025"]["flat"].update(stake_yen=True),
        lambda r: r["methods"]["pl_mid"]["years"]["2025"]["flat"].update(stake_yen=-1),
        lambda r: r["methods"]["blend_mid"]["years"]["2024"].update(flat={"stake_yen": 0}),
        lambda r: r["selection"]["2025"].update(method="pl_width"),
        lambda r: r["selection"]["2025"].update(comparison_years=[2024]),
    ],
)
def test_a_backtest_report_that_breaks_its_own_rules_is_rejected(change: object) -> None:
    report = copy.deepcopy(_report())
    change(report)  # type: ignore[operator]

    with pytest.raises(ValueError, match="backtest report"):
        backtest_results(report, (2024, 2025))


def test_the_policy_and_settings_are_copied_from_the_backtest() -> None:
    settings = estimator_settings((2023, 2024), policy=BettingPolicy(race_budget_yen=3000))
    record, _ = fit_betting_estimator(
        settings=settings,
        results=BacktestResults(flat=flat_results((2023, 2024)).flat),
        hits=varied_hits(range(2021, 2025)),
        graded_race_ids=frozenset(),
        blend_training=blend_training((2023, 2024)),
        sources=SOURCES,
        provenance={},
    )

    assert record.policy.race_budget_yen == 3000
    assert record.settings.place_mid_bands == settings.place_bands
    assert record.blend_fit_years == (2023, 2024)
    assert record.comparison_years == (2023, 2024)
