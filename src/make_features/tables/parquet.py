"""Persist and reload validated intermediate feature tables."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from data_loader.read_parquet import read_parquet
from data_saver.write_parquet import write_parquet
from make_features.tables.schema import (
    FEATURE_COLUMNS,
    IntermediateFeatureTable,
    contract_metadata,
    feature_column_types,
    resolve_feature_name,
    table_column_types,
)
from make_features.validation.table import validate_feature_table


def write_feature_table(
    table: IntermediateFeatureTable,
    path: str | Path,
    feature_name: str | None = None,
    *,
    registered_names: Sequence[str] = (),
) -> None:
    """Validate and save one feature table with its explicit schema metadata."""
    resolved = resolve_feature_name(table, feature_name, registered_names=registered_names)
    types = (
        feature_column_types(resolved, registered_names=registered_names)
        if resolved in FEATURE_COLUMNS
        else table_column_types(table, registered_names=registered_names)
    )
    table = table.replace_schema_metadata(contract_metadata(resolved, types))
    validate_feature_table(table, resolved, registered_names=registered_names)
    write_parquet(table, path)


def read_feature_table(
    path: str | Path,
    feature_name: str | None = None,
    *,
    registered_names: Sequence[str] = (),
) -> IntermediateFeatureTable:
    """Read and validate an explicitly saved feature table."""
    return validate_feature_table(
        read_parquet(path), feature_name, registered_names=registered_names
    )


save_feature_table = write_feature_table
load_feature_table = read_feature_table
write_intermediate_table = write_feature_table
read_intermediate_table = read_feature_table
