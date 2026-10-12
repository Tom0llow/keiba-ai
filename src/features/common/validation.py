"""Validate feature scalars, missingness, status and source evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite, isnan

from features.common.availability import audit_time_limits, parse_group_timestamps
from features.common.leakage import audit_source
from features.common.leakage import is_result_field as _is_result_field
from features.common.types import (
    FEATURE_GROUP_IDS,
    FeatureGroupInput,
    FeatureScalar,
    FeatureViolation,
    _violation,
)

_ALLOWED_SOURCE_SCOPES = frozenset({"pre_race", "historical"})
_ALLOWED_STATUSES = frozenset({"confirmed", "missing", "unconfirmed"})


def audit_group(
    group: object,
    *,
    expected_feature_id: str,
    row_index: int,
    race_id: str,
    horse_id: str,
    freeze_at: datetime | None,
    violations: list[FeatureViolation],
) -> None:
    """Append scalar, missingness, source and time violations for one feature group."""
    if not isinstance(group, FeatureGroupInput):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                None,
                None,
                "groups must contain FeatureGroupInput values",
            )
        )
        return
    feature_id = group.feature_id
    if feature_id != expected_feature_id:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                expected_feature_id,
                None,
                "feature_id must match its groups mapping key",
            )
        )
    if feature_id not in FEATURE_GROUP_IDS:
        violations.append(
            _violation(
                row_index, race_id, horse_id, feature_id, None, "feature group is not F01-F21"
            )
        )
    if group.source_scope not in _ALLOWED_SOURCE_SCOPES:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "source_scope must be pre_race or historical",
            )
        )
    if group.status not in _ALLOWED_STATUSES:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "status must be confirmed, missing, or unconfirmed",
            )
        )
    audit_source(
        group,
        row_index=row_index,
        race_id=race_id,
        horse_id=horse_id,
        freeze_at=freeze_at,
        violations=violations,
    )

    available_at, source_event_at = parse_group_timestamps(
        group,
        row_index=row_index,
        race_id=race_id,
        horse_id=horse_id,
        freeze_at=freeze_at,
        violations=violations,
    )
    if not isinstance(group.values, Mapping):
        violations.append(
            _violation(row_index, race_id, horse_id, feature_id, None, "values must be a mapping")
        )
        return

    non_missing = False
    all_missing = True
    for field_name, value in group.values.items():
        if not isinstance(field_name, str) or not field_name:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    feature_id,
                    None,
                    "feature field names must be non-empty strings",
                )
            )
            continue
        if _is_result_field(field_name):
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    feature_id,
                    field_name,
                    "result-derived field is not allowed",
                )
            )
        if not _is_feature_value(value):
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    feature_id,
                    field_name,
                    "feature value must be a scalar or None",
                )
            )
            continue
        if _is_missing(value):
            continue
        non_missing = True
        all_missing = False
        if available_at is None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    feature_id,
                    field_name,
                    "non-missing feature value requires available_at",
                    freeze_at=freeze_at,
                )
            )
    if group.status == "unconfirmed":
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "unconfirmed feature values are not allowed",
            )
        )
    if group.status == "missing" and non_missing:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "missing status cannot contain non-missing values",
            )
        )
    if group.status == "confirmed" and all_missing:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "all-missing values must use status='missing'",
            )
        )
    audit_time_limits(
        group,
        row_index=row_index,
        race_id=race_id,
        horse_id=horse_id,
        freeze_at=freeze_at,
        violations=violations,
        available_at=available_at,
        source_event_at=source_event_at,
        non_missing=non_missing,
    )


def _is_feature_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and (isnan(value) or isfinite(value))


def _is_missing(value: FeatureScalar) -> bool:
    return value is None or (isinstance(value, float) and isnan(value))


def _is_non_missing(value: FeatureScalar) -> bool:
    return not _is_missing(value)


def _feature_values_equal(left: FeatureScalar, right: FeatureScalar) -> bool:
    if _is_missing(left) or _is_missing(right):
        return _is_missing(left) and _is_missing(right)
    return left == right
