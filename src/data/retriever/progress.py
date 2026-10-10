"""Persist weekly acquisition state separately from the raw acquisition store."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from data.race_key import RaceKey
from data.retriever.acquisition_lock import AcquisitionBlocked, canonical_path
from data.retriever.historical import _race_key_from_row
from data.retriever.setting import HistoricalOddsBatch, JVLinkProfile

LEDGER_FILENAME = "historical-odds-progress.db"
ARCHIVE_TABLES = {"0B41": "ARCHIVE_O1_ODDS_TANFUKUWAKU", "0B42": "ARCHIVE_O2_ODDS_UMAREN"}
KEY_COLUMNS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
TERMINAL_STATES = {"acquired", "provider_missing"}
API_NAMES = frozenset({"JVOpen", "JVRTOpen", "JVStatus", "JVRead", "JVGets"})
NO_DATA_API_NAMES = frozenset({"JVOpen", "JVRTOpen"})
STATE_REASONS = {
    "pending": frozenset({"new_candidate", "unrequested"}),
    "running": frozenset({"request_started"}),
    "acquired": frozenset(
        {
            "external_archive_observed",
            "initial_archive_observed",
            "recovered_archive_commit",
            "requested_archive_committed",
        }
    ),
    "provider_missing": frozenset(
        {
            "jvopen_no_data",
            "legacy_provider_missing",
            "provider_confirmed_missing",
            "user_accepted_existing_gaps",
        }
    ),
    "failed": frozenset(
        {
            "archive_schema_mismatch",
            "empty_response_unverified",
            "jvlink_error",
            "recovered_unconfirmed",
            "staging_race_mismatch",
            "staging_schema_invalid",
            "staging_table_missing",
        }
    ),
}


@dataclass(frozen=True)
class RawSnapshot:
    """Represent one consistent read-only snapshot of candidates and archive counts."""

    races: tuple[RaceKey, ...]
    counts: dict[tuple[str, str], int]
    schemas: dict[str, str]


@dataclass(frozen=True)
class SpecState:
    """Represent a ledger entry for one race and one odds DataSpec."""

    race_id: str
    data_spec: str
    state: str
    reason: str
    before_rows: int
    after_rows: int
    attempts: int = 0


def race_key_from_id(race_id: str) -> RaceKey:
    """Validate and restore the complete persisted race key."""
    if len(race_id) != 16 or not race_id.isdigit():
        raise AcquisitionBlocked("invalid race_id in progress ledger")
    return _race_key_from_row(
        (race_id[:4], race_id[4:8], race_id[8:10], race_id[10:12], race_id[12:14], race_id[14:16])
    )


def policy_hash(profile: JVLinkProfile, batch: HistoricalOddsBatch) -> str:
    """Hash fixed policy without treating generated execution settings as policy."""
    payload = {
        "first_year": batch.first_year,
        "last_year": batch.last_year,
        "years_per_run": batch.years_per_run,
        "frontier": str(batch.accept_existing_gaps_through),
        "race_start_date": str(profile.race_start_date),
        "data_specs": sorted(profile.realtime_data_specs),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


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
        races = tuple(_race_key_from_row(row) for row in rows)
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
                key = _race_key_from_row(tuple(row[:6]))
                counts[(key.race_id, spec)] = row[6]
    return RawSnapshot(races, counts, schemas)


class ProgressLedger:
    """Own versioned weekly state, transactions, and reproducible derived reports."""

    def __init__(
        self, path: Path, raw_db: Path, profile: JVLinkProfile, batch: HistoricalOddsBatch
    ) -> None:
        self.path = path.expanduser().resolve()
        self.raw_db = raw_db.expanduser().resolve()
        self.profile = profile
        self.batch = batch
        self.policy_hash = policy_hash(profile, batch)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path)) as database, database:
            database.execute("BEGIN IMMEDIATE")
            _ensure_api_result_columns(database)
            yield database
            database.execute(
                "UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='state_revision'"
            )

    def bootstrap(self, snapshot: RawSnapshot, now: datetime) -> None:
        """Freeze initial candidates and accept only initial frontier gaps."""
        if self.path.exists():
            raise AcquisitionBlocked("existing ledger must be validated, never reinitialized")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as database, database:
            database.executescript("""
                PRAGMA user_version=1;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE race_specs (
                    race_id TEXT NOT NULL, data_spec TEXT NOT NULL, year INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending','running','acquired','provider_missing','failed')),
                    reason TEXT NOT NULL, last_run TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                    before_rows INTEGER NOT NULL DEFAULT 0, after_rows INTEGER NOT NULL DEFAULT 0,
                    requested_at TEXT, updated_at TEXT NOT NULL, returncode INTEGER,
                    api_name TEXT, api_returncode INTEGER,
                    PRIMARY KEY(race_id, data_spec));
                CREATE TABLE years (year INTEGER PRIMARY KEY, publication TEXT NOT NULL, snapshot_id TEXT);
                CREATE TABLE runs (run_id TEXT PRIMARY KEY, year INTEGER, cutoff TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                    candidate_hash TEXT NOT NULL, report TEXT NOT NULL, quarantine TEXT NOT NULL DEFAULT '[]');
            """)
            metadata = {
                "schema_version": "1",
                "state_revision": "1",
                "raw_db": canonical_path(self.raw_db),
                "policy_hash": self.policy_hash,
                "frontier": str(self.batch.accept_existing_gaps_through),
                "bootstrap_at": now.isoformat(),
                "bootstrap_candidate_hash": candidate_hash(snapshot.races),
                "bootstrap_reason": "user_accepted_existing_gaps",
                "recovery_required": "false",
                "archive_schemas": json.dumps(snapshot.schemas, sort_keys=True),
            }
            database.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
            frontier_year = self.batch.accept_existing_gaps_through.race_date.year
            managed_years = {
                key.race_date.year for key in snapshot.races if key.race_date.year >= frontier_year
            }
            for year in range(self.batch.first_year, self.batch.last_year + 1):
                publication = (
                    "pending"
                    if year in managed_years
                    else ("baseline" if year < frontier_year else "published")
                )
                database.execute("INSERT INTO years VALUES (?,?,NULL)", (year, publication))
            for key in snapshot.races:
                for spec in sorted(self.profile.realtime_data_specs):
                    count = snapshot.counts.get((key.race_id, spec), 0)
                    if count:
                        state, reason = "acquired", "initial_archive_observed"
                    elif key <= self.batch.accept_existing_gaps_through:
                        state, reason = "provider_missing", "user_accepted_existing_gaps"
                    else:
                        state, reason = "pending", "unrequested"
                    database.execute(
                        "INSERT INTO race_specs (race_id,data_spec,year,state,reason,before_rows,after_rows,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            key.race_id,
                            spec,
                            key.race_date.year,
                            state,
                            reason,
                            count,
                            count,
                            now.isoformat(),
                        ),
                    )

    def read(self) -> tuple[dict[tuple[str, str], SpecState], dict[int, str], int]:
        """Validate ledger ownership and return its committed states."""
        with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)) as database:
            database.execute("BEGIN")
            metadata = dict(database.execute("SELECT key,value FROM metadata"))
            if (
                database.execute("PRAGMA user_version").fetchone()[0] != 1
                or metadata.get("schema_version") != "1"
            ):
                raise AcquisitionBlocked("unsupported progress ledger schema version")
            if (
                metadata.get("raw_db") != canonical_path(self.raw_db)
                or metadata.get("policy_hash") != self.policy_hash
            ):
                raise AcquisitionBlocked(
                    "progress ledger raw database or policy differs; explicit migration is required"
                )
            if metadata.get("recovery_required") != "false":
                raise AcquisitionBlocked("staging recovery is incomplete")
            states: dict[tuple[str, str], SpecState] = {}
            race_spec_columns = {
                row[1] for row in database.execute("PRAGMA table_info(race_specs)")
            }
            has_api_columns = {"api_name", "api_returncode"} <= race_spec_columns
            api_columns = ",api_name,api_returncode" if has_api_columns else ",NULL,NULL"
            for row in database.execute(
                "SELECT race_id,data_spec,state,reason,before_rows,after_rows,attempts"
                f"{api_columns} FROM race_specs"
            ):
                key = race_key_from_id(row[0])
                if (
                    key.jyo_code not in {f"{code:02d}" for code in range(1, 11)}
                    or not self.batch.first_year <= key.race_date.year <= self.batch.last_year
                ):
                    raise AcquisitionBlocked("progress ledger race lies outside the policy")
                if (
                    row[1] not in self.profile.realtime_data_specs
                    or row[2] not in STATE_REASONS
                    or row[3] not in STATE_REASONS[row[2]]
                ):
                    raise AcquisitionBlocked("unsupported or unresolved race/spec state")
                _validate_api_observation(
                    row[2], row[3], row[7], row[8], allow_legacy_no_data=not has_api_columns
                )
                if any(type(value) is not int or value < 0 for value in row[4:7]):
                    raise AcquisitionBlocked("invalid progress row counts")
                states[(row[0], row[1])] = SpecState(*row[:7])
            years = dict(database.execute("SELECT year,publication FROM years"))
            if set(years) != set(range(self.batch.first_year, self.batch.last_year + 1)) or not set(
                years.values()
            ) <= {"baseline", "published", "pending", "failed"}:
                raise AcquisitionBlocked("invalid publication year states")
            revision = int(metadata["state_revision"])
            if revision < 1:
                raise AcquisitionBlocked("invalid ledger revision")
        return states, years, revision

    def running_requests(self) -> tuple[tuple[str, RaceKey, frozenset[str]], ...]:
        """Return unresolved requests for an explicit operator recovery."""
        if not self.path.is_file():
            return ()
        try:
            with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)) as database:
                if database.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise AcquisitionBlocked("unsupported progress ledger schema version")
                metadata = dict(database.execute("SELECT key,value FROM metadata"))
                if metadata.get("schema_version") != "1":
                    raise AcquisitionBlocked("unsupported progress ledger schema version")
                if (
                    metadata.get("raw_db") != canonical_path(self.raw_db)
                    or metadata.get("policy_hash") != self.policy_hash
                ):
                    raise AcquisitionBlocked("progress ledger raw database or policy differs")
                if metadata.get("recovery_required") != "true":
                    raise AcquisitionBlocked("no unresolved progress recovery is recorded")
                try:
                    archive_schemas = json.loads(metadata["archive_schemas"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise AcquisitionBlocked("invalid progress archive schema metadata") from exc
                if not isinstance(archive_schemas, dict) or not all(
                    isinstance(spec, str) and isinstance(schema, str)
                    for spec, schema in archive_schemas.items()
                ):
                    raise AcquisitionBlocked("invalid progress archive schema metadata")
                grouped: dict[tuple[str, str], set[str]] = {}
                race_spec_columns = {
                    row[1] for row in database.execute("PRAGMA table_info(race_specs)")
                }
                has_api_columns = {"api_name", "api_returncode"} <= race_spec_columns
                api_columns = ",api_name,api_returncode" if has_api_columns else ",NULL,NULL"
                for row in database.execute(
                    "SELECT last_run,race_id,data_spec,state,reason,before_rows,after_rows,attempts"
                    f"{api_columns} FROM race_specs"
                ):
                    run_id, race_id, data_spec, state, reason = row[:5]
                    counts = row[5:8]
                    key = race_key_from_id(race_id)
                    if (
                        key.jyo_code not in {f"{code:02d}" for code in range(1, 11)}
                        or not self.batch.first_year <= key.race_date.year <= self.batch.last_year
                        or data_spec not in self.profile.realtime_data_specs
                        or state not in STATE_REASONS
                        or reason not in STATE_REASONS[state]
                        or any(type(value) is not int or value < 0 for value in counts)
                    ):
                        raise AcquisitionBlocked("invalid progress ledger state")
                    _validate_api_observation(
                        state,
                        reason,
                        row[8],
                        row[9],
                        allow_legacy_no_data=not has_api_columns,
                    )
                    if state == "running":
                        if not isinstance(run_id, str) or not run_id:
                            raise AcquisitionBlocked("running progress row has no run id")
                        grouped.setdefault((run_id, race_id), set()).add(data_spec)
                years = dict(database.execute("SELECT year,publication FROM years"))
                if set(years) != set(
                    range(self.batch.first_year, self.batch.last_year + 1)
                ) or not set(years.values()) <= {"baseline", "published", "pending", "failed"}:
                    raise AcquisitionBlocked("invalid publication year states")
                for run_id, _ in grouped:
                    if not database.execute(
                        "SELECT 1 FROM runs WHERE run_id=?", (run_id,)
                    ).fetchone():
                        raise AcquisitionBlocked("running progress row refers to an unknown run")
        except sqlite3.DatabaseError as exc:
            raise AcquisitionBlocked("progress ledger is incomplete or invalid") from exc
        return tuple(
            (run_id, race_key_from_id(race_id), frozenset(specs))
            for (run_id, race_id), specs in grouped.items()
        )

    def recover_running(
        self,
        key: RaceKey,
        specs: frozenset[str],
        now: datetime,
        acquired_counts: dict[str, int] | None = None,
    ) -> None:
        """Resolve quarantined requests from an observed archive commit or failure."""
        counts = acquired_counts or {}
        with self._transaction() as database:
            for spec in specs:
                before_row = database.execute(
                    "SELECT before_rows FROM race_specs WHERE race_id=? AND data_spec=? "
                    "AND state='running'",
                    (key.race_id, spec),
                ).fetchone()
                if before_row is None:
                    continue
                after_rows = counts.get(spec, 0)
                if after_rows > before_row[0]:
                    state, reason = "acquired", "recovered_archive_commit"
                else:
                    state, reason = "failed", "recovered_unconfirmed"
                database.execute(
                    "UPDATE race_specs SET state=?,reason=?,after_rows=?,updated_at=?,returncode=NULL,api_name=NULL,api_returncode=NULL "
                    "WHERE race_id=? AND data_spec=? AND state='running'",
                    (state, reason, after_rows, now.isoformat(), key.race_id, spec),
                )
                if state == "acquired":
                    database.execute(
                        "UPDATE years SET publication='pending' WHERE year=?",
                        (key.race_date.year,),
                    )
            unresolved = database.execute(
                "SELECT 1 FROM race_specs WHERE state='running' LIMIT 1"
            ).fetchone()
            database.execute(
                "UPDATE metadata SET value=? WHERE key='recovery_required'",
                ("true" if unresolved else "false",),
            )

    def reconcile(self, snapshot: RawSnapshot, now: datetime) -> dict[str, int]:
        """Adopt external archive additions and refuse loss of acquired data."""
        states, _, _ = self.read()
        proposed, changed_years, adopted = reconcile_states(
            states, snapshot, self.profile.realtime_data_specs
        )
        with self._transaction() as database:
            metadata = dict(database.execute("SELECT key,value FROM metadata"))
            prior_schemas = json.loads(metadata["archive_schemas"])
            if any(snapshot.schemas.get(spec) != schema for spec, schema in prior_schemas.items()):
                raise AcquisitionBlocked("archive schema disappeared or changed")
            for pair, entry in proposed.items():
                if entry == states.get(pair):
                    continue
                year = race_key_from_id(entry.race_id).race_date.year
                database.execute(
                    "INSERT INTO race_specs (race_id,data_spec,year,state,reason,before_rows,after_rows,attempts,updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(race_id,data_spec) DO UPDATE SET state=excluded.state,reason=excluded.reason,before_rows=excluded.before_rows,after_rows=excluded.after_rows,updated_at=excluded.updated_at",
                    (
                        entry.race_id,
                        entry.data_spec,
                        year,
                        entry.state,
                        entry.reason,
                        entry.before_rows,
                        entry.after_rows,
                        entry.attempts,
                        now.isoformat(),
                    ),
                )
            for year in changed_years:
                database.execute("UPDATE years SET publication='pending' WHERE year=?", (year,))
            database.execute(
                "UPDATE metadata SET value=? WHERE key='archive_schemas'",
                (json.dumps(snapshot.schemas, sort_keys=True),),
            )
        return adopted

    def start_run(
        self,
        run_id: str,
        year: int | None,
        cutoff: date,
        now: datetime,
        races: tuple[RaceKey, ...],
        report: dict[str, object],
    ) -> None:
        """Persist the fixed run envelope before any external request."""
        with self._transaction() as database:
            database.execute(
                "INSERT INTO runs (run_id,year,cutoff,started_at,status,candidate_hash,report) VALUES (?,?,?,?,?,?,?)",
                (
                    run_id,
                    year,
                    cutoff.isoformat(),
                    now.isoformat(),
                    "running",
                    candidate_hash(races),
                    json.dumps(report, sort_keys=True),
                ),
            )

    def request(
        self,
        run_id: str,
        key: RaceKey,
        specs: frozenset[str],
        counts: dict[str, int],
        now: datetime,
    ) -> None:
        """Commit write-ahead running state and pre-request archive counts."""
        with self._transaction() as database:
            for spec in specs:
                cursor = database.execute(
                    "UPDATE race_specs SET state='running',reason='request_started',last_run=?,attempts=attempts+1,before_rows=?,after_rows=?,requested_at=?,updated_at=?,returncode=NULL,api_name=NULL,api_returncode=NULL WHERE race_id=? AND data_spec=? AND state IN ('pending','failed')",
                    (
                        run_id,
                        counts[spec],
                        counts[spec],
                        now.isoformat(),
                        now.isoformat(),
                        key.race_id,
                        spec,
                    ),
                )
                if cursor.rowcount != 1:
                    raise AcquisitionBlocked("request no longer matches an eligible ledger state")
            database.execute("UPDATE metadata SET value='true' WHERE key='recovery_required'")

    def finish_request(
        self,
        key: RaceKey,
        results: dict[str, tuple[str, str, int]],
        now: datetime,
        *,
        recovered: bool,
        returncode: int | None = None,
        api_results: dict[str, tuple[str, int]] | None = None,
    ) -> None:
        """Confirm results while retaining process and DataSpec API return codes."""
        with self._transaction() as database:
            for spec, (state, reason, after) in results.items():
                if state not in STATE_REASONS or reason not in STATE_REASONS[state]:
                    raise ValueError(f"unsupported state/reason pair: {state}/{reason}")
                api_result = api_results.get(spec) if api_results is not None else None
                _validate_api_observation(
                    state,
                    reason,
                    api_result[0] if api_result else None,
                    api_result[1] if api_result else None,
                )
                database.execute(
                    "UPDATE race_specs SET state=?,reason=?,after_rows=?,updated_at=?,returncode=?,api_name=?,api_returncode=? WHERE race_id=? AND data_spec=? AND state='running'",
                    (
                        state,
                        reason,
                        after,
                        now.isoformat(),
                        returncode,
                        api_result[0] if api_result else None,
                        api_result[1] if api_result else None,
                        key.race_id,
                        spec,
                    ),
                )
                if state == "acquired":
                    database.execute(
                        "UPDATE years SET publication='pending' WHERE year=?", (key.race_date.year,)
                    )
            database.execute(
                "UPDATE metadata SET value=? WHERE key='recovery_required'",
                ("false" if recovered else "true",),
            )

    def confirm_provider_missing(
        self,
        key: RaceKey,
        specs: frozenset[str],
        now: datetime,
        archive_counts: dict[str, int],
    ) -> None:
        """Promote explicitly verified empty responses to provider-side gaps."""
        # Validate ledger ownership and schema before allowing a terminal-state change.
        if not self.path.is_file():
            raise AcquisitionBlocked("provider-missing confirmation requires an existing ledger")
        self.read()
        if not specs or not specs <= self.profile.realtime_data_specs:
            raise ValueError("provider-missing confirmation contains unsupported DataSpecs")
        if any(archive_counts.get(spec, 0) != 0 for spec in specs):
            raise AcquisitionBlocked("provider-missing confirmation conflicts with archive rows")
        with self._transaction() as database:
            rows = {
                spec: database.execute(
                    "SELECT state,reason FROM race_specs WHERE race_id=? AND data_spec=?",
                    (key.race_id, spec),
                ).fetchone()
                for spec in specs
            }
            if any(row is None for row in rows.values()):
                raise AcquisitionBlocked("provider-missing confirmation targets an unknown race")
            if any(
                row[0] != "failed" or row[1] != "empty_response_unverified"
                for row in rows.values()
                if row is not None
            ):
                raise AcquisitionBlocked(
                    "provider-missing confirmation requires empty-response failures"
                )
            for spec in specs:
                database.execute(
                    "UPDATE race_specs SET state='provider_missing',reason='provider_confirmed_missing',"
                    "after_rows=0,updated_at=? WHERE race_id=? AND data_spec=? AND state='failed' "
                    "AND reason='empty_response_unverified'",
                    (now.isoformat(), key.race_id, spec),
                )
            database.execute(
                "UPDATE years SET publication='pending' WHERE year=?", (key.race_date.year,)
            )

    def record_quarantine(self, run_id: str, artifacts: list[dict[str, object]]) -> None:
        """Retain immutable staging evidence without counting it as acquired data."""
        with self._transaction() as database:
            prior = json.loads(
                database.execute(
                    "SELECT quarantine FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()[0]
            )
            database.execute(
                "UPDATE runs SET quarantine=? WHERE run_id=?",
                (json.dumps(prior + artifacts, sort_keys=True), run_id),
            )

    def publication(self, year: int, state: str, snapshot_id: str | None = None) -> None:
        """Record preprocessing independently of raw acquisition outcomes."""
        if state not in {"published", "failed"}:
            raise ValueError("invalid publication outcome")
        with self._transaction() as database:
            database.execute(
                "UPDATE years SET publication=?,snapshot_id=? WHERE year=?",
                (state, snapshot_id, year),
            )

    def finish_run(self, run_id: str, report: dict[str, object], now: datetime) -> None:
        """Persist final metrics before regenerating derived files."""
        with self._transaction() as database:
            database.execute(
                "UPDATE runs SET finished_at=?,status=?,report=? WHERE run_id=?",
                (now.isoformat(), report["status"], json.dumps(report, sort_keys=True), run_id),
            )


def reconcile_states(
    states: dict[tuple[str, str], SpecState], snapshot: RawSnapshot, specs: frozenset[str]
) -> tuple[dict[tuple[str, str], SpecState], set[int], dict[str, int]]:
    """Compute reconciliation without writes, including previews."""
    candidate_pairs = {(key.race_id, spec) for key in snapshot.races for spec in specs}
    if states.keys() - candidate_pairs:
        raise AcquisitionBlocked("previously managed race candidates disappeared")
    proposed = dict(states)
    changed_years: set[int] = set()
    adopted = dict.fromkeys(sorted(specs), 0)
    for key in snapshot.races:
        for spec in specs:
            pair = (key.race_id, spec)
            prior = states.get(pair)
            count = snapshot.counts.get(pair, 0)
            if (
                prior is not None
                and prior.state == "acquired"
                and (count == 0 or count < prior.after_rows)
            ):
                raise AcquisitionBlocked(f"acquired archive rows disappeared: {key}/{spec}")
            if count and (prior is None or prior.state != "acquired" or count > prior.after_rows):
                entry = SpecState(
                    key.race_id,
                    spec,
                    "acquired",
                    "external_archive_observed",
                    count,
                    count,
                    prior.attempts if prior else 0,
                )
                adopted[spec] += 1
            elif prior is None:
                entry = SpecState(key.race_id, spec, "pending", "new_candidate", 0, 0)
            else:
                entry = prior
            proposed[pair] = entry
            if entry != prior:
                changed_years.add(key.race_date.year)
    return proposed, changed_years, adopted


def candidate_hash(races: tuple[RaceKey, ...]) -> str:
    """Identify the exact sorted candidate set fixed for a run."""
    return hashlib.sha256("\n".join(key.race_id for key in races).encode()).hexdigest()


def atomic_write(path: Path, content: str) -> None:
    """Replace one derived artifact after its complete contents are durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _ensure_api_result_columns(database: sqlite3.Connection) -> None:
    """Add API-result columns to a v1 ledger without changing process returncodes."""
    columns = {row[1] for row in database.execute("PRAGMA table_info(race_specs)")}
    needs_migration = "api_name" not in columns or "api_returncode" not in columns
    if "api_name" not in columns:
        database.execute("ALTER TABLE race_specs ADD COLUMN api_name TEXT")
    if "api_returncode" not in columns:
        database.execute("ALTER TABLE race_specs ADD COLUMN api_returncode INTEGER")
    if needs_migration:
        database.execute(
            "UPDATE race_specs SET reason='legacy_provider_missing' "
            "WHERE state='provider_missing' AND reason='jvopen_no_data'"
        )


def _validate_api_observation(
    state: str,
    reason: str,
    api_name: str | None,
    api_returncode: int | None,
    *,
    allow_legacy_no_data: bool = False,
) -> None:
    """Require API evidence whenever a reason claims JVOpen found no data."""
    if (api_name is None) != (api_returncode is None):
        raise AcquisitionBlocked("incomplete API return observation")
    if api_name is not None and api_name not in API_NAMES:
        raise AcquisitionBlocked("unsupported API return observation")
    if api_returncode is not None and type(api_returncode) is not int:
        raise AcquisitionBlocked("invalid API return code")
    if (
        state == "provider_missing"
        and reason == "jvopen_no_data"
        and (api_name not in NO_DATA_API_NAMES or api_returncode != -1)
    ):
        if allow_legacy_no_data and api_name is None and api_returncode is None:
            return
        raise AcquisitionBlocked("provider-missing state lacks JVOpen/JVRTOpen -1 evidence")
