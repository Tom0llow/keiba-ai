"""Race-ranking model primitives for the LambdaRank MVP."""

from models.evaluate_model import (
    RankingMetrics,
    evaluate_ranking,
    ndcg_at_3,
    top1_accuracy,
    top3_overlap,
)
from models.predict_model import RankingModel, RankingPrediction
from models.ranker import LightGBMUnavailableError
from models.ranking_dataset import (
    DEFAULT_LABEL_GAIN,
    TIE_BREAK_RULE,
    FeatureRow,
    FeatureSchema,
    FeatureSpec,
    FeatureValue,
    RankingDataset,
    RankingRow,
    label_for_finish_position,
)
from models.train_model import train_lambdarank
from models.walk_forward import (
    WalkForwardConfig,
    WalkForwardEvaluation,
    WalkForwardFold,
    WalkForwardFoldResult,
    evaluate_walk_forward,
    make_walk_forward_folds,
)

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
