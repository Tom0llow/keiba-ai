"""Persist and reload validated datamart Parquet tables."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa

from data.loader.read_parquet import read_parquet
from data.saver.write_parquet import write_parquet
from make_datamart.builder import join_feature_tables
from make_datamart.validation.table import validate_datamart
from make_features.tables.parquet import read_feature_table


def write_datamart(
    table: pa.Table, path: str | Path, *, registered_names: Sequence[str] = ()
) -> None:
    """Write a validated datamart to an explicit Parquet path."""
    validate_datamart(table, registered_names=registered_names)
    write_parquet(table, path)


def read_datamart(path: str | Path, *, registered_names: Sequence[str] = ()) -> pa.Table:
    """Read and validate a saved datamart Parquet table."""
    table = read_parquet(path)
    validate_datamart(table, registered_names=registered_names)
    return table


def make_datamart(paths: Sequence[str | Path], *, registered_names: Sequence[str] = ()) -> pa.Table:
    """Read intermediate Parquet files and left-join them in the given order."""
    if not paths:
        raise ValueError("at least one feature table path is required")
    tables = [read_feature_table(path, registered_names=registered_names) for path in paths]
    return join_feature_tables(tables, registered_names=registered_names)


def build_datamart(
    paths: Sequence[str | Path], *, registered_names: Sequence[str] = ()
) -> pa.Table:
    """Build a datamart from intermediate feature Parquet files."""
    return make_datamart(paths, registered_names=registered_names)
