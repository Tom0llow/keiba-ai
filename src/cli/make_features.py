"""Execute explanatory-variable generation at the command-line boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from hydra.errors import HydraException
from omegaconf.errors import OmegaConfBaseException

from cli.json_io import exit_input_error, input_error_payload, parse_json_inputs
from configuration.feature_calculation import load_feature_calculation_config
from data.saver.write_json import write_json
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.contracts.types import FeatureBatchInput
from make_features.explanatory_variables import FeatureBuildError, build_explanatory_variables
from make_features.generation.calculate import calculate_features
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.observations import (
    calculation_payload,
    parse_calculation_parameters,
    parse_observation_inputs,
)
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


def model_calculate_features(
    input_path: Annotated[Path, typer.Option("--input", help="Normalized evidence JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="New calculated JSON path.")],
    config_dir: Annotated[
        Path, typer.Option("--config-dir", help="Hydra feature configuration directory.")
    ] = Path("configs/feature_calculation"),
    config_name: Annotated[str, typer.Option("--config-name")] = "calculate",
    overrides: Annotated[
        list[str] | None, typer.Option("--override", help="Repeatable Hydra override.")
    ] = None,
    features_config: Annotated[Path, typer.Option("--features-config")] = Path(
        "configs/features.toml"
    ),
) -> None:
    """Calculate all 21 groups from normalized timestamped source observations."""
    try:
        if (
            output_path.exists()
            or output_path.is_symlink()
            or output_path.resolve() == input_path.resolve()
        ):
            raise ValueError(
                "output must be a new path, distinct from inputs and existing artifacts"
            )
        registry = create_feature_registry(load_feature_definitions(features_config))
        parameters = parse_calculation_parameters(
            load_feature_calculation_config(
                config_dir, config_name=config_name, overrides=overrides or ()
            )
        )
        observations = parse_json_inputs(input_path, parse_observation_inputs)
        result = calculate_features(observations, parameters, registry=registry)
        write_json(
            output_path,
            calculation_payload(result, feature_ids=registry.feature_ids),
            overwrite=False,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        typer.BadParameter,
        HydraException,
        OmegaConfBaseException,
    ) as exc:
        typer.echo(json.dumps({"error": input_error_payload(exc)}, ensure_ascii=False), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Calculated {len(result.built.inputs)} rows across {len(registry.features)} feature groups."
    )
