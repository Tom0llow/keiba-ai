"""Execute processed-data publication and report command results."""

from __future__ import annotations

from pathlib import Path

import typer

from cli.cli_common import DataConfigOption
from storage.snapshot_builder import DataPreprocesser


def _preprocesser(data_config: Path) -> DataPreprocesser:
    return DataPreprocesser.from_toml(data_config)


def preprocess_rebuild(
    data_config: DataConfigOption = Path("config/data.toml"),
) -> None:
    """Rebuild a complete Parquet snapshot without retrieving new raw data."""
    tables = _preprocesser(data_config).rebuild()
    typer.echo(f"processed snapshot published: {len(tables)} tables")
