"""Read Parquet files and bounded batches without storage-version policy."""

from collections.abc import Iterator, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def read_parquet(path: str | Path, *, columns: Sequence[str] | None = None) -> pa.Table:
    """Read the Arrow table and metadata from an explicit Parquet path.

    ``columns`` optionally projects the read to the named columns.
    """
    return pq.read_table(Path(path), columns=None if columns is None else list(columns))


def read_parquet_metadata(path: Path) -> pq.FileMetaData:
    """Read physical Parquet metadata without loading table values."""
    return pq.read_metadata(path)


def iter_parquet_batches(path: Path, *, batch_size: int = 1_000) -> Iterator[pa.RecordBatch]:
    """Yield bounded record batches while owning the input file handle."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    with path.open("rb") as source:
        yield from pq.ParquetFile(source).iter_batches(batch_size=batch_size)
