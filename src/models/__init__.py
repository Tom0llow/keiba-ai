"""Race-ranking model primitives for the LambdaRank MVP."""

from models.dataset.dataset import RankingDataset
from models.dataset.rows import FeatureRow, FeatureValue, RankingRow
from models.dataset.schema import FeatureSchema, FeatureSpec
from models.dataset.validation import label_for_finish_position
from models.evaluation.metrics import (
    RankingMetrics,
    evaluate_ranking,
    ndcg_at_3,
    top1_accuracy,
    top3_overlap,
)
from models.evaluation.walk_forward import (
    WalkForwardConfig,
    WalkForwardEvaluation,
    WalkForwardFold,
    WalkForwardFoldResult,
    evaluate_walk_forward,
    make_walk_forward_folds,
)
from models.ranking.ranker import LightGBMUnavailableError, RankingModel, RankingPrediction
from models.ranking.rules import DEFAULT_LABEL_GAIN, TIE_BREAK_RULE
from models.training.train import train_lambdarank

__all__ = [
    "DEFAULT_LABEL_GAIN",
    "TIE_BREAK_RULE",
    "FeatureRow",
    "FeatureSchema",
    "FeatureSpec",
    "FeatureValue",
    "LightGBMUnavailableError",
    "RankingDataset",
    "RankingMetrics",
    "RankingModel",
    "RankingPrediction",
    "RankingRow",
    "WalkForwardConfig",
    "WalkForwardEvaluation",
    "WalkForwardFold",
    "WalkForwardFoldResult",
    "evaluate_ranking",
    "evaluate_walk_forward",
    "label_for_finish_position",
    "make_walk_forward_folds",
    "ndcg_at_3",
    "top1_accuracy",
    "top3_overlap",
    "train_lambdarank",
]
