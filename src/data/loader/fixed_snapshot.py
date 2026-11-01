"""Pin one processed version and project/filter only explicitly requested races."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.dataset as ds

from data.storage.snapshot_store import SnapshotStore

_KEYS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")


class FixedSnapshot:
    """Resolve CURRENT once; never combine tables from different publications."""

    def __init__(self, processed_root: Path, *, snapshot_id: str | None = None) -> None:
        root = processed_root.expanduser().resolve()
        if snapshot_id is None:
            self.path = SnapshotStore(root).current_snapshot().resolve()
        else:
            if re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id) is None:
                raise ValueError("invalid snapshot_id")
            self.path = (root / "snapshots" / snapshot_id).resolve()
        if not self.path.is_dir() or self.path.parent != root / "snapshots":
            raise ValueError("snapshot must be one fixed complete processed version")
        self._hashes: dict[str, str] = {}

    def read_races(
        self,
        table: str,
        race_ids: Sequence[str],
        *,
        columns: Sequence[str] | None,
        publication_times: Sequence[str] | None = None,
    ) -> list[dict[str, object]]:
        """Use Arrow predicate pushdown and column projection, without SQLite access."""
        path = self._table_path(table)
        if table not in self._hashes:
            self._hashes[table] = _file_hash(path)
        predicate = None
        for identity in race_ids:
            if re.fullmatch(r"[0-9]{16}", identity) is None:
                raise ValueError("complete 16-digit race_id is required")
            values = (
                identity[:4],
                identity[4:8],
                identity[8:10],
                identity[10:12],
                identity[12:14],
                identity[14:16],
            )
            match = None
            for key, value in zip(_KEYS, values, strict=True):
                term = ds.field(key) == value
                match = term if match is None else match & term
            predicate = match if predicate is None else predicate | match
        if predicate is None:
            raise ValueError("at least one explicit race is required")
        if publication_times is not None:
            predicate = (
                predicate
                & ds.field("HappyoTime").isin(publication_times)
                & (ds.field("headDataKubun") == "1")
            )
        dataset = ds.dataset(path, format="parquet")
        required = set(_KEYS) | (set(columns) if columns is not None else set())
        if required - set(dataset.schema.names):
            raise ValueError(
                f"{table}: missing required columns: {sorted(required - set(dataset.schema.names))}"
            )
        selected = list(columns) if columns is not None else dataset.schema.names
        if any(not pa.types.is_string(dataset.schema.field(name).type) for name in selected):
            raise ValueError(f"{table}: source columns must preserve nullable strings")
        return cast(
            list[dict[str, object]],
            dataset.to_table(columns=selected, filter=predicate).to_pylist(),
        )

    def manifest(self) -> dict[str, object]:
        """Recheck physical hashes before publishing the input's snapshot evidence."""
        for table, digest in self._hashes.items():
            if _file_hash(self._table_path(table)) != digest:
                raise ValueError(f"snapshot table changed while reading: {table}")
        return {
            "snapshot_id": self.path.name,
            "snapshot_path": str(self.path),
            "tables": {
                table: {"file": f"{table}.parquet", "sha256": digest}
                for table, digest in sorted(self._hashes.items())
            },
        }

    def read_period(
        self,
        table: str,
        *,
        columns: Sequence[str],
        start: str,
        end: str,
        date_column: str | None = None,
        venues: Sequence[str] | None = None,
    ) -> list[dict[str, object]]:
        """Filter a bounded YYYYMMDD source period and preserve all rows in that population."""
        if (
            re.fullmatch(r"[0-9]{8}", start) is None
            or re.fullmatch(r"[0-9]{8}", end) is None
            or start > end
        ):
            raise ValueError("an ordered explicit YYYYMMDD period is required")
        if date_column is not None:
            predicate = (ds.field(date_column) >= start) & (ds.field(date_column) <= end)
        else:
            after = (ds.field("idYear") > start[:4]) | (
                (ds.field("idYear") == start[:4]) & (ds.field("idMonthDay") >= start[4:])
            )
            before = (ds.field("idYear") < end[:4]) | (
                (ds.field("idYear") == end[:4]) & (ds.field("idMonthDay") <= end[4:])
            )
            predicate = after & before
            if venues is not None:
                predicate = predicate & ds.field("idJyoCD").isin(venues)
        return self._read_filtered(table, columns, predicate)

    def read_identifiers(
        self, table: str, *, columns: Sequence[str], column: str, identities: Sequence[str]
    ) -> list[dict[str, object]]:
        """Read only a declared identifier population, for stable pedigree IDs."""
        return self._read_filtered(table, columns, ds.field(column).isin(identities))

    def _read_filtered(
        self, table: str, columns: Sequence[str], predicate: ds.Expression
    ) -> list[dict[str, object]]:
        path = self._table_path(table)
        if table not in self._hashes:
            self._hashes[table] = _file_hash(path)
        dataset = ds.dataset(path, format="parquet")
        if set(columns) - set(dataset.schema.names):
            raise ValueError(f"{table}: required projected source columns are missing")
        if any(not pa.types.is_string(dataset.schema.field(name).type) for name in columns):
            raise ValueError("reference sources must preserve nullable strings")
        return cast(
            list[dict[str, object]],
            dataset.to_table(columns=list(columns), filter=predicate).to_pylist(),
        )

    def _table_path(self, name: str) -> Path:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError("invalid table name")
        path = self.path / f"{name}.parquet"
        if not path.is_file() or path.resolve().parent != self.path:
            raise ValueError(f"snapshot table missing or outside fixed snapshot: {name}")
        return path


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
