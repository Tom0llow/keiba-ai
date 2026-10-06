"""Prediction facade for score-and-rank-only model output."""

from models.ranker import RankingModel, RankingPrediction

__all__ = ["RankingModel", "RankingPrediction"]
