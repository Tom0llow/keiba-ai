"""Race-level ranking metrics for the LambdaRank MVP."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, log2
from numbers import Real

from models.ranking_dataset import DEFAULT_LABEL_GAIN, RankingDataset


@dataclass(frozen=True)
class RankingMetrics:
    """Store race-equally weighted ranking metrics."""

    ndcg_at_3: float
    top1_accuracy: float
    top3_overlap: float


def evaluate_ranking(dataset: RankingDataset, scores: Sequence[float]) -> RankingMetrics:
    """Calculate NDCG@3, Top1, and Top3 overlap for every race."""
    validated_scores = _validate_scores(dataset, scores)
    return RankingMetrics(
        ndcg_at_3=ndcg_at_3(dataset, validated_scores),
        top1_accuracy=top1_accuracy(dataset, validated_scores),
        top3_overlap=top3_overlap(dataset, validated_scores),
    )


def ndcg_at_3(dataset: RankingDataset, scores: Sequence[float]) -> float:
    """Return the mean race-level NDCG@3 using the default LightGBM gains."""
    validated_scores = _validate_scores(dataset, scores)
    values: list[float] = []
    for start, stop in _race_ranges(dataset.groups):
        predicted_order = _score_order(validated_scores, start, stop)
        ideal_order = sorted(range(start, stop), key=lambda index: (-dataset.labels[index], index))
        predicted_dcg = _dcg(dataset.labels, predicted_order[:3])
        ideal_dcg = _dcg(dataset.labels, ideal_order[:3])
        values.append(predicted_dcg / ideal_dcg if ideal_dcg else 0.0)
    return sum(values) / len(values)


def top1_accuracy(dataset: RankingDataset, scores: Sequence[float]) -> float:
    """Return the fraction of races whose predicted first row is the winner."""
    validated_scores = _validate_scores(dataset, scores)
    correct = 0
    for start, stop in _race_ranges(dataset.groups):
        predicted_winner = _score_order(validated_scores, start, stop)[0]
        actual_order = sorted(range(start, stop), key=lambda index: (-dataset.labels[index], index))
        if dataset.labels[actual_order[0]] == 3 and predicted_winner == actual_order[0]:
            correct += 1
    return correct / len(dataset.groups)


def top3_overlap(dataset: RankingDataset, scores: Sequence[float]) -> float:
    """Return the mean overlap of predicted and actual top-three sets.

    The denominator is three, matching the ADR-009 MVP definition.
    """
    validated_scores = _validate_scores(dataset, scores)
    overlaps: list[float] = []
    for start, stop in _race_ranges(dataset.groups):
        predicted = set(_score_order(validated_scores, start, stop)[:3])
        actual_order = sorted(range(start, stop), key=lambda index: (-dataset.labels[index], index))
        actual = set(actual_order[:3])
        overlaps.append(len(predicted & actual) / 3)
    return sum(overlaps) / len(overlaps)


def _validate_scores(dataset: RankingDataset, scores: Sequence[float]) -> tuple[float, ...]:
    if len(scores) != len(dataset.rows):
        raise ValueError("scores must have one value per dataset row")
    values: list[float] = []
    for score in scores:
        if isinstance(score, bool) or not isinstance(score, Real):
            raise ValueError("scores must be real numbers")
        values.append(float(score))

    validated = tuple(values)
    if any(not isfinite(score) for score in validated):
        raise ValueError("scores must be finite")
    return validated


def _race_ranges(groups: Sequence[int]) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    start = 0
    for group in groups:
        stop = start + group
        ranges.append((start, stop))
        start = stop
    return tuple(ranges)


def _score_order(scores: Sequence[float], start: int, stop: int) -> list[int]:
    return sorted(range(start, stop), key=lambda index: (-scores[index], index))


def _dcg(labels: Sequence[int], order: Sequence[int]) -> float:
    return sum(
        DEFAULT_LABEL_GAIN[labels[index]] / log2(rank + 2) for rank, index in enumerate(order)
    )


__all__ = [
    "RankingMetrics",
    "evaluate_ranking",
    "ndcg_at_3",
    "top1_accuracy",
    "top3_overlap",
]
