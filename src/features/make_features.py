"""Execute feature generation and audits at the JSON CLI boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from math import isnan
from pathlib import Path
from typing import Annotated, cast

import typer

from data.loader.read_json import read_json
from features.explanatory_variables import (
    FEATURE_GROUP_IDS,
    FeatureAudit,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureBuildResult,
    FeatureGroupInput,
    FeatureScalar,
    build_explanatory_variables,
)
from models.dataset_builder import (
    AvailabilityAudit,
    FeatureGenerationError,
    FeatureGenerationResult,
    FeatureInput,
    TimestampInput,
    audit_feature_availability,
    build_features,
)
from models.ranking_dataset import FeatureSchema, FeatureValue


def register_feature_commands(model_app: typer.Typer) -> None:
    """Register the audit, features, and explanatory-variables commands."""
    model_app.command("audit")(model_audit)
    model_app.command("features")(model_features)
    model_app.command("explanatory-variables")(model_explanatory_variables)


def model_audit(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Audit output JSON path.")],
) -> None:
    """Audit feature availability at each row's freeze time."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    audit = audit_feature_availability(records, feature_schema=schema)
    write_json(
        output_path,
        {
            "schema_id": schema.schema_id,
            "feature_names": list(schema.feature_names),
            "freeze_at": [_freeze_at_payload(record.freeze_at) for record in records],
            "audit": audit_payload(audit),
        },
    )
    if not audit.valid:
        raise typer.Exit(code=1)


def model_features(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Generated feature JSON path.")],
) -> None:
    """Generate validated feature rows without imputing missing values."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    try:
        result = build_features(records, feature_schema=schema)
    except FeatureGenerationError as exc:
        write_json(
            output_path,
            {
                "schema_id": schema.schema_id,
                "audit": audit_payload(exc.audit),
                "error": input_error_payload(exc),
            },
        )
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        write_json(
            output_path,
            {"schema_id": schema.schema_id, "error": input_error_payload(exc)},
        )
        raise typer.Exit(code=1) from exc
    write_json(
        output_path,
        {
            "schema_id": schema.schema_id,
            "feature_names": list(schema.feature_names),
            "records": _generated_records(result),
            "audit": audit_payload(result.audit),
        },
    )


def model_explanatory_variables(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Feature output JSON path.")],
) -> None:
    """Validate F01-F21 feature values without using the model schema."""
    try:
        records = _read_explanatory_inputs(input_path)
        result = build_explanatory_variables(records)
    except typer.BadParameter as exc:
        write_json(output_path, {"error": input_error_payload(exc)})
        raise typer.Exit(code=1) from exc
    except FeatureBuildError as exc:
        write_json(
            output_path,
            {
                "feature_ids": list(FEATURE_GROUP_IDS),
                "audit": _explanatory_audit_payload(exc.audit),
                "error": input_error_payload(exc),
            },
        )
        raise typer.Exit(code=1) from exc
    except (TypeError, ValueError) as exc:
        write_json(output_path, {"error": input_error_payload(exc)})
        raise typer.Exit(code=1) from exc
    write_json(
        output_path,
        {
            "feature_ids": list(FEATURE_GROUP_IDS),
            "records": _explanatory_records(result),
            "audit": _explanatory_audit_payload(result.audit),
        },
    )


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
