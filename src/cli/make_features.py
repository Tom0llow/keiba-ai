"""Execute explanatory-variable generation at the command-line boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cli.json_io import exit_input_error, parse_json_inputs
from data.saver.write_json import write_json
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.contracts.types import FeatureBatchInput
from make_features.explanatory_variables import FeatureBuildError, build_explanatory_variables
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.outputs import explanatory_payload, feature_audit_payload


def model_explanatory_variables(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Feature output JSON path.")],
    features_config: Annotated[
        Path, typer.Option("--features-config", help="Feature registration TOML path.")
    ] = Path("configs/features.toml"),
) -> None:
    """Validate F01-F21 feature values without using the model schema."""
    try:
        registry = create_feature_registry(load_feature_definitions(features_config))
        records = _read_explanatory_inputs(input_path)
        result = build_explanatory_variables(records, registry=registry)
    except typer.BadParameter as exc:
        exit_input_error(output_path, exc)
    except FeatureBuildError as exc:
        exit_input_error(
            output_path,
            exc,
            feature_ids=list(registry.feature_ids),
            audit=feature_audit_payload(exc.audit),
        )
    except (OSError, TypeError, ValueError) as exc:
        exit_input_error(output_path, exc)
    write_json(output_path, explanatory_payload(result, feature_ids=registry.feature_ids))


def _read_explanatory_inputs(path: Path) -> tuple[FeatureBatchInput, ...]:
    return parse_json_inputs(path, parse_explanatory_inputs)
