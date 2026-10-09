"""Run the local JVLinkToSQLite executable for race-data acquisition."""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path


class JVLinkToSQLiteError(RuntimeError):
    """Report a failure while invoking JVLinkToSQLite."""

    def __init__(self, message: str, *, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


class JVLinkToSQLiteRunner:
    """Represent one configured local JVLinkToSQLite process boundary."""

    def __init__(
        self,
        executable: Path,
        database: Path,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        """Configure the executable and SQLite destination used by each run.

        Args:
            executable: Path to the local JVLinkToSQLite executable.
            database: SQLite database path passed to JVLinkToSQLite. The file may
                already exist or be created by JVLinkToSQLite, but its parent
                directory must exist.
            timeout_seconds: Optional positive process timeout. ``None`` allows
                JVLinkToSQLite to run until it exits.

        Raises:
            FileNotFoundError: If the executable or database parent directory
                does not exist.
            ValueError: If the executable is not a file, the database path names
                an existing non-file, or the timeout is not positive.
        """
        self._executable = _resolve_existing_file(executable, "JVLinkToSQLite executable")
        self._database = database.expanduser().resolve()
        if not self._database.parent.is_dir():
            raise FileNotFoundError(
                f"database parent directory does not exist: {self._database.parent}"
            )
        if self._database.exists() and not self._database.is_file():
            raise ValueError(f"database path is not a file: {self._database}")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds

    def execute(self, setting: Path, *, skip_last_modified_update: bool = False) -> None:
        """Run JVLinkToSQLite once in ``Exec`` mode.

        The setting and database paths are passed as argv tokens without a shell.
        JVLinkToSQLite may update its setting file after a successful run unless
        ``skip_last_modified_update`` is true.

        Args:
            setting: Existing JVLinkToSQLite XML setting file.
            skip_last_modified_update: Pass the JVLinkToSQLite option that keeps
                the latest read-start position unchanged.

        Raises:
            FileNotFoundError: If the setting file does not exist.
            ValueError: If the setting path is not a file.
            JVLinkToSQLiteError: If the process cannot start, times out, or exits
                with a non-zero status.
        """
        setting_path = _resolve_existing_file(setting, "JVLinkToSQLite setting file")
        command = [
            str(self._executable),
            "main",
            "--mode",
            "Exec",
            "--datasource",
            str(self._database),
            "--setting",
            str(setting_path),
        ]
        if skip_last_modified_update:
            command.append("--skipslastmodifiedupdate")

        try:
            subprocess.run(
                command,
                cwd=self._executable.parent,
                check=True,
                timeout=self._timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise JVLinkToSQLiteError(
                f"JVLinkToSQLite timed out after {self._timeout_seconds} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise JVLinkToSQLiteError(
                f"JVLinkToSQLite exited with status {exc.returncode}",
                returncode=exc.returncode,
            ) from exc
        except OSError as exc:
            raise JVLinkToSQLiteError(f"failed to start JVLinkToSQLite: {exc}") from exc

    def assert_not_running(self) -> None:
        """Fail closed unless no configured JV-Link executable is still running."""
        if os.name != "nt":
            raise JVLinkToSQLiteError("cannot verify JVLinkToSQLite process on this platform")
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"IMAGENAME eq {self._executable.name}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )
        except OSError as exc:
            raise JVLinkToSQLiteError(f"failed to inspect JVLinkToSQLite process: {exc}") from exc
        if result.returncode != 0:
            raise JVLinkToSQLiteError(
                f"tasklist failed while inspecting JVLinkToSQLite: {result.returncode}"
            )
        executable_name = self._executable.name.casefold()
        for row in csv.reader(result.stdout.splitlines()):
            if row and row[0].strip().casefold() == executable_name:
                raise JVLinkToSQLiteError("JVLinkToSQLite is still running")


def _resolve_existing_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"{label} does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    return resolved
