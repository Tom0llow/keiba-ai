"""Immutable model input rows and numeric value types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal

type TimestampInput = datetime | str

type FeatureValue = int | float | None

type FeatureValueType = Literal["numeric"]

type MissingValuePolicy = Literal["preserve_native_missing"]


@dataclass(frozen=True)
class FeatureRow:
    """Represent one horse's feature values for prediction."""

    race_id: str
    horse_id: str
    features: Mapping[str, FeatureValue]
    freeze_at: datetime | None = None
    available_at: Mapping[str, datetime | None] = MappingProxyType({})


@dataclass(frozen=True)
class RankingRow:
    """Represent one labeled horse row for ranking training."""

    race_id: str
    horse_id: str
    features: Mapping[str, FeatureValue]
    finish_position: int
    freeze_at: datetime | None = None


@dataclass(frozen=True)
class FeatureInput:
    """Describe one horse's raw feature values at an explicit freeze time."""

    race_id: str
    horse_id: str
    freeze_at: TimestampInput
    features: Mapping[str, FeatureValue]
    available_at: Mapping[str, TimestampInput | None]
    finish_position: int | None = None
