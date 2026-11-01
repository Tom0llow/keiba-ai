"""Prepare new model inputs from explicit normalized observations and separate results."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from hydra.errors import HydraException
from omegaconf.errors import OmegaConfBaseException

from configuration.model_projection import load_model_projection_config
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.generation.calculate import calculate_features
from make_features.serialization.observations import (
    parse_calculation_parameters,
    parse_historical_results,
    parse_observation_inputs,
)
from models.serialization.projection import prepare_model_payload


def model_prepare_input(
    input_path: Annotated[Path, typer.Option("--input", help="Normalized evidence JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="New prepared model JSON path.")],
    results_path: Annotated[
        Path | None,
        typer.Option(
            "--results", help="Separate complete normalized results; omit for prediction."
        ),
    ] = None,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/model_projection"),
    config_name: Annotated[str, typer.Option("--config-name")] = "prepare",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
    features_config: Annotated[Path, typer.Option("--features-config")] = Path(
        "configs/features.toml"
    ),
) -> None:
    """Calculate all groups and project explicitly selected, approved numeric columns."""
    try:
        inputs = [input_path, features_config, *([] if results_path is None else [results_path])]
        if (
            output_path.exists()
            or output_path.is_symlink()
            or any(output_path.resolve() == p.resolve() for p in inputs)
        ):
            raise ValueError(
                "output must be a new path distinct from inputs and existing artifacts"
            )
        raw_parameters, columns = load_model_projection_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        parameters = parse_calculation_parameters(raw_parameters)
        registry = create_feature_registry(load_feature_definitions(features_config))
        observations = parse_observation_inputs(read_json(input_path))
        calculated = calculate_features(observations, parameters, registry=registry)
        results = (
            None if results_path is None else parse_historical_results(read_json(results_path))
        )
        payload = prepare_model_payload(
            calculated, registry=registry, selected_columns=columns, results=results
        )
        write_json(output_path, payload, overwrite=False)
    except (OSError, TypeError, ValueError, HydraException, OmegaConfBaseException) as exc:
        typer.echo(f"model prepare-input failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Prepared {len(calculated.built.inputs)} rows with {len(columns)} numeric columns.")
