"""Evaluate top-three Plackett--Luce probabilities on yearly folds of a reference datamart."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, cast

import typer

if TYPE_CHECKING:
    from models.experiments.pl_evaluation import PLEvaluationSettings


def model_evaluate_pl(
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/pl_evaluation"),
    config_name: Annotated[str, typer.Option("--config-name")] = "evaluate",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
) -> None:
    """Train, calibrate and compare PL probabilities with the market on yearly folds."""
    # Keep Hydra, NumPy, Arrow and LightGBM out of imports and CLI help.
    from configuration.pl_evaluation import load_pl_evaluation_config
    from data.loader.fixed_snapshot import FixedSnapshot
    from data.saver.write_json import write_json
    from data.saver.write_parquet import write_parquet
    from data.storage.directory_publisher import publish_directory
    from make_datamart.tables.reference import (
        read_reference_datamart,
        read_reference_datamart_race_ids,
    )
    from make_features.real_market import MARKET_COLUMN
    from models.dataset.calculated import closed_numeric_columns
    from models.experiments.pl_evaluation import evaluate_pl
    from models.experiments.provenance import experiment_provenance
    from models.serialization.race_arrays import race_arrays_from_reference_tables
    from models.serialization.race_subsets import (
        JRA_FLAT_GRADED_STAKES_V1,
        JRA_FLAT_GRADED_STAKES_V1_DEFINITION,
        RACE_KEY_COLUMNS,
        classify_nl_ra_race_rows,
    )

    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        config = load_pl_evaluation_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        datamart = Path(cast(str, config["datamart_path"]))
        processed_root = Path(cast(str, config["processed_root"]))
        expected_sha256 = cast(str, config["datamart_manifest_sha256"])
        manifest_bytes = (datamart / "manifest.json").read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != expected_sha256:
            raise ValueError("datamart manifest SHA-256 differs from datamart_manifest_sha256")
        manifest = json.loads(manifest_bytes)
        snapshot_id, snapshot_race_sha256, start, end, venues = _snapshot_inputs(manifest)
        snapshot = FixedSnapshot(processed_root, snapshot_id=snapshot_id)
        snapshot_race_rows = snapshot.read_period(
            "NL_RA_RACE",
            columns=(*RACE_KEY_COLUMNS, "GradeCD", "TrackCD"),
            start=start,
            end=end,
            venues=venues,
        )
        snapshot_manifest = snapshot.manifest()
        observed_race_sha256 = _snapshot_table_sha256(snapshot_manifest, "NL_RA_RACE")
        if observed_race_sha256 != snapshot_race_sha256:
            raise ValueError("snapshot NL_RA_RACE SHA-256 differs from datamart manifest")
        classification = classify_nl_ra_race_rows(snapshot_race_rows)
        race_subsets = classification.subsets
        snapshot_race_ids = classification.race_ids
        calculation = _calculation_parameters(manifest)
        columns = closed_numeric_columns(calculation)
        names = [column.name for column in columns]
        if MARKET_COLUMN not in names:
            raise ValueError(f"datamart does not contain the market column {MARKET_COLUMN!r}")
        # Build and validate the settings, fold years and variants, and record the code
        # that runs, before the long read and training. Label-boundary and split checks
        # that need the race data still run after the read.
        settings = _settings(config, names)
        _validate_fold_years(settings.train_start_year, settings.test_years, start, end)
        header: dict[str, object] = {
            "format": "pl_probability_evaluation",
            "format_version": 1,
            "datamart": {
                "path": str(datamart.resolve()),
                "manifest_sha256": expected_sha256,
                "target_period": manifest["target_period"],
                "contract_sha256": manifest["contract"]["sha256"],
            },
            "race_subsets": {
                JRA_FLAT_GRADED_STAKES_V1: {
                    "definition": JRA_FLAT_GRADED_STAKES_V1_DEFINITION,
                    "source": {
                        "table": "NL_RA_RACE",
                        "sha256": snapshot_race_sha256,
                        "snapshot_id": snapshot_id,
                    },
                }
            },
            "config": config,
            "provenance": experiment_provenance(),
        }
        # Reject test races without a snapshot classification before the long,
        # fully validated datamart read; that read rechecks every file hash.
        test_years = cast(list[int], config["test_years"])
        test_race_ids = read_reference_datamart_race_ids(
            datamart, years=test_years, expected_manifest_sha256=expected_sha256
        )
        missing_test_races = sorted(test_race_ids - snapshot_race_ids)
        if missing_test_races:
            raise ValueError(f"NL_RA_RACE is missing {len(missing_test_races)} datamart test races")
        # Graded stakes held out of the datamart (dead heats, stoppages, scratches)
        # are outside the evaluated subset; record how many per test year.
        cast(dict[str, dict[str, object]], header["race_subsets"])[JRA_FLAT_GRADED_STAKES_V1][
            "not_in_datamart_by_test_year"
        ] = {
            str(year): sum(
                1
                for race_id in race_subsets[JRA_FLAT_GRADED_STAKES_V1] - test_race_ids
                if race_id[:4] == str(year)
            )
            for year in test_years
        }
        loaded = read_reference_datamart(
            datamart, expected_columns=columns, expected_manifest_sha256=expected_sha256
        )
        _progress("read", started, races=loaded.races.num_rows, rows=loaded.rows.num_rows)
        arrays = race_arrays_from_reference_tables(
            loaded.rows, loaded.races, feature_columns=names, market_column=MARKET_COLUMN
        )
        del loaded
        evaluation = evaluate_pl(
            arrays,
            settings,
            race_subsets=race_subsets,
            progress=lambda values: _progress("fold", started, **values),
        )
        report: dict[str, object] = {**header, **evaluation.report}
        with publish_directory(output_path) as staging:
            write_json(staging / "report.json", report, overwrite=False)
            write_parquet(evaluation.predictions, staging / "predictions.parquet")
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo("model evaluate-pl failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"model evaluate-pl failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    folds = cast(list[object], evaluation.report["folds"])
    test_races = sum(
        cast(int, cast(dict[str, dict[str, object]], fold)["counts"]["test_races"])
        for fold in folds
    )
    typer.echo(
        "Evaluated PL probabilities: "
        f"folds={len(folds)} variants={len(settings.variants)} test_races={test_races} "
        f"output={output_path}"
    )


def _calculation_parameters(manifest: object) -> Mapping[str, object]:
    value = manifest
    for key in ("contract", "settings", "parameters", "calculation"):
        if not isinstance(value, dict) or key not in value:
            raise ValueError("datamart manifest has no reference calculation contract")
        value = value[key]
    if not isinstance(value, dict):
        raise ValueError("datamart manifest has no reference calculation contract")
    return cast(Mapping[str, object], value)


def _snapshot_inputs(manifest: object) -> tuple[str, str, str, str, tuple[str, ...]]:
    if not isinstance(manifest, Mapping):
        raise ValueError("datamart manifest must be a mapping")
    snapshot = manifest.get("snapshot")
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("snapshot_id"), str):
        raise ValueError("datamart manifest has no valid snapshot identity")
    snapshot_id = cast(str, snapshot["snapshot_id"])
    tables = snapshot.get("tables")
    if not isinstance(tables, Mapping):
        raise ValueError("datamart manifest has no snapshot tables")
    race_table = tables.get("NL_RA_RACE")
    if not isinstance(race_table, Mapping):
        raise ValueError("datamart manifest has no NL_RA_RACE snapshot identity")
    race_sha256 = race_table.get("sha256")
    if not isinstance(race_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", race_sha256) is None:
        raise ValueError("datamart manifest has an invalid NL_RA_RACE snapshot hash")

    period = manifest.get("target_period")
    if not isinstance(period, Mapping):
        raise ValueError("datamart manifest has no target period")
    try:
        start_date = date.fromisoformat(cast(str, period["start"]))
        end_date = date.fromisoformat(cast(str, period["end"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("datamart manifest target period is invalid") from exc
    if start_date > end_date:
        raise ValueError("datamart manifest target period is invalid")

    assurance = manifest.get("assurance")
    rules = assurance.get("rules") if isinstance(assurance, Mapping) else None
    venues = rules.get("venues") if isinstance(rules, Mapping) else None
    if (
        not isinstance(venues, list)
        or not venues
        or any(not isinstance(venue, str) or not venue for venue in venues)
    ):
        raise ValueError("datamart manifest has no valid reference venues")
    return (
        snapshot_id,
        race_sha256,
        start_date.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d"),
        tuple(venues),
    )


def _snapshot_table_sha256(manifest: Mapping[str, object], table: str) -> str:
    tables = manifest.get("tables")
    entry = tables.get(table) if isinstance(tables, Mapping) else None
    digest = entry.get("sha256") if isinstance(entry, Mapping) else None
    if not isinstance(digest, str):
        raise ValueError(f"snapshot manifest has no {table} SHA-256")
    return digest


def _validate_fold_years(
    train_start_year: int, test_years: Sequence[int], start: str, end: str
) -> None:
    """Reject fold years the datamart cannot supply, before reading it."""
    first, last = int(start[:4]), int(end[:4])
    for year in (train_start_year, *test_years):
        if not first <= year <= last:
            raise ValueError(f"year {year} is outside the datamart target period {first}-{last}")
    if train_start_year > min(test_years) - 2:
        raise ValueError("train_start_year must be at most test_year - 2")


def _settings(config: Mapping[str, object], names: list[str]) -> PLEvaluationSettings:
    from models.experiments.pl_evaluation import PLEvaluationSettings, PLVariant

    variants = tuple(
        PLVariant(cast(str, item["name"]), tuple(cast(list[str], item["excluded_columns"])))
        for item in cast(list[dict[str, object]], config["variants"])
    )
    for variant in variants:
        unknown = sorted(set(variant.excluded_columns) - set(names))
        if unknown:
            raise ValueError(f"variant {variant.name!r} excludes unknown columns: {unknown!r}")
        if set(names) <= set(variant.excluded_columns):
            raise ValueError(f"variant {variant.name!r} leaves no feature column")
    bootstrap = cast(dict[str, object], config["bootstrap"])
    bounds = cast(list[float], config["temperature_bounds"])
    return PLEvaluationSettings(
        train_start_year=cast(int, config["train_start_year"]),
        test_years=tuple(cast(list[int], config["test_years"])),
        variants=variants,
        lightgbm=dict(cast(dict[str, object], config["lightgbm"])),
        num_boost_round=cast(int, config["num_boost_round"]),
        early_stopping_rounds=cast(int, config["early_stopping_rounds"]),
        temperature_bounds=(float(bounds[0]), float(bounds[1])),
        probability_chunk_races=cast(int, config["probability_chunk_races"]),
        bootstrap_resamples=cast(int, bootstrap["resamples"]),
        bootstrap_seed=cast(int, bootstrap["seed"]),
        bootstrap_confidence=float(cast(float, bootstrap["confidence"])),
        probability_bands=tuple(float(v) for v in cast(list[float], config["probability_bands"])),
        odds_bands=tuple(float(v) for v in cast(list[float], config["odds_bands"])),
    )


def _progress(phase: str, started: float, **values: object) -> None:
    """Print one stderr line; ``seconds`` is always the time since the command started."""
    fields = " ".join(
        f"{key}={value:.6g}" if isinstance(value, float) else f"{key}={value}"
        for key, value in values.items()
    )
    typer.echo(
        f"phase={phase}{' ' + fields if fields else ''} seconds={perf_counter() - started:.1f}",
        err=True,
    )
