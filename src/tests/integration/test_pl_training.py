"""Train the top-three Plackett--Luce objective with the real LightGBM backend."""

from __future__ import annotations

from typing import cast

import numpy as np
import pytest

from models.backends.lightgbm import fit_native_pl_booster
from models.dataset.race_arrays import RaceArrays
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


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"objective": "lambdarank"}, "reserved"),
        ({"metric": "ndcg"}, "reserved"),
        ({"n_estimators": 10}, "reserved"),
        ({"early_stopping_round": 3}, "reserved"),
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
