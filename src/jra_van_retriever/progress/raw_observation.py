"""Observe raw acquisition data and close readers before external writes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import date
from pathlib import Path

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.acquisition_lock import AcquisitionBlocked
from jra_van_retriever.config.profiles import HistoricalOddsBatch, JVLinkProfile
from jra_van_retriever.contracts.odds import ARCHIVE_TABLES, KEY_COLUMNS
from jra_van_retriever.parsing.race_key import race_key_from_row
from jra_van_retriever.progress.state import RawSnapshot


def read_raw_snapshot(
    database_path: Path, profile: JVLinkProfile, batch: HistoricalOddsBatch, cutoff: date
) -> RawSnapshot:
    """Read every managed year once and close all readers before acquisition."""
    if not database_path.is_file():
        raise FileNotFoundError(f"raw race database does not exist: {database_path}")
    assert profile.race_start_date is not None
    lower = profile.race_start_date.strftime("%Y%m%d")
    upper = min(cutoff, date(batch.last_year, 12, 31)).strftime("%Y%m%d")
    columns = ", ".join(KEY_COLUMNS)
    counts: dict[tuple[str, str], int] = {}
    schemas: dict[str, str] = {}
    with closing(
        sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    ) as database:
        database.execute("BEGIN")
        rows = database.execute(
            f"SELECT DISTINCT {columns} FROM NL_RA_RACE WHERE idYear || idMonthDay BETWEEN ? AND ? "
            "AND idJyoCD IN ('01','02','03','04','05','06','07','08','09','10') "
            f"ORDER BY {columns}",
            (lower, upper),
        ).fetchall()
        races = tuple(race_key_from_row(row) for row in rows)
        for spec in sorted(profile.realtime_data_specs):
            table = ARCHIVE_TABLES[spec]
            if not database.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                continue
            schema = [(row[1], row[2]) for row in database.execute(f'PRAGMA table_info("{table}")')]
            if not set(KEY_COLUMNS) <= {name for name, _ in schema}:
                raise AcquisitionBlocked(f"archive key schema is invalid: {table}")
            schemas[spec] = hashlib.sha256(json.dumps(schema).encode()).hexdigest()
            for row in database.execute(
                f'SELECT {columns}, COUNT(*) FROM "{table}" WHERE idYear || idMonthDay BETWEEN ? AND ? GROUP BY {columns}',
                (lower, upper),
            ):
                key = race_key_from_row(tuple(row[:6]))
                counts[(key.race_id, spec)] = row[6]
    return RawSnapshot(races, counts, schemas)


_JRA_JYO_CODES = tuple(f"{code:02d}" for code in range(1, 11))


def iter_historical_race_keys(database_path: Path, *, start_date: date) -> Iterator[RaceKey]:
    """Yield a snapshot of race keys after closing the SQLite reader connection."""
    if not database_path.is_file():
        raise FileNotFoundError(f"raw race database does not exist: {database_path}")

    placeholders = ", ".join("?" for _ in _JRA_JYO_CODES)
    query = f"""
        SELECT idYear, idMonthDay, idJyoCD, idKaiji, idNichiji, idRaceNum
        FROM NL_RA_RACE
        WHERE idYear || idMonthDay >= ?
          AND idJyoCD IN ({placeholders})
        ORDER BY idYear, idMonthDay, idJyoCD, idKaiji, idNichiji, idRaceNum
    """
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as database:
        rows = database.execute(
            query,
            (start_date.strftime("%Y%m%d"), *_JRA_JYO_CODES),
        ).fetchall()

    for row in rows:
        yield race_key_from_row(row)


def read_archived_race_keys(
    database_path: Path, data_specs: frozenset[str]
) -> dict[str, set[RaceKey]]:
    """Read archive presence without imposing batch schema or period policy."""
    archived_races: dict[str, set[RaceKey]] = {}
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as database:
        database.execute("BEGIN")
        for data_spec, table in ARCHIVE_TABLES.items():
            if data_spec not in data_specs:
                continue
            exists = database.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if exists is None:
                continue
            rows = database.execute(
                f"SELECT DISTINCT idYear, idMonthDay, idJyoCD, idKaiji, idNichiji, idRaceNum "
                f'FROM "{table}"'
            ).fetchall()
            archived_races[data_spec] = {race_key_from_row(row) for row in rows}
    return archived_races
