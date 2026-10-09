"""Persist JVLinkToSQLite realtime odds tables without changing their schema."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from data.race_key import RaceKey

KEY_COLUMNS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
ODDS_TABLES = {
    "0B41": ("RT_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O1_ODDS_TANFUKUWAKU"),
    "0B42": ("RT_O2_ODDS_UMAREN", "ARCHIVE_O2_ODDS_UMAREN"),
}


@dataclass(frozen=True)
class RequestedArchiveResult:
    """Report a verified per-spec save or an unverified/invalid staging result."""

    acquired: bool
    inserted_rows: int
    after_rows: int
    reason: str


_REALTIME_ODDS_TABLES = (
    ("RT_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O1_ODDS_TANFUKUWAKU"),
    ("RT_O2_ODDS_UMAREN", "ARCHIVE_O2_ODDS_UMAREN"),
)


class OddsArchive:
    """Copy transient JVLinkToSQLite odds rows into cumulative archive tables."""

    def __init__(self, database: Path) -> None:
        self._database = database.expanduser().resolve()

    def archive(self) -> int:
        """Archive O1/O2 realtime rows and return the number of newly inserted rows.

        JVLinkToSQLite recreates its ``RT_*`` tables for realtime executions. The
        archive tables therefore preserve the exact source columns while keeping
        rows accumulated across executions. ``EXCEPT`` provides idempotent full-row
        deduplication without inventing a synthetic business key.
        """
        if not self._database.is_file():
            raise FileNotFoundError(f"raw race database does not exist: {self._database}")

        inserted = 0
        with sqlite3.connect(self._database) as database:
            for source, destination in _REALTIME_ODDS_TABLES:
                if not _table_exists(database, source):
                    continue
                if not _table_exists(database, destination):
                    database.execute(
                        f'CREATE TABLE "{destination}" AS SELECT * FROM "{source}" WHERE 0'
                    )
                before = database.total_changes
                database.execute(
                    f'INSERT INTO "{destination}" '
                    f'SELECT * FROM "{source}" EXCEPT SELECT * FROM "{destination}"'
                )
                inserted += database.total_changes - before
        return inserted

    def quarantine_staging(
        self, specs: frozenset[str], directory: Path, label: str
    ) -> list[dict[str, object]]:
        """Preserve unknown staging rows with schema/count/hash validation."""
        artifacts: list[dict[str, object]] = []
        with closing(sqlite3.connect(f"{self._database.as_uri()}?mode=ro", uri=True)) as source:
            source.execute("BEGIN")
            tables = [
                ODDS_TABLES[spec][0]
                for spec in sorted(specs)
                if _table_exists(source, ODDS_TABLES[spec][0])
            ]
            if not any(
                source.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() for table in tables
            ):
                return artifacts
            directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".quarantine-", suffix=".db", dir=directory
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            final = directory / f"{label}-{uuid.uuid4().hex}.db"
            evidence: dict[str, object] = {}
            try:
                with closing(sqlite3.connect(temporary)) as destination, destination:
                    for table in tables:
                        schema = [
                            (row[1], row[2])
                            for row in source.execute(f'PRAGMA table_info("{table}")')
                        ]
                        if any(
                            not re.fullmatch(r"[A-Za-z0-9_ (),]*", column_type)
                            for _, column_type in schema
                        ):
                            raise ValueError(
                                "unsupported staging column declaration for quarantine"
                            )
                        declaration = ", ".join(
                            f"{_quote(name)} {column_type}" for name, column_type in schema
                        )
                        destination.execute(f'CREATE TABLE "{table}" ({declaration})')
                        placeholders = ", ".join("?" for _ in schema)
                        cursor = source.execute(f'SELECT * FROM "{table}"')
                        count = 0
                        digest = hashlib.sha256()
                        while rows := cursor.fetchmany(1024):
                            for row in rows:
                                digest.update(repr(tuple(row)).encode("utf-8"))
                            destination.executemany(
                                f'INSERT INTO "{table}" VALUES ({placeholders})', rows
                            )
                            count += len(rows)
                        copied_schema = [
                            (row[1], row[2])
                            for row in destination.execute(f'PRAGMA table_info("{table}")')
                        ]
                        copied_digest = hashlib.sha256()
                        copied_count = 0
                        for row in destination.execute(f'SELECT * FROM "{table}"'):
                            copied_digest.update(repr(tuple(row)).encode("utf-8"))
                            copied_count += 1
                        if (
                            copied_schema != schema
                            or copied_count != count
                            or copied_digest.hexdigest() != digest.hexdigest()
                        ):
                            raise ValueError("staging quarantine verification failed")
                        evidence[table] = {
                            "rows": count,
                            "sha256": digest.hexdigest(),
                            "schema": schema,
                        }
                os.replace(temporary, final)
                artifacts.append({"path": str(final), "tables": evidence})
            finally:
                temporary.unlink(missing_ok=True)
        return artifacts

    def reset_staging(self, specs: frozenset[str]) -> None:
        """Clear only requested staging after its quarantine evidence is committed."""
        with closing(sqlite3.connect(self._database)) as database, database:
            for spec in specs:
                source = ODDS_TABLES[spec][0]
                if _table_exists(database, source):
                    database.execute(f'DELETE FROM "{source}"')

    def archive_request(
        self, key: RaceKey, specs: frozenset[str]
    ) -> dict[str, RequestedArchiveResult]:
        """Save only the requested fresh race/spec rows with full-row deduplication.

        A present, valid, empty realtime table is returned as a candidate for
        the normal ``JVOpen``/``JVRTOpen`` no-data result (RC=-1). The caller
        must verify that API return code before recording
        ``provider_missing``. Missing tables and validation failures remain
        errors.
        """
        results: dict[str, RequestedArchiveResult] = {}
        values = (
            f"{key.race_date:%Y}",
            f"{key.race_date:%m%d}",
            key.jyo_code,
            key.kaiji,
            key.nichiji,
            key.race_number,
        )
        condition = " AND ".join(f'"{column}"=?' for column in KEY_COLUMNS)
        with closing(sqlite3.connect(self._database)) as database, database:
            for spec in sorted(specs):
                source, destination = ODDS_TABLES[spec]
                if not _table_exists(database, source):
                    results[spec] = RequestedArchiveResult(False, 0, 0, "staging_table_missing")
                    continue
                schema = [
                    (row[1], row[2]) for row in database.execute(f'PRAGMA table_info("{source}")')
                ]
                if not (set(KEY_COLUMNS) | {"HappyoTime"}) <= {name for name, _ in schema}:
                    results[spec] = RequestedArchiveResult(False, 0, 0, "staging_schema_invalid")
                    continue
                keys = database.execute(
                    f'SELECT DISTINCT {", ".join(KEY_COLUMNS)} FROM "{source}"'
                ).fetchall()
                if not keys:
                    results[spec] = RequestedArchiveResult(False, 0, 0, "jvopen_no_data")
                    continue
                if keys != [values]:
                    results[spec] = RequestedArchiveResult(False, 0, 0, "staging_race_mismatch")
                    continue
                if _table_exists(database, destination):
                    archive_schema = [
                        (row[1], row[2])
                        for row in database.execute(f'PRAGMA table_info("{destination}")')
                    ]
                    if archive_schema != schema:
                        results[spec] = RequestedArchiveResult(
                            False, 0, 0, "archive_schema_mismatch"
                        )
                        continue
                else:
                    database.execute(
                        f'CREATE TABLE "{destination}" AS SELECT * FROM "{source}" WHERE 0'
                    )
                database.execute(
                    f'CREATE INDEX IF NOT EXISTS "{destination}_race_key" ON "{destination}" ({", ".join(KEY_COLUMNS)})'
                )
                before = database.total_changes
                database.execute(
                    f'INSERT INTO "{destination}" SELECT * FROM "{source}" WHERE {condition} EXCEPT SELECT * FROM "{destination}" WHERE {condition}',
                    values + values,
                )
                inserted = database.total_changes - before
                after = database.execute(
                    f'SELECT COUNT(*) FROM "{destination}" WHERE {condition}', values
                ).fetchone()[0]
                results[spec] = RequestedArchiveResult(
                    True, inserted, after, "requested_archive_committed"
                )
        return results


def _table_exists(database: sqlite3.Connection, table: str) -> bool:
    row = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
