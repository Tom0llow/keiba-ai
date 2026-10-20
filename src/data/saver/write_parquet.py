"""Write explicit Arrow tables or batches to Parquet files."""

from collections.abc import Iterable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet(table: pa.Table, path: str | Path) -> None:
    """Save an Arrow table without changing its schema or metadata."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, destination)


def write_parquet_batches(path: Path, schema: pa.Schema, batches: Iterable[pa.Table]) -> int:
    """Save batches, including an empty table's schema, and return the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with pq.ParquetWriter(path, schema) as writer:
        for batch in batches:
            writer.write_table(batch)
            row_count += batch.num_rows
    return row_count
