"""Build a datamart from explicitly ordered intermediate Parquet inputs."""

from pathlib import Path
from typing import Annotated

import typer

from make_datamart.tables.parquet import make_datamart, write_datamart
from make_features.catalog.loader import load_feature_definitions


def datamart_build(
    inputs: Annotated[
        list[Path], typer.Option("--input", help="Feature Parquet path; repeat in join order.")
    ],
    output: Annotated[Path, typer.Option("--output", help="Datamart Parquet output path.")],
    features_config: Annotated[
        Path, typer.Option("--features-config", help="Feature registration TOML path.")
    ] = Path("configs/features.toml"),
) -> None:
    """Join feature tables and save a validated datamart."""
    try:
        names = tuple(definition.name for definition in load_feature_definitions(features_config))
        table = make_datamart(inputs, registered_names=names)
        write_datamart(table, output, registered_names=names)
    except (OSError, TypeError, ValueError) as exc:
        typer.echo(f"cannot build datamart: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"datamart saved: {table.num_rows} rows")
