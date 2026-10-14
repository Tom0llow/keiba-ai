"""Run standalone processed snapshot publication."""

from __future__ import annotations

from pathlib import Path

import typer

from run.retrieval import DataConfigOption, _preprocesser


def preprocess_rebuild(
    data_config: DataConfigOption = Path("config/data.toml"),
) -> None:
    """Rebuild a complete Parquet snapshot without retrieving new raw data."""
    tables = _preprocesser(data_config).rebuild()
    typer.echo(f"processed snapshot published: {len(tables)} tables")
