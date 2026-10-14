"""Serialize command results and audits as standard UTF-8 JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from math import isnan
from pathlib import Path

from features.contracts.types import (
    FeatureAudit,
    FeatureBuildResult,
)
from models.dataset_builder import (
    AvailabilityAudit,
    FeatureGenerationResult,
    TimestampInput,
)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Write UTF-8 result JSON, converting missing NaN values to null."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _json_safe(value: object) -> object:
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def input_error_payload(error: Exception) -> dict[str, str]:
    """Return the structured input error used by model commands."""
    return {"type": "input", "message": str(error)}


def _freeze_at_payload(value: TimestampInput) -> str:
    return value.isoformat() if isinstance(value, datetime) else value


def audit_payload(audit: AvailabilityAudit) -> dict[str, object]:
    """Return a JSON-ready feature availability audit with violation timestamps."""
    return {
        "records_checked": audit.records_checked,
        "non_missing_values": audit.non_missing_values,
        "missing_values": audit.missing_values,
        "valid": audit.valid,
        "violations": [
            {
                "row_index": violation.row_index,
                "race_id": violation.race_id,
                "horse_id": violation.horse_id,
                "feature_name": violation.feature_name,
                "reason": violation.reason,
                "freeze_at": (
                    violation.freeze_at.isoformat() if violation.freeze_at is not None else None
                ),
                "available_at": (
                    violation.available_at.isoformat()
                    if violation.available_at is not None
                    else None
                ),
            }
            for violation in audit.violations
        ],
    }


def _explanatory_audit_payload(audit: FeatureAudit) -> dict[str, object]:
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


def _generated_records(result: FeatureGenerationResult) -> list[dict[str, object]]:
    ranking_by_key = {
        (row.race_id, row.horse_id): row.finish_position for row in result.ranking_rows
    }
    return [
        {
            "race_id": row.race_id,
            "horse_id": row.horse_id,
            "freeze_at": row.freeze_at.isoformat() if row.freeze_at is not None else None,
            "available_at": {
                feature_name: (available_at.isoformat() if available_at is not None else None)
                for feature_name, available_at in row.available_at.items()
            },
            "features": dict(row.features),
            **(
                {"finish_position": ranking_by_key[(row.race_id, row.horse_id)]}
                if (row.race_id, row.horse_id) in ranking_by_key
                else {}
            ),
        }
        for row in result.feature_rows
    ]


def _explanatory_records(result: FeatureBuildResult) -> list[dict[str, object]]:
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
