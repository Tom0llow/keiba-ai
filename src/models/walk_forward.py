"""Race-level chronological walk-forward splitting and evaluation."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from models.evaluate_model import RankingMetrics, evaluate_ranking
from models.ranking_dataset import FeatureRow, RankingDataset, RankingRow
from models.train_model import train_lambdarank


class _ScoreModel(Protocol):
    def predict_scores(self, rows: Sequence[FeatureRow]) -> Sequence[float]:
        """Return one finite score for each feature row."""


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configure expanding chronological race-level evaluation windows."""

    min_train_races: int
    validation_races: int
    test_races: int
    step_races: int

    def __post_init__(self) -> None:
        for name in ("min_train_races", "validation_races", "test_races", "step_races"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class WalkForwardFold:
    """Describe one race-disjoint train, validation, and test window.

    The source dataset and race boundaries are retained instead of materializing
    an expanding training dataset for every fold.  The public dataset
    properties build the requested split on demand.
    """

    fold_index: int
    train_race_ids: tuple[str, ...]
    validation_race_ids: tuple[str, ...]
    test_race_ids: tuple[str, ...]
    train_freeze_at: tuple[datetime, ...]
    validation_freeze_at: tuple[datetime, ...]
    test_freeze_at: tuple[datetime, ...]
    _dataset: RankingDataset = field(repr=False, compare=False)
    _races: tuple[_RaceSlice, ...] = field(repr=False, compare=False)
    _train_bounds: tuple[int, int] = field(repr=False, compare=False)
    _validation_bounds: tuple[int, int] = field(repr=False, compare=False)
    _test_bounds: tuple[int, int] = field(repr=False, compare=False)

    @property
    def train(self) -> RankingDataset:
        """Build the expanding training dataset for this fold on demand."""
        return _dataset_for_races(self._dataset, self._races[slice(*self._train_bounds)])

    @property
    def validation(self) -> RankingDataset:
        """Build the validation dataset for this fold on demand."""
        return _dataset_for_races(
            self._dataset,
            self._races[slice(*self._validation_bounds)],
        )

    @property
    def test(self) -> RankingDataset:
        """Build the test dataset for this fold on demand."""
        return _dataset_for_races(self._dataset, self._races[slice(*self._test_bounds)])


@dataclass(frozen=True)
class WalkForwardFoldResult:
    """Store one fold's test scores and race-level metrics."""

    fold: WalkForwardFold
    scores: tuple[float, ...]
    metrics: RankingMetrics


@dataclass(frozen=True)
class WalkForwardEvaluation:
    """Store every fold result and the equal-weight mean fold metrics."""

    fold_results: tuple[WalkForwardFoldResult, ...]
    metrics: RankingMetrics

    @property
    def results(self) -> tuple[WalkForwardFoldResult, ...]:
        """Return fold results in chronological order."""
        return self.fold_results

    @property
    def folds(self) -> tuple[WalkForwardFold, ...]:
        """Return fold descriptors in chronological order."""
        return tuple(result.fold for result in self.fold_results)

    def __iter__(self) -> Iterator[WalkForwardFoldResult]:
        """Iterate over fold results for convenient focused inspection."""
        return iter(self.fold_results)


def make_walk_forward_folds(
    dataset: RankingDataset,
    config: WalkForwardConfig,
) -> tuple[WalkForwardFold, ...]:
    """Split a validated dataset into chronological, race-complete folds.

    The input order must already be chronological by each race's common
    ``freeze_at``.  The train window expands from the first race, validation
    immediately follows train, and test immediately follows validation.
    """
    races = _race_slices(dataset)
    window_size = config.min_train_races + config.validation_races + config.test_races
    if len(races) < window_size:
        raise ValueError(
            "insufficient races for walk-forward configuration: "
            f"need {window_size}, got {len(races)}"
        )

    folds: list[WalkForwardFold] = []
    fold_index = 0
    cursor = 0
    while cursor + window_size <= len(races):
        train_stop = cursor + config.min_train_races
        validation_stop = train_stop + config.validation_races
        test_stop = validation_stop + config.test_races
        train_races = races[:train_stop]
        validation_races = races[train_stop:validation_stop]
        test_races = races[validation_stop:test_stop]
        folds.append(
            WalkForwardFold(
                fold_index=fold_index,
                train_race_ids=tuple(race.race_id for race in train_races),
                validation_race_ids=tuple(race.race_id for race in validation_races),
                test_race_ids=tuple(race.race_id for race in test_races),
                train_freeze_at=tuple(race.freeze_at for race in train_races),
                validation_freeze_at=tuple(race.freeze_at for race in validation_races),
                test_freeze_at=tuple(race.freeze_at for race in test_races),
                _dataset=dataset,
                _races=races,
                _train_bounds=(0, train_stop),
                _validation_bounds=(train_stop, validation_stop),
                _test_bounds=(validation_stop, test_stop),
            )
        )
        fold_index += 1
        cursor += config.step_races
    if not folds:
        raise ValueError("walk-forward configuration produced no complete folds")
    return tuple(folds)


def evaluate_walk_forward(
    dataset: RankingDataset,
    config: WalkForwardConfig,
    *,
    trainer: Callable[[RankingDataset], _ScoreModel] | None = None,
) -> WalkForwardEvaluation:
    """Train and evaluate one LambdaRank model per chronological fold.

    Only the fold's train dataset is sent to ``train_lambdarank``.  The
    validation dataset is retained in the descriptor for an outer caller's
    selection procedure and is never used to train or score the test fold.
    """
    folds = make_walk_forward_folds(dataset, config)
    train = train_lambdarank if trainer is None else trainer
    results: list[WalkForwardFoldResult] = []
    for fold in folds:
        model = train(fold.train)
        test_rows = tuple(
            FeatureRow(
                race_id=row.race_id,
                horse_id=row.horse_id,
                features=row.features,
                freeze_at=row.freeze_at,
            )
            for row in fold.test.rows
        )
        scores = tuple(model.predict_scores(test_rows))
        results.append(
            WalkForwardFoldResult(
                fold=fold,
                scores=scores,
                metrics=evaluate_ranking(fold.test, scores),
            )
        )
    return WalkForwardEvaluation(
        tuple(results), _mean_metrics(result.metrics for result in results)
    )


@dataclass(frozen=True)
class _RaceSlice:
    race_id: str
    rows: tuple[RankingRow, ...]
    freeze_at: datetime


def _race_slices(dataset: RankingDataset) -> tuple[_RaceSlice, ...]:
    slices: list[_RaceSlice] = []
    start = 0
    previous_freeze_at: datetime | None = None
    for group_size in dataset.groups:
        rows = tuple(dataset.rows[start : start + group_size])
        if not rows:
            raise ValueError("ranking dataset contains an empty race group")
        freeze_values = {row.freeze_at for row in rows}
        if None in freeze_values or len(freeze_values) != 1:
            raise ValueError("every row in a race must have the same aware freeze_at")
        freeze_at = next(iter(freeze_values))
        if not isinstance(freeze_at, datetime) or freeze_at.tzinfo is None:
            raise ValueError("freeze_at must be a timezone-aware datetime")
        if freeze_at.utcoffset() is None:
            raise ValueError("freeze_at must be a timezone-aware datetime")
        if previous_freeze_at is not None:
            if freeze_at == previous_freeze_at:
                raise ValueError("duplicate freeze_at values are not allowed across races")
            if freeze_at < previous_freeze_at:
                raise ValueError("race chronology must be strictly increasing by freeze_at")
        race_id = rows[0].race_id
        if any(row.race_id != race_id for row in rows):
            raise ValueError("ranking dataset group contains multiple race IDs")
        slices.append(_RaceSlice(race_id, rows, freeze_at))
        previous_freeze_at = freeze_at
        start += group_size
    return tuple(slices)


def _dataset_for_races(dataset: RankingDataset, races: Sequence[_RaceSlice]) -> RankingDataset:
    rows = tuple(row for race in races for row in race.rows)
    return RankingDataset.from_rows(
        rows,
        feature_names=dataset.feature_names,
        feature_schema=dataset.feature_schema,
    )


def _mean_metrics(metrics: Iterator[RankingMetrics]) -> RankingMetrics:
    values = tuple(metrics)
    if not values:
        raise ValueError("walk-forward evaluation requires at least one fold")
    return RankingMetrics(
        ndcg_at_3=sum(value.ndcg_at_3 for value in values) / len(values),
        top1_accuracy=sum(value.top1_accuracy for value in values) / len(values),
        top3_overlap=sum(value.top3_overlap for value in values) / len(values),
    )


__all__ = [
    "WalkForwardConfig",
    "WalkForwardEvaluation",
    "WalkForwardFold",
    "WalkForwardFoldResult",
    "evaluate_walk_forward",
    "make_walk_forward_folds",
]
