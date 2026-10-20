"""Score feature rows and assign deterministic race-local ranks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import cast

from models.artifacts.native_model import NativeModelArtifact
from models.backends.lightgbm import (
    LightGBMUnavailableError as LightGBMUnavailableError,
)
from models.backends.lightgbm import (
    NativeBooster,
    validate_native_booster,
)
from models.dataset.rows import FeatureRow
from models.dataset.schema import FeatureSchema, validate_feature_names
from models.dataset.validation import validate_feature_rows
from models.ranking.rules import (
    OBJECTIVE,
    TIE_BREAK_RULE,
    race_group_sizes,
    race_ranges,
    score_order,
)


@dataclass(frozen=True)
class RankingPrediction:
    """Return one finite score and its deterministic race-local rank."""

    race_id: str
    horse_id: str
    score: float
    rank: int


@dataclass(frozen=True)
class RankingModel:
    """Wrap a native LightGBM booster for score-only ranking inference."""

    _booster: NativeBooster
    feature_names: tuple[str, ...]
    feature_schema: FeatureSchema
    objective: str = OBJECTIVE
    tie_break_rule: str = TIE_BREAK_RULE

    def __post_init__(self) -> None:
        """Validate the fixed model contract."""
        validate_feature_names(self.feature_names)
        if self.feature_schema.feature_names != self.feature_names:
            raise ValueError("feature_schema names must match feature_names")
        if self.objective != OBJECTIVE:
            raise ValueError(f"objective must be {OBJECTIVE!r}")
        if self.tie_break_rule != TIE_BREAK_RULE:
            raise ValueError(f"tie_break_rule must be {TIE_BREAK_RULE!r}")
        validate_native_booster(self._booster, self.feature_names)

    @classmethod
    def from_native_booster(
        cls,
        booster: NativeBooster,
        feature_names: Sequence[str],
        feature_schema: FeatureSchema,
    ) -> RankingModel:
        """Create a model wrapper around a trained native booster."""
        names = tuple(feature_names)
        if feature_schema.feature_names != names:
            raise ValueError("feature_schema names must match feature_names")
        return cls(booster, names, feature_schema)

    def predict_scores(
        self,
        rows: Sequence[FeatureRow],
        *,
        feature_schema: FeatureSchema | None = None,
    ) -> tuple[float, ...]:
        """Return finite LightGBM scores in the input row order."""
        schema = feature_schema or self.feature_schema
        if schema != self.feature_schema:
            raise ValueError("feature_schema does not match the trained model")
        normalized = validate_feature_rows(rows, self.feature_names)
        return self._predict_scores(normalized)

    def _predict_scores(self, rows: Sequence[FeatureRow]) -> tuple[float, ...]:
        raw_scores = self._booster.predict(
            [[row.features.get(name) for name in self.feature_names] for row in rows]
        )
        values = cast(Sequence[object], raw_scores)
        if len(values) != len(rows):
            raise ValueError("LightGBM returned an unexpected number of scores")
        scores = tuple(_finite_score(value) for value in values)
        return scores

    def predict(
        self,
        rows: Sequence[FeatureRow],
        *,
        feature_schema: FeatureSchema | None = None,
    ) -> tuple[RankingPrediction, ...]:
        """Return only race-local finite scores and ranks for all input rows."""
        normalized = validate_feature_rows(rows, self.feature_names)
        if feature_schema is not None and feature_schema != self.feature_schema:
            raise ValueError("feature_schema does not match the trained model")
        scores = self._predict_scores(normalized)
        predictions: list[RankingPrediction] = []
        horse_ids = tuple(row.horse_id for row in normalized)
        groups = race_group_sizes(row.race_id for row in normalized)
        for start, stop in race_ranges(groups):
            for rank, row_index in enumerate(score_order(scores, horse_ids, start, stop), start=1):
                row = normalized[row_index]
                predictions.append(
                    RankingPrediction(
                        race_id=row.race_id,
                        horse_id=row.horse_id,
                        score=scores[row_index],
                        rank=rank,
                    )
                )
        return tuple(predictions)

    def save(self, path: Path) -> None:
        """Save the native booster and JSON schema metadata without pickle."""
        NativeModelArtifact(path).save(self._booster, self.feature_schema)

    @classmethod
    def load(cls, path: Path) -> RankingModel:
        """Load a native LightGBM model after validating its JSON metadata."""
        contents = NativeModelArtifact(path).load()
        return cls(
            contents.booster,
            contents.feature_schema.feature_names,
            contents.feature_schema,
            contents.objective,
            contents.tie_break_rule,
        )


def _finite_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("LightGBM returned a non-numeric score")
    score = float(value)
    if not isfinite(score):
        raise ValueError("LightGBM returned a non-finite score")
    return score
