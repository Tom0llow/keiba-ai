"""Assemble fixed-snapshot market preparation without modifying source data."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import typer
from hydra.errors import HydraException
from omegaconf.errors import OmegaConfBaseException

from configuration.real_market import load_real_market_config
from data.loader.fixed_snapshot import FixedSnapshot
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from make_features.real_market import (
    O1_COLUMNS,
    O1_TABLE,
    RA_COLUMNS,
    RA_TABLE,
    SE_COLUMNS,
    SE_TABLE,
    latest_o1,
    validate_market_settings,
    validate_races,
)
from models.serialization.inputs import parse_feature_inputs
from models.serialization.real_market import prepare_real_market_payload


def model_prepare_real_input(
    manifest_path: Annotated[Path, typer.Option("--manifest")],
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/real_market"),
    config_name: Annotated[str, typer.Option("--config-name")] = "prepare",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
) -> None:
    """Prepare intermediate win odds at scheduled start minus five minutes."""
    try:
        if (
            output_path.exists()
            or output_path.is_symlink()
            or output_path.resolve() == manifest_path.resolve()
        ):
            raise ValueError("output must be a new path distinct from the manifest")
        config = load_real_market_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        settings = validate_market_settings(config["parameters"])
        manifest = read_json(manifest_path)
        if set(manifest) != {"races"}:
            raise ValueError("manifest requires only an explicit races list")
        races = validate_races(manifest["races"])
        identities = [cast(str, r["race_id"]) for r in races]
        snapshot = FixedSnapshot(
            Path(cast(str, config["processed_root"])),
            snapshot_id=cast(str | None, config["snapshot_id"]),
        )
        if output_path.resolve().is_relative_to(snapshot.path.parent.parent):
            raise ValueError("prepared output must stay outside immutable processed data")
        projected = snapshot.read_races(O1_TABLE, identities, columns=O1_COLUMNS)
        selected = [latest_o1(projected, race) for race in races]
        originals = snapshot.read_races(
            O1_TABLE,
            identities,
            columns=None,
            publication_times=[cast(str, r["HappyoTime"]) for r in selected],
        )
        # Recheck conflicts using complete selected raw rows, including unprojected fields.
        selected = [latest_o1(originals, race) for race in races]
        labels = cast(dict[str, object] | None, config["labels"])
        needs_ra = settings["schedule_basis"] == "assumed_stored_schedule" or labels is not None
        ra = snapshot.read_races(RA_TABLE, identities, columns=RA_COLUMNS) if needs_ra else []
        se = (
            snapshot.read_races(SE_TABLE, identities, columns=SE_COLUMNS)
            if labels is not None
            else None
        )
        payload = prepare_real_market_payload(
            settings=settings,
            races=races,
            odds_rows=selected,
            snapshot=snapshot.manifest(),
            schedule_rows=ra,
            result_rows=se,
            result_races=ra,
            label_settings=labels,
        )
        payload["preparation_config"] = config
        parse_feature_inputs(payload)
        write_json(output_path, payload, overwrite=False)
    except (OSError, TypeError, ValueError, HydraException, OmegaConfBaseException) as exc:
        typer.echo(f"model prepare-real-input failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Prepared {len(cast(list[object], payload['records']))} rows from snapshot {snapshot.path.name}."
    )
