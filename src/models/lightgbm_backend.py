"""Connect validated model inputs to the lazily imported LightGBM backend."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

from models.ranking_dataset import RankingDataset
from models.ranking_rules import LABEL_GAIN, OBJECTIVE


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
