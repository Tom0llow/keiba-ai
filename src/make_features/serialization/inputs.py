"""Convert decoded JSON objects into feature group input contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from make_features.contracts.types import FeatureBatchInput, FeatureGroupInput, FeatureScalar


def parse_explanatory_inputs(payload: Mapping[str, object]) -> tuple[FeatureBatchInput, ...]:
    """Convert a decoded JSON object into explicit feature group inputs."""
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("input JSON requires a records list")
    return tuple(_explanatory_input(value) for value in raw_records)


def _explanatory_input(value: object) -> FeatureBatchInput:
    if not isinstance(value, dict):
        raise ValueError("each feature record must be a JSON object")
    record = cast(dict[str, object], value)
    if "finish_position" in record:
        raise ValueError("feature records must not contain finish_position")
    unexpected_record_fields = set(record) - {"race_id", "horse_id", "freeze_at", "groups"}
    if unexpected_record_fields:
        raise ValueError(
            f"feature records contain unsupported fields: {sorted(unexpected_record_fields)!r}"
        )
    race_id = record.get("race_id")
    horse_id = record.get("horse_id")
    freeze_at = record.get("freeze_at")
    groups = record.get("groups")
    if not isinstance(race_id, str) or not isinstance(horse_id, str):
        raise ValueError("each feature record requires string race_id and horse_id")
    if not isinstance(freeze_at, str):
        raise ValueError("each feature record requires an ISO-8601 freeze_at")
    if not isinstance(groups, dict):
        raise ValueError("each feature record requires a groups object")
    parsed_groups: dict[str, FeatureGroupInput] = {}
    for feature_id, raw_group in groups.items():
        if not isinstance(feature_id, str) or not isinstance(raw_group, dict):
            raise ValueError("feature groups must be JSON objects keyed by group id")
        unexpected_group_fields = set(raw_group) - {
            "values",
            "available_at",
            "source_event_at",
            "source_scope",
            "status",
            "source_race_ids",
            "contains_target_result",
            "contains_future_data",
        }
        if unexpected_group_fields:
            raise ValueError(
                f"feature group {feature_id!r} contains unsupported fields: "
                f"{sorted(unexpected_group_fields)!r}"
            )
        missing_boundary_flags = {
            field_name
            for field_name in ("contains_target_result", "contains_future_data")
            if field_name not in raw_group
        }
        if missing_boundary_flags:
            raise ValueError(
                f"feature group {feature_id!r} requires explicit boundary flags: "
                f"{sorted(missing_boundary_flags)!r}"
            )
        values = raw_group.get("values")
        available_at = raw_group.get("available_at")
        source_event_at = raw_group.get("source_event_at")
        source_scope = raw_group.get("source_scope")
        status = raw_group.get("status")
        source_race_ids = raw_group.get("source_race_ids", [])
        contains_target_result = raw_group["contains_target_result"]
        contains_future_data = raw_group["contains_future_data"]
        if not isinstance(values, dict):
            raise ValueError(f"feature group {feature_id!r} requires a values object")
        if available_at is not None and not isinstance(available_at, str):
            raise ValueError(
                f"feature group {feature_id!r} available_at must be an ISO-8601 string"
            )
        if source_event_at is not None and not isinstance(source_event_at, str):
            raise ValueError(
                f"feature group {feature_id!r} source_event_at must be an ISO-8601 string"
            )
        if not isinstance(source_scope, str) or not isinstance(status, str):
            raise ValueError(f"feature group {feature_id!r} requires source_scope and status")
        if (
            isinstance(source_race_ids, str)
            or not isinstance(source_race_ids, list)
            or not all(isinstance(source_race_id, str) for source_race_id in source_race_ids)
        ):
            raise ValueError(
                f"feature group {feature_id!r} source_race_ids must be a list of strings"
            )
        if not isinstance(contains_target_result, bool) or not isinstance(
            contains_future_data, bool
        ):
            raise ValueError(f"feature group {feature_id!r} boundary flags must be boolean")
        parsed_groups[feature_id] = FeatureGroupInput(
            feature_id=feature_id,
            values=cast(Mapping[str, FeatureScalar], values),
            available_at=available_at,
            source_event_at=source_event_at,
            source_scope=source_scope,
            status=status,
            source_race_ids=tuple(cast(list[str], source_race_ids)),
            contains_target_result=contains_target_result,
            contains_future_data=contains_future_data,
        )
    return FeatureBatchInput(
        race_id=race_id,
        horse_id=horse_id,
        freeze_at=freeze_at,
        groups=parsed_groups,
    )
