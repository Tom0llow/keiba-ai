"""Persist JVLinkToSQLite realtime odds tables without changing their schema."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import JVLinkExecutionResult
from jra_van_retriever.contracts.odds import ARCHIVE_CAPTURE_LOG as ARCHIVE_CAPTURE_LOG
from jra_van_retriever.contracts.odds import CAPTURE_TABLES as CAPTURE_TABLES
from jra_van_retriever.contracts.odds import KEY_COLUMNS as KEY_COLUMNS
from jra_van_retriever.contracts.odds import ODDS_TABLES as ODDS_TABLES
from jra_van_retriever.contracts.odds import PREDICTION_SPECS


class _ClassificationLike(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def reason(self) -> str: ...


class CaptureClassifier(Protocol):
    """Classify one DataSpec from the JV-Link result and the archive attempt."""

    def __call__(
        self,
        data_spec: str,
        execution: JVLinkExecutionResult | None,
        *,
        archived: bool,
        observed_rows: int,
        failure_reason: str | None = None,
    ) -> _ClassificationLike: ...


@dataclass(frozen=True)
class RequestedArchiveResult:
    """Report a verified per-spec save or an unverified/invalid staging result."""

    acquired: bool
    inserted_rows: int
    after_rows: int
    reason: str


@dataclass(frozen=True)
class CaptureResult:
    """Report the persisted result for one DataSpec capture."""

    status: str
    reason: str
    observed_rows: int = 0
    inserted_rows: int = 0
    child_observed_rows: int = 0
    child_inserted_rows: int = 0


@dataclass(frozen=True)
class _CaptureArchiveAttempt:
    archived: bool
    failure_reason: str | None
    observed_rows: int
    inserted_rows: int
    child_observed_rows: int
    child_inserted_rows: int
    head_data_kubun: str | None
    happyo_time: str | None
    has_staging_rows: bool


_REALTIME_ODDS_TABLES = tuple(ODDS_TABLES.values())
# Keep earlier evidence (for example a pre-request quarantine) when a row is finalized.
_APPEND_REASON = "CASE WHEN reason IS NULL THEN ? ELSE reason || '; ' || ? END"
_CAPTURE_LOG_COLUMNS = (
    "capture_id",
    *KEY_COLUMNS,
    "data_spec",
    "scheduled_start_at",
    "offset_minutes",
    "planned_at",
    "started_at",
    "completed_at",
    "status",
    "reason",
    "process_returncode",
    "api_name",
    "api_returncode",
    "headDataKubun",
    "HappyoTime",
    "observed_rows",
    "inserted_rows",
    "child_observed_rows",
    "child_inserted_rows",
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
        tables = [ODDS_TABLES[spec][0] for spec in sorted(specs)]
        return _quarantine_tables(self._database, tables, directory, label)

    def quarantine_capture_staging(
        self, specs: frozenset[str], directory: Path, label: str
    ) -> list[dict[str, object]]:
        """Preserve capture parent and child staging with verified evidence.

        Prediction DataSpecs (0B41/0B42) share ``RT_O1``/``RT_O2`` with 0B31/0B32; each
        staging table is preserved once.
        """
        return _quarantine_tables(self._database, _staging_tables(specs), directory, label)

    def reset_staging(self, specs: frozenset[str]) -> None:
        """Clear only requested staging after its quarantine evidence is committed."""
        with closing(sqlite3.connect(self._database)) as database, database:
            for spec in specs:
                source = ODDS_TABLES[spec][0]
                if _table_exists(database, source):
                    database.execute(f'DELETE FROM "{source}"')

    def reset_capture_staging(self, specs: frozenset[str]) -> None:
        """Clear requested capture parent and child staging tables."""
        with closing(sqlite3.connect(self._database)) as database, database:
            for source in _staging_tables(specs):
                if _table_exists(database, source):
                    database.execute(f'DELETE FROM "{source}"')

    def begin_capture(
        self,
        capture_id: str,
        key: RaceKey,
        specs: frozenset[str],
        *,
        scheduled_start_at: datetime,
        offset_minutes: int,
        planned_at: datetime,
    ) -> None:
        """Commit one running log row per DataSpec before staging is changed."""
        values = _race_key_values(key)
        with closing(sqlite3.connect(self._database)) as database, database:
            _ensure_capture_log(database)
            placeholders = ", ".join("?" for _ in _CAPTURE_LOG_COLUMNS)
            columns = ", ".join(_quote(column) for column in _CAPTURE_LOG_COLUMNS)
            for spec in sorted(specs):
                database.execute(
                    f'INSERT INTO "{ARCHIVE_CAPTURE_LOG}" ({columns}) VALUES ({placeholders})',
                    (
                        capture_id,
                        *values,
                        spec,
                        scheduled_start_at.isoformat(),
                        str(offset_minutes),
                        _utc_iso(planned_at),
                        None,
                        None,
                        "running",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                )

    def append_capture_reason(self, capture_id: str, reason: str) -> None:
        """Attach staging evidence to every still-running row in one capture."""
        with closing(sqlite3.connect(self._database)) as database, database:
            cursor = database.execute(
                f'UPDATE "{ARCHIVE_CAPTURE_LOG}" SET reason = {_APPEND_REASON} '
                "WHERE capture_id = ? AND status = 'running'",
                (reason, reason, capture_id),
            )
            if cursor.rowcount == 0:
                raise sqlite3.IntegrityError("running capture log rows are missing")

    def append_capture_reason_for_running(self, reason: str) -> None:
        """Attach recovery evidence to all unresolved capture rows."""
        with closing(sqlite3.connect(self._database)) as database, database:
            cursor = database.execute(
                f'UPDATE "{ARCHIVE_CAPTURE_LOG}" SET reason = {_APPEND_REASON} WHERE status = ?',
                (reason, reason, "running"),
            )
            if cursor.rowcount == 0:
                raise sqlite3.IntegrityError("running capture log rows are missing")

    def append_finished_capture_reason(self, capture_id: str, reason: str) -> None:
        """Attach later evidence, such as a publication failure, to a finished capture."""
        with closing(sqlite3.connect(self._database)) as database, database:
            cursor = database.execute(
                f'UPDATE "{ARCHIVE_CAPTURE_LOG}" SET reason = {_APPEND_REASON} '
                "WHERE capture_id = ? AND status <> 'running'",
                (reason, reason, capture_id),
            )
            if cursor.rowcount == 0:
                raise sqlite3.IntegrityError("finished capture log rows are missing")

    def mark_capture_started(self, capture_id: str, started_at: datetime) -> None:
        """Record the UTC clock immediately before invoking JVLinkToSQLite."""
        with closing(sqlite3.connect(self._database)) as database, database:
            cursor = database.execute(
                f'UPDATE "{ARCHIVE_CAPTURE_LOG}" SET started_at = ? '
                "WHERE capture_id = ? AND status = 'running'",
                (_utc_iso(started_at), capture_id),
            )
            if cursor.rowcount == 0:
                raise sqlite3.IntegrityError("running capture log rows are missing")

    def record_skipped_capture(
        self,
        capture_id: str,
        key: RaceKey,
        specs: frozenset[str],
        *,
        scheduled_start_at: datetime,
        offset_minutes: int,
        planned_at: datetime,
    ) -> None:
        """Persist a late capture without recording execution timestamps."""
        values = _race_key_values(key)
        with closing(sqlite3.connect(self._database)) as database, database:
            _ensure_capture_log(database)
            placeholders = ", ".join("?" for _ in _CAPTURE_LOG_COLUMNS)
            columns = ", ".join(_quote(column) for column in _CAPTURE_LOG_COLUMNS)
            for spec in sorted(specs):
                database.execute(
                    f'INSERT INTO "{ARCHIVE_CAPTURE_LOG}" ({columns}) VALUES ({placeholders})',
                    (
                        capture_id,
                        *values,
                        spec,
                        scheduled_start_at.isoformat(),
                        str(offset_minutes),
                        _utc_iso(planned_at),
                        None,
                        None,
                        "skipped_late",
                        "late_tolerance_exceeded",
                        None,
                        None,
                        None,
                        None,
                        None,
                        "0",
                        "0",
                        "0",
                        "0",
                    ),
                )

    def capture_statuses(self, capture_id: str) -> dict[str, tuple[str, str]]:
        """Return the persisted status and reason of each DataSpec in one capture."""
        with closing(sqlite3.connect(self._database)) as database:
            rows = database.execute(
                f'SELECT data_spec, status, reason FROM "{ARCHIVE_CAPTURE_LOG}" WHERE capture_id = ?',
                (capture_id,),
            ).fetchall()
        return {str(spec): (str(status), str(reason or "")) for spec, status, reason in rows}

    def running_capture_specs(self) -> frozenset[str]:
        """Return DataSpecs belonging to unresolved race-day captures."""
        if not self._database.is_file():
            return frozenset()
        with closing(sqlite3.connect(self._database)) as database:
            if not _table_exists(database, ARCHIVE_CAPTURE_LOG):
                return frozenset()
            rows = database.execute(
                f"SELECT DISTINCT data_spec FROM \"{ARCHIVE_CAPTURE_LOG}\" WHERE status = 'running'"
            ).fetchall()
        return frozenset(str(row[0]) for row in rows)

    def finished_capture_keys(self, key_prefix: tuple[str, str]) -> frozenset[tuple[str, str, str]]:
        """Return (race_id, offset_minutes, kind) with a terminal log row on one race date.

        ``kind`` is ``prediction`` for 0B41/0B42 rows and ``capture`` otherwise, so a
        prediction fetch and a capture at the same offset are finished independently.
        """
        if not self._database.is_file():
            return frozenset()
        with closing(sqlite3.connect(self._database)) as database:
            if not _table_exists(database, ARCHIVE_CAPTURE_LOG):
                return frozenset()
            columns = " || ".join(_quote(column) for column in KEY_COLUMNS)
            specs = ", ".join(f"'{spec}'" for spec in sorted(PREDICTION_SPECS))
            rows = database.execute(
                f"SELECT DISTINCT {columns}, offset_minutes, "
                f"CASE WHEN data_spec IN ({specs}) THEN 'prediction' ELSE 'capture' END "
                f'FROM "{ARCHIVE_CAPTURE_LOG}" '
                "WHERE idYear = ? AND idMonthDay = ? AND status <> 'running'",
                key_prefix,
            ).fetchall()
        return frozenset((str(race_id), str(offset), str(kind)) for race_id, offset, kind in rows)

    def interrupt_running_captures(self, completed_at: datetime, reason: str) -> int:
        """Finalize every unresolved capture after its staging evidence is safe."""
        with closing(sqlite3.connect(self._database)) as database, database:
            if not _table_exists(database, ARCHIVE_CAPTURE_LOG):
                return 0
            cursor = database.execute(
                f'UPDATE "{ARCHIVE_CAPTURE_LOG}" '
                f"SET completed_at = ?, status = 'interrupted', reason = {_APPEND_REASON} "
                "WHERE status = 'running'",
                (_utc_iso(completed_at), reason, reason),
            )
            return cursor.rowcount

    def finish_capture(
        self,
        capture_id: str,
        key: RaceKey,
        specs: frozenset[str],
        execution: JVLinkExecutionResult | None,
        *,
        completed_at: datetime,
        quarantine_directory: Path,
        quarantine_label: str,
        classifier: CaptureClassifier,
    ) -> dict[str, CaptureResult]:
        """Validate, archive, and finalize each DataSpec independently."""
        results: dict[str, CaptureResult] = {}
        for spec in sorted(specs):
            with closing(sqlite3.connect(self._database)) as database:
                database.execute("SAVEPOINT capture_spec")
                attempt = (
                    _observe_capture_attempt(database, key, spec)
                    if execution is not None and spec in execution.fatal_specs
                    else _archive_prediction_spec(database, key, spec)
                    if spec in ODDS_TABLES
                    else _archive_capture_spec(database, key, spec)
                )
                classification = classifier(
                    spec,
                    execution,
                    archived=attempt.archived,
                    observed_rows=attempt.observed_rows,
                    failure_reason=attempt.failure_reason,
                )
                needs_quarantine = classification.status == "failed" and attempt.has_staging_rows
                if needs_quarantine:
                    database.execute("ROLLBACK TO capture_spec")
                    database.execute("RELEASE capture_spec")
                    database.commit()
                else:
                    _reset_capture_spec(database, spec)
                    _finish_capture_log(
                        database,
                        capture_id,
                        spec,
                        execution,
                        completed_at,
                        classification.status,
                        classification.reason,
                        attempt,
                    )
                    database.execute("RELEASE capture_spec")
                    database.commit()
            if needs_quarantine:
                artifacts = self.quarantine_capture_staging(
                    frozenset({spec}),
                    quarantine_directory,
                    f"{quarantine_label}-{spec}",
                )
                reason = classification.reason
                if artifacts:
                    evidence = json.dumps(artifacts, ensure_ascii=False, sort_keys=True)
                    reason = f"{reason}: quarantined {evidence}"
                with closing(sqlite3.connect(self._database)) as database, database:
                    _reset_capture_spec(database, spec)
                    _finish_capture_log(
                        database,
                        capture_id,
                        spec,
                        execution,
                        completed_at,
                        classification.status,
                        reason,
                        attempt,
                    )
            results[spec] = CaptureResult(
                classification.status,
                classification.reason,
                attempt.observed_rows,
                attempt.inserted_rows,
                attempt.child_observed_rows,
                attempt.child_inserted_rows,
            )
        return results

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


def _archive_prediction_spec(
    database: sqlite3.Connection, key: RaceKey, spec: str
) -> _CaptureArchiveAttempt:
    """Archive one race's 0B41/0B42 time series into ``ARCHIVE_O1``/``ARCHIVE_O2``.

    A time series has many publications, so the single-row and ``happyo_conflict``
    rules of the capture archive do not apply; rows are deduplicated as full rows
    against the race's archived rows (ADR-007). The log keeps the latest intermediate
    publication of the staged rows.
    """
    source, destination = ODDS_TABLES[spec]
    if not _table_exists(database, source):
        return _failed_capture_attempt("staging_table_missing")
    schema = _table_schema(database, source)
    names = [name for name, _ in schema]
    if not set(KEY_COLUMNS) | {"headDataKubun", "HappyoTime"} <= set(names):
        return _failed_capture_attempt("staging_schema_invalid", has_staging_rows=True)
    expected_key = _race_key_values(key)
    rows = [tuple(row) for row in database.execute(f'SELECT * FROM "{source}"')]
    if not rows:
        return _CaptureArchiveAttempt(False, None, 0, 0, 0, 0, None, None, False)
    key_indexes = tuple(names.index(column) for column in KEY_COLUMNS)
    observed_rows = sum(tuple(row[i] for i in key_indexes) == expected_key for row in rows)
    kubun_index, happyo_index = names.index("headDataKubun"), names.index("HappyoTime")
    intermediate = [
        cast(str, row[happyo_index])
        for row in rows
        if row[kubun_index] == "1" and isinstance(row[happyo_index], str)
    ]
    head_data_kubun = "1" if intermediate else None
    happyo_time = max(intermediate) if intermediate else None
    if observed_rows != len(rows):
        return _failed_capture_attempt(
            "staging_race_mismatch", observed_rows=observed_rows, has_staging_rows=True
        )
    if _table_exists(database, destination) and _table_schema(database, destination) != schema:
        return _failed_capture_attempt(
            "archive_schema_mismatch",
            observed_rows=observed_rows,
            head_data_kubun=head_data_kubun,
            happyo_time=happyo_time,
            has_staging_rows=True,
        )
    if not _table_exists(database, destination):
        database.execute(f'CREATE TABLE "{destination}" AS SELECT * FROM "{source}" WHERE 0')
    index_columns = ", ".join(_quote(column) for column in KEY_COLUMNS)
    database.execute(
        f'CREATE INDEX IF NOT EXISTS "{destination}_race_key" ON "{destination}" ({index_columns})'
    )
    key_condition = " AND ".join(f"{_quote(column)} = ?" for column in KEY_COLUMNS)
    before = database.total_changes
    database.execute(
        f'INSERT INTO "{destination}" SELECT * FROM "{source}" '
        f'EXCEPT SELECT * FROM "{destination}" WHERE {key_condition}',
        expected_key,
    )
    return _CaptureArchiveAttempt(
        True,
        None,
        observed_rows,
        database.total_changes - before,
        0,
        0,
        head_data_kubun,
        happyo_time,
        True,
    )


def _archive_capture_spec(
    database: sqlite3.Connection, key: RaceKey, spec: str
) -> _CaptureArchiveAttempt:
    pairs = CAPTURE_TABLES[spec]
    parent_source, _ = pairs[0]
    if not _table_exists(database, parent_source):
        # Child rows may still exist; they must be quarantined, not deleted by the reset.
        child_rows_present = len(pairs) == 2 and bool(
            _table_exists(database, pairs[1][0])
            and database.execute(f'SELECT 1 FROM "{pairs[1][0]}" LIMIT 1').fetchone()
        )
        return _failed_capture_attempt("staging_table_missing", has_staging_rows=child_rows_present)

    parent_schema = _table_schema(database, parent_source)
    parent_names = [name for name, _ in parent_schema]
    required_parent = set(KEY_COLUMNS) | {"headDataKubun", "HappyoTime"}
    if not required_parent <= set(parent_names):
        return _failed_capture_attempt("staging_schema_invalid", has_staging_rows=True)
    expected_key = _race_key_values(key)
    parent_rows = [tuple(row) for row in database.execute(f'SELECT * FROM "{parent_source}"')]
    parent_key_indexes = tuple(parent_names.index(column) for column in KEY_COLUMNS)
    observed_rows = sum(
        tuple(row[index] for index in parent_key_indexes) == expected_key for row in parent_rows
    )

    child_schema: list[tuple[str, str]] = []
    child_rows: list[tuple[object, ...]] = []
    child_observed_rows = 0
    if len(pairs) == 2:
        child_source, _ = pairs[1]
        if not _table_exists(database, child_source):
            return _failed_capture_attempt(
                "staging_table_missing",
                observed_rows=observed_rows,
                has_staging_rows=bool(parent_rows),
            )
        child_schema = _table_schema(database, child_source)
        child_names = [name for name, _ in child_schema]
        if not set(KEY_COLUMNS) <= set(child_names) or {"headDataKubun", "HappyoTime"} & set(
            child_names
        ):
            return _failed_capture_attempt(
                "staging_schema_invalid", observed_rows=observed_rows, has_staging_rows=True
            )
        child_rows = [tuple(row) for row in database.execute(f'SELECT * FROM "{child_source}"')]
        child_key_indexes = tuple(child_names.index(column) for column in KEY_COLUMNS)
        child_observed_rows = sum(
            tuple(row[index] for index in child_key_indexes) == expected_key for row in child_rows
        )
    has_staging_rows = bool(parent_rows or child_rows)

    if not parent_rows:
        if child_rows:
            return _failed_capture_attempt(
                "orphan_child_rows",
                child_observed_rows=child_observed_rows,
                has_staging_rows=True,
            )
        return _CaptureArchiveAttempt(False, None, 0, 0, 0, 0, None, None, False)

    if observed_rows != len(parent_rows):
        return _failed_capture_attempt(
            "staging_race_mismatch",
            observed_rows=observed_rows,
            child_observed_rows=child_observed_rows,
            has_staging_rows=True,
        )
    if observed_rows > 1:
        return _failed_capture_attempt(
            "staging_multiple_rows",
            observed_rows=observed_rows,
            child_observed_rows=child_observed_rows,
            has_staging_rows=True,
        )

    head_data_kubun = parent_rows[0][parent_names.index("headDataKubun")]
    happyo_time = parent_rows[0][parent_names.index("HappyoTime")]
    if not isinstance(head_data_kubun, str) or not isinstance(happyo_time, str):
        return _failed_capture_attempt(
            "staging_schema_invalid",
            observed_rows=observed_rows,
            child_observed_rows=child_observed_rows,
            has_staging_rows=True,
        )
    if child_schema and child_observed_rows != len(child_rows):
        return _failed_capture_attempt(
            "child_race_mismatch",
            observed_rows=observed_rows,
            child_observed_rows=child_observed_rows,
            head_data_kubun=head_data_kubun,
            happyo_time=happyo_time,
            has_staging_rows=True,
        )

    expected_schemas: list[list[tuple[str, str]]] = [parent_schema]
    if child_schema:
        expected_schemas.append(
            [(name, "TEXT") for name, _ in child_schema]
            + [("headDataKubun", "TEXT"), ("HappyoTime", "TEXT")]
        )
    for (_, destination), expected_schema in zip(pairs, expected_schemas, strict=True):
        if (
            _table_exists(database, destination)
            and _table_schema(database, destination) != expected_schema
        ):
            return _failed_capture_attempt(
                "archive_schema_mismatch",
                observed_rows=observed_rows,
                child_observed_rows=child_observed_rows,
                head_data_kubun=head_data_kubun,
                happyo_time=happyo_time,
                has_staging_rows=True,
            )

    current_sets = [set(parent_rows)]
    if child_schema:
        current_sets.append({(*row, head_data_kubun, happyo_time) for row in child_rows})
    version_condition = " AND ".join(
        [
            *(f"{_quote(column)} = ?" for column in KEY_COLUMNS),
            '"headDataKubun" = ?',
            '"HappyoTime" = ?',
        ]
    )
    version_values = (*expected_key, head_data_kubun, happyo_time)
    parent_version_archived = False
    for index, ((_, destination), current_rows) in enumerate(zip(pairs, current_sets, strict=True)):
        archived_rows: set[tuple[object, ...]] = set()
        if _table_exists(database, destination):
            archived_rows = {
                tuple(row)
                for row in database.execute(
                    f'SELECT * FROM "{destination}" WHERE {version_condition}', version_values
                )
            }
        if index == 0:
            parent_version_archived = bool(archived_rows)
        # Once a parent version is archived, its child set is fixed, even when empty.
        if (archived_rows or (index > 0 and parent_version_archived)) and (
            archived_rows != current_rows
        ):
            return _failed_capture_attempt(
                "happyo_conflict",
                observed_rows=observed_rows,
                child_observed_rows=child_observed_rows,
                head_data_kubun=head_data_kubun,
                happyo_time=happyo_time,
                has_staging_rows=True,
            )

    key_condition = " AND ".join(f"{_quote(column)} = ?" for column in KEY_COLUMNS)
    inserted_rows = 0
    child_inserted_rows = 0
    for index, ((source, destination), expected_schema) in enumerate(
        zip(pairs, expected_schemas, strict=True)
    ):
        if not _table_exists(database, destination):
            if index == 0:
                database.execute(
                    f'CREATE TABLE "{destination}" AS SELECT * FROM "{source}" WHERE 0'
                )
            else:
                declaration = ", ".join(f"{_quote(name)} TEXT" for name, _ in expected_schema)
                database.execute(f'CREATE TABLE "{destination}" ({declaration})')
        index_columns = ", ".join(_quote(column) for column in KEY_COLUMNS)
        database.execute(
            f'CREATE INDEX IF NOT EXISTS "{destination}_race_key" '
            f'ON "{destination}" ({index_columns})'
        )
        # Staging holds only the requested race (checked above), so comparing against
        # that race's archived rows is the same full-row deduplication without a full scan.
        before = database.total_changes
        if index == 0:
            database.execute(
                f'INSERT INTO "{destination}" SELECT * FROM "{source}" '
                f'EXCEPT SELECT * FROM "{destination}" WHERE {key_condition}',
                expected_key,
            )
            inserted_rows = database.total_changes - before
        else:
            database.execute(
                f'INSERT INTO "{destination}" SELECT *, ?, ? FROM "{source}" '
                f'EXCEPT SELECT * FROM "{destination}" WHERE {key_condition}',
                (head_data_kubun, happyo_time, *expected_key),
            )
            child_inserted_rows = database.total_changes - before

    return _CaptureArchiveAttempt(
        True,
        None,
        observed_rows,
        inserted_rows,
        child_observed_rows,
        child_inserted_rows,
        head_data_kubun,
        happyo_time,
        has_staging_rows,
    )


def _observe_capture_attempt(
    database: sqlite3.Connection, key: RaceKey, spec: str
) -> _CaptureArchiveAttempt:
    """Count target-race staging rows for a DataSpec that JV-Link reported as failed."""
    pairs = _spec_tables(spec)
    expected_key = _race_key_values(key)
    key_condition = " AND ".join(f"{_quote(column)} = ?" for column in KEY_COLUMNS)
    totals: dict[str, int] = {}
    matching: dict[str, int] = {}
    for source, _ in pairs:
        if not _table_exists(database, source):
            totals[source] = matching[source] = 0
            continue
        totals[source] = int(database.execute(f'SELECT COUNT(*) FROM "{source}"').fetchone()[0])
        names = {name for name, _ in _table_schema(database, source)}
        matching[source] = (
            int(
                database.execute(
                    f'SELECT COUNT(*) FROM "{source}" WHERE {key_condition}', expected_key
                ).fetchone()[0]
            )
            if set(KEY_COLUMNS) <= names
            else 0
        )
    parent_source = pairs[0][0]
    head_data_kubun: str | None = None
    happyo_time: str | None = None
    if totals[parent_source] == 1 and matching[parent_source] == 1:
        names_list = [name for name, _ in _table_schema(database, parent_source)]
        if {"headDataKubun", "HappyoTime"} <= set(names_list):
            row = database.execute(f'SELECT * FROM "{parent_source}"').fetchone()
            head = row[names_list.index("headDataKubun")]
            happyo = row[names_list.index("HappyoTime")]
            head_data_kubun = head if isinstance(head, str) else None
            happyo_time = happyo if isinstance(happyo, str) else None
    return _CaptureArchiveAttempt(
        False,
        None,
        matching[parent_source],
        0,
        matching[pairs[1][0]] if len(pairs) == 2 else 0,
        0,
        head_data_kubun,
        happyo_time,
        any(totals.values()),
    )


def _failed_capture_attempt(
    reason: str,
    *,
    observed_rows: int = 0,
    child_observed_rows: int = 0,
    head_data_kubun: str | None = None,
    happyo_time: str | None = None,
    has_staging_rows: bool = False,
) -> _CaptureArchiveAttempt:
    return _CaptureArchiveAttempt(
        False,
        reason,
        observed_rows,
        0,
        child_observed_rows,
        0,
        head_data_kubun,
        happyo_time,
        has_staging_rows,
    )


def _ensure_capture_log(database: sqlite3.Connection) -> None:
    declaration = ", ".join(f"{_quote(column)} TEXT" for column in _CAPTURE_LOG_COLUMNS)
    database.execute(f'CREATE TABLE IF NOT EXISTS "{ARCHIVE_CAPTURE_LOG}" ({declaration})')
    schema = _table_schema(database, ARCHIVE_CAPTURE_LOG)
    if schema != [(column, "TEXT") for column in _CAPTURE_LOG_COLUMNS]:
        raise sqlite3.IntegrityError("capture log schema is invalid")
    database.execute(
        f'CREATE INDEX IF NOT EXISTS "{ARCHIVE_CAPTURE_LOG}_status" '
        f'ON "{ARCHIVE_CAPTURE_LOG}" (status)'
    )


def _finish_capture_log(
    database: sqlite3.Connection,
    capture_id: str,
    spec: str,
    execution: JVLinkExecutionResult | None,
    completed_at: datetime,
    status: str,
    reason: str,
    attempt: _CaptureArchiveAttempt,
) -> None:
    process_returncode = getattr(execution, "process_returncode", None)
    api_results = getattr(execution, "api_results", {})
    api_name, api_returncode = api_results.get(spec, (None, None))
    cursor = database.execute(
        f'UPDATE "{ARCHIVE_CAPTURE_LOG}" SET '
        f"completed_at = ?, status = ?, reason = {_APPEND_REASON}, process_returncode = ?, "
        "api_name = ?, api_returncode = ?, headDataKubun = ?, HappyoTime = ?, "
        "observed_rows = ?, inserted_rows = ?, child_observed_rows = ?, "
        "child_inserted_rows = ? WHERE capture_id = ? AND data_spec = ? "
        "AND status = 'running'",
        (
            _utc_iso(completed_at),
            status,
            reason,
            reason,
            None if process_returncode is None else str(process_returncode),
            api_name,
            None if api_returncode is None else str(api_returncode),
            attempt.head_data_kubun,
            attempt.happyo_time,
            str(attempt.observed_rows),
            str(attempt.inserted_rows),
            str(attempt.child_observed_rows),
            str(attempt.child_inserted_rows),
            capture_id,
            spec,
        ),
    )
    if cursor.rowcount != 1:
        raise sqlite3.IntegrityError("running capture log row is missing")


def _reset_capture_spec(database: sqlite3.Connection, spec: str) -> None:
    for source, _ in _spec_tables(spec):
        if _table_exists(database, source):
            database.execute(f'DELETE FROM "{source}"')


def _spec_tables(spec: str) -> tuple[tuple[str, str], ...]:
    """Return the (staging, archive) pairs of one capture or prediction DataSpec."""
    if spec in ODDS_TABLES:
        return (ODDS_TABLES[spec],)
    return CAPTURE_TABLES[spec]


def _staging_tables(specs: frozenset[str]) -> list[str]:
    """Return each staging table of the DataSpecs once, in DataSpec order."""
    tables: list[str] = []
    for spec in sorted(specs):
        for source, _ in _spec_tables(spec):
            if source not in tables:
                tables.append(source)
    return tables


def _quarantine_tables(
    database_path: Path, tables: list[str], directory: Path, label: str
) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        existing = [table for table in tables if _table_exists(source, table)]
        if not any(
            source.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() for table in existing
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
                for table in existing:
                    schema = _table_schema(source, table)
                    if any(
                        not re.fullmatch(r"[A-Za-z0-9_ (),]*", column_type)
                        for _, column_type in schema
                    ):
                        raise ValueError("unsupported staging column declaration for quarantine")
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
                    copied_schema = _table_schema(destination, table)
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


def _table_schema(database: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(str(row[1]), str(row[2])) for row in database.execute(f'PRAGMA table_info("{table}")')]


def _race_key_values(key: RaceKey) -> tuple[str, str, str, str, str, str]:
    return (
        f"{key.race_date:%Y}",
        f"{key.race_date:%m%d}",
        key.jyo_code,
        key.kaiji,
        key.nichiji,
        key.race_number,
    )


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("capture timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _table_exists(database: sqlite3.Connection, table: str) -> bool:
    row = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
