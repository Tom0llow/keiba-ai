"""Tests for pure yearly final-odds fold evaluation and selection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest

from models.evaluation.final_odds_metrics import (
    BootstrapInterval,
    FinalOddsBootstrap,
)
from models.experiments.final_odds_evaluation import (
    FinalOddsEvaluation,
    FinalOddsEvaluationSettings,
    FinalOddsRaceSubset,
    evaluate_final_odds,
    select_final_odds_variant,
)
from models.serialization.final_odds_observations import (
    BET_TYPES,
    HitObservation,
    RaceHold,
    RaceObservations,
)
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1


def _bootstrap(
    payout_lower: float,
    payout_upper: float,
    mean_lower: float,
    mean_upper: float,
) -> FinalOddsBootstrap:
    return FinalOddsBootstrap(
        payout_ratio=BootstrapInterval(1.0, payout_lower, payout_upper),
        mean_payout_ratio=BootstrapInterval(1.0, mean_lower, mean_upper),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def _items(value: object) -> list[object]:
    return cast(list[object], value)


def test_yearly_fold_corrections_do_not_use_test_or_later_payouts() -> None:
    settings = _settings(test_years=(2016,))
    base = (
        _race(2014, 1, final_odds=4.0),
        _race(2015, 1, final_odds=6.0),
        _race(2016, 1, final_odds=8.0),
        _race(2017, 1, final_odds=10.0),
    )
    changed = (
        base[0],
        base[1],
        _with_final_odds(base[2], 80.0),
        _with_final_odds(base[3], 100.0),
    )

    original_report = _evaluate(base, settings).report
    changed_report = _evaluate(changed, settings).report

    original_fold = _mapping(_items(original_report["folds"])[0])
    changed_fold = _mapping(_items(changed_report["folds"])[0])
    original_corrections = original_fold["corrections"]
    changed_corrections = changed_fold["corrections"]
    assert json.dumps(original_corrections, sort_keys=True) == json.dumps(
        changed_corrections, sort_keys=True
    )


def test_merged_band_corrections_do_not_use_test_or_later_payouts() -> None:
    settings = replace(
        _settings(test_years=(2016,)),
        bands={bet_type: (1.0, 3.0, 10.0) for bet_type in BET_TYPES},
        min_hits=2,
    )
    base = (
        _race(2014, 1, final_odds=4.0, freeze_odds=2.0),
        _race(2015, 1, final_odds=6.0, freeze_odds=5.0),
        _race(2016, 1, final_odds=8.0, freeze_odds=5.0),
        _race(2016, 2, final_odds=30.0, freeze_odds=20.0),
        _race(2017, 1, final_odds=10.0, freeze_odds=5.0),
    )
    changed = (
        base[0],
        base[1],
        _with_final_odds(base[2], 80.0),
        _with_final_odds(base[3], 300.0),
        _with_final_odds(base[4], 100.0),
    )

    original_report = _evaluate(base, settings).report
    changed_report = _evaluate(changed, settings).report

    original_corrections = _mapping(_mapping(_items(original_report["folds"])[0])["corrections"])
    changed_corrections = _mapping(_mapping(_items(changed_report["folds"])[0])["corrections"])
    for bet_type in BET_TYPES:
        all_bands = _items(_mapping(_mapping(original_corrections["all"])[bet_type])["bands"])
        assert [_mapping(band)["source_lowers"] for band in all_bands] == [[1.0, 3.0, 10.0]]
    assert json.dumps(original_corrections, sort_keys=True) == json.dumps(
        changed_corrections, sort_keys=True
    )


@pytest.mark.parametrize(
    ("all_bootstrap", "graded_bootstrap", "expected"),
    [
        (_bootstrap(0.9, 1.1, 0.9, 1.1), _bootstrap(0.9, 1.1, 0.9, 1.1), "all"),
        (_bootstrap(1.1, 1.2, 0.9, 1.1), _bootstrap(0.9, 1.1, 0.9, 1.1), "graded"),
        (_bootstrap(0.9, 1.1, 0.9, 1.1), _bootstrap(0.8, 0.9, 0.9, 1.1), "all"),
        (_bootstrap(1.1, 1.2, 0.9, 1.1), _bootstrap(0.8, 0.9, 1.1, 1.2), None),
    ],
)
def test_decision_six_selects_the_expected_variant(
    all_bootstrap: FinalOddsBootstrap,
    graded_bootstrap: FinalOddsBootstrap,
    expected: str | None,
) -> None:
    selection = select_final_odds_variant(all_bootstrap, graded_bootstrap)

    assert selection.selected_variant == expected


def test_counts_keep_race_holds_and_each_table_hold_separate() -> None:
    o1_held = replace(
        _race(2016, 2, final_odds=8.0),
        holds=(RaceHold("2016010101010002", "o1", "stale_publication", "fixture"),),
    )
    o2_held = replace(
        _race(2016, 3, final_odds=8.0),
        holds=(
            RaceHold("2016010101010003", "o2", "no_publication", "fixture"),
            RaceHold("2016010101010003", "o2", "stale_publication", "fixture"),
        ),
    )
    race_held = replace(
        _race(2016, 4, final_odds=8.0),
        hits=(),
        holds=(RaceHold("2016010101010004", "race", "cancelled_race", "fixture"),),
    )
    report = _evaluate(
        (
            _race(2014, 1, final_odds=4.0),
            _race(2015, 1, final_odds=6.0),
            _race(2016, 1, final_odds=8.0),
            o1_held,
            o2_held,
            race_held,
        ),
        _settings(test_years=(2016,)),
    ).report

    counts = _mapping(report["counts"])
    assert counts["race_holds_by_reason"] == {"cancelled_race": 1}
    assert counts["table_holds_by_table_and_reason"] == {
        "o1": {"stale_publication": 1},
        "o2": {"no_publication": 1, "stale_publication": 1},
    }


def test_report_covers_every_variant_subset_and_bet_type() -> None:
    report = _evaluate(
        (
            _race(2014, 1, final_odds=4.0),
            _race(2015, 1, final_odds=6.0),
            _race(2016, 1, final_odds=8.0),
        ),
        _settings(test_years=(2016,)),
    ).report

    assert set(report) == {
        "format",
        "format_version",
        "config",
        "snapshot",
        "provenance",
        "race_subsets",
        "selection",
        "counts",
        "folds",
        "pooled",
    }
    assert report["format"] == "final_odds_evaluation"
    assert report["format_version"] == 1
    race_subsets = _mapping(report["race_subsets"])
    assert race_subsets[JRA_FLAT_GRADED_STAKES_V1] == {
        "definition": "fixture graded stakes",
        "source": {"table": "NL_RA_RACE", "snapshot_id": "fixture"},
    }
    fold = _mapping(_items(report["folds"])[0])
    corrections = _mapping(fold["corrections"])
    metrics = _mapping(fold["metrics"])
    for variant in ("all", "graded", "none"):
        assert set(_mapping(corrections[variant])) == set(BET_TYPES)
        for subset in ("all", JRA_FLAT_GRADED_STAKES_V1):
            variant_metrics = _mapping(metrics[variant])
            assert set(_mapping(variant_metrics[subset])) == set(BET_TYPES)
    for period in ("all_test_years", "2016_2020"):
        pooled = _mapping(_mapping(report["pooled"])[period])
        pooled_metrics = _mapping(pooled["metrics"])
        pooled_bootstrap = _mapping(pooled["bootstrap"])
        for variant in ("all", "graded", "none"):
            for subset in ("all", JRA_FLAT_GRADED_STAKES_V1):
                assert set(_mapping(_mapping(pooled_metrics[variant])[subset])) == set(BET_TYPES)
                assert set(_mapping(_mapping(pooled_bootstrap[variant])[subset])) == set(BET_TYPES)
        assert set(_mapping(pooled["differences"])) == {
            "all_minus_none",
            "graded_minus_none",
            "all_minus_graded",
        }
    assert set(_mapping(report["selection"])) == set(BET_TYPES)
    assert json.loads(json.dumps(report)) == report


def test_empty_graded_training_population_uses_the_all_race_fallback() -> None:
    report = evaluate_final_odds(
        (
            _race(2014, 1, final_odds=4.0),
            _race(2015, 1, final_odds=6.0),
            _race(2016, 1, final_odds=8.0),
        ),
        _settings(test_years=(2016,)),
        race_subsets={
            JRA_FLAT_GRADED_STAKES_V1: FinalOddsRaceSubset(
                frozenset(), "fixture graded stakes", {"table": "NL_RA_RACE"}
            )
        },
        config={"fixture": True},
        snapshot={"snapshot_id": "fixture"},
        provenance={"source_sha256": "fixture"},
    ).report

    folds = cast(list[object], report["folds"])
    fold = cast(Mapping[str, object], folds[0])
    corrections = cast(Mapping[str, object], fold["corrections"])
    graded_by_bet = cast(Mapping[str, object], corrections["graded"])
    graded = cast(Mapping[str, object], graded_by_bet["win"])
    bands = cast(list[Mapping[str, object]], graded["bands"])
    assert [band["hit_count"] for band in bands] == [0]
    metrics = cast(Mapping[str, object], fold["metrics"])
    graded_metrics = cast(Mapping[str, object], metrics["graded"])
    all_metrics = cast(Mapping[str, object], graded_metrics["all"])
    win_metrics = cast(Mapping[str, object], all_metrics["win"])
    assert win_metrics["hits"] == 1


def _settings(*, test_years: tuple[int, ...]) -> FinalOddsEvaluationSettings:
    return FinalOddsEvaluationSettings(
        train_start_year=2014,
        test_years=test_years,
        bands={bet_type: (1.0,) for bet_type in BET_TYPES},
        quantiles=(0.1, 0.5, 0.9),
        min_hits=1,
        graded_shrinkage_k=2,
        bootstrap_resamples=20,
        bootstrap_seed=0,
        bootstrap_confidence=0.95,
    )


def _evaluate(
    races: tuple[RaceObservations, ...], settings: FinalOddsEvaluationSettings
) -> FinalOddsEvaluation:
    return evaluate_final_odds(
        races,
        settings,
        race_subsets={
            JRA_FLAT_GRADED_STAKES_V1: FinalOddsRaceSubset(
                frozenset(race.race_id for race in races),
                "fixture graded stakes",
                {"table": "NL_RA_RACE", "snapshot_id": "fixture"},
            )
        },
        config={"fixture": True},
        snapshot={"snapshot_id": "fixture"},
        provenance={"source_sha256": "fixture"},
    )


def _race(
    year: int, number: int, *, final_odds: float, freeze_odds: float = 2.0
) -> RaceObservations:
    race_id = f"{year}01010101{number:04d}"
    hits = tuple(
        HitObservation(
            race_id=race_id,
            bet_type=bet_type,
            combination=f"{number:02d}",
            freeze_odds=freeze_odds,
            final_odds=final_odds,
            publication_age_seconds=60,
        )
        for bet_type in BET_TYPES
    )
    return RaceObservations(
        race_id=race_id,
        hits=hits,
        exclusions=(),
        holds=(),
        refund=False,
        publication_ages={"o1": 60, "o2": 120},
    )


def _with_final_odds(race: RaceObservations, final_odds: float) -> RaceObservations:
    return replace(
        race,
        hits=tuple(replace(hit, final_odds=final_odds) for hit in race.hits),
    )
