"""Tests for temporal feature construction and availability auditing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isnan

import pytest

from features.builder import (
    FeatureGenerationError,
    FeatureInput,
    audit_feature_availability,
    build_feature_rows,
    build_ranking_dataset,
)
from models.ranking_dataset import FeatureSchema


def _schema() -> FeatureSchema:
    return FeatureSchema.from_names(
        ("ability", "historical_odds"),
        schema_id="test-features-v1",
    )


def _records(
    *,
    freeze_at: datetime | str = "2026-01-01T12:00:00+00:00",
    historical_odds: float | None = None,
    finish_positions: tuple[int, int, int] | None = (1, 2, 3),
) -> list[FeatureInput]:
    available_at = {"ability": "2025-12-31T12:00:00+00:00"}
    return [
        FeatureInput(
            race_id="race-1",
            horse_id=f"horse-{index}",
            freeze_at=freeze_at,
            features={"ability": float(4 - index), "historical_odds": historical_odds},
            available_at=available_at,
            finish_position=None if finish_positions is None else finish_positions[index - 1],
        )
        for index in range(1, 4)
    ]


def test_build_ranking_dataset_preserves_freeze_at_and_schema_order() -> None:
    dataset = build_ranking_dataset(_records(), feature_schema=_schema())

    assert dataset.feature_names == ("ability", "historical_odds")
    assert [row.freeze_at for row in dataset.rows] == [datetime(2026, 1, 1, 12, tzinfo=UTC)] * 3
    assert dataset.feature_matrix() == [[3.0, None], [2.0, None], [1.0, None]]


def test_missing_historical_odds_stays_missing_without_fallback() -> None:
    records = _records(historical_odds=float("nan"), finish_positions=None)

    rows = build_feature_rows(records, feature_schema=_schema())

    assert all(
        isinstance(row.features["historical_odds"], float)
        and isnan(row.features["historical_odds"])
        for row in rows
    )
    assert all(row.features["historical_odds"] != 3.0 for row in rows)


def test_missing_schema_feature_is_counted_without_fallback() -> None:
    records = [
        FeatureInput(
            race_id="race-1",
            horse_id=f"horse-{index}",
            freeze_at="2026-01-01T12:00:00+00:00",
            features={"ability": float(4 - index)},
            available_at={"ability": "2025-12-31T12:00:00+00:00"},
        )
        for index in range(1, 4)
    ]

    audit = audit_feature_availability(records, feature_schema=_schema())

    assert audit.valid
    assert audit.missing_values == 3


def test_future_non_missing_feature_is_reported_and_rejected() -> None:
    freeze_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    records = _records(freeze_at=freeze_at)
    records[1] = FeatureInput(
        **{
            **records[1].__dict__,
            "available_at": {"ability": freeze_at + timedelta(minutes=1)},
        }
    )

    with pytest.raises(FeatureGenerationError) as error:
        build_ranking_dataset(records, feature_schema=_schema())

    assert len(error.value.audit.violations) == 1
    violation = error.value.audit.violations[0]
    assert violation.feature_name == "ability"
    assert "after freeze_at" in violation.reason
    assert "race-1/horse-2" in str(error.value)


def test_audit_rejects_naive_timestamps() -> None:
    records = _records(freeze_at=datetime(2026, 1, 1, 12))

    audit = audit_feature_availability(records, feature_schema=_schema())

    assert not audit.valid
    assert any("timezone-aware" in violation.reason for violation in audit.violations)
