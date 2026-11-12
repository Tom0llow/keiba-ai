"""Read one race-scoped processed version, pinned once, with its file identities.

The race-day feature command (ADR-037) reads a race's odds and capture-log rows from
the version that ``CURRENT`` names when it is read; later publications never mix in.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.dataset as ds

from data.loader.file_hash import file_sha256
from data.storage.snapshot_store import SnapshotStore
from domain.race_key import RaceKey

_KEY_COLUMNS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
_VERSION = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class RaceVersion:
    """Hold the projected rows and SHA-256 of each table read from one race version."""

    snapshot_id: str
    rows: Mapping[str, list[dict[str, object]]]
    sha256: Mapping[str, str]


def current_race_version_id(processed_root: Path, race_key: RaceKey) -> str | None:
    """Return the version name that the race's CURRENT selects, or None if unpublished."""
    _, pointer = SnapshotStore(processed_root).locations(race_key)
    if not pointer.is_file():
        return None
    value = pointer.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"empty processed snapshot pointer: {pointer}")
    return value


def read_race_version(
    processed_root: Path,
    race_key: RaceKey,
    *,
    columns: Mapping[str, Sequence[str]],
    optional: frozenset[str] = frozenset(),
    snapshot_id: str | None = None,
) -> RaceVersion | None:
    """Return one race version, or None when nothing was published yet.

    Without ``snapshot_id`` the race's CURRENT is resolved once; with it, that version is
    read and CURRENT is not opened. Every requested column must be a nullable string and
    include the race key; every row must belong to ``race_key``. A table in ``optional``
    may be absent from the version and is then left out of the result.
    """
    store = SnapshotStore(processed_root)
    versions, _ = store.locations(race_key)
    if snapshot_id is None:
        snapshot_id = current_race_version_id(processed_root, race_key)
        if snapshot_id is None:
            return None
    if _VERSION.fullmatch(snapshot_id) is None:
        raise ValueError(f"invalid race snapshot version: {snapshot_id!r}")
    version = versions / snapshot_id
    if not version.is_dir():
        raise FileNotFoundError(version)
    expected = (
        f"{race_key.race_date:%Y}",
        f"{race_key.race_date:%m%d}",
        race_key.jyo_code,
        race_key.kaiji,
        race_key.nichiji,
        race_key.race_number,
    )
    rows: dict[str, list[dict[str, object]]] = {}
    hashes: dict[str, str] = {}
    for table, selected in columns.items():
        if set(_KEY_COLUMNS) - set(selected):
            raise ValueError(f"{table}: race columns must include the race key")
        path = version / f"{table}.parquet"
        if not path.is_file():
            if table in optional:
                continue
            raise ValueError(f"race snapshot table is missing: {table}")
        digest = file_sha256(path)
        dataset = ds.dataset(path, format="parquet")
        if set(selected) - set(dataset.schema.names):
            raise ValueError(f"{table}: required projected source columns are missing")
        if any(not pa.types.is_string(dataset.schema.field(name).type) for name in selected):
            raise ValueError(f"{table}: race snapshot columns must be nullable strings")
        values = cast(list[dict[str, object]], dataset.to_table(columns=list(selected)).to_pylist())
        if any(tuple(row[name] for name in _KEY_COLUMNS) != expected for row in values):
            raise ValueError(f"{table}: race snapshot row belongs to another race")
        rows[table] = values
        hashes[table] = digest
    return RaceVersion(version.name, rows, hashes)
