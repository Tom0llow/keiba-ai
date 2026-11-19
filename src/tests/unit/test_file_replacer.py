"""Tests for exclusive creation and checked atomic replacement of small files."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from data.storage import file_replacer
from data.storage.file_replacer import create_file, replace_file_if_unchanged


def _leftovers(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if path.name.endswith(".tmp"))


def test_create_file_writes_a_new_file_and_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"

    create_file(path, b"one\n")

    assert path.read_bytes() == b"one\n"
    with pytest.raises(FileExistsError):
        create_file(path, b"two\n")
    assert path.read_bytes() == b"one\n"


def test_create_file_removes_a_partly_written_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"

    with (
        patch("data.storage.file_replacer.os.fsync", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        create_file(path, b"one\n")

    assert not path.exists()


def test_replace_file_if_unchanged_replaces_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"old\n")

    replace_file_if_unchanged(path, b"old\nnew\n", expected=b"old\n")

    assert path.read_bytes() == b"old\nnew\n"
    assert _leftovers(tmp_path) == []


def test_a_file_changed_before_replacement_is_left_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"changed\n")

    with pytest.raises(ValueError, match="changed"):
        replace_file_if_unchanged(path, b"new\n", expected=b"old\n")

    assert path.read_bytes() == b"changed\n"
    assert _leftovers(tmp_path) == []


def test_the_check_reads_the_file_just_before_replacing(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"old\n")

    with (
        patch.object(file_replacer, "_current_bytes", return_value=b"someone else\n"),
        pytest.raises(ValueError, match="changed"),
    ):
        replace_file_if_unchanged(path, b"new\n", expected=b"old\n")

    assert path.read_bytes() == b"old\n"


def test_a_refused_replacement_is_retried_then_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"old\n")
    real_replace = os.replace
    calls: list[int] = []

    def flaky(source: Path, target: Path) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("locked by a reader")
        real_replace(source, target)

    with (
        patch("data.storage.file_replacer.os.replace", side_effect=flaky),
        patch("data.storage.file_replacer.time.sleep") as sleep,
    ):
        replace_file_if_unchanged(path, b"new\n", expected=b"old\n")

    assert path.read_bytes() == b"new\n"
    assert len(calls) == 3
    assert sleep.call_count == 2


def test_every_refused_replacement_fails_without_changing_the_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"old\n")

    with (
        patch(
            "data.storage.file_replacer.os.replace", side_effect=PermissionError("locked")
        ) as replace,
        patch("data.storage.file_replacer.time.sleep"),
        pytest.raises(PermissionError),
    ):
        replace_file_if_unchanged(path, b"new\n", expected=b"old\n")

    assert replace.call_count == 20
    assert path.read_bytes() == b"old\n"
    assert _leftovers(tmp_path) == []


def test_an_interrupted_replacement_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"old\n")

    with (
        patch("data.storage.file_replacer.os.replace", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        replace_file_if_unchanged(path, b"new\n", expected=b"old\n")

    assert path.read_bytes() == b"old\n"
    assert _leftovers(tmp_path) == []


def test_a_change_during_the_retries_stops_the_replacement(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"old\n")

    def refuse_then_change(source: Path, target: Path) -> None:
        path.write_bytes(b"other writer\n")
        raise PermissionError("locked by a reader")

    with (
        patch("data.storage.file_replacer.os.replace", side_effect=refuse_then_change) as replace,
        patch("data.storage.file_replacer.time.sleep"),
        pytest.raises(ValueError, match="changed"),
    ):
        replace_file_if_unchanged(path, b"new\n", expected=b"old\n")

    assert replace.call_count == 1
    assert path.read_bytes() == b"other writer\n"
    assert _leftovers(tmp_path) == []
