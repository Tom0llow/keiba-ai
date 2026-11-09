"""Build and atomically publish a reference-feature datamart, one calendar year at a time."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Annotated, cast

import typer

from configuration.reference_datamart import load_reference_datamart_config
from data.loader.fixed_snapshot import FixedSnapshot, PeriodReader
from data.loader.reference_input import read_reference_workouts, read_reference_year
from data.storage.directory_publisher import publish_directory
from make_datamart.tables.reference import ReferenceDatamartWriter
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.reference_raw import (
    HC_COLUMNS,
    HISTORY_RA_COLUMNS,
    HISTORY_SE_COLUMNS,
    MARKET_O1_COLUMNS,
    MARKET_O2_COLUMNS,
    UM_COLUMNS,
    WC_COLUMNS,
)
from make_features.reference_rules import validate_reference_rules
from models.experiments.provenance import experiment_provenance
from models.serialization.reference_datamart import (
    MarketRows,
    ReferenceDatamartBuilder,
    workout_window,
)

_TABLES = (
    "NL_RA_RACE",
    "NL_SE_RACE_UMA",
    "ARCHIVE_O1_ODDS_TANFUKUWAKU",
    "ARCHIVE_O2_ODDS_UMAREN",
    "NL_HC_HANRO",
    "NL_WC_WOOD",
    "NL_UM_UMA",
)


def datamart_build_reference(
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/reference_datamart"),
    config_name: Annotated[str, typer.Option("--config-name")] = "build",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
    features_config: Annotated[Path, typer.Option("--features-config")] = Path(
        "configs/features.toml"
    ),
) -> None:
    """Calculate every reference feature once in time order and publish yearly Parquet."""
    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        config = load_reference_datamart_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        rules = validate_reference_rules(config["reference_rules"])
        processed_root = Path(cast(str, config["processed_root"]))
        if output_path.resolve().is_relative_to(processed_root.expanduser().resolve()):
            raise ValueError("reference datamart output must stay outside processed_root")
        snapshot = FixedSnapshot(
            processed_root, snapshot_id=cast(str | None, config["snapshot_id"])
        )
        snapshot.pin(_TABLES)
        _progress("hash", started)
        settings = cast(dict[str, object], config["calculation_settings"])
        target_start = date.fromisoformat(cast(str, config["target_start"]))
        target_end = date.fromisoformat(cast(str, config["target_end"]))
        venues = cast(list[str], rules["venues"])
        builder = ReferenceDatamartBuilder(
            settings=settings,
            rules=rules,
            registry=create_feature_registry(load_feature_definitions(features_config)),
            target_start=target_start,
            target_end=target_end,
            snapshot=snapshot.pinned_manifest(),
            pedigree_rows=snapshot.read_all("NL_UM_UMA", columns=UM_COLUMNS),
        )
        provenance = experiment_provenance()
        history_start = date.fromisoformat(cast(str, settings["history_start"]))
        totals = {"races": 0, "rows": 0, "held": 0}
        held: list[dict[str, object]] = []
        with publish_directory(output_path) as staging:
            writer = ReferenceDatamartWriter(
                staging,
                columns=builder.columns,
                available_at_groups=builder.available_at_groups,
                contract=builder.contract.as_metadata(),
            )
            for year in builder.years:
                year_started = perf_counter()
                ra_rows, se_rows = read_reference_year(
                    snapshot,
                    first=max(date(year, 1, 1), history_start),
                    last=min(date(year, 12, 31), target_end),
                    venues=venues,
                    ra_columns=HISTORY_RA_COLUMNS,
                    se_columns=HISTORY_SE_COLUMNS,
                )
                window = workout_window(
                    year,
                    target_start=target_start,
                    target_end=target_end,
                    days_window=cast(int, settings["days_window"]),
                )
                workouts = (
                    read_reference_workouts(
                        snapshot,
                        first=window[0],
                        last=window[1],
                        columns={"hc": HC_COLUMNS, "wc": WC_COLUMNS},
                    )
                    if window is not None
                    else []
                )
                # Market tables are read only for target years; their footers are large.
                markets = (
                    _markets(
                        snapshot.period_reader(
                            "ARCHIVE_O1_ODDS_TANFUKUWAKU", columns=MARKET_O1_COLUMNS, venues=venues
                        ),
                        snapshot.period_reader(
                            "ARCHIVE_O2_ODDS_UMAREN", columns=MARKET_O2_COLUMNS, venues=venues
                        ),
                    )
                    if year >= target_start.year
                    else _no_markets
                )
                output = builder.add_year(
                    year,
                    ra_rows=ra_rows,
                    se_rows=se_rows,
                    workout_rows=workouts,
                    markets=markets,
                )
                del ra_rows, se_rows, workouts, markets
                held.extend(output.held)
                if year >= target_start.year:
                    writer.write_year(year, output.rows, output.races)
                    totals["races"] += len(output.races)
                    totals["rows"] += len(output.rows)
                _progress(
                    "year",
                    year_started,
                    year=year,
                    targets=output.target_races,
                    races=len(output.races),
                    rows=len(output.rows),
                    held=len(output.held),
                )
                del output
            manifest = builder.manifest(
                snapshot=snapshot.manifest(),
                provenance=provenance,
                preparation_config=config,
            )
            _progress("manifest", started)
            manifest_sha256 = writer.finish(manifest, held)
            totals["held"] = len(held)
            _progress("validate", started)
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo("datamart build-reference failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"datamart build-reference failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    years = len(builder.target_years())
    typer.echo(
        "Built reference datamart: "
        f"years={years} races={totals['races']} rows={totals['rows']} "
        f"held={totals['held']} manifest_sha256={manifest_sha256}"
    )


def _markets(o1: PeriodReader, o2: PeriodReader) -> MarketRows:
    """Read one race date of win/place and quinella publications from parsed datasets."""

    def markets(day: date) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        stamp = day.strftime("%Y%m%d")
        return o1.read(stamp, stamp), o2.read(stamp, stamp)

    return markets


def _no_markets(day: date) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raise ValueError(f"history-only years do not read markets: {day.isoformat()}")


def _progress(phase: str, started: float, **values: int) -> None:
    details = "".join(f" {name}={value}" for name, value in values.items())
    typer.echo(f"phase={phase}{details} seconds={perf_counter() - started:.3f}", err=True)
