"""Convert explicit JSON values into validated feature inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

import typer

from features.contracts.types import (
    FeatureBatchInput,
    FeatureGroupInput,
    FeatureScalar,
)
from models.dataset_builder import (
    FeatureInput,
    TimestampInput,
)
from models.ranking_dataset import FeatureSchema, FeatureValue
from run.json_output import input_error_payload, write_json
from utils.loader.read_json import read_json


def read_feature_inputs_or_exit(
    input_path: Path,
    output_path: Path,
) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    """Read feature inputs, or write the input error and exit with code 1."""
    try:
        return _read_feature_inputs(input_path)
    except typer.BadParameter as exc:
        write_json(output_path, {"error": input_error_payload(exc)})
        raise typer.Exit(code=1) from exc


def _read_feature_inputs(path: Path) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    payload = _read_json_object(path)
    schema_id = payload.get("schema_id")
    feature_names = payload.get("feature_names")
    raw_records = payload.get("records")
    if not isinstance(schema_id, str) or not isinstance(feature_names, list):
        raise typer.BadParameter("input JSON requires schema_id and feature_names")
    if not all(isinstance(name, str) for name in feature_names):
        raise typer.BadParameter("feature_names must be a list of strings")
    if not isinstance(raw_records, list):
        raise typer.BadParameter("input JSON requires a records list")
    try:
        schema = FeatureSchema.from_names(
            tuple(cast(list[str], feature_names)), schema_id=schema_id
        )
        records = tuple(_feature_input(value) for value in raw_records)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    return schema, records


def _feature_input(value: object) -> FeatureInput:
    if not isinstance(value, dict):
        raise ValueError("each record must be a JSON object")
    record = cast(dict[str, object], value)
    features = record.get("features")
    available_at = record.get("available_at")
    if not isinstance(features, dict) or not isinstance(available_at, dict):
        raise ValueError("each record requires features and available_at objects")
    return FeatureInput(
        race_id=cast(str, record.get("race_id")),
        horse_id=cast(str, record.get("horse_id")),
        freeze_at=cast(datetime | str, record.get("freeze_at")),
        features=cast(Mapping[str, FeatureValue], features),
        available_at=cast(Mapping[str, TimestampInput | None], available_at),
        finish_position=cast(int | None, record.get("finish_position")),
    )


def _read_explanatory_inputs(path: Path) -> tuple[FeatureBatchInput, ...]:
    payload = _read_json_object(path)
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise typer.BadParameter("input JSON requires a records list")
    try:
        return tuple(_explanatory_input(value) for value in raw_records)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


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


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        return read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"cannot read input JSON: {exc}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
