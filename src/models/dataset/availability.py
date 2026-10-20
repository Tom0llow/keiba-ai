"""Audit feature values at their explicit freeze timestamps."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, isnan

from models.dataset.rows import FeatureInput, FeatureValue, TimestampInput
from models.dataset.schema import FeatureSchema


@dataclass(frozen=True)
class AvailabilityViolation:
    """Describe one temporal or input-contract violation."""

    row_index: int
    race_id: str
    horse_id: str
    feature_name: str | None
    reason: str
    freeze_at: datetime | None = None
    available_at: datetime | None = None

    @property
    def message(self) -> str:
        """Return a concise human-readable description of the violation."""
        location = f"row {self.row_index} ({self.race_id}/{self.horse_id})"
        if self.feature_name is not None:
            location += f" feature {self.feature_name!r}"
        return f"{location}: {self.reason}"


@dataclass(frozen=True)
class AvailabilityAudit:
    """Summarize temporal availability checks without dropping input rows."""

    records_checked: int
    non_missing_values: int
    missing_values: int
    violations: tuple[AvailabilityViolation, ...]

    @property
    def valid(self) -> bool:
        """Return whether all checked records passed the audit."""
        return not self.violations

    @property
    def is_valid(self) -> bool:
        """Return whether all checked records passed the audit."""
        return self.valid


class FeatureGenerationError(ValueError):
    """Indicate that feature inputs failed the availability audit."""

    def __init__(self, audit: AvailabilityAudit) -> None:
        self.audit = audit
        details = "; ".join(violation.message for violation in audit.violations)
        super().__init__(f"feature generation availability audit failed: {details}")


def audit_feature_availability(
    records: Sequence[FeatureInput],
    *,
    feature_schema: FeatureSchema | None = None,
) -> AvailabilityAudit:
    """Audit typed feature inputs against their freeze times.

    Missing values are counted and retained.  They do not use an available-at
    timestamp and are never replaced by a value from another period.
    """
    allowed_names = None if feature_schema is None else set(feature_schema.feature_names)
    violations: list[AvailabilityViolation] = []
    non_missing_values = 0
    missing_values = 0

    for row_index, record in enumerate(records):
        if not isinstance(record, FeatureInput):
            raise TypeError("records must contain FeatureInput values")
        race_id = record.race_id if isinstance(record.race_id, str) else "<invalid>"
        horse_id = record.horse_id if isinstance(record.horse_id, str) else "<invalid>"
        if not isinstance(record.race_id, str) or not record.race_id:
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "race_id must be non-empty"
                )
            )
        if not isinstance(record.horse_id, str) or not record.horse_id:
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "horse_id must be non-empty"
                )
            )

        freeze_at, freeze_error = _parse_timestamp(record.freeze_at)
        if freeze_error is not None:
            violations.append(
                AvailabilityViolation(row_index, race_id, horse_id, None, freeze_error)
            )

        if not isinstance(record.features, Mapping):
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "features must be a mapping"
                )
            )
            continue
        if not isinstance(record.available_at, Mapping):
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "available_at must be a mapping"
                )
            )
            available_values: Mapping[str, TimestampInput | None] = {}
        else:
            available_values = record.available_at

        parsed_available: dict[str, datetime | None] = {}
        for feature_name, raw_available_at in available_values.items():
            if not isinstance(feature_name, str) or not feature_name:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        "available_at feature names must be non-empty strings",
                    )
                )
                continue
            if feature_name not in record.features:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "available_at is provided without a feature value",
                    )
                )
            if raw_available_at is None:
                parsed_available[feature_name] = None
                continue
            parsed, error = _parse_timestamp(raw_available_at)
            if error is not None:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        f"available_at {error}",
                    )
                )
            parsed_available[feature_name] = parsed

        for feature_name, value in record.features.items():
            if not isinstance(feature_name, str) or not feature_name:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        "feature names must be non-empty strings",
                    )
                )
                continue
            if allowed_names is not None and feature_name not in allowed_names:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "feature is outside the approved schema",
                    )
                )
            if not _is_feature_value(value):
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "feature value must be numeric, NaN, or None",
                    )
                )
                continue
            if _is_missing(value):
                missing_values += 1
                continue
            non_missing_values += 1
            available_at = parsed_available.get(feature_name)
            if available_at is None:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "non-missing feature value requires available_at",
                        freeze_at=freeze_at,
                    )
                )
            elif freeze_at is not None and available_at > freeze_at:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "available_at is after freeze_at",
                        freeze_at=freeze_at,
                        available_at=available_at,
                    )
                )

        if feature_schema is not None:
            missing_values += sum(
                feature_name not in record.features for feature_name in feature_schema.feature_names
            )

    return AvailabilityAudit(
        records_checked=len(records),
        non_missing_values=non_missing_values,
        missing_values=missing_values,
        violations=tuple(violations),
    )


def _normalized_available_at(
    record: FeatureInput,
    feature_names: Sequence[str],
) -> dict[str, datetime | None]:
    values: dict[str, datetime | None] = {}
    for feature_name in feature_names:
        raw_available_at = record.available_at.get(feature_name)
        if raw_available_at is None:
            values[feature_name] = None
            continue
        available_at, error = _parse_timestamp(raw_available_at)
        if error is not None or available_at is None:
            raise AssertionError("validated availability audit must contain timestamps")
        values[feature_name] = available_at
    return values


def _parse_timestamp(value: TimestampInput) -> tuple[datetime | None, str | None]:
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
    return parsed, None


def _is_feature_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not (isinstance(value, float) and not isnan(value) and not isfinite(value))


def _is_missing(value: FeatureValue) -> bool:
    return value is None or (isinstance(value, float) and isnan(value))
