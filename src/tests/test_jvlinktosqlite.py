"""Tests for the local JVLinkToSQLite subprocess boundary."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from data.retriever.jvlinktosqlite import JVLinkToSQLiteError, JVLinkToSQLiteRunner


def _create_runner_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    executable = tmp_path / "JVLinkToSQLite.exe"
    executable.write_bytes(b"")
    setting = tmp_path / "setting.xml"
    setting.write_text("<setting />", encoding="utf-8")
    database = tmp_path / "race.db"
    return executable, setting, database


@pytest.mark.parametrize(
    ("skip_last_modified_update", "expected_suffix"),
    [
        (False, []),
        (True, ["--skipslastmodifiedupdate"]),
    ],
)
def test_execute_invokes_exec_mode_without_shell(
    tmp_path: Path,
    skip_last_modified_update: bool,
    expected_suffix: list[str],
) -> None:
    executable, setting, database = _create_runner_files(tmp_path)
    runner = JVLinkToSQLiteRunner(executable, database)

    with patch("data.retriever.jvlinktosqlite.subprocess.run") as run:
        runner.execute(setting, skip_last_modified_update=skip_last_modified_update)

    run.assert_called_once_with(
        [
            str(executable.resolve()),
            "main",
            "--mode",
            "Exec",
            "--datasource",
            str(database.resolve()),
            "--setting",
            str(setting.resolve()),
            *expected_suffix,
        ],
        cwd=executable.resolve().parent,
        check=True,
        timeout=None,
        shell=False,
    )


def test_execute_translates_nonzero_exit_status(tmp_path: Path) -> None:
    executable, setting, database = _create_runner_files(tmp_path)
    runner = JVLinkToSQLiteRunner(executable, database)

    with patch("data.retriever.jvlinktosqlite.subprocess.run") as run:
        run.side_effect = subprocess.CalledProcessError(7, [str(executable)])
        with pytest.raises(JVLinkToSQLiteError, match="status 7") as exc_info:
            runner.execute(setting)

    assert exc_info.value.returncode == 7


def test_execute_translates_timeout(tmp_path: Path) -> None:
    executable, setting, database = _create_runner_files(tmp_path)
    runner = JVLinkToSQLiteRunner(executable, database, timeout_seconds=30.0)

    with patch("data.retriever.jvlinktosqlite.subprocess.run") as run:
        run.side_effect = subprocess.TimeoutExpired([str(executable)], 30.0)
        with pytest.raises(JVLinkToSQLiteError, match=r"timed out after 30\.0 seconds"):
            runner.execute(setting)


def test_missing_setting_is_rejected_before_process_start(tmp_path: Path) -> None:
    executable, _, database = _create_runner_files(tmp_path)
    runner = JVLinkToSQLiteRunner(executable, database)
    missing_setting = tmp_path / "missing.xml"

    with (
        patch("data.retriever.jvlinktosqlite.subprocess.run") as run,
        pytest.raises(FileNotFoundError, match="setting file does not exist"),
    ):
        runner.execute(missing_setting)

    run.assert_not_called()


def test_missing_executable_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "race.db"

    with pytest.raises(FileNotFoundError, match="executable does not exist"):
        JVLinkToSQLiteRunner(tmp_path / "missing.exe", database)


def test_database_parent_must_exist(tmp_path: Path) -> None:
    executable = tmp_path / "JVLinkToSQLite.exe"
    executable.write_bytes(b"")

    with pytest.raises(FileNotFoundError, match="database parent directory does not exist"):
        JVLinkToSQLiteRunner(executable, tmp_path / "missing" / "race.db")


@pytest.mark.parametrize("timeout_seconds", [0.0, -1.0])
def test_timeout_must_be_positive(tmp_path: Path, timeout_seconds: float) -> None:
    executable, _, database = _create_runner_files(tmp_path)

    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        JVLinkToSQLiteRunner(executable, database, timeout_seconds=timeout_seconds)


def test_assert_not_running_uses_tasklist_csv(tmp_path: Path) -> None:
    executable, _, database = _create_runner_files(tmp_path)
    runner = JVLinkToSQLiteRunner(executable, database)

    with (
        patch("data.retriever.jvlinktosqlite.os.name", "nt"),
        patch("data.retriever.jvlinktosqlite.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(
            ["tasklist"], 0, '"other.exe","1","Console","1","1 K"\n', ""
        )
        runner.assert_not_running()

    run.assert_called_once_with(
        ["tasklist", "/FI", "IMAGENAME eq JVLinkToSQLite.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def test_assert_not_running_rejects_matching_process(tmp_path: Path) -> None:
    executable, _, database = _create_runner_files(tmp_path)
    runner = JVLinkToSQLiteRunner(executable, database)

    with (
        patch("data.retriever.jvlinktosqlite.os.name", "nt"),
        patch("data.retriever.jvlinktosqlite.subprocess.run") as run,
    ):
        run.return_value = subprocess.CompletedProcess(
            ["tasklist"], 0, '"JVLinkToSQLite.exe","1","Console","1","1 K"\n', ""
        )
        with pytest.raises(JVLinkToSQLiteError, match="still running"):
            runner.assert_not_running()
