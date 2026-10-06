"""Training entry point for the LambdaRank MVP."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from models.ranker import (
    LightGBMUnavailableError,
    RankingModel,
    _LightGBMRanker,
    _load_lightgbm,
)
from models.ranking_dataset import DEFAULT_LABEL_GAIN, RankingDataset

_DEFAULT_PARAMETERS: Mapping[str, object] = {
    "deterministic": True,
    "force_col_wise": True,
    "learning_rate": 0.05,
    "min_child_samples": 5,
    "n_estimators": 30,
    "n_jobs": 1,
    "num_leaves": 7,
    "random_state": 0,
    "verbosity": -1,
}


def train_lambdarank(
    dataset: RankingDataset,
    *,
    parameters: Mapping[str, object] | None = None,
) -> RankingModel:
    """Train ``LGBMRanker(objective='lambdarank')`` on a validated dataset.

    The objective is fixed by this MVP API even if a caller supplies another
    value in ``parameters``. Feature missingness is passed to LightGBM as-is.

    Raises:
        LightGBMUnavailableError: If the optional dependency is unavailable.
        ValueError: If the training dataset is empty or LightGBM cannot fit it.
    """
    if not dataset.rows:
        raise ValueError("ranking dataset must contain at least one row")
    module = _load_lightgbm()
    ranker_constructor = cast(Callable[..., object], module.__dict__["LGBMRanker"])
    ranker_parameters = dict(_DEFAULT_PARAMETERS)
    if parameters is not None:
        ranker_parameters.update(parameters)
    ranker_parameters["objective"] = "lambdarank"
    ranker_parameters["label_gain"] = list(DEFAULT_LABEL_GAIN.values())
    ranker = cast(_LightGBMRanker, ranker_constructor(**ranker_parameters))
    ranker.fit(
        dataset.feature_matrix(),
        list(dataset.labels),
        group=list(dataset.groups),
        feature_name=list(dataset.feature_names),
    )
    if not hasattr(ranker, "booster_"):
        raise ValueError("LightGBM did not expose a trained booster")
    return RankingModel.from_native_booster(
        ranker.booster_, dataset.feature_names, dataset.feature_schema
    )


__all__ = ["LightGBMUnavailableError", "train_lambdarank"]
