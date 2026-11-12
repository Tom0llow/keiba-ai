"""Train and publish the final top-three Plackett--Luce model (ADR-038)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import Annotated, cast

import typer

_HEX64 = re.compile(r"[0-9a-f]{64}")


def model_train_pl(
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/pl_training"),
    config_name: Annotated[str, typer.Option("--config-name")] = "train",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
) -> None:
    """Fit the final PL model on train years, early-stop and calibrate on the valid year."""
    # Keep Hydra, NumPy, Arrow and LightGBM out of imports and CLI help.
    import numpy as np

    from configuration.pl_training import load_pl_training_config
    from data.storage.directory_publisher import publish_directory
    from make_datamart.tables.reference import (
        read_reference_datamart,
        read_reference_datamart_label_usable_through,
        read_reference_datamart_manifest,
    )
    from make_features.real_market import MARKET_COLUMN
    from models.artifacts.pl_model import read_pl_model, write_pl_model
    from models.dataset.calculated import closed_numeric_columns
    from models.experiments.pl_evaluation import PLVariant
    from models.experiments.pl_training import (
        PLTrainingSettings,
        pl_model_record,
        train_final_pl,
        variant_columns,
    )
    from models.experiments.provenance import experiment_provenance
    from models.serialization.race_arrays import race_arrays_from_reference_tables

    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        config = load_pl_training_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        datamart = Path(cast(str, config["datamart_path"]))
        expected_sha256 = cast(str, config["datamart_manifest_sha256"])
        manifest = read_reference_datamart_manifest(
            datamart, expected_manifest_sha256=expected_sha256
        )
        columns = closed_numeric_columns(_calculation_parameters(manifest))
        names = [column.name for column in columns]
        if MARKET_COLUMN not in names:
            raise ValueError(f"datamart does not contain the market column {MARKET_COLUMN!r}")
        variant_config = cast(dict[str, object], config["variant"])
        variant = PLVariant(
            cast(str, variant_config["name"]),
            tuple(cast(list[str], variant_config["excluded_columns"])),
        )
        variant_columns(names, variant)
        _validate_years(
            cast(int, config["train_start_year"]),
            cast(int, config["valid_year"]),
            cast(Mapping[str, object], manifest["target_period"]),
        )
        bounds = cast(list[float], config["temperature_bounds"])
        settings = PLTrainingSettings(
            train_start_year=cast(int, config["train_start_year"]),
            valid_year=cast(int, config["valid_year"]),
            variant=variant,
            lightgbm=cast(dict[str, object], config["lightgbm"]),
            num_boost_round=cast(int, config["num_boost_round"]),
            early_stopping_rounds=cast(int, config["early_stopping_rounds"]),
            temperature_bounds=(float(bounds[0]), float(bounds[1])),
        )
        # Record the code that runs before the long read and training.
        provenance = experiment_provenance()
        source = _source_datamart(
            manifest,
            expected_sha256,
            read_reference_datamart_label_usable_through(
                datamart, expected_manifest_sha256=expected_sha256
            ),
        )
        loaded = read_reference_datamart(
            datamart, expected_columns=columns, expected_manifest_sha256=expected_sha256
        )
        _progress("read", started, races=loaded.races.num_rows, rows=loaded.rows.num_rows)
        arrays = race_arrays_from_reference_tables(
            loaded.rows, loaded.races, feature_columns=names, market_column=MARKET_COLUMN
        )
        del loaded
        final = train_final_pl(arrays, settings)
        del arrays
        _progress(
            "train",
            started,
            best_iteration=final.fit.best_iteration,
            train_races=final.train_races,
            valid_races=final.valid_races,
        )
        # The datamart location is not part of the identity; its SHA-256 is.
        persisted = {key: value for key, value in config.items() if key != "datamart_path"}
        record = pl_model_record(
            final, source_datamart=source, provenance=provenance, config=persisted
        )
        with publish_directory(output_path) as staging:
            manifest_sha256 = write_pl_model(staging, record, final.fit.booster)
            model = read_pl_model(staging, expected_manifest_sha256=manifest_sha256)
            # Re-score the valid rows from the written model before publication.
            rescored = np.asarray(model.booster.predict(final.valid_features), dtype=np.float64)
            if not np.array_equal(rescored, final.valid_scores):
                raise ValueError("written PL model scores differ from the trained booster")
            del model
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo("model train-pl failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"model train-pl failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        "Trained PL model: "
        f"best_iteration={final.fit.best_iteration} "
        f"temperature={final.temperature.temperature:.6f} "
        f"label_usable_through={final.audit.label_usable_through.astimezone(UTC).isoformat()} "
        f"manifest_sha256={manifest_sha256}"
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


def _validate_years(train_start_year: int, valid_year: int, period: Mapping[str, object]) -> None:
    first = date.fromisoformat(cast(str, period["start"])).year
    last = date.fromisoformat(cast(str, period["end"])).year
    for name, year in (("train_start_year", train_start_year), ("valid_year", valid_year)):
        if not first <= year <= last:
            raise ValueError(f"{name} {year} lies outside the datamart target period")
    if train_start_year > valid_year - 1:
        raise ValueError("train_start_year must be at most valid_year - 1")


def _source_datamart(
    manifest: Mapping[str, object], manifest_sha256: str, label_usable_through: object
) -> dict[str, object]:
    """Bind the model to its datamart with the keys prediction features carry (ADR-036)."""
    contract = cast(dict[str, object], manifest["contract"])
    provenance = manifest.get("provenance")
    source_sha256 = provenance.get("source_sha256") if isinstance(provenance, dict) else None
    if not isinstance(source_sha256, str) or _HEX64.fullmatch(source_sha256) is None:
        raise ValueError("reference datamart provenance has no source_sha256")
    if not isinstance(label_usable_through, datetime):
        raise ValueError("reference datamart label boundary is invalid")
    return {
        "manifest_sha256": manifest_sha256,
        "contract_sha256": contract["sha256"],
        "target_period": manifest["target_period"],
        "label_usable_through": label_usable_through.astimezone(UTC).isoformat(),
        "provenance_source_sha256": source_sha256,
        "columns": manifest["columns"],
    }


def _progress(phase: str, started: float, **values: object) -> None:
    details = "".join(f" {name}={value}" for name, value in values.items())
    typer.echo(f"phase={phase}{details} seconds={perf_counter() - started:.3f}", err=True)
