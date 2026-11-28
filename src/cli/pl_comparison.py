"""Compare pinned saved Plackett--Luce evaluation variants and residual segments."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from itertools import pairwise
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, cast

import typer

if TYPE_CHECKING:
    import pyarrow as pa

    from models.experiments.pl_comparison import (
        NormalizedPredictions,
        NormalizedVariantPredictions,
        PLComparisonSettings,
        VariantComparison,
    )
    from models.serialization.residual_segments import ResidualSegmentAssignments


_COMMAND = "model compare-pl-variants"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_RACE_TABLE = "NL_RA_RACE"
_SE_TABLE = "NL_SE_RACE_UMA"
_DISTANCE_COLUMN = "basic_conditions_and_weight__race_distance_m"
_PRIOR_POSITION_COLUMN = "recent_performance__past_finish_lag1"
_PRIOR_SIGNED_GAP_COLUMN = "past_racing_ability__past_signed_gap_sec_lag1"
_PREDICTION_COLUMNS = (
    "variant",
    "test_year",
    "race_id",
    "horse_id",
    "finish_position",
    "score",
    "temperature",
    "p_win",
    "p_top2",
    "p_top3",
    "in_jra_flat_graded_stakes",
)
_LOSS_METRICS = (
    "winner_log_loss",
    "multiclass_brier",
    "exacta_log_loss",
    "quinella_log_loss",
    "trifecta_log_loss",
    "trio_log_loss",
)


def model_compare_pl_variants(
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/pl_comparison"),
    config_name: Annotated[str, typer.Option("--config-name")] = "compare",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
) -> None:
    """Compare saved PL variants and report their fixed residual segments."""
    # Keep Hydra, NumPy, Arrow, and the comparison calculations out of CLI help.
    from configuration.pl_comparison import load_pl_comparison_config
    from data.loader.fixed_snapshot import FixedSnapshot
    from data.loader.read_parquet import read_parquet
    from data.saver.write_json import write_json
    from data.storage.directory_publisher import publish_directory
    from make_datamart.tables.reference import (
        read_reference_datamart,
        read_reference_datamart_manifest,
    )
    from make_features.reference_raw import race_identity
    from models.dataset.calculated import closed_numeric_columns
    from models.experiments.pl_comparison import (
        PLComparisonSettings,
        VariantComparison,
        build_pl_comparison_report,
        normalize_pl_predictions,
    )
    from models.experiments.provenance import experiment_provenance
    from models.serialization.race_subsets import RACE_KEY_COLUMNS

    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        config = load_pl_comparison_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        settings = _settings(config, PLComparisonSettings, VariantComparison)
        evaluation_path = Path(cast(str, config["evaluation_path"]))
        processed_root = Path(cast(str, config["processed_root"]))
        _reject_output_inside(output_path, (evaluation_path, processed_root))

        report_bytes = _pinned_bytes(
            evaluation_path / "report.json", cast(str, config["pl_report_sha256"])
        )
        evaluation = _evaluation_report(report_bytes, settings.comparisons)
        datamart_path = Path(cast(str, evaluation["datamart_path"]))
        _reject_output_inside(output_path, (datamart_path,))
        _pinned_bytes(
            evaluation_path / "predictions.parquet", cast(str, config["pl_predictions_sha256"])
        )

        datamart_manifest = read_reference_datamart_manifest(
            datamart_path,
            expected_manifest_sha256=cast(str, evaluation["datamart_manifest_sha256"]),
        )
        columns = closed_numeric_columns(_calculation_parameters(datamart_manifest))
        names = {column.name for column in columns}
        if _DISTANCE_COLUMN not in names or _PRIOR_POSITION_COLUMN not in names:
            raise ValueError("datamart does not contain required PL residual-segment columns")
        start, end, venues = _snapshot_period(
            datamart_manifest, cast(tuple[int, ...], evaluation["test_years"])
        )
        snapshot_identity = _datamart_snapshot_identity(datamart_manifest)
        if snapshot_identity["snapshot_id"] != evaluation["snapshot_id"]:
            raise ValueError("datamart snapshot differs from the PL evaluation's graded source")
        snapshot = FixedSnapshot(processed_root, snapshot_id=cast(str, evaluation["snapshot_id"]))
        _reject_output_inside(output_path, (snapshot.path,))
        snapshot.pin((_RACE_TABLE, _SE_TABLE))
        pinned_snapshot = snapshot.pinned_manifest()
        _validate_snapshot_hashes(
            pinned_snapshot, snapshot_identity, cast(str, evaluation["snapshot_race_sha256"])
        )

        predictions = read_parquet(
            evaluation_path / "predictions.parquet", columns=_PREDICTION_COLUMNS
        )
        _validate_prediction_report_identity(
            predictions,
            cast(tuple[str, ...], evaluation["variant_names"]),
            cast(tuple[int, ...], evaluation["test_years"]),
        )
        normalized = normalize_pl_predictions(predictions)
        if normalized.test_years != evaluation["test_years"]:
            raise ValueError("prediction test_years differ from the PL evaluation report")
        _validate_report_averages(evaluation["report"], normalized)
        _pinned_bytes(
            evaluation_path / "predictions.parquet", cast(str, config["pl_predictions_sha256"])
        )
        _progress(
            "read_predictions",
            started,
            variants=len(normalized.variants),
            races=next(iter(normalized.variants.values())).layout.race_count,
        )

        reference = next(iter(normalized.variants.values()))
        loaded = read_reference_datamart(
            datamart_path,
            expected_columns=columns,
            expected_manifest_sha256=cast(str, evaluation["datamart_manifest_sha256"]),
        )
        race_rows = snapshot.read_period(
            _RACE_TABLE,
            columns=(*RACE_KEY_COLUMNS, "TrackCD"),
            start=start,
            end=end,
            venues=venues,
        )
        se_rows = snapshot.read_period(
            _SE_TABLE,
            columns=(*RACE_KEY_COLUMNS, "KettoNum", "Umaban", "Barei"),
            start=start,
            end=end,
            venues=venues,
        )
        segments = _segment_assignments(
            reference,
            _segment_datamart_rows(
                loaded.rows,
                reference.race_ids,
                _PRIOR_SIGNED_GAP_COLUMN in names,
            ),
            race_rows,
            se_rows,
            race_identity,
            _PRIOR_SIGNED_GAP_COLUMN in names,
        )
        del loaded, race_rows, se_rows
        _progress("read_inputs", started, rows=reference.layout.row_count)

        body = build_pl_comparison_report(normalized, settings, segments)
        snapshot_manifest = snapshot.manifest()
        report = {
            "format": "pl_variant_comparison",
            "format_version": 1,
            "inputs": {
                "evaluation": {
                    "path": str(evaluation_path.resolve()),
                    "report_sha256": config["pl_report_sha256"],
                    "predictions_sha256": config["pl_predictions_sha256"],
                },
                "datamart": {
                    "path": str(datamart_path.resolve()),
                    "manifest_sha256": evaluation["datamart_manifest_sha256"],
                },
                "snapshot": snapshot_manifest,
            },
            "config": {key: value for key, value in config.items() if key != "evaluation_path"},
            "provenance": experiment_provenance(),
            **body,
        }
        _progress("compare", started)
        with publish_directory(output_path) as staging:
            write_json(staging / "report.json", report, overwrite=False)
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo(f"{_COMMAND} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        typer.echo(f"{_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        "Compared PL variants: "
        f"comparisons={len(settings.comparisons)} variants={len(normalized.variants)} "
        f"test_races={next(iter(normalized.variants.values())).layout.race_count} output={output_path}"
    )


def _settings(
    config: Mapping[str, object],
    settings_type: type[PLComparisonSettings],
    comparison_type: type[VariantComparison],
) -> PLComparisonSettings:
    """Return calculation settings after configuration-only structural validation."""
    comparisons = tuple(
        comparison_type(cast(str, item["candidate"]), cast(str, item["baseline"]))
        for item in cast(list[dict[str, object]], config["comparisons"])
    )
    bootstrap = cast(dict[str, object], config["bootstrap"])
    return settings_type(
        comparisons=comparisons,
        bootstrap_resamples=cast(int, bootstrap["resamples"]),
        bootstrap_seed=cast(int, bootstrap["seed"]),
        bootstrap_confidence=float(cast(float, bootstrap["confidence"])),
    )


def _pinned_bytes(path: Path, expected_sha256: str) -> bytes:
    """Read one pinned artifact and reject content that differs from its configured hash."""
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"{path.name} SHA-256 differs from the configured value")
    return data


def _reject_output_inside(output_path: Path, inputs: Sequence[Path]) -> None:
    """Reject output paths that equal or lie within an input directory."""
    target = output_path.resolve()
    for path in inputs:
        if target.is_relative_to(path.resolve()):
            raise ValueError("output must stay outside every input directory")


def _evaluation_report(data: bytes, comparisons: Sequence[VariantComparison]) -> dict[str, object]:
    """Return validated comparison inputs from one pinned PL evaluation report."""
    try:
        report = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PL evaluation report is not valid JSON") from exc
    if (
        not isinstance(report, dict)
        or report.get("format") != "pl_probability_evaluation"
        or report.get("format_version") != 1
    ):
        raise ValueError("PL evaluation report format is not pl_probability_evaluation v1")
    test_years = _test_years(report.get("test_years"))
    variants = report.get("variants")
    if not isinstance(variants, list):
        raise ValueError("PL evaluation report has no variants")
    names = {
        item.get("name")
        for item in variants
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
    }
    if len(names) != len(variants):
        raise ValueError("PL evaluation report has invalid variants")
    for comparison in comparisons:
        missing = {comparison.candidate, comparison.baseline} - names
        if missing:
            raise ValueError(f"PL evaluation has no variants: {sorted(missing)!r}")
    try:
        datamart = report["datamart"]
        source = report["race_subsets"]["jra_flat_graded_stakes_v1"]["source"]
    except (KeyError, TypeError) as exc:
        raise ValueError("PL evaluation report lacks datamart or graded-source identity") from exc
    if not isinstance(datamart, dict) or not isinstance(source, dict):
        raise ValueError("PL evaluation report lacks datamart or graded-source identity")
    path = datamart.get("path")
    manifest_sha256 = datamart.get("manifest_sha256")
    snapshot_id = source.get("snapshot_id")
    race_sha256 = source.get("sha256")
    if (
        not isinstance(path, str)
        or not path
        or not _is_sha256(manifest_sha256)
        or not isinstance(snapshot_id, str)
        or not snapshot_id
        or not _is_sha256(race_sha256)
    ):
        raise ValueError("PL evaluation report has invalid datamart or graded-source identity")
    return {
        "report": report,
        "variant_names": tuple(sorted(cast(set[str], names))),
        "test_years": test_years,
        "datamart_path": path,
        "datamart_manifest_sha256": manifest_sha256,
        "snapshot_id": snapshot_id,
        "snapshot_race_sha256": race_sha256,
    }


def _validate_prediction_report_identity(
    predictions: pa.Table,
    report_variant_names: Sequence[str],
    report_test_years: Sequence[int],
) -> None:
    """Reject prediction variants or test years that differ from the evaluation report."""
    import pyarrow.compute as pc

    variant_names = pc.unique(predictions["variant"]).to_pylist()
    if any(not isinstance(name, str) or not name for name in variant_names) or tuple(
        sorted(cast(list[str], variant_names))
    ) != tuple(report_variant_names):
        raise ValueError("prediction variants differ from the PL evaluation report")
    test_years = pc.unique(predictions["test_year"]).to_pylist()
    if any(isinstance(year, bool) or not isinstance(year, int) for year in test_years) or tuple(
        sorted(cast(list[int], test_years))
    ) != tuple(report_test_years):
        raise ValueError("prediction test_years differ from the PL evaluation report")


def _test_years(value: object) -> tuple[int, ...]:
    """Return strictly increasing four-digit evaluation years."""
    if not isinstance(value, list) or not value:
        raise ValueError("PL evaluation report has invalid test_years")
    years: list[int] = []
    for year in value:
        if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
            raise ValueError("PL evaluation report has invalid test_years")
        years.append(year)
    if any(left >= right for left, right in pairwise(years)):
        raise ValueError("PL evaluation report has invalid test_years")
    return tuple(years)


def _datamart_snapshot_identity(manifest: Mapping[str, object]) -> dict[str, str]:
    """Return the required raw-table identities from a validated datamart manifest."""
    snapshot = manifest.get("snapshot")
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("snapshot_id"), str):
        raise ValueError("datamart manifest has no valid snapshot identity")
    tables = snapshot.get("tables")
    if not isinstance(tables, Mapping):
        raise ValueError("datamart manifest has no snapshot tables")
    result = {"snapshot_id": cast(str, snapshot["snapshot_id"])}
    for table in (_RACE_TABLE, _SE_TABLE):
        entry = tables.get(table)
        digest = entry.get("sha256") if isinstance(entry, Mapping) else None
        if not _is_sha256(digest):
            raise ValueError(f"datamart manifest has no valid {table} snapshot hash")
        result[table] = cast(str, digest)
    return result


def _validate_snapshot_hashes(
    observed: Mapping[str, object], expected: Mapping[str, str], evaluation_race_sha256: str
) -> None:
    """Require both raw inputs and the evaluation's graded source to be identical."""
    tables = observed.get("tables")
    if not isinstance(tables, Mapping):
        raise ValueError("fixed snapshot has no pinned table hashes")
    for table in (_RACE_TABLE, _SE_TABLE):
        item = tables.get(table)
        digest = item.get("sha256") if isinstance(item, Mapping) else None
        if digest != expected[table]:
            raise ValueError(f"snapshot {table} SHA-256 differs from datamart manifest")
    race = tables[_RACE_TABLE]
    digest = race.get("sha256") if isinstance(race, Mapping) else None
    if digest != evaluation_race_sha256:
        raise ValueError("snapshot NL_RA_RACE differs from the PL evaluation's graded source")


def _calculation_parameters(manifest: Mapping[str, object]) -> Mapping[str, object]:
    """Return the closed reference-calculation parameters from a datamart manifest."""
    value: object = manifest
    for key in ("contract", "settings", "parameters", "calculation"):
        if not isinstance(value, Mapping) or key not in value:
            raise ValueError("datamart manifest has no reference calculation contract")
        value = value[key]
    if not isinstance(value, Mapping):
        raise ValueError("datamart manifest has no reference calculation contract")
    return value


def _snapshot_period(
    manifest: Mapping[str, object], test_years: Sequence[int]
) -> tuple[str, str, tuple[str, ...]]:
    """Return the test-year period and manifest-recorded venues for raw input reads."""
    period = manifest.get("target_period")
    if not isinstance(period, Mapping):
        raise ValueError("datamart manifest has no target period")
    try:
        start = date.fromisoformat(cast(str, period["start"]))
        end = date.fromisoformat(cast(str, period["end"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("datamart manifest target period is invalid") from exc
    if start > end:
        raise ValueError("datamart manifest target period is invalid")
    first, last = test_years[0], test_years[-1]
    if first < start.year or last > end.year:
        raise ValueError("PL evaluation test_years are outside the datamart target period")
    assurance = manifest.get("assurance")
    rules = assurance.get("rules") if isinstance(assurance, Mapping) else None
    venues = rules.get("venues") if isinstance(rules, Mapping) else None
    if (
        not isinstance(venues, list)
        or not venues
        or any(not isinstance(venue, str) or not venue for venue in venues)
    ):
        raise ValueError("datamart manifest has no valid reference venues")
    return f"{first}0101", f"{last}1231", tuple(venues)


def _segment_assignments(
    reference: NormalizedVariantPredictions,
    datamart_rows: Sequence[Mapping[str, object]],
    race_rows: Sequence[Mapping[str, object]],
    se_rows: Sequence[Mapping[str, object]],
    race_key: Callable[[Mapping[str, object]], str],
    signed_gaps_available: bool,
) -> ResidualSegmentAssignments:
    """Join normalized prediction rows to pinned datamart and snapshot segment inputs."""
    import numpy.typing as npt

    datamart_by_key = _datamart_rows_by_key(datamart_rows)
    wanted_races = set(reference.race_ids)
    track_by_race = _track_codes_by_race(race_rows, wanted_races, race_key)
    se_by_key = _se_rows_by_key(se_rows, wanted_races, race_key)
    field_sizes = [size for size in reference.layout.group_sizes for _ in range(size)]
    tracks: list[str | None] = []
    distances: list[object] = []
    numbers: list[object] = []
    ages: list[object] = []
    prior_positions: list[object] = []
    signed_gaps: list[object] = []
    for year, race_id, horse_id, finish in zip(
        reference.row_test_years,
        reference.row_race_ids,
        reference.horse_ids,
        reference.finish_positions,
        strict=True,
    ):
        if not race_id.startswith(f"{int(year):04d}"):
            raise ValueError("prediction test_year differs from race_id")
        key = (race_id, horse_id)
        datamart = datamart_by_key.get(key)
        if datamart is None:
            raise ValueError("prediction row has no matching datamart row")
        if datamart["finish_position"] != int(finish):
            raise ValueError("prediction finish_position differs from datamart")
        source = se_by_key.get(key)
        if source is None:
            raise ValueError("prediction row has no matching NL_SE_RACE_UMA row")
        if race_id not in track_by_race:
            raise ValueError("prediction race has no matching NL_RA_RACE row")
        tracks.append(track_by_race[race_id])
        distances.append(datamart[_DISTANCE_COLUMN])
        numbers.append(source["Umaban"])
        ages.append(source["Barei"])
        prior_positions.append(datamart[_PRIOR_POSITION_COLUMN])
        if signed_gaps_available:
            signed_gaps.append(datamart[_PRIOR_SIGNED_GAP_COLUMN])
    from models.serialization.residual_segments import assign_residual_segments

    return assign_residual_segments(
        tracks,
        cast(npt.ArrayLike, distances),
        cast(npt.ArrayLike, numbers),
        cast(npt.ArrayLike, field_sizes),
        cast(npt.ArrayLike, ages),
        cast(npt.ArrayLike, prior_positions),
        None if not signed_gaps_available else cast(npt.ArrayLike, signed_gaps),
    )


def _segment_datamart_rows(
    rows: pa.Table,
    race_ids: Sequence[str],
    signed_gaps_available: bool,
) -> list[dict[str, object]]:
    """Return only evaluated rows and columns needed for residual segments."""
    import pyarrow as pa
    import pyarrow.compute as pc

    columns = [
        "race_id",
        "horse_id",
        "finish_position",
        _DISTANCE_COLUMN,
        _PRIOR_POSITION_COLUMN,
    ]
    if signed_gaps_available:
        columns.append(_PRIOR_SIGNED_GAP_COLUMN)
    selected = rows.select(columns)
    test_rows = selected.filter(
        pc.is_in(selected["race_id"], value_set=pa.array(race_ids, type=pa.string()))
    )
    return cast(list[dict[str, object]], test_rows.to_pylist())


def _datamart_rows_by_key(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], Mapping[str, object]]:
    """Index datamart horse rows while rejecting ambiguous keys."""
    result: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in rows:
        race_id = row.get("race_id")
        horse_id = row.get("horse_id")
        finish_position = row.get("finish_position")
        if (
            not isinstance(race_id, str)
            or not race_id
            or not isinstance(horse_id, str)
            or not horse_id
            or isinstance(finish_position, bool)
            or not isinstance(finish_position, int)
        ):
            raise ValueError("datamart rows have invalid prediction-join keys")
        key = (race_id, horse_id)
        if key in result:
            raise ValueError("datamart has duplicate race_id/horse_id rows")
        result[key] = row
    return result


def _track_codes_by_race(
    rows: Sequence[Mapping[str, object]],
    wanted: set[str],
    race_key: Callable[[Mapping[str, object]], str],
) -> dict[str, str | None]:
    """Return the required TrackCD value for every evaluated race."""
    result: dict[str, str | None] = {}
    for row in rows:
        race_id = race_key(row)
        if race_id not in wanted:
            continue
        track = row.get("TrackCD")
        if track is not None and not isinstance(track, str):
            raise ValueError("NL_RA_RACE TrackCD must contain strings or null")
        if race_id in result:
            raise ValueError("NL_RA_RACE has duplicate evaluated race_id")
        result[race_id] = track
    return result


def _se_rows_by_key(
    rows: Sequence[Mapping[str, object]],
    wanted: set[str],
    race_key: Callable[[Mapping[str, object]], str],
) -> dict[tuple[str, str], Mapping[str, object]]:
    """Index pinned start-list rows by the same horse identity as predictions."""
    result: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in rows:
        race_id = race_key(row)
        if race_id not in wanted:
            continue
        horse_id = row.get("KettoNum")
        if not isinstance(horse_id, str) or not horse_id:
            raise ValueError("NL_SE_RACE_UMA KettoNum must be a nonempty string")
        key = (race_id, horse_id)
        if key in result:
            raise ValueError("NL_SE_RACE_UMA has duplicate race_id/KettoNum rows")
        result[key] = row
    return result


def _validate_report_averages(report: object, normalized: NormalizedPredictions) -> None:
    """Require stored pooled calibrated means to reproduce from saved predictions."""
    pooled = report.get("pooled") if isinstance(report, Mapping) else None
    if not isinstance(pooled, Mapping):
        raise ValueError("PL evaluation report has no pooled metrics")
    for name, variant in normalized.variants.items():
        recorded = pooled.get(name)
        all_races = recorded.get("all_test_races") if isinstance(recorded, Mapping) else None
        calibrated = all_races.get("calibrated") if isinstance(all_races, Mapping) else None
        if not isinstance(calibrated, Mapping):
            raise ValueError(f"PL evaluation report has no pooled calibrated metrics for {name!r}")
        expected_races = calibrated.get("race_count")
        if expected_races != variant.layout.race_count:
            raise ValueError(f"PL evaluation report race count differs for {name!r}")
        for metric in _LOSS_METRICS:
            _validate_average(calibrated.get(metric), _mean_metric(variant, metric), name, metric)
        stages = calibrated.get("stage_nll")
        if not isinstance(stages, list) or len(stages) != 3:
            raise ValueError(f"PL evaluation report has invalid stage_nll for {name!r}")
        for index, value in enumerate(stages):
            _validate_average(value, _mean_stage(variant, index), name, f"stage{index + 1}_nll")


def _mean_metric(variant: NormalizedVariantPredictions, name: str) -> float:
    """Return one canonical recalculated race-mean metric."""
    import numpy as np

    return float(np.mean(getattr(variant.metrics, name)))


def _mean_stage(variant: NormalizedVariantPredictions, index: int) -> float:
    """Return one canonical recalculated stage loss mean."""
    import numpy as np

    return float(np.mean(variant.metrics.stage_nll[:, index]))


def _validate_average(recorded: object, observed: float, variant: str, metric: str) -> None:
    """Reject a stored pooled metric that differs beyond its relative tolerance."""
    if (
        isinstance(recorded, bool)
        or not isinstance(recorded, (int, float))
        or not math.isfinite(recorded)
        or not math.isclose(float(recorded), observed, rel_tol=1e-12, abs_tol=0.0)
    ):
        raise ValueError(
            f"PL evaluation report pooled calibrated {metric} differs from recomputation for {variant!r}"
        )


def _is_sha256(value: object) -> bool:
    """Return whether ``value`` is one lowercase SHA-256 digest."""
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _progress(phase: str, started: float, **values: object) -> None:
    """Print one stderr progress line with elapsed seconds."""
    fields = " ".join(
        f"{key}={value:.6g}" if isinstance(value, float) else f"{key}={value}"
        for key, value in values.items()
    )
    typer.echo(
        f"phase={phase}{' ' + fields if fields else ''} seconds={perf_counter() - started:.1f}",
        err=True,
    )
