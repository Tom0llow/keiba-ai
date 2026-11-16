"""Pin one processed version and project/filter only explicitly requested races."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from data.loader.file_hash import file_sha256
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
            self._hashes[table] = file_sha256(path)
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

    def pinned_manifest(self) -> dict[str, object]:
        """Return the identities hashed so far without rereading the files."""
        return {
            "snapshot_id": self.path.name,
            "snapshot_path": str(self.path),
            "tables": {
                table: {"file": f"{table}.parquet", "sha256": digest}
                for table, digest in sorted(self._hashes.items())
            },
        }

    def manifest(self) -> dict[str, object]:
        """Recheck physical hashes before publishing the input's snapshot evidence."""
        for table, digest in self._hashes.items():
            if file_sha256(self._table_path(table)) != digest:
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

    def pin(self, tables: Sequence[str]) -> None:
        """Hash each named table once, before any row is read from it."""
        for table in tables:
            if table not in self._hashes:
                self._hashes[table] = file_sha256(self._table_path(table))

    def read_all(self, table: str, *, columns: Sequence[str]) -> list[dict[str, object]]:
        """Read every row of a small table, projected to explicit nullable-string columns."""
        return self._read_filtered(table, columns, None)

    def period_reader(
        self, table: str, *, columns: Sequence[str], venues: Sequence[str]
    ) -> PeriodReader:
        """Return a reader that parses one large table's footer once for many periods."""
        path = self._table_path(table)
        if table not in self._hashes:
            self._hashes[table] = file_sha256(path)
        dataset = ds.dataset(path, format="parquet")
        _check_columns(table, dataset.schema, columns)
        return PeriodReader(dataset, tuple(columns), tuple(venues))

    def publication_reader(
        self,
        table: str,
        *,
        key_columns: Sequence[str],
        value_columns: Sequence[str],
        venues: Sequence[str],
    ) -> PublicationReader:
        """Return a two-pass reader for one large intermediate-publication table.

        The returned reader opens the Parquet dataset once.  Its first pass
        projects only race keys, publication kind and publication time; its
        second pass returns full value rows for explicitly selected
        ``(race_id, HappyoTime)`` pairs.
        """
        path = self._table_path(table)
        if table not in self._hashes:
            self._hashes[table] = file_sha256(path)
        keys = _publication_key_columns(key_columns)
        values = _publication_value_columns(value_columns, keys)
        reader_venues = _publication_venues(venues)
        dataset = ds.dataset(path, format="parquet")
        _check_columns(table, dataset.schema, (*keys, "headDataKubun", "HappyoTime", *values))
        return PublicationReader(dataset, keys, values, reader_venues)

    def read_identifiers(
        self, table: str, *, columns: Sequence[str], column: str, identities: Sequence[str]
    ) -> list[dict[str, object]]:
        """Read only a declared identifier population, for stable pedigree IDs."""
        return self._read_filtered(table, columns, ds.field(column).isin(identities))

    def _read_filtered(
        self, table: str, columns: Sequence[str], predicate: ds.Expression | None
    ) -> list[dict[str, object]]:
        path = self._table_path(table)
        if table not in self._hashes:
            self._hashes[table] = file_sha256(path)
        dataset = ds.dataset(path, format="parquet")
        _check_columns(table, dataset.schema, columns)
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


class PeriodReader:
    """Read race-key date periods from one parsed dataset, in physical row order."""

    def __init__(
        self, dataset: ds.Dataset, columns: tuple[str, ...], venues: tuple[str, ...]
    ) -> None:
        self._dataset = dataset
        self._columns = columns
        self._venues = venues

    def read(self, start: str, end: str) -> list[dict[str, object]]:
        """Return the rows whose race-key date lies in an ordered YYYYMMDD period."""
        if (
            re.fullmatch(r"[0-9]{8}", start) is None
            or re.fullmatch(r"[0-9]{8}", end) is None
            or start > end
        ):
            raise ValueError("an ordered explicit YYYYMMDD period is required")
        after = (ds.field("idYear") > start[:4]) | (
            (ds.field("idYear") == start[:4]) & (ds.field("idMonthDay") >= start[4:])
        )
        before = (ds.field("idYear") < end[:4]) | (
            (ds.field("idYear") == end[:4]) & (ds.field("idMonthDay") <= end[4:])
        )
        predicate = after & before & ds.field("idJyoCD").isin(self._venues)
        return cast(
            list[dict[str, object]],
            self._dataset.to_table(columns=list(self._columns), filter=predicate).to_pylist(),
        )


class PublicationReader:
    """Read one publication table through small scan and selected-row passes."""

    def __init__(
        self,
        dataset: ds.Dataset,
        key_columns: tuple[str, ...],
        value_columns: tuple[str, ...],
        venues: tuple[str, ...],
    ) -> None:
        self._dataset = dataset
        self._key_columns = key_columns
        self._value_columns = value_columns
        self._venues = venues

    def scan(self, year: int) -> list[dict[str, object]]:
        """Return intermediate-publication keys and clocks for one race year."""
        text_year = _publication_year(year)
        columns = _unique_columns((*self._key_columns, "headDataKubun", "HappyoTime"))
        predicate = (
            (ds.field("idYear") == text_year)
            & ds.field("idJyoCD").isin(self._venues)
            & (ds.field("headDataKubun") == "1")
        )
        return cast(
            list[dict[str, object]],
            self._dataset.to_table(columns=list(columns), filter=predicate).to_pylist(),
        )

    def read_pairs(
        self, year: int, pairs: Sequence[tuple[str, str | None]]
    ) -> list[dict[str, object]]:
        """Return every value row matching the selected pairs in one race year."""
        text_year = _publication_year(year)
        selected = _publication_pairs(pairs, text_year)
        if not selected:
            return []
        times = sorted(clock for _, clock in selected if clock is not None)
        clock_predicate: ds.Expression | None = None
        if times:
            clock_predicate = ds.field("HappyoTime").isin(times)
        if any(clock is None for _, clock in selected):
            null_clock = ds.field("HappyoTime").is_null()
            clock_predicate = (
                null_clock if clock_predicate is None else clock_predicate | null_clock
            )
        assert clock_predicate is not None
        predicate = (
            (ds.field("idYear") == text_year)
            & ds.field("idJyoCD").isin(self._venues)
            & (ds.field("headDataKubun") == "1")
            & clock_predicate
        )
        table = self._dataset.to_table(columns=list(self._value_columns), filter=predicate)
        # Other races publish at the same minutes; keep only the exact selected pairs
        # in Arrow before building Python rows. A null key part never matches.
        race_ids = pc.binary_join_element_wise(*(table[name] for name in self._key_columns), "")
        clocks = table["HappyoTime"]
        timed = pc.is_in(
            pc.binary_join_element_wise(race_ids, clocks, "|"),
            value_set=pa.array(
                [f"{race_id}|{clock}" for race_id, clock in selected if clock is not None],
                type=pa.string(),
            ),
        )
        untimed = pc.and_(
            pc.is_null(clocks),
            pc.is_in(
                race_ids,
                value_set=pa.array(
                    [race_id for race_id, clock in selected if clock is None], type=pa.string()
                ),
            ),
        )
        mask = pc.fill_null(pc.or_(timed, untimed), False)
        return cast(list[dict[str, object]], table.filter(mask).to_pylist())


def _check_columns(table: str, schema: pa.Schema, columns: Sequence[str]) -> None:
    if set(columns) - set(schema.names):
        raise ValueError(f"{table}: required projected source columns are missing")
    if any(not pa.types.is_string(schema.field(name).type) for name in columns):
        raise ValueError("reference sources must preserve nullable strings")


def _publication_key_columns(columns: Sequence[str]) -> tuple[str, ...]:
    """Return the complete fixed-snapshot race key projection."""
    values = tuple(columns)
    if values != _KEYS:
        raise ValueError("publication readers require the complete fixed-snapshot race key columns")
    return values


def _publication_value_columns(
    columns: Sequence[str], key_columns: Sequence[str]
) -> tuple[str, ...]:
    """Validate and return full rows needed after publication selection."""
    values = _unique_columns(tuple(columns))
    required = set(key_columns) | {"headDataKubun", "HappyoTime"}
    if not values or required - set(values):
        raise ValueError(
            "publication value columns must include keys, headDataKubun and HappyoTime"
        )
    return values


def _publication_venues(venues: Sequence[str]) -> tuple[str, ...]:
    """Return the explicit venue set used by publication-table predicates."""
    values = tuple(venues)
    if not values or any(not isinstance(venue, str) or not venue for venue in values):
        raise ValueError("publication readers require nonempty string venues")
    return values


def _publication_year(year: int) -> str:
    """Return one valid four-digit race-key year."""
    if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
        raise ValueError("publication year must be a four-digit integer")
    return f"{year:04d}"


def _publication_pairs(
    pairs: Sequence[tuple[str, str | None]], year: str
) -> frozenset[tuple[str, str | None]]:
    """Validate selected publication identities for one pass-two read."""
    selected: set[tuple[str, str | None]] = set()
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("publication pairs must contain race_id and HappyoTime")
        race_id, clock = pair
        if not isinstance(race_id, str) or re.fullmatch(r"[0-9]{16}", race_id) is None:
            raise ValueError("publication pairs require complete 16-digit race_id values")
        if race_id[:4] != year:
            raise ValueError("publication pairs must belong to the requested year")
        if clock is not None and not isinstance(clock, str):
            raise ValueError("publication HappyoTime must be a nullable string")
        selected.add((race_id, clock))
    return frozenset(selected)


def _unique_columns(columns: Sequence[str]) -> tuple[str, ...]:
    """Return columns in declared order without duplicated projections."""
    return tuple(dict.fromkeys(columns))
