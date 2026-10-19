"""Execute processed-data publication and report command results."""

from __future__ import annotations

from pathlib import Path

import typer

from cli.options import DataConfigOption
from data.storage.snapshot_builder import SnapshotBuilder


def preprocess_rebuild(
    data_config: DataConfigOption = Path("configs/data.toml"),
) -> None:
    """Rebuild a complete Parquet snapshot without retrieving new raw data."""
    tables = SnapshotBuilder.from_toml(data_config).rebuild()
    typer.echo(f"processed snapshot published: {len(tables)} tables")
