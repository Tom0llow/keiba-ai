"""Assemble all-group reference input from one immutable processed snapshot."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Annotated, cast

import typer
from hydra.errors import HydraException
from omegaconf.errors import OmegaConfBaseException

from configuration.reference_input import load_reference_input_config
from data.loader.fixed_snapshot import FixedSnapshot
from data.loader.read_json import read_json
from data.loader.reference_input import read_reference_tables
from data.saver.write_json import write_json
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.real_market import KEY_COLUMNS, O1_TABLE, latest_o1, timestamp, validate_races
from make_features.reference_raw import (
    CARD_RA_COLUMNS,
    CARD_SE_COLUMNS,
    HC_COLUMNS,
    HISTORY_RA_COLUMNS,
    HISTORY_SE_COLUMNS,
    MARKET_O1_COLUMNS,
    MARKET_O2_COLUMNS,
    O2_TABLE,
    UM_COLUMNS,
    WC_COLUMNS,
)
from make_features.reference_rules import validate_reference_rules
from models.serialization.reference import prepare_reference_payload


def model_prepare_reference_input(
    manifest_path: Annotated[Path, typer.Option("--manifest")],
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/reference_input"),
    config_name: Annotated[str, typer.Option("--config-name")] = "prepare",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
    features_config: Annotated[Path, typer.Option("--features-config")] = Path(
        "configs/features.toml"
    ),
) -> None:
    """Calculate all 21 groups with explicit assumptions and whole-race hold reports."""
    try:
        if (
            output_path.exists()
            or output_path.is_symlink()
            or output_path.resolve() in {manifest_path.resolve(), features_config.resolve()}
        ):
            raise ValueError("output must be a new path distinct from all inputs")
        config = load_reference_input_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        rules = validate_reference_rules(config["reference_rules"])
        manifest = read_json(manifest_path)
        if set(manifest) != {"races"}:
            raise ValueError("reference manifest requires only explicit races")
        races = validate_races(manifest["races"])
        settings = cast(dict[str, object], config["calculation_settings"])
        days_window = settings.get("days_window")
        history_start = settings.get("history_start")
        if type(days_window) is not int or days_window < 1 or not isinstance(history_start, str):
            raise ValueError("explicit valid history_start and days_window are required")
        snapshot = FixedSnapshot(
            Path(cast(str, config["processed_root"])),
            snapshot_id=cast(str | None, config["snapshot_id"]),
        )
        if output_path.resolve().is_relative_to(snapshot.path.parent.parent):
            raise ValueError("prepared output must stay outside immutable processed data")
        columns = {
            "history_ra": HISTORY_RA_COLUMNS,
            "history_se": HISTORY_SE_COLUMNS,
            "target_ra": CARD_RA_COLUMNS,
            "target_se": CARD_SE_COLUMNS,
            "o1": MARKET_O1_COLUMNS,
            "o2": MARKET_O2_COLUMNS,
            "hc": HC_COLUMNS,
            "wc": WC_COLUMNS,
            "um": UM_COLUMNS,
        }
        tables = read_reference_tables(
            snapshot,
            races=races,
            history_start=history_start,
            days_window=days_window,
            venues=cast(list[str], rules["venues"]),
            include_labels=cast(bool, config["include_labels"]),
            columns=columns,
        )
        _preserve_market_originals(
            snapshot, tables, races, anchor_seconds=cast(int, settings["market_anchor_seconds"])
        )
        raw = {
            "format_version": 1,
            "snapshot": snapshot.manifest(),
            "rules": rules,
            "calculation_settings": settings,
            "races": list(races),
            "tables": tables,
            "include_labels": config["include_labels"],
        }
        registry = create_feature_registry(load_feature_definitions(features_config))
        payload = prepare_reference_payload(
            raw, registry=registry, selected_columns=cast(list[str], config["selected_columns"])
        )
        payload["preparation_config"] = config
        write_json(output_path, payload, overwrite=False)
    except (OSError, TypeError, ValueError, HydraException, OmegaConfBaseException) as exc:
        typer.echo(f"model prepare-reference-input failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Prepared {len(cast(list[object], payload['records']))} rows; held {len(cast(list[object], payload['held_races']))} whole races. Reference assumptions are recorded in the output."
    )


def _preserve_market_originals(
    snapshot: FixedSnapshot,
    tables: dict[str, object],
    races: tuple[dict[str, object], ...],
    *,
    anchor_seconds: int,
) -> None:
    """Read complete original O1/O2 rows only at selected publication identities."""
    for name, table in (("o1", O1_TABLE), ("o2", O2_TABLE)):
        projected = cast(list[dict[str, object]], tables[name])
        selected: set[tuple[object, ...]] = set()
        times: set[str] = set()
        for race in races:
            for anchor in (
                timestamp(race["freeze_at"]) - timedelta(seconds=anchor_seconds),
                timestamp(race["freeze_at"]),
            ):
                try:
                    row = latest_o1(
                        projected, {"race_id": race["race_id"], "freeze_at": anchor.isoformat()}
                    )
                except ValueError:
                    # Normalization retains and reports this whole-race hold reason.
                    continue
                selected.add(tuple(row[k] for k in (*KEY_COLUMNS, "HappyoTime")))
                times.add(cast(str, row["HappyoTime"]))
        if not selected:
            continue
        originals = snapshot.read_races(
            table,
            [cast(str, r["race_id"]) for r in races],
            columns=None,
            publication_times=sorted(times),
        )
        kept = [
            row
            for row in projected
            if tuple(row[k] for k in (*KEY_COLUMNS, "HappyoTime")) not in selected
        ]
        kept.extend(
            row
            for row in originals
            if tuple(row[k] for k in (*KEY_COLUMNS, "HappyoTime")) in selected
        )
        tables[name] = kept
