"""Run the local JVLinkToSQLite executable for race-data acquisition."""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class JVLinkExecutionResult:
    """Return values reported by JV-Link for each requested DataSpec."""

    api_returncodes: dict[str, int]
    no_data_specs: frozenset[str] = frozenset()
    fatal_specs: frozenset[str] = frozenset()
    api_results: dict[str, tuple[str, int]] = field(default_factory=dict)
    open_returncodes: dict[str, int] = field(default_factory=dict)
    fatal_returncodes: dict[str, int] = field(default_factory=dict)
    process_returncode: int | None = None


class JVLinkToSQLiteError(RuntimeError):
    """Report a failure while invoking JVLinkToSQLite."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        api_returncodes: dict[str, int] | None = None,
        fatal_returncodes: dict[str, int] | None = None,
        api_results: dict[str, tuple[str, int]] | None = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.api_returncodes = api_returncodes or {}
        self.fatal_returncodes = fatal_returncodes or {}
        self.api_results = api_results or {}


_API_RETURNCODE = re.compile(
    r"\[(?P<api>JVOpen|JVRTOpen|JVStatus|JVRead|JVGets)\][^\r\n]*?"
    r"RC=(?P<code>-?\d+)\s*\((?P<data_spec>0B\d{2})\s*,"
)


@dataclass(frozen=True)
class _ParsedApiResults:
    latest: dict[str, tuple[str, int]]
    open_returncodes: dict[str, int]
    fatal_returncodes: dict[str, int]
    no_data_specs: frozenset[str]
    fatal_specs: frozenset[str]


def _parse_api_returncodes(
    *outputs: str | bytes | None,
) -> _ParsedApiResults:
    """Extract API return codes and their terminal classifications."""
    latest: dict[str, tuple[str, int]] = {}
    open_returncodes: dict[str, int] = {}
    for output in outputs:
        if output is None:
            continue
        text = output.decode(errors="replace") if isinstance(output, bytes) else output
        for match in _API_RETURNCODE.finditer(text):
            data_spec = match.group("data_spec")
            api = match.group("api")
            code = int(match.group("code"))
            latest[data_spec] = (api, code)
            if api in {"JVOpen", "JVRTOpen"}:
                open_returncodes[data_spec] = code
    no_data_specs = {
        spec for spec, (api, code) in latest.items() if api in {"JVOpen", "JVRTOpen"} and code == -1
    }
    fatal_returncodes = {
        spec: code
        for spec, (api, code) in latest.items()
        if code < 0
        and not (api in {"JVRead", "JVGets"} and code in {-1, -3})
        and not (api in {"JVOpen", "JVRTOpen"} and code == -1)
    }
    return _ParsedApiResults(
        latest,
        open_returncodes,
        fatal_returncodes,
        frozenset(no_data_specs),
        frozenset(fatal_returncodes),
    )


def _echo_output(output: str | bytes | None, *, error: bool = False) -> None:
    """Preserve the executable's console output after capturing it for parsing."""
    if output is None:
        return
    text = output.decode(errors="replace") if isinstance(output, bytes) else output
    stream = sys.stderr if error else sys.stdout
    print(text, end="" if text.endswith(("\n", "\r")) else "\n", file=stream)


class JVLinkToSQLiteRunner:
    """Represent one configured local JVLinkToSQLite process boundary."""

    def __init__(
        self,
        executable: Path,
        database: Path,
        *,
        timeout_seconds: float | None = None,
        validate_executable: bool = True,
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
        self._executable = (
            _resolve_existing_file(executable, "JVLinkToSQLite executable")
            if validate_executable
            else executable.expanduser().resolve()
        )
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

    def execute(
        self, setting: Path, *, skip_last_modified_update: bool = False
    ) -> JVLinkExecutionResult:
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
                with a non-zero status. Any DataSpec-specific JV-Link return
                codes observed before the failure are attached to the exception.
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
            completed = subprocess.run(
                command,
                cwd=self._executable.parent,
                check=True,
                encoding="cp932",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=self._timeout_seconds,
                shell=False,
                text=True,
            )
            _echo_output(completed.stdout)
            parsed = _parse_api_returncodes(completed.stdout)
            return JVLinkExecutionResult(
                {spec: code for spec, (_, code) in parsed.latest.items()},
                parsed.no_data_specs,
                parsed.fatal_specs,
                parsed.latest,
                parsed.open_returncodes,
                parsed.fatal_returncodes,
                completed.returncode,
            )
        except subprocess.TimeoutExpired as exc:
            _echo_output(exc.stdout)
            parsed = _parse_api_returncodes(exc.stdout)
            raise JVLinkToSQLiteError(
                f"JVLinkToSQLite timed out after {self._timeout_seconds} seconds",
                api_returncodes={spec: code for spec, (_, code) in parsed.latest.items()},
                fatal_returncodes=parsed.fatal_returncodes,
                api_results=parsed.latest,
            ) from exc
        except subprocess.CalledProcessError as exc:
            _echo_output(exc.stdout)
            parsed = _parse_api_returncodes(exc.stdout)
            raise JVLinkToSQLiteError(
                f"JVLinkToSQLite exited with status {exc.returncode}",
                returncode=exc.returncode,
                api_returncodes={spec: code for spec, (_, code) in parsed.latest.items()},
                fatal_returncodes=parsed.fatal_returncodes,
                api_results=parsed.latest,
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
