"""Tests for race-level chronological walk-forward evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from models.ranking_dataset import FeatureRow, FeatureSchema, RankingDataset, RankingRow
from models.walk_forward import (
    WalkForwardConfig,
    evaluate_walk_forward,
    make_walk_forward_folds,
)


def _schema() -> FeatureSchema:
    return FeatureSchema.from_names(("ability",), schema_id="walk-forward-v1")


def _dataset(
    freeze_times: tuple[datetime, ...],
    *,
    race_ids: tuple[str, ...] | None = None,
) -> RankingDataset:
    ids = race_ids or tuple(f"race-{index}" for index in range(len(freeze_times)))
    rows = [
        RankingRow(
            race_id=race_id,
            horse_id=f"horse-{horse_index}",
            features={"ability": float(4 - horse_index)},
            finish_position=horse_index,
            freeze_at=freeze_at,
        )
        for race_id, freeze_at in zip(ids, freeze_times, strict=True)
        for horse_index in range(1, 4)
    ]
    return RankingDataset.from_rows(
        rows,
        feature_names=("ability",),
        feature_schema=_schema(),
    )


class _FeatureScoreModel:
    def predict_scores(self, rows: Sequence[FeatureRow]) -> tuple[float, ...]:
        return tuple(float(cast(float, row.features["ability"])) for row in rows)


def _times(count: int) -> tuple[datetime, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(start + timedelta(days=index) for index in range(count))


def test_folds_are_race_complete_and_chronological() -> None:
    dataset = _dataset(_times(5))
    folds = make_walk_forward_folds(
        dataset,
        WalkForwardConfig(min_train_races=2, validation_races=1, test_races=1, step_races=1),
    )

    assert len(folds) == 2
    assert folds[0].train_race_ids == ("race-0", "race-1")
    assert folds[0].validation_race_ids == ("race-2",)
    assert folds[0].test_race_ids == ("race-3",)
    assert folds[1].train_race_ids == ("race-0", "race-1", "race-2")
    assert not set(folds[0].train_race_ids) & set(folds[0].test_race_ids)
    assert len(folds[0].test.rows) == 3


def test_evaluation_trains_only_on_past_and_returns_fold_metrics() -> None:
    dataset = _dataset(_times(5))
    trained_on: list[tuple[str, ...]] = []

    def trainer(train_dataset: RankingDataset) -> _FeatureScoreModel:
        trained_on.append(tuple(row.race_id for row in train_dataset.rows))
        return _FeatureScoreModel()

    evaluation = evaluate_walk_forward(
        dataset,
        WalkForwardConfig(min_train_races=2, validation_races=1, test_races=1, step_races=1),
        trainer=trainer,
    )

    assert trained_on == [
        ("race-0", "race-0", "race-0", "race-1", "race-1", "race-1"),
        (
            "race-0",
            "race-0",
            "race-0",
            "race-1",
            "race-1",
            "race-1",
            "race-2",
            "race-2",
            "race-2",
        ),
    ]
    assert all(result.metrics.ndcg_at_3 == 1.0 for result in evaluation)
    assert evaluation.metrics.top1_accuracy == 1.0


@pytest.mark.parametrize(
    "freeze_times",
    [
        (datetime(2026, 1, 1, tzinfo=UTC),) * 4,
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 4, tzinfo=UTC),
        ),
    ],
)
def test_folds_reject_duplicate_or_non_monotonic_freeze_times(
    freeze_times: tuple[datetime, ...],
) -> None:
    with pytest.raises(ValueError, match=r"duplicate|strictly increasing"):
        make_walk_forward_folds(
            _dataset(freeze_times),
            WalkForwardConfig(min_train_races=1, validation_races=1, test_races=1, step_races=1),
        )


def test_folds_reject_insufficient_races_and_non_contiguous_rows() -> None:
    with pytest.raises(ValueError, match="insufficient"):
        make_walk_forward_folds(
            _dataset(_times(3)),
            WalkForwardConfig(min_train_races=2, validation_races=1, test_races=1, step_races=1),
        )

    rows = [
        RankingRow("race-0", "horse-1", {"ability": 3.0}, 1, _times(2)[0]),
        RankingRow("race-0", "horse-2", {"ability": 2.0}, 2, _times(2)[0]),
        RankingRow("race-0", "horse-3", {"ability": 1.0}, 3, _times(2)[0]),
        RankingRow("race-1", "horse-1", {"ability": 3.0}, 1, _times(2)[1]),
        RankingRow("race-1", "horse-2", {"ability": 2.0}, 2, _times(2)[1]),
        RankingRow("race-1", "horse-3", {"ability": 1.0}, 3, _times(2)[1]),
        RankingRow("race-0", "horse-4", {"ability": 0.0}, 4, _times(2)[0]),
    ]
    with pytest.raises(ValueError, match="contiguous"):
        RankingDataset.from_rows(
            rows,
            feature_names=("ability",),
            feature_schema=_schema(),
        )
