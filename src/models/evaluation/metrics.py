"""Race-level ranking metrics for the LambdaRank MVP."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from math import isfinite, log2
from numbers import Real

from models.dataset.dataset import RankingDataset
from models.ranking.rules import DEFAULT_LABEL_GAIN, race_ranges, score_order


@dataclass(frozen=True)
class RankingMetrics:
    """Store race-equally weighted ranking metrics."""

    ndcg_at_3: float
    top1_accuracy: float
    top3_overlap: float


def evaluate_ranking(dataset: RankingDataset, scores: Sequence[float]) -> RankingMetrics:
    """Calculate NDCG@3, Top1, and Top3 overlap for every race."""
    validated_scores = _validate_scores(dataset, scores)
    ndcg_values: list[float] = []
    top1_values: list[bool] = []
    overlap_values: list[float] = []
    for predicted, actual in _race_orders(dataset, validated_scores):
        ndcg_values.append(_race_ndcg(dataset.labels, predicted, actual))
        top1_values.append(_race_top1(dataset.labels, predicted, actual))
        overlap_values.append(_race_top3_overlap(predicted, actual))
    race_count = len(dataset.groups)
    return RankingMetrics(
        ndcg_at_3=sum(ndcg_values) / race_count,
        top1_accuracy=sum(top1_values) / race_count,
        top3_overlap=sum(overlap_values) / race_count,
    )


def ndcg_at_3(dataset: RankingDataset, scores: Sequence[float]) -> float:
    """Return the mean race-level NDCG@3 using the default LightGBM gains."""
    validated_scores = _validate_scores(dataset, scores)
    return sum(
        _race_ndcg(dataset.labels, predicted, actual)
        for predicted, actual in _race_orders(dataset, validated_scores)
    ) / len(dataset.groups)


def top1_accuracy(dataset: RankingDataset, scores: Sequence[float]) -> float:
    """Return the fraction of races whose predicted first row is the winner."""
    validated_scores = _validate_scores(dataset, scores)
    return sum(
        _race_top1(dataset.labels, predicted, actual)
        for predicted, actual in _race_orders(dataset, validated_scores)
    ) / len(dataset.groups)


def top3_overlap(dataset: RankingDataset, scores: Sequence[float]) -> float:
    """Return the mean overlap of predicted and actual top-three sets.

    The denominator is three, matching the ADR-009 MVP definition.
    """
    validated_scores = _validate_scores(dataset, scores)
    return sum(
        _race_top3_overlap(predicted, actual)
        for predicted, actual in _race_orders(dataset, validated_scores)
    ) / len(dataset.groups)


def _race_orders(
    dataset: RankingDataset, scores: Sequence[float]
) -> Iterator[tuple[list[int], list[int]]]:
    horse_ids = tuple(row.horse_id for row in dataset.rows)
    for start, stop in race_ranges(dataset.groups):
        predicted = score_order(scores, horse_ids, start, stop)
        actual = sorted(range(start, stop), key=lambda index: (-dataset.labels[index], index))
        yield predicted, actual


def _race_ndcg(labels: Sequence[int], predicted: Sequence[int], actual: Sequence[int]) -> float:
    predicted_dcg = _dcg(labels, predicted[:3])
    ideal_dcg = _dcg(labels, actual[:3])
    return predicted_dcg / ideal_dcg if ideal_dcg else 0.0


def _race_top1(labels: Sequence[int], predicted: Sequence[int], actual: Sequence[int]) -> bool:
    return labels[actual[0]] == 3 and predicted[0] == actual[0]


def _race_top3_overlap(predicted: Sequence[int], actual: Sequence[int]) -> float:
    return len(set(predicted[:3]) & set(actual[:3])) / 3


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
