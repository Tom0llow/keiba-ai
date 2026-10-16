"""Training entry point for the LambdaRank MVP."""

from __future__ import annotations

from collections.abc import Mapping

from models.lightgbm_backend import (
    LightGBMUnavailableError,
    fit_native_ranker,
)
from models.ranker import RankingModel
from models.ranking_dataset import RankingDataset
from models.ranking_rules import LABEL_GAIN, OBJECTIVE

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
    ranker_parameters = dict(_DEFAULT_PARAMETERS)
    if parameters is not None:
        ranker_parameters.update(parameters)
    ranker_parameters["objective"] = OBJECTIVE
    ranker_parameters["label_gain"] = list(LABEL_GAIN)
    booster = fit_native_ranker(dataset, ranker_parameters)
    return RankingModel.from_native_booster(booster, dataset.feature_names, dataset.feature_schema)


__all__ = ["LightGBMUnavailableError", "train_lambdarank"]
