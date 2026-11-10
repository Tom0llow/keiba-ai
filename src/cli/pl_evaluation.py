"""Evaluate top-three Plackett--Luce probabilities on yearly folds of a reference datamart."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
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
    from data.saver.write_json import write_json
    from data.saver.write_parquet import write_parquet
    from data.storage.directory_publisher import publish_directory
    from make_datamart.tables.reference import read_reference_datamart
    from make_features.real_market import MARKET_COLUMN
    from models.dataset.calculated import closed_numeric_columns
    from models.experiments.pl_evaluation import evaluate_pl
    from models.experiments.provenance import experiment_provenance
    from models.serialization.race_arrays import race_arrays_from_reference_tables

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
        expected_sha256 = cast(str, config["datamart_manifest_sha256"])
        manifest_bytes = (datamart / "manifest.json").read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != expected_sha256:
            raise ValueError("datamart manifest SHA-256 differs from datamart_manifest_sha256")
        manifest = json.loads(manifest_bytes)
        calculation = _calculation_parameters(manifest)
        columns = closed_numeric_columns(calculation)
        names = [column.name for column in columns]
        if MARKET_COLUMN not in names:
            raise ValueError(f"datamart does not contain the market column {MARKET_COLUMN!r}")
        # Build and validate every setting, and record the code that runs, before the
        # long read and training, so neither a bad setting nor a later edit is found late.
        settings = _settings(config, names)
        header: dict[str, object] = {
            "format": "pl_probability_evaluation",
            "format_version": 1,
            "datamart": {
                "path": str(datamart.resolve()),
                "manifest_sha256": expected_sha256,
                "target_period": manifest["target_period"],
                "contract_sha256": manifest["contract"]["sha256"],
            },
            "config": config,
            "provenance": experiment_provenance(),
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
        typer.echo(f"model evaluate-pl failed: {exc}", err=True)
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
