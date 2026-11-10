"""Connect validated model inputs to the lazily imported LightGBM backend."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt

from models.dataset.dataset import RankingDataset
from models.dataset.race_arrays import RaceArrays
from models.probability.plackett_luce import RaceLayout, top3_plackett_luce
from models.ranking.rules import LABEL_GAIN, OBJECTIVE

PL_VALID_METRIC = "pl_top3_nll"
_PL_RESERVED_PARAMETERS = frozenset(
    {
        "objective",
        "objective_type",
        "app",
        "application",
        "loss",
        "metric",
        "metrics",
        "metric_types",
        "num_iterations",
        "num_iteration",
        "n_iter",
        "num_tree",
        "num_trees",
        "num_round",
        "num_rounds",
        "nrounds",
        "num_boost_round",
        "n_estimators",
        "max_iter",
        "early_stopping_round",
        "early_stopping_rounds",
        "early_stopping",
        "n_iter_no_change",
        "verbosity",
        "verbose",
    }
)
_PL_BOOSTING_KEYS = ("boosting", "boosting_type", "boost")


class LightGBMUnavailableError(ImportError):
    """Indicate that the optional LightGBM dependency is not installed."""


class NativeBooster(Protocol):
    """Describe the native booster operations used by inference and artifacts."""

    params: Mapping[str, object]

    def predict(self, data: object) -> object:
        """Return raw model scores."""

    def feature_name(self) -> object:
        """Return the native model feature names."""

    def save_model(self, filename: str) -> object:
        """Write the LightGBM native model format."""


class LightGBMRanker(Protocol):
    """Describe the estimator operations used at the training boundary."""

    booster_: NativeBooster

    def fit(
        self,
        features: object,
        labels: object,
        *,
        group: Sequence[int],
        feature_name: Sequence[str],
    ) -> object:
        """Fit the ranker."""


def load_lightgbm() -> ModuleType:
    """Import LightGBM only when training or loading a model requires it."""
    try:
        return importlib.import_module("lightgbm")
    except ImportError as exc:
        raise LightGBMUnavailableError(
            "LightGBM is required for training, prediction, and model loading"
        ) from exc


def fit_native_ranker(dataset: RankingDataset, parameters: Mapping[str, object]) -> NativeBooster:
    """Fit a LightGBM estimator and return its trained native booster."""
    module = load_lightgbm()
    constructor = cast(Callable[..., object], module.__dict__["LGBMRanker"])
    ranker = cast(LightGBMRanker, constructor(**parameters))
    ranker.fit(
        dataset.feature_matrix(),
        list(dataset.labels),
        group=list(dataset.groups),
        feature_name=list(dataset.feature_names),
    )
    if not hasattr(ranker, "booster_"):
        raise ValueError("LightGBM did not expose a trained booster")
    return ranker.booster_


def load_native_booster(path: Path, feature_names: Sequence[str]) -> NativeBooster:
    """Load a native booster and verify its fixed feature and ranking contract."""
    module = load_lightgbm()
    constructor = cast(Callable[..., object], module.__dict__["Booster"])
    booster = cast(NativeBooster, constructor(model_file=str(path)))
    validate_native_booster(booster, feature_names)
    return booster


def _native_feature_names(booster: NativeBooster) -> tuple[str, ...]:
    value = booster.feature_name()
    if not isinstance(value, Sequence) or not all(isinstance(name, str) for name in value):
        raise ValueError("native model has invalid feature names")
    return tuple(cast(Sequence[str], value))


def validate_native_booster(
    booster: NativeBooster,
    feature_names: Sequence[str],
) -> None:
    """Validate native feature names, objective, and fixed label gains."""
    if _native_feature_names(booster) != tuple(feature_names):
        raise ValueError("native model feature names do not match metadata")
    parameters = booster.params
    if parameters.get("objective") != OBJECTIVE:
        raise ValueError(f"native model objective must be {OBJECTIVE!r}")
    label_gain = parameters.get("label_gain")
    if not isinstance(label_gain, Sequence) or isinstance(label_gain, (str, bytes)):
        raise ValueError("native model has invalid label_gain")
    if tuple(label_gain) != LABEL_GAIN:
        raise ValueError("native model label_gain does not match the MVP contract")


class PLBooster(Protocol):
    """Describe the native booster operations used by the PL evaluation."""

    best_iteration: int
    best_score: Mapping[str, Mapping[str, float]]

    def predict(self, data: object, *, num_iteration: int | None = None) -> object:
        """Return raw model scores."""

    def feature_name(self) -> object:
        """Return the native model feature names."""


@dataclass(frozen=True)
class PLBoosterFit:
    """Hold an early-stopped PL booster and its validation result."""

    booster: PLBooster
    best_iteration: int
    best_valid_nll: float
    feature_names: tuple[str, ...]

    def predict_scores(self, arrays: RaceArrays) -> npt.NDArray[np.float64]:
        """Return finite raw scores at the best iteration in the array row order."""
        if arrays.feature_names != self.feature_names:
            raise ValueError("feature names differ from the trained PL booster")
        values = np.asarray(
            self.booster.predict(arrays.features, num_iteration=self.best_iteration),
            dtype=np.float64,
        )
        if values.shape != (arrays.features.shape[0],) or not np.all(np.isfinite(values)):
            raise ValueError("LightGBM returned invalid PL scores")
        return values


def fit_native_pl_booster(
    train: RaceArrays,
    valid: RaceArrays,
    *,
    parameters: Mapping[str, object],
    num_boost_round: int,
    early_stopping_rounds: int,
) -> PLBoosterFit:
    """Train a top-three Plackett--Luce booster with validation early stopping.

    The custom objective returns the gradient and exact Hessian diagonal of
    the summed train-race NLL. Early stopping uses the race-mean top-three NLL
    of ``valid``. LightGBM's label is only required to build the datasets and
    is never read by the objective or the metric.

    Raises:
        LightGBMUnavailableError: If LightGBM is unavailable.
        ValueError: If reserved parameters, a non-gbdt booster, or invalid
            round settings are supplied, or the inputs disagree.
    """
    validate_pl_parameters(parameters)
    for name, value in (
        ("num_boost_round", num_boost_round),
        ("early_stopping_rounds", early_stopping_rounds),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if train.feature_names != valid.feature_names:
        raise ValueError("train and valid feature names must match")
    if not train.feature_names:
        raise ValueError("PL training requires at least one feature")

    module = load_lightgbm()
    dataset_constructor = cast(Callable[..., object], module.__dict__["Dataset"])
    train_function = cast(Callable[..., object], module.__dict__["train"])
    early_stopping = cast(Callable[..., object], module.__dict__["early_stopping"])
    feature_names = list(train.feature_names)
    train_layout = RaceLayout.from_group_sizes(train.group_sizes.tolist())
    valid_layout = RaceLayout.from_group_sizes(valid.group_sizes.tolist())
    train_positions = train.finish_positions
    valid_positions = valid.finish_positions
    train_set = dataset_constructor(
        train.features,
        label=train_positions.astype(np.float64),
        group=train.group_sizes.tolist(),
        feature_name=feature_names,
        free_raw_data=False,
    )
    valid_set = dataset_constructor(
        valid.features,
        label=valid_positions.astype(np.float64),
        group=valid.group_sizes.tolist(),
        feature_name=feature_names,
        reference=train_set,
        free_raw_data=False,
    )

    def objective(
        predictions: npt.NDArray[np.float64], dataset: object
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        if dataset is not train_set:
            raise ValueError("PL objective received an unexpected dataset")
        result = top3_plackett_luce(predictions, train_positions, train_layout)
        return result.gradient, result.hessian_diagonal

    def valid_metric(
        predictions: npt.NDArray[np.float64], dataset: object
    ) -> tuple[str, float, bool]:
        if dataset is not valid_set:
            raise ValueError("PL validation metric received an unexpected dataset")
        result = top3_plackett_luce(predictions, valid_positions, valid_layout)
        return PL_VALID_METRIC, float(result.race_nll.mean()), False

    booster = cast(
        PLBooster,
        train_function(
            {**parameters, "objective": objective, "metric": "None", "verbosity": -1},
            train_set,
            num_boost_round=num_boost_round,
            valid_sets=[valid_set],
            valid_names=["valid"],
            feval=valid_metric,
            callbacks=[early_stopping(early_stopping_rounds, verbose=False)],
        ),
    )
    names = booster.feature_name()
    if not isinstance(names, Sequence) or tuple(cast(Sequence[str], names)) != train.feature_names:
        raise ValueError("native PL booster feature names do not match the inputs")
    best_iteration = booster.best_iteration
    if isinstance(best_iteration, bool) or not isinstance(best_iteration, int):
        raise ValueError("LightGBM did not report a best iteration")
    if not 1 <= best_iteration <= num_boost_round:
        raise ValueError("LightGBM reported an invalid best iteration")
    best_valid_nll = float(booster.best_score["valid"][PL_VALID_METRIC])
    if not isfinite(best_valid_nll):
        raise ValueError("LightGBM reported a non-finite validation NLL")
    return PLBoosterFit(booster, best_iteration, best_valid_nll, train.feature_names)


def validate_pl_parameters(parameters: Mapping[str, object]) -> None:
    """Reject parameters that would override the PL objective, metric or early stopping."""
    if not isinstance(parameters, Mapping) or any(not isinstance(key, str) for key in parameters):
        raise ValueError("PL parameters must be a mapping with string keys")
    reserved = sorted(set(parameters) & _PL_RESERVED_PARAMETERS)
    if reserved:
        raise ValueError(f"PL parameters must not set reserved keys: {reserved!r}")
    for key in _PL_BOOSTING_KEYS:
        if key in parameters and parameters[key] != "gbdt":
            raise ValueError("PL training supports only boosting='gbdt'")
