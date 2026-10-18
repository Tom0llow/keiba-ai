"""Execute model input audits, projection and walk-forward evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cli.cli_common import _exit_input_error, _parse_inputs
from data_saver.write_json import write_json
from models.dataset.availability import FeatureGenerationError, audit_feature_availability
from models.dataset.builder import build_features, build_ranking_dataset
from models.dataset.rows import FeatureInput
from models.dataset.schema import FeatureSchema
from models.evaluation.walk_forward import WalkForwardConfig, evaluate_walk_forward
from models.serialization.inputs import parse_feature_inputs
from models.serialization.outputs import (
    audit_payload,
    model_audit_payload,
    model_evaluation_payload,
    model_features_payload,
)


def model_audit(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Audit output JSON path.")],
) -> None:
    """Audit feature availability at each row's freeze time."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    audit = audit_feature_availability(records, feature_schema=schema)
    write_json(output_path, model_audit_payload(schema, records, audit))
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
        _exit_input_error(
            output_path, exc, schema_id=schema.schema_id, audit=audit_payload(exc.audit)
        )
    except ValueError as exc:
        _exit_input_error(output_path, exc, schema_id=schema.schema_id)
    write_json(output_path, model_features_payload(schema, result))


def model_walk_forward(
    input_path: Annotated[Path, typer.Option("--input", help="Labeled feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Evaluation output JSON path.")],
    min_train_races: Annotated[
        int, typer.Option("--min-train-races", help="Initial training race count.")
    ],
    validation_races: Annotated[
        int, typer.Option("--validation-races", help="Validation race count per fold.")
    ],
    test_races: Annotated[int, typer.Option("--test-races", help="Test race count per fold.")],
    step_races: Annotated[
        int, typer.Option("--step-races", help="Race count by which the fold advances.")
    ],
) -> None:
    """Run race-disjoint chronological LambdaRank walk-forward evaluation."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    try:
        dataset = build_ranking_dataset(records, feature_schema=schema)
        evaluation = evaluate_walk_forward(
            dataset,
            WalkForwardConfig(
                min_train_races=min_train_races,
                validation_races=validation_races,
                test_races=test_races,
                step_races=step_races,
            ),
        )
    except FeatureGenerationError as exc:
        _exit_input_error(
            output_path, exc, schema_id=schema.schema_id, audit=audit_payload(exc.audit)
        )
    except ValueError as exc:
        _exit_input_error(output_path, exc, schema_id=schema.schema_id)
    write_json(
        output_path,
        model_evaluation_payload(
            schema, audit_feature_availability(records, feature_schema=schema), evaluation
        ),
    )


def read_feature_inputs_or_exit(
    input_path: Path,
    output_path: Path,
) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    """Read feature inputs, or write the input error and exit with code 1."""
    try:
        return _read_feature_inputs(input_path)
    except typer.BadParameter as exc:
        _exit_input_error(output_path, exc)


def _read_feature_inputs(path: Path) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    return _parse_inputs(path, parse_feature_inputs)
