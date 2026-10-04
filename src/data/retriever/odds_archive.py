"""Persist JVLinkToSQLite realtime odds tables without changing their schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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


def _table_exists(database: sqlite3.Connection, table: str) -> bool:
    row = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None
