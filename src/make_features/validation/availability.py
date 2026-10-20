"""Normalize and validate explicitly supplied feature timestamps."""

from __future__ import annotations

from datetime import UTC, datetime

from make_features.contracts.types import (
    FeatureGroupInput,
    FeatureTimestamp,
    FeatureViolation,
    _violation,
)


def parse_timestamp(value: FeatureTimestamp | None) -> tuple[datetime | None, str | None]:
    """Return a UTC timestamp or a validation reason without raising on invalid input."""
    if value is None:
        return None, None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            return None, f"must be a valid ISO-8601 timestamp ({exc})"
    else:
        return None, "must be a datetime or ISO-8601 timestamp string"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "must be timezone-aware"
    return parsed.astimezone(UTC), None


def require_timestamp(value: FeatureTimestamp | None, field_name: str) -> datetime:
    """Return a timezone-aware UTC timestamp or reject invalid input."""
    parsed, error = parse_timestamp(value)
    if error is not None or parsed is None:
        raise ValueError(f"{field_name} {error or 'is required'}")
    return parsed


def parse_group_timestamps(
    group: FeatureGroupInput,
    *,
    row_index: int,
    race_id: str,
    horse_id: str,
    freeze_at: datetime | None,
    violations: list[FeatureViolation],
) -> tuple[datetime | None, datetime | None]:
    """Parse both source timestamps while retaining structured violations."""
    feature_id = group.feature_id
    available_at: datetime | None = None
    if group.available_at is not None:
        available_at, timestamp_error = parse_timestamp(group.available_at)
        if timestamp_error is not None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    feature_id,
                    None,
                    f"available_at {timestamp_error}",
                )
            )
    source_event_at: datetime | None = None
    if group.source_event_at is not None:
        source_event_at, timestamp_error = parse_timestamp(group.source_event_at)
        if timestamp_error is not None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    feature_id,
                    None,
                    f"source_event_at {timestamp_error}",
                )
            )
    return available_at, source_event_at


def audit_time_limits(
    group: FeatureGroupInput,
    *,
    row_index: int,
    race_id: str,
    horse_id: str,
    freeze_at: datetime | None,
    violations: list[FeatureViolation],
    available_at: datetime | None,
    source_event_at: datetime | None,
    non_missing: bool,
) -> None:
    """Audit temporal limits and availability evidence without inventing times."""
    feature_id = group.feature_id
    if freeze_at is not None and available_at is not None and available_at > freeze_at:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "available_at is after freeze_at",
                freeze_at=freeze_at,
                available_at=available_at,
            )
        )
    if group.status == "missing" and group.available_at is not None:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "missing values must not have available_at",
            )
        )
    if group.source_scope == "historical" and non_missing and source_event_at is None:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "historical non-missing values require source_event_at",
            )
        )
    if freeze_at is not None and source_event_at is not None and source_event_at > freeze_at:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "source_event_at is after freeze_at",
                freeze_at=freeze_at,
                source_event_at=source_event_at,
            )
        )


def normalize_timestamp(value: datetime, field_name: str) -> datetime:
    """Require a datetime and normalize its timezone-aware instant to UTC."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    parsed, error = parse_timestamp(value)
    if error is not None or parsed is None:
        raise ValueError(f"{field_name} {error or 'is required'}")
    return parsed
