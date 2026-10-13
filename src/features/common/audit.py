"""Audit race shape and coordinate shared feature validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from features.common.availability import parse_timestamp as _parse_timestamp
from features.common.types import (
    FEATURE_GROUP_IDS,
    FeatureAudit,
    FeatureBatchInput,
    FeatureGroupInput,
    FeatureViolation,
    _violation,
)
from features.common.validation import _is_feature_value, _is_missing, _is_non_missing
from features.common.validation import audit_group as _audit_group


def audit_feature_inputs(
    records: Sequence[FeatureBatchInput],
    *,
    required_feature_ids: Sequence[str] = FEATURE_GROUP_IDS,
) -> FeatureAudit:
    """Audit explicit F01-F21 feature inputs.

    The audit checks timezone-aware as-of timestamps, target-result and future
    data markers, missing/unconfirmed status, and race-contiguous row shape.
    It never imputes a missing feature value.
    """
    violations: list[FeatureViolation] = []
    records_checked = len(records)
    groups_checked = 0
    non_missing_values = 0
    missing_values = 0
    seen_races: set[str] = set()
    current_race: str | None = None
    current_horses: set[str] = set()
    race_freeze_at: dict[str, datetime] = {}
    race_group_fields: dict[tuple[str, str], frozenset[str]] = {}
    race_group_scopes: dict[tuple[str, str], str] = {}

    for row_index, record in enumerate(records):
        if not isinstance(record, FeatureBatchInput):
            raise TypeError("records must contain FeatureBatchInput values")
        race_id = record.race_id if isinstance(record.race_id, str) else "<invalid>"
        horse_id = record.horse_id if isinstance(record.horse_id, str) else "<invalid>"
        if not isinstance(record.race_id, str) or not record.race_id:
            violations.append(
                _violation(row_index, race_id, horse_id, None, None, "race_id must be non-empty")
            )
        if not isinstance(record.horse_id, str) or not record.horse_id:
            violations.append(
                _violation(row_index, race_id, horse_id, None, None, "horse_id must be non-empty")
            )

        freeze_at, freeze_error = _parse_timestamp(record.freeze_at)
        if freeze_error is not None:
            violations.append(_violation(row_index, race_id, horse_id, None, None, freeze_error))
        elif freeze_at is None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    None,
                    None,
                    "freeze_at is required",
                )
            )

        if current_race != race_id:
            if race_id in seen_races:
                violations.append(
                    _violation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        None,
                        "rows for each race must be contiguous",
                    )
                )
            if current_race is not None:
                current_horses.clear()
            current_race = race_id
            seen_races.add(race_id)
        if horse_id in current_horses:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    None,
                    None,
                    "horse_id must be unique within a race",
                )
            )
        current_horses.add(horse_id)

        if freeze_at is not None:
            previous_freeze_at = race_freeze_at.setdefault(race_id, freeze_at)
            if previous_freeze_at != freeze_at:
                violations.append(
                    _violation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        None,
                        "freeze_at must be identical for all rows in a race",
                        freeze_at=freeze_at,
                    )
                )

        if not isinstance(record.groups, Mapping):
            violations.append(
                _violation(row_index, race_id, horse_id, None, None, "groups must be a mapping")
            )
            continue

        feature_ids = set(record.groups)
        for feature_id in required_feature_ids:
            if feature_id not in record.groups:
                violations.append(
                    _violation(
                        row_index, race_id, horse_id, feature_id, None, "feature group is missing"
                    )
                )
        for feature_id in feature_ids:
            if not isinstance(feature_id, str) or feature_id not in required_feature_ids:
                violations.append(
                    _violation(
                        row_index,
                        race_id,
                        horse_id,
                        str(feature_id),
                        None,
                        "feature group is not F01-F21",
                    )
                )

        for feature_id in required_feature_ids:
            if feature_id not in record.groups:
                continue
            group = record.groups[feature_id]
            groups_checked += 1
            _audit_group(
                group,
                expected_feature_id=feature_id,
                row_index=row_index,
                race_id=race_id,
                horse_id=horse_id,
                freeze_at=freeze_at,
                violations=violations,
            )
            if not isinstance(group, FeatureGroupInput):
                continue

            if isinstance(group.values, Mapping):
                values = group.values
                non_missing_values += sum(
                    _is_non_missing(value) for value in values.values() if _is_feature_value(value)
                )
                missing_values += sum(
                    _is_missing(value) for value in values.values() if _is_feature_value(value)
                )
                key = (race_id, feature_id)
                field_names = frozenset(
                    field_name for field_name in values if isinstance(field_name, str)
                )
                previous_fields = race_group_fields.setdefault(key, field_names)
                if previous_fields != field_names:
                    violations.append(
                        _violation(
                            row_index,
                            race_id,
                            horse_id,
                            feature_id,
                            None,
                            "feature field names must be identical within a race",
                        )
                    )
            if isinstance(group.source_scope, str):
                key = (race_id, feature_id)
                previous_scope = race_group_scopes.setdefault(key, group.source_scope)
                if previous_scope != group.source_scope:
                    violations.append(
                        _violation(
                            row_index,
                            race_id,
                            horse_id,
                            feature_id,
                            None,
                            "source_scope must be identical within a race and group",
                        )
                    )

    return FeatureAudit(
        records_checked=records_checked,
        groups_checked=groups_checked,
        non_missing_values=non_missing_values,
        missing_values=missing_values,
        violations=tuple(violations),
    )
