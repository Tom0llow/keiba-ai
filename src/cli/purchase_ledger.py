"""Record actual purchases and confirmations in the ADR-046 purchase ledger."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

_COMMAND = "model record-purchases"


def model_record_purchases(
    ledger_path: Annotated[Path, typer.Option("--ledger", help="Purchase ledger (JSON Lines).")],
    bets: Annotated[
        list[str] | None,
        typer.Option(
            "--bet",
            help="A purchase as <race_id>:<bet_type>:<selection>:<stake_yen>; repeatable.",
        ),
    ] = None,
    create: Annotated[bool, typer.Option("--create", help="Create a new ledger.")] = False,
) -> None:
    """Append actual purchases and a confirmation that the ledger is complete until now.

    Without ``--bet`` only the confirmation is appended: no other purchase was made.
    Every bet type and race counts toward the race and calendar-year totals.
    """
    # Keep the ledger and storage modules out of imports and CLI help.
    from data.storage.file_replacer import create_file, replace_file_if_unchanged
    from models.betting.policy import BettingPolicy
    from models.betting.purchase_ledger import (
        JST,
        LedgerError,
        append_entries,
        new_ledger,
        parse_bet,
        parse_ledger,
    )

    updated: bytes | None = None
    try:
        if ledger_path.is_symlink():
            raise ValueError("--ledger must not be a symbolic link")
        exists = ledger_path.exists()
        if create and exists:
            raise ValueError("--create needs a ledger path that does not exist yet")
        if not create and not exists:
            raise ValueError("the ledger does not exist; pass --create to start a new one")
        if create and not ledger_path.parent.is_dir():
            raise ValueError("the ledger's parent directory must already exist")
        confirmed_at = _clock()
        purchases = [parse_bet(text, recorded_at=confirmed_at) for text in bets or []]
        original = new_ledger() if create else ledger_path.read_bytes()
        updated = append_entries(original, purchases, confirmed_at=confirmed_at)
        if create:
            create_file(ledger_path, updated)
        else:
            replace_file_if_unchanged(ledger_path, updated, expected=original)
        ledger = parse_ledger(updated)
    except KeyboardInterrupt as exc:
        written = updated is not None and _holds(ledger_path, updated)
        state = "after the ledger was written" if written else "the ledger is unchanged"
        typer.echo(f"{_COMMAND} failed: interrupted ({state})", err=True)
        raise typer.Exit(code=130) from exc
    except (LedgerError, ValueError, OSError) as exc:
        typer.echo(f"{_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    policy = BettingPolicy()
    races = {item.race_id: ledger.race_spent_yen(item.race_id) for item in purchases}
    years = {item.race_year for item in purchases} | {confirmed_at.astimezone(JST).year}
    totals = {str(year): ledger.annual_spent_yen(year) for year in sorted(years)}
    for race_id, spent in sorted(races.items()):
        if spent > policy.race_budget_yen:
            typer.echo(
                f"warning: race {race_id} total {spent} yen exceeds {policy.race_budget_yen} yen",
                err=True,
            )
    for year, spent in totals.items():
        if spent > policy.annual_budget_yen:
            typer.echo(
                f"warning: {year} total {spent} yen exceeds {policy.annual_budget_yen} yen",
                err=True,
            )
    typer.echo(
        json.dumps(
            {
                "appended": len(purchases),
                "confirmed_at": confirmed_at.isoformat(),
                "ledger_sha256": ledger.sha256,
                "races": races,
                "years": totals,
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
        )
    )


def _holds(path: Path, data: bytes) -> bool:
    # An interrupt can land just after the replacement; re-running would record twice.
    try:
        return path.read_bytes() == data
    except OSError:
        return False


def _clock() -> datetime:
    return datetime.now(UTC)
