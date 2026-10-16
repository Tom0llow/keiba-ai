"""Persist and reload validated datamart Parquet tables."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from make_datamart.validation.table import validate_datamart


def write_datamart(
    table: pa.Table, path: str | Path, *, registered_names: Sequence[str] = ()
) -> None:
    """Write a validated datamart to an explicit Parquet path."""
    validate_datamart(table, registered_names=registered_names)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, destination)


def read_datamart(path: str | Path, *, registered_names: Sequence[str] = ()) -> pa.Table:
    """Read and validate a saved datamart Parquet table."""
    table = pq.read_table(Path(path))
    validate_datamart(table, registered_names=registered_names)
    return table
