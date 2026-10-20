"""Convert feature generation results and audits to JSON-ready values."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from make_features.contracts.types import FeatureAudit, FeatureBuildResult


def explanatory_payload(
    result: FeatureBuildResult, *, feature_ids: Sequence[str]
) -> dict[str, object]:
    """Return a complete generated-feature document in registration order."""
    return {
        "feature_ids": list(feature_ids),
        "records": explanatory_records(result),
        "audit": feature_audit_payload(result.audit),
    }


def feature_audit_payload(audit: FeatureAudit) -> dict[str, object]:
    """Return a JSON-ready feature group audit with source timestamps."""
    return {
        "records_checked": audit.records_checked,
        "groups_checked": audit.groups_checked,
        "non_missing_values": audit.non_missing_values,
        "missing_values": audit.missing_values,
        "valid": audit.valid,
        "violations": [
            {
                "row_index": violation.row_index,
                "race_id": violation.race_id,
                "horse_id": violation.horse_id,
                "feature_id": violation.feature_id,
                "field_name": violation.field_name,
                "reason": violation.reason,
                "freeze_at": (
                    violation.freeze_at.isoformat() if violation.freeze_at is not None else None
                ),
                "available_at": (
                    violation.available_at.isoformat()
                    if violation.available_at is not None
                    else None
                ),
                "source_event_at": (
                    violation.source_event_at.isoformat()
                    if violation.source_event_at is not None
                    else None
                ),
            }
            for violation in audit.violations
        ],
    }


def explanatory_records(result: FeatureBuildResult) -> list[dict[str, object]]:
    """Return generated feature records with their explicit source boundaries."""
    return [
        {
            "race_id": record.race_id,
            "horse_id": record.horse_id,
            "freeze_at": (
                record.freeze_at.isoformat()
                if isinstance(record.freeze_at, datetime)
                else record.freeze_at
            ),
            "groups": {
                feature_id: {
                    "values": dict(result.rows[feature_id][row_index].values),
                    "available_at": (
                        group.available_at.isoformat()
                        if isinstance(group.available_at, datetime)
                        else group.available_at
                    ),
                    "source_event_at": (
                        group.source_event_at.isoformat()
                        if isinstance(group.source_event_at, datetime)
                        else group.source_event_at
                    ),
                    "source_scope": group.source_scope,
                    "status": group.status,
                    "source_race_ids": list(group.source_race_ids),
                    "contains_target_result": group.contains_target_result,
                    "contains_future_data": group.contains_future_data,
                }
                for feature_id, group in record.groups.items()
            },
        }
        for row_index, record in enumerate(result.inputs)
    ]
