"""Train the top-three Plackett--Luce objective with the real LightGBM backend."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import numpy as np
import pytest

from models.backends.lightgbm import fit_native_pl_booster
from models.dataset.race_arrays import RaceArrays
from models.evaluation.yearly_folds import plan_final_fit
from models.experiments.pl_evaluation import PLVariant
from models.experiments.pl_training import (
    PLTrainingSettings,
    train_final_pl,
    variant_columns,
)
from models.probability.calibration import calibrate_temperature
from models.probability.plackett_luce import RaceLayout, top3_plackett_luce
from tests.pl_fixtures import pl_parameters, synthetic_race_arrays


def _year(arrays: RaceArrays, year: int) -> RaceArrays:
    return arrays.subset([i for i, value in enumerate(arrays.years) if value == year])


def _split() -> tuple[RaceArrays, RaceArrays, RaceArrays]:
    arrays = synthetic_race_arrays((2020, 2021, 2022), races_per_year=120, seed=7)
    columns = ("signal", "noise")
    return (
        _year(arrays, 2020).columns(columns),
        _year(arrays, 2021).columns(columns),
        _year(arrays, 2022).columns(columns),
    )


def _mean_nll(scores: np.ndarray, arrays: RaceArrays) -> float:
    layout = RaceLayout.from_group_sizes(arrays.group_sizes.tolist())
    return float(top3_plackett_luce(scores, arrays.finish_positions, layout).race_nll.mean())


def test_pl_booster_learns_the_signal_and_reports_its_validation_nll() -> None:
    train, valid, test = _split()

    fit = fit_native_pl_booster(
        train,
        valid,
        parameters=pl_parameters(),
        num_boost_round=200,
        early_stopping_rounds=20,
    )
    scores = fit.predict_scores(test)
    uniform = np.zeros_like(scores)

    assert _mean_nll(scores, test) < _mean_nll(uniform, test) - 0.1
    assert 1 <= fit.best_iteration <= 200
    assert fit.feature_names == ("signal", "noise")
    assert tuple(cast(list[str], fit.booster.feature_name())) == ("signal", "noise")
    valid_scores = fit.predict_scores(valid)
    assert fit.best_valid_nll == pytest.approx(_mean_nll(valid_scores, valid), rel=1e-9)


def test_pl_booster_stops_early_when_validation_stagnates() -> None:
    arrays = synthetic_race_arrays(
        (2020, 2021), races_per_year=80, seed=3, random_finishes=True
    ).columns(("noise",))
    train = _year(arrays, 2020)
    valid = _year(arrays, 2021)

    fit = fit_native_pl_booster(
        train,
        valid,
        parameters={**pl_parameters(), "learning_rate": 0.5, "min_data_in_leaf": 5},
        num_boost_round=300,
        early_stopping_rounds=5,
    )

    assert fit.best_iteration < 300
    assert fit.best_valid_nll == pytest.approx(
        _mean_nll(fit.predict_scores(valid), valid), rel=1e-9
    )


def test_pl_booster_is_deterministic() -> None:
    train, valid, test = _split()

    first = fit_native_pl_booster(
        train,
        valid,
        parameters=pl_parameters(),
        num_boost_round=50,
        early_stopping_rounds=10,
    )
    second = fit_native_pl_booster(
        train,
        valid,
        parameters=pl_parameters(),
        num_boost_round=50,
        early_stopping_rounds=10,
    )

    np.testing.assert_array_equal(first.predict_scores(test), second.predict_scores(test))


def test_final_fit_rejects_valid_missing_values_in_columns_complete_in_train() -> None:
    arrays = synthetic_race_arrays(
        (2020, 2021, 2022), races_per_year=40, seed=13, incomplete_market_race=False
    )
    features = arrays.features.copy()
    row_years = np.repeat(arrays.years, arrays.group_sizes)
    features[int(np.flatnonzero(row_years == 2022)[0]), 1] = np.nan
    settings = PLTrainingSettings(
        train_start_year=2020,
        valid_year=2022,
        variant=PLVariant("all_columns"),
        lightgbm=pl_parameters(),
        num_boost_round=30,
        early_stopping_rounds=5,
        temperature_bounds=(0.05, 20.0),
    )

    with pytest.raises(ValueError, match="noise"):
        train_final_pl(replace(arrays, features=features), settings)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"objective": "lambdarank"}, "reserved"),
        ({"metric": "ndcg"}, "reserved"),
        ({"n_estimators": 10}, "reserved"),
        ({"early_stopping_round": 3}, "reserved"),
        ({"use_missing": False}, "reserved"),
        ({"zero_as_missing": True}, "reserved"),
        ({"boosting": "dart"}, "gbdt"),
        ({"boosting_type": "rf"}, "gbdt"),
    ],
)
def test_pl_booster_rejects_reserved_parameters_and_other_boosters(
    override: dict[str, object], message: str
) -> None:
    train, valid, _ = _split()

    with pytest.raises(ValueError, match=message):
        fit_native_pl_booster(
            train,
            valid,
            parameters={**pl_parameters(), **override},
            num_boost_round=10,
            early_stopping_rounds=2,
        )


# ADR-038: the final fit is one evaluation fold without a test year.


def _final_settings(**changes: object) -> PLTrainingSettings:
    values: dict[str, object] = {
        "train_start_year": 2020,
        "valid_year": 2022,
        "variant": PLVariant("all_columns"),
        "lightgbm": pl_parameters(),
        "num_boost_round": 60,
        "early_stopping_rounds": 10,
        "temperature_bounds": (0.05, 20.0),
    }
    values.update(changes)
    return PLTrainingSettings(**values)  # type: ignore[arg-type]


def test_final_fit_equals_the_evaluation_functions_on_the_same_split() -> None:
    arrays = synthetic_race_arrays((2020, 2021, 2022), races_per_year=80, seed=5)
    settings = _final_settings()

    final = train_final_pl(arrays, settings)

    split = plan_final_fit(arrays, train_start_year=2020, valid_year=2022).materialize(arrays)
    names = arrays.feature_names
    direct = fit_native_pl_booster(
        split.train.columns(names),
        split.valid.columns(names),
        parameters=settings.lightgbm,
        num_boost_round=settings.num_boost_round,
        early_stopping_rounds=settings.early_stopping_rounds,
    )
    valid = split.valid.columns(names)
    direct_scores = direct.predict_scores(valid)
    direct_temperature = calibrate_temperature(
        direct_scores,
        valid.finish_positions,
        RaceLayout.from_group_sizes(valid.group_sizes.tolist()),
        temperature_bounds=settings.temperature_bounds,
    )
    assert final.fit.best_iteration == direct.best_iteration
    assert final.fit.best_valid_nll == direct.best_valid_nll
    assert final.temperature == direct_temperature
    np.testing.assert_array_equal(final.valid_scores, direct_scores)
    assert final.audit == split.audit
    assert (final.train_races, final.valid_races) == (160, 80)
    assert final.valid_rows == int(valid.features.shape[0])


def test_final_fit_is_deterministic() -> None:
    arrays = synthetic_race_arrays((2020, 2021, 2022), races_per_year=60, seed=9)

    first = train_final_pl(arrays, _final_settings())
    second = train_final_pl(arrays, _final_settings())

    assert first.fit.best_iteration == second.fit.best_iteration
    assert first.temperature == second.temperature
    np.testing.assert_array_equal(first.valid_scores, second.valid_scores)


def test_final_fit_keeps_only_the_variant_columns_and_records_missingness() -> None:
    arrays = synthetic_race_arrays((2020, 2021, 2022), races_per_year=60, seed=9)

    final = train_final_pl(arrays, _final_settings(variant=PLVariant("without_noise", ("noise",))))

    assert final.feature_names == ("signal", "market_feature")
    assert tuple(cast(list[str], final.fit.booster.feature_name())) == final.feature_names
    # Only the market feature has missing values in train (its first race of each year).
    assert final.nullable_in_training == (False, True)


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        (PLVariant("bad", ("unknown",)), "unknown columns"),
        (PLVariant("empty", ("signal", "noise", "market_feature")), "every column"),
    ],
)
def test_variant_columns_reject_unknown_or_all_excluded_columns(
    variant: PLVariant, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        variant_columns(("signal", "noise", "market_feature"), variant)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"num_boost_round": 0}, "positive integer"),
        ({"valid_year": True}, "positive integer"),
        ({"lightgbm": {**pl_parameters(), "objective": "lambdarank"}}, "reserved"),
        ({"lightgbm": {**pl_parameters(), "boosting": "dart"}}, "gbdt"),
        ({"temperature_bounds": (0.0, 20.0)}, "temperature_bounds"),
        ({"variant": PLVariant("", ())}, "variant name"),
        ({"variant": PLVariant("dup", ("noise", "noise"))}, "unique"),
    ],
)
def test_final_settings_reject_invalid_values(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _final_settings(**changes)
