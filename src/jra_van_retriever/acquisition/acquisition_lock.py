"""Serialize application acquisition and bind one raw database to its ledger."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import TracebackType
from typing import BinaryIO


class AcquisitionBlocked(RuntimeError):
    """Refuse acquisition while another writer or unresolved request exists."""


def canonical_path(path: Path) -> str:
    """Return the canonical local path used in acquisition bindings."""
    return os.path.normcase(str(path.expanduser().resolve()))


def check_unresolved(ledger: Path) -> None:
    """Reject unconfirmed executions without changing the progress database."""
    if not ledger.exists():
        return
    with closing(sqlite3.connect(f"{ledger.resolve().as_uri()}?mode=ro", uri=True)) as database:
        if database.execute("SELECT 1 FROM race_specs WHERE state = 'running' LIMIT 1").fetchone():
            raise AcquisitionBlocked(
                "unresolved running request; verify the child process and recover staging first"
            )
        row = database.execute(
            "SELECT value FROM metadata WHERE key = 'recovery_required'"
        ).fetchone()
        if row is None or row[0] != "false":
            raise AcquisitionBlocked(
                "unquarantined staging or invalid recovery state; acquisition is blocked"
            )


class AcquisitionLock:
    """Hold a nonblocking OS lock released automatically on process termination."""

    def __init__(self, raw_db: Path, ledger: Path, *, allow_unresolved: bool = False) -> None:
        self.raw_db = raw_db.expanduser().resolve()
        self.ledger = ledger.expanduser().resolve()
        self.allow_unresolved = allow_unresolved
        self.path = Path(f"{self.raw_db}.acquisition.lock")
        self._file: BinaryIO | None = None

    def __enter__(self) -> AcquisitionLock:
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        self._file = os.fdopen(descriptor, "r+b")
        try:
            if self._file.seek(0, os.SEEK_END) == 0:
                self._file.write(b"\0")
                self._file.flush()
            self._file.seek(0)
            _lock(self._file)
        except OSError as exc:
            self._file.close()
            self._file = None
            raise AcquisitionBlocked(
                "another acquisition process holds the raw database lock"
            ) from exc
        try:
            self._file.seek(1)
            content = self._file.read()
            if content:
                try:
                    self._validate_binding(json.loads(content))
                except (TypeError, ValueError) as exc:
                    raise AcquisitionBlocked("raw database lock binding is invalid") from exc
            if not self.allow_unresolved:
                try:
                    check_unresolved(self.ledger)
                except sqlite3.DatabaseError as exc:
                    raise AcquisitionBlocked("progress ledger is incomplete or invalid") from exc
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _validate_binding(self, binding: object) -> None:
        expected = {"raw_db": canonical_path(self.raw_db), "ledger": canonical_path(self.ledger)}
        if binding != expected:
            raise AcquisitionBlocked(
                "raw database is bound to another ledger/runtime; use its original configuration"
            )

    def bind(self) -> None:
        """Persist the raw/ledger correspondence while retaining the OS lock."""
        if self._file is None:
            raise RuntimeError("acquisition lock is not held")
        payload = {"raw_db": canonical_path(self.raw_db), "ledger": canonical_path(self.ledger)}
        self._file.seek(1)
        self._file.write(json.dumps(payload, sort_keys=True).encode("utf-8"))
        self._file.truncate()
        self._file.flush()
        os.fsync(self._file.fileno())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is not None:
            try:
                _unlock(self._file)
            finally:
                self._file.close()
                self._file = None


def _lock(file: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(file: BinaryIO) -> None:
    file.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
