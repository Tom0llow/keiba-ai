"""Execute feature generation and audits at the JSON CLI boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from features.catalog.loader import load_feature_definitions
from features.catalog.registry import create_feature_registry
from features.explanatory_variables import (
    FeatureBuildError,
    build_explanatory_variables,
)
from models.dataset_builder import (
    FeatureGenerationError,
    audit_feature_availability,
    build_features,
)
from run.feature_inputs import _read_explanatory_inputs, read_feature_inputs_or_exit
from run.json_output import (
    _explanatory_audit_payload,
    _explanatory_records,
    _freeze_at_payload,
    _generated_records,
    audit_payload,
    input_error_payload,
    write_json,
)


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
    features_config: Annotated[
        Path, typer.Option("--features-config", help="Feature registration TOML path.")
    ] = Path("config/features.toml"),
) -> None:
    """Validate F01-F21 feature values without using the model schema."""
    try:
        registry = create_feature_registry(load_feature_definitions(features_config))
        records = _read_explanatory_inputs(input_path)
        result = build_explanatory_variables(records, registry=registry)
    except typer.BadParameter as exc:
        write_json(output_path, {"error": input_error_payload(exc)})
        raise typer.Exit(code=1) from exc
    except FeatureBuildError as exc:
        write_json(
            output_path,
            {
                "feature_ids": list(registry.feature_ids),
                "audit": _explanatory_audit_payload(exc.audit),
                "error": input_error_payload(exc),
            },
        )
        raise typer.Exit(code=1) from exc
    except (OSError, TypeError, ValueError) as exc:
        write_json(output_path, {"error": input_error_payload(exc)})
        raise typer.Exit(code=1) from exc
    write_json(
        output_path,
        {
            "feature_ids": list(registry.feature_ids),
            "records": _explanatory_records(result),
            "audit": _explanatory_audit_payload(result.audit),
        },
    )
