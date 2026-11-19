"""Integration tests for ``model record-purchases`` (ADR-046), on synthetic ledgers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner, Result

from main import app
from models.betting.purchase_ledger import parse_ledger
from tests.reference_fixtures import ROOT

T0 = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)
RACE_A = "2026111505050811"
RACE_B = "2026111508050811"


def _record(ledger: Path, *options: str, at: datetime = T0) -> Result:
    with patch("cli.purchase_ledger._clock", return_value=at):
        return CliRunner().invoke(
            app, ["model", "record-purchases", "--ledger", str(ledger), *options]
        )


def _leftovers(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if path.name.endswith(".tmp"))


def test_create_records_purchases_and_a_confirmation(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"

    result = _record(
        ledger, "--create", "--bet", f"{RACE_A}:place:07:1000", "--bet", f"{RACE_A}:win:07:500"
    )

    assert result.exit_code == 0, result.output
    data = ledger.read_bytes()
    summary = json.loads(result.stdout)
    assert summary == {
        "appended": 2,
        "confirmed_at": T0.isoformat(),
        "ledger_sha256": parse_ledger(data).sha256,
        "races": {RACE_A: 1_500},
        "years": {"2026": 1_500},
    }
    parsed = parse_ledger(data)
    assert [(p.bet_type, p.stake_yen) for p in parsed.purchases] == [("place", 1_000), ("win", 500)]
    assert parsed.confirmations == (T0,)


def test_appending_keeps_earlier_lines_and_a_bare_run_only_confirms(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _record(ledger, "--create", "--bet", f"{RACE_A}:place:07:1000").exit_code == 0
    first = ledger.read_bytes()
    later = T0 + timedelta(minutes=30)

    result = _record(ledger, at=later)

    assert result.exit_code == 0, result.output
    data = ledger.read_bytes()
    assert data.startswith(first)
    assert data[len(first) :].count(b"\n") == 1
    summary = json.loads(result.stdout)
    assert (summary["appended"], summary["races"], summary["years"]) == (0, {}, {"2026": 1_000})
    assert parse_ledger(data).latest_confirmation == later
    assert _leftovers(tmp_path) == []


def test_totals_over_the_race_and_annual_budgets_are_recorded_with_warnings(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"

    result = _record(
        ledger,
        "--create",
        "--bet",
        f"{RACE_A}:win:01:5100",
        "--bet",
        f"{RACE_B}:win:01:95000",
    )

    assert result.exit_code == 0, result.output
    assert f"warning: race {RACE_A} total 5100 yen exceeds 5000 yen" in result.stderr
    assert "warning: 2026 total 100100 yen exceeds 100000 yen" in result.stderr
    assert parse_ledger(ledger.read_bytes()).annual_spent_yen(2026) == 100_100


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (["--create"], "does not exist yet"),
        (["--bet", f"{RACE_A}:place:7:1000"], "selection"),
        (["--bet", f"{RACE_A}:place:07:150"], "multiple of 100"),
    ],
)
def test_rejected_runs_leave_an_existing_ledger_unchanged(
    tmp_path: Path, options: list[str], message: str
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _record(ledger, "--create").exit_code == 0
    before = ledger.read_bytes()

    result = _record(ledger, *options, at=T0 + timedelta(minutes=1))

    assert result.exit_code == 1
    assert message in result.stderr
    assert ledger.read_bytes() == before
    assert _leftovers(tmp_path) == []


def test_a_missing_ledger_without_create_is_refused(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"

    result = _record(ledger, "--bet", f"{RACE_A}:place:07:1000")

    assert result.exit_code == 1
    assert "pass --create" in result.stderr
    assert not ledger.exists()


def test_an_invalid_ledger_is_never_extended(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b'{"format": "purchase_ledger", "format_version": 1, "kind": "header"}')

    result = _record(ledger, "--bet", f"{RACE_A}:place:07:1000")

    assert result.exit_code == 1
    assert "incomplete" in result.stderr
    assert ledger.read_bytes().count(b"\n") == 0


def test_a_symbolic_link_ledger_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "real.jsonl"
    assert _record(target, "--create").exit_code == 0
    link = tmp_path / "ledger.jsonl"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symbolic links are not available")
    before = target.read_bytes()

    result = _record(link, at=T0 + timedelta(minutes=1))

    assert result.exit_code == 1
    assert "symbolic link" in result.stderr
    assert target.read_bytes() == before


def test_a_ledger_changed_before_replacement_is_left_unchanged(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _record(ledger, "--create").exit_code == 0
    before = ledger.read_bytes()

    with patch("data.storage.file_replacer._current_bytes", return_value=b"other\n"):
        result = _record(ledger, "--bet", f"{RACE_A}:place:07:1000", at=T0 + timedelta(1))

    assert result.exit_code == 1
    assert "changed" in result.stderr
    assert ledger.read_bytes() == before
    assert _leftovers(tmp_path) == []


def test_an_interrupted_replacement_exits_130_and_leaves_the_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _record(ledger, "--create").exit_code == 0
    before = ledger.read_bytes()

    with patch("data.storage.file_replacer.os.replace", side_effect=KeyboardInterrupt):
        result = _record(ledger, "--bet", f"{RACE_A}:place:07:1000", at=T0 + timedelta(1))

    assert result.exit_code == 130
    assert "interrupted (the ledger is unchanged)" in result.stderr
    assert ledger.read_bytes() == before
    assert _leftovers(tmp_path) == []


def test_an_interrupt_just_after_the_replacement_says_the_ledger_was_written(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _record(ledger, "--create").exit_code == 0
    before = ledger.read_bytes()
    real_replace = os.replace

    def replace_then_interrupt(source: Path, target: Path) -> None:
        real_replace(source, target)
        raise KeyboardInterrupt

    with patch("data.storage.file_replacer.os.replace", side_effect=replace_then_interrupt):
        result = _record(ledger, "--bet", f"{RACE_A}:place:07:1000", at=T0 + timedelta(1))

    assert result.exit_code == 130
    assert "interrupted (after the ledger was written)" in result.stderr
    assert ledger.read_bytes().startswith(before)
    assert parse_ledger(ledger.read_bytes()).race_spent_yen(RACE_A) == 1_000


def test_an_earlier_clock_cannot_append(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _record(ledger, "--create").exit_code == 0
    before = ledger.read_bytes()

    result = _record(ledger, at=T0 - timedelta(seconds=1))

    assert result.exit_code == 1
    assert "earlier" in result.stderr
    assert ledger.read_bytes() == before


def test_help_and_import_do_not_load_the_ledger_modules() -> None:
    script = """
import sys
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "record-purchases", "--help"])
assert result.exit_code == 0, result.output
for name in ("models.betting.purchase_ledger", "data.storage.file_replacer"):
    assert name not in sys.modules, name
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "src",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_totals_at_the_budgets_are_recorded_without_warnings(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"

    # Twenty races of 5,000 yen each reach both budgets exactly.
    races = [f"20261115{venue:02d}0508{race:02d}" for venue in (5, 8) for race in range(1, 11)]
    bets = [option for race in races for option in ("--bet", f"{race}:win:01:5000")]

    result = _record(ledger, "--create", *bets)

    assert result.exit_code == 0, result.output
    assert "warning:" not in result.stderr
    assert json.loads(result.stdout)["years"] == {"2026": 100_000}
