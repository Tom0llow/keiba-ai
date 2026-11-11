"""Build and atomically publish reference features, one calendar year at a time.

``build-reference`` publishes the labeled datamart (ADR-034). ``build-reference-prediction``
publishes label-free features for one race date (ADR-036), with the calculation settings
of a labeled datamart pinned by its manifest SHA-256.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Annotated, cast

import typer

from configuration.reference_datamart import (
    load_reference_datamart_config,
    validate_reference_datamart_config,
)
from data.loader.fixed_snapshot import FixedSnapshot, PeriodReader
from data.loader.reference_input import read_reference_workouts, read_reference_year
from data.storage.directory_publisher import publish_directory
from make_datamart.tables.reference import (
    ReferenceDatamartWriter,
    read_reference_datamart_label_usable_through,
    read_reference_datamart_manifest,
)
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.real_market import KEY_COLUMNS
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
from make_features.reference_snapshot import reference_parameters
from make_features.serialization.observations import normalized_payload
from models.dataset.calculated import CalculationContract, closed_numeric_columns
from models.experiments.provenance import experiment_provenance
from models.serialization.reference_datamart import (
    MarketRows,
    ReferenceDatamartBuilder,
    ReferenceYearOutput,
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
_HEX64 = re.compile(r"[0-9a-f]{64}")


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
        _check_new_output(output_path)
        config = load_reference_datamart_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        rules = validate_reference_rules(config["reference_rules"])
        processed_root = Path(cast(str, config["processed_root"]))
        _check_outside(output_path, processed_root)
        snapshot = FixedSnapshot(
            processed_root, snapshot_id=cast(str | None, config["snapshot_id"])
        )
        snapshot.pin(_TABLES)
        _progress("hash", started)
        settings = cast(dict[str, object], config["calculation_settings"])
        target_start = date.fromisoformat(cast(str, config["target_start"]))
        target_end = date.fromisoformat(cast(str, config["target_end"]))
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
                output = _add_year(snapshot, builder, year, settings, rules)
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


def datamart_build_reference_prediction(
    reference_datamart: Annotated[Path, typer.Option("--reference-datamart")],
    reference_datamart_manifest_sha256: Annotated[
        str, typer.Option("--reference-datamart-manifest-sha256")
    ],
    race_datetime: Annotated[
        datetime, typer.Option("--date", formats=["%Y-%m-%d"], help="Race date (JST).")
    ],
    processed_root: Annotated[Path, typer.Option("--processed-root")],
    output_path: Annotated[Path, typer.Option("--output")],
    snapshot_id: Annotated[str | None, typer.Option("--snapshot-id")] = None,
    features_config: Annotated[Path, typer.Option("--features-config")] = Path(
        "configs/features.toml"
    ),
) -> None:
    """Calculate label-free reference features for one race date (ADR-036).

    The calculation settings and rules come only from the labeled datamart pinned by
    its manifest SHA-256; there is nothing to tune, so no Hydra config is read.
    """
    started = perf_counter()
    target = race_datetime.date()
    try:
        _check_new_output(output_path)
        _check_outside(output_path, processed_root)
        if _HEX64.fullmatch(reference_datamart_manifest_sha256) is None:
            raise ValueError("--reference-datamart-manifest-sha256 must be 64 lowercase hex digits")
        source = read_reference_datamart_manifest(
            reference_datamart, expected_manifest_sha256=reference_datamart_manifest_sha256
        )
        prepared = validate_reference_datamart_config(source["preparation_config"])
        settings = cast(dict[str, object], prepared["calculation_settings"])
        rules = validate_reference_rules(prepared["reference_rules"])
        if target < date.fromisoformat(cast(str, settings["history_start"])):
            raise ValueError("--date must not be earlier than the datamart history_start")
        # Settings, rules and columns must reproduce the pinned contract before any read.
        parameters, _ = reference_parameters(dict(settings), rules)
        columns = closed_numeric_columns(settings)
        names = [column.name for column in columns]
        contract = CalculationContract.reference(parameters, rules, names).as_metadata()
        if contract != source["contract"]:
            raise ValueError("calculation contract differs from the reference datamart")
        payload = [
            {
                "name": column.name,
                "group": column.group,
                "column": column.column,
                "meaning": column.meaning,
                "unit": column.unit,
            }
            for column in columns
        ]
        if payload != source["columns"]:
            raise ValueError("closed numeric columns differ from the reference datamart")
        registry = create_feature_registry(load_feature_definitions(features_config))
        if normalized_payload(registry.definitions) != source["feature_definitions"]:
            raise ValueError("feature definitions differ from the reference datamart")
        source_binding = _source_binding(
            source,
            reference_datamart,
            reference_datamart_manifest_sha256,
        )
        snapshot = FixedSnapshot(processed_root, snapshot_id=snapshot_id)
        snapshot.pin(_TABLES)
        _progress("hash", started)
        # Fail on a wrong date or a missing `latest` before minutes of history reading.
        stamp = target.strftime("%Y%m%d")
        target_ra = snapshot.read_period(
            "NL_RA_RACE",
            columns=KEY_COLUMNS,
            start=stamp,
            end=stamp,
            venues=cast(list[str], rules["venues"]),
        )
        _require_races(target_ra, target)
        del target_ra
        builder = ReferenceDatamartBuilder(
            settings=settings,
            rules=rules,
            registry=registry,
            target_start=target,
            target_end=target,
            snapshot=snapshot.pinned_manifest(),
            pedigree_rows=snapshot.read_all("NL_UM_UMA", columns=UM_COLUMNS),
            labeled=False,
        )
        if builder.contract.as_metadata() != source["contract"]:
            raise ValueError("calculation contract differs from the reference datamart")
        provenance = experiment_provenance()
        held: list[dict[str, object]] = []
        totals = {"targets": 0, "races": 0, "rows": 0}
        with publish_directory(output_path) as staging:
            writer = ReferenceDatamartWriter(
                staging,
                columns=builder.columns,
                available_at_groups=builder.available_at_groups,
                contract=builder.contract.as_metadata(),
                labeled=False,
            )
            for year in builder.years:
                year_started = perf_counter()
                output = _add_year(snapshot, builder, year, settings, rules, require_date=target)
                held.extend(output.held)
                if year == target.year:
                    writer.write_year(year, output.rows, output.races)
                    totals = {
                        "targets": output.target_races,
                        "races": len(output.races),
                        "rows": len(output.rows),
                    }
                _progress("year", year_started, year=year, held=len(output.held))
                del output
            manifest = builder.prediction_manifest(
                snapshot=snapshot.manifest(),
                provenance=provenance,
                preparation_config={
                    "reference_datamart": str(reference_datamart.resolve()),
                    "reference_datamart_manifest_sha256": reference_datamart_manifest_sha256,
                    "date": target.isoformat(),
                    "processed_root": str(processed_root.expanduser().resolve()),
                    "snapshot_id": snapshot.path.name,
                    "features_config": str(features_config.resolve()),
                    "calculation_settings": settings,
                    "reference_rules": rules,
                },
                source_datamart=source_binding,
            )
            manifest_sha256 = writer.finish(manifest, held)
            _progress("validate", started)
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo("datamart build-reference-prediction failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"datamart build-reference-prediction failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    targets = [item for item in held if item["role"] == "target"]
    stages = Counter(str(item["stage"]) for item in targets)
    typer.echo("target_holds " + " ".join(f"{k}={v}" for k, v in sorted(stages.items())), err=True)
    freshness = builder.freshness()
    typer.echo("freshness " + " ".join(f"{k}={freshness[k]}" for k in sorted(freshness)), err=True)
    typer.echo(
        "Built reference prediction features: "
        f"date={target.isoformat()} targets={totals['targets']} races={totals['races']} "
        f"rows={totals['rows']} held_targets={len(targets)} manifest_sha256={manifest_sha256}"
    )


def _add_year(
    snapshot: FixedSnapshot,
    builder: ReferenceDatamartBuilder,
    year: int,
    settings: dict[str, object],
    rules: dict[str, object],
    *,
    require_date: date | None = None,
) -> ReferenceYearOutput:
    """Read one calendar year of the pinned snapshot and feed it to the builder."""
    history_start = date.fromisoformat(cast(str, settings["history_start"]))
    venues = cast(list[str], rules["venues"])
    ra_rows, se_rows = read_reference_year(
        snapshot,
        first=max(date(year, 1, 1), history_start),
        last=min(date(year, 12, 31), builder.target_end),
        venues=venues,
        ra_columns=HISTORY_RA_COLUMNS,
        se_columns=HISTORY_SE_COLUMNS,
    )
    if require_date is not None and year == require_date.year:
        _require_races(ra_rows, require_date)
    window = workout_window(
        year,
        target_start=builder.target_start,
        target_end=builder.target_end,
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
        if year >= builder.target_start.year
        else _no_markets
    )
    return builder.add_year(
        year,
        ra_rows=ra_rows,
        se_rows=se_rows,
        workout_rows=workouts,
        markets=markets,
    )


def _require_races(ra_rows: list[dict[str, object]], day: date) -> None:
    stamp = (str(day.year), day.strftime("%m%d"))
    if not any((row.get("idYear"), row.get("idMonthDay")) == stamp for row in ra_rows):
        raise ValueError(f"snapshot has no races on {day.isoformat()} in the declared venues")


def _source_binding(
    source: dict[str, object], path: Path, manifest_sha256: str
) -> dict[str, object]:
    """Bind the prediction to its training datamart for #52 and #53 (ADR-036)."""
    contract = cast(dict[str, object], source["contract"])
    provenance = source["provenance"]
    source_sha256 = provenance.get("source_sha256") if isinstance(provenance, dict) else None
    if not isinstance(source_sha256, str) or _HEX64.fullmatch(source_sha256) is None:
        raise ValueError("reference datamart provenance has no source_sha256")
    through = read_reference_datamart_label_usable_through(
        path, expected_manifest_sha256=manifest_sha256
    )
    return {
        "manifest_sha256": manifest_sha256,
        "contract_sha256": contract["sha256"],
        "target_period": source["target_period"],
        "label_usable_through": through.isoformat(),
        "provenance_source_sha256": source_sha256,
    }


def _check_new_output(output_path: Path) -> None:
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("output must be a new non-symbolic-link path")
    if not output_path.parent.is_dir():
        raise ValueError("output parent directory must already exist")


def _check_outside(output_path: Path, processed_root: Path) -> None:
    if output_path.resolve().is_relative_to(processed_root.expanduser().resolve()):
        raise ValueError("reference datamart output must stay outside processed_root")


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
