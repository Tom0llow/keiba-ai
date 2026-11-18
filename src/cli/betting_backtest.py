"""Replay the fixed expected-value win and place policy on graded races (ADR-043, ADR-044)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, cast

import typer

if TYPE_CHECKING:
    from datetime import datetime

    from data.loader.fixed_snapshot import FixedSnapshot, PublicationReader
    from models.experiments.betting_backtest import BettingBacktestSettings
    from models.serialization.final_odds_observations import HitObservation

type _Identity = Callable[[Mapping[str, object]], str]
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SNAPSHOT_ID = re.compile(r"[A-Za-z0-9_-]+")
_COMMAND = "model backtest-betting"


def model_backtest_betting(
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path("configs/betting_backtest"),
    config_name: Annotated[str, typer.Option("--config-name")] = "evaluate",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
) -> None:
    """Backtest the fixed expected-value policy under yearly selected estimation methods."""
    # Keep Hydra, NumPy and Arrow out of imports and CLI help.
    from configuration.betting_backtest import load_betting_backtest_config
    from data.loader.fixed_snapshot import FixedSnapshot
    from data.loader.read_parquet import read_parquet
    from data.saver.write_json import write_json
    from data.saver.write_parquet import write_parquet
    from data.storage.directory_publisher import publish_directory
    from make_datamart.tables.reference import read_reference_datamart_target_holds
    from make_features.reference_raw import race_identity
    from make_features.reference_rules import REFERENCE_BASES
    from models.experiments.betting_backtest import (
        GradedRaceInput,
        bets_table,
        races_table,
        run_betting_backtest,
    )
    from models.experiments.provenance import experiment_provenance
    from models.serialization.betting_inputs import (
        PL_BLEND_COLUMNS,
        PL_PREDICTION_COLUMNS,
        SE_COLUMNS,
        SE_TABLE,
        blend_training_races,
        race_predictions,
    )
    from models.serialization.final_odds_observations import (
        HR_TABLE,
        O1_TABLE,
        RA_TABLE,
    )

    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        config = load_betting_backtest_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        settings = _settings(config)
        processed_root = Path(cast(str, config["processed_root"]))
        pl_path = Path(cast(str, config["pl_evaluation_path"]))
        _reject_output_inside(output_path, (processed_root, pl_path))
        # The datamart and the snapshot are known only from the pinned PL report.
        report_bytes = _pinned_bytes(pl_path / "report.json", cast(str, config["pl_report_sha256"]))
        pl_report = _pl_report(report_bytes, cast(str, config["pl_variant"]), settings.test_years)
        source = cast(dict[str, str], pl_report["source"])
        datamart_path = Path(cast(str, pl_report["datamart_path"]))
        _reject_output_inside(output_path, (datamart_path,))
        snapshot = FixedSnapshot(processed_root, snapshot_id=source["snapshot_id"])
        _reject_output_inside(output_path, (snapshot.path,))
        _pinned_bytes(pl_path / "predictions.parquet", cast(str, config["pl_predictions_sha256"]))
        # Hash every source before any row is read; manifest() rechecks them at the end.
        snapshot.pin((RA_TABLE, SE_TABLE, HR_TABLE, O1_TABLE))
        pinned = cast(dict[str, dict[str, str]], snapshot.pinned_manifest()["tables"])
        if pinned[RA_TABLE]["sha256"] != source["sha256"]:
            raise ValueError("snapshot NL_RA_RACE differs from the PL evaluation's graded source")
        holds = _target_hold_stages(
            read_reference_datamart_target_holds(
                datamart_path,
                expected_manifest_sha256=cast(str, pl_report["datamart_manifest_sha256"]),
            )
        )
        prediction_rows = read_parquet(
            pl_path / "predictions.parquet", columns=PL_PREDICTION_COLUMNS
        ).to_pylist()
        predictions = race_predictions(
            prediction_rows, variant=cast(str, config["pl_variant"]), test_years=settings.test_years
        )
        del prediction_rows
        # ADR-044: earlier years' winners fit the blend; a year's fit never sees its own results.
        blend_rows = read_parquet(
            pl_path / "predictions.parquet", columns=PL_BLEND_COLUMNS
        ).to_pylist()
        blend_training = blend_training_races(
            blend_rows, variant=cast(str, config["pl_variant"]), test_years=settings.test_years
        )
        del blend_rows
        _pinned_bytes(pl_path / "predictions.parquet", cast(str, config["pl_predictions_sha256"]))
        _progress(
            "read_predictions",
            started,
            predicted_races=len(predictions),
            blend_races=sum(len(races) for races in blend_training.races.values()),
        )
        venues = cast(list[str], REFERENCE_BASES["venues"])
        last_year = settings.test_years[-1]
        training = _read_training(
            snapshot,
            first_year=settings.train_start_year,
            last_year=last_year,
            max_publication_age_seconds=settings.max_publication_age_seconds,
            graded_o1_years=frozenset(settings.test_years),
            started=started,
        )
        ra_by_race, hr_by_race = training.ra_by_race, training.hr_by_race
        graded_ids, training_hits, graded_o1 = (
            training.graded_ids,
            training.hits,
            training.graded_o1,
        )
        test_graded = sorted(
            race_id for race_id in graded_ids if int(race_id[:4]) in settings.test_years
        )
        wanted = set(test_graded)
        se_by_race = _by_race(
            [
                row
                for row in snapshot.read_period(
                    SE_TABLE,
                    columns=SE_COLUMNS,
                    start=f"{settings.test_years[0]}0101",
                    end=f"{last_year}1231",
                    venues=venues,
                )
                if race_identity(row) in wanted
            ],
            race_identity,
        )
        _progress("read_se", started, graded_test_races=len(test_graded))
        backtest = run_betting_backtest(
            settings=settings,
            graded_races=[
                GradedRaceInput(
                    race_id=race_id,
                    ra_rows=ra_by_race[race_id],
                    o1_rows=graded_o1.get(race_id, []),
                    se_rows=se_by_race.get(race_id, []),
                    hr_rows=hr_by_race.get(race_id, []),
                )
                for race_id in test_graded
            ],
            predictions=predictions,
            target_hold_stages=holds,
            training_hits=training_hits,
            blend_training=blend_training,
            graded_race_ids=graded_ids,
            config=config,
            inputs={
                "pl_evaluation": {
                    "path": str(pl_path),
                    "report_sha256": config["pl_report_sha256"],
                    "predictions_sha256": config["pl_predictions_sha256"],
                    "variant": config["pl_variant"],
                },
                "datamart": {
                    "path": str(datamart_path),
                    "manifest_sha256": pl_report["datamart_manifest_sha256"],
                },
                "snapshot": snapshot.manifest(),
            },
            provenance=experiment_provenance(),
        )
        _progress("evaluate", started)
        with publish_directory(output_path) as staging:
            write_json(staging / "report.json", backtest.report, overwrite=False)
            write_parquet(bets_table(backtest), staging / "bets.parquet")
            write_parquet(races_table(backtest), staging / "races.parquet")
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo(f"{_COMMAND} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"{_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(_summary(output_path, len(test_graded), backtest.report, started))


_FIT_COMMAND = "model fit-betting-estimator"
_FIT_TABLES = ("NL_RA_RACE", "NL_HR_PAY", "ARCHIVE_O1_ODDS_TANFUKUWAKU")
_RECORDED = "the backtest report's recorded inputs"


def model_fit_betting_estimator(
    backtest_path: Annotated[Path, typer.Option("--backtest")],
    backtest_report_sha256: Annotated[str, typer.Option("--backtest-report-sha256")],
    pl_evaluation_path: Annotated[Path, typer.Option("--pl-evaluation")],
    processed_root: Annotated[Path, typer.Option("--processed-root")],
    output_path: Annotated[Path, typer.Option("--output")],
) -> None:
    """Save the race-day estimator for the year after a backtest's last test year (ADR-045).

    Every setting comes from the pinned backtest report; its recorded paths are not used.
    """
    # Keep NumPy and Arrow out of imports and CLI help.
    from configuration.betting_backtest import validate_betting_backtest_config
    from data.loader.fixed_snapshot import FixedSnapshot
    from data.loader.read_parquet import read_parquet
    from data.storage.directory_publisher import publish_directory
    from models.artifacts.betting_estimator import (
        read_betting_estimator,
        require_storable_width_bands,
        write_betting_estimator,
    )
    from models.experiments.betting_estimator import (
        backtest_results,
        fit_betting_estimator,
        require_same_estimates,
    )
    from models.experiments.provenance import experiment_provenance
    from models.serialization.betting_inputs import PL_BLEND_COLUMNS, blend_training_races

    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        if _HEX64.fullmatch(backtest_report_sha256) is None:
            raise ValueError("--backtest-report-sha256 must be 64 lowercase hex digits")
        _reject_output_inside(
            output_path,
            (backtest_path, processed_root, pl_evaluation_path),
            what="estimator output",
        )
        report_bytes = _pinned_bytes(
            backtest_path / "report.json",
            backtest_report_sha256,
            source="--backtest-report-sha256",
        )
        try:
            report = json.loads(report_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("backtest report is not valid JSON") from exc
        if not isinstance(report, dict):
            raise ValueError("backtest report must be a JSON object")
        config = validate_betting_backtest_config(report.get("config"))
        settings = _settings(config)
        # Fail before any row is read when the artifact could not store the bands.
        require_storable_width_bands(settings.place_width_bands)
        results = backtest_results(report, settings.test_years)
        inputs = _backtest_inputs(report.get("inputs"), config)
        pl = cast(dict[str, str], inputs["pl_evaluation"])
        for name, digest in (
            ("report.json", "report_sha256"),
            ("predictions.parquet", "predictions_sha256"),
        ):
            _pinned_bytes(pl_evaluation_path / name, pl[digest], source=_RECORDED)
        recorded = cast(dict[str, object], inputs["snapshot"])
        snapshot = FixedSnapshot(processed_root, snapshot_id=cast(str, recorded["snapshot_id"]))
        _reject_output_inside(output_path, (snapshot.path,), what="estimator output")
        # Hash the tables before any row is read; manifest() rechecks them at the end.
        snapshot.pin(_FIT_TABLES)
        pinned = cast(dict[str, dict[str, str]], snapshot.pinned_manifest()["tables"])
        recorded_tables = cast(dict[str, dict[str, str]], recorded["tables"])
        for table in _FIT_TABLES:
            if pinned[table]["sha256"] != recorded_tables[table]["sha256"]:
                raise ValueError(f"snapshot {table} differs from the backtest's input")
        blend_rows = read_parquet(
            pl_evaluation_path / "predictions.parquet", columns=PL_BLEND_COLUMNS
        ).to_pylist()
        blend_training = blend_training_races(
            blend_rows, variant=pl["variant"], test_years=settings.test_years
        )
        del blend_rows
        _pinned_bytes(
            pl_evaluation_path / "predictions.parquet", pl["predictions_sha256"], source=_RECORDED
        )
        _progress(
            "read_predictions",
            started,
            blend_races=sum(len(races) for races in blend_training.races.values()),
        )
        training = _read_training(
            snapshot,
            first_year=settings.train_start_year,
            last_year=settings.test_years[-1],
            max_publication_age_seconds=settings.max_publication_age_seconds,
            graded_o1_years=frozenset(),
            started=started,
        )
        manifest = snapshot.manifest()
        tables = cast(dict[str, dict[str, str]], manifest["tables"])
        sources = {
            "backtest_report_sha256": backtest_report_sha256,
            "pl_evaluation": {
                "report_sha256": pl["report_sha256"],
                "predictions_sha256": pl["predictions_sha256"],
                "variant": pl["variant"],
            },
            "snapshot": {
                "snapshot_id": manifest["snapshot_id"],
                "tables": {table: tables[table]["sha256"] for table in _FIT_TABLES},
            },
        }
        record, fitted = fit_betting_estimator(
            settings=settings,
            results=results,
            hits=training.hits,
            graded_race_ids=training.graded_ids,
            blend_training=blend_training,
            sources=sources,
            provenance=experiment_provenance(),
        )
        _progress("fit", started, target_year=record.target_year, method=record.method)
        with publish_directory(output_path) as staging:
            digest = write_betting_estimator(staging, record)
            written = read_betting_estimator(staging, expected_manifest_sha256=digest)
            require_same_estimates(fitted, written.record, training.hits)
    except KeyboardInterrupt as exc:
        typer.echo(f"{_FIT_COMMAND} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"{_FIT_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"ev betting estimator: {output_path} manifest_sha256={digest} "
        f"target_year={record.target_year} method={record.method} "
        f"seconds={perf_counter() - started:.1f}"
    )


def _backtest_inputs(value: object, config: Mapping[str, object]) -> dict[str, object]:
    """Return a backtest report's PL evaluation and snapshot identities, checked."""
    if not isinstance(value, dict):
        raise ValueError("backtest report inputs must be an object")
    pl = value.get("pl_evaluation")
    snapshot = value.get("snapshot")
    if (
        not isinstance(pl, dict)
        or pl.get("report_sha256") != config["pl_report_sha256"]
        or pl.get("predictions_sha256") != config["pl_predictions_sha256"]
        or pl.get("variant") != config["pl_variant"]
    ):
        raise ValueError("backtest report PL evaluation inputs differ from its config")
    tables = snapshot.get("tables") if isinstance(snapshot, dict) else None
    if (
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("snapshot_id"), str)
        or _SNAPSHOT_ID.fullmatch(cast(str, snapshot["snapshot_id"])) is None
        or not isinstance(tables, dict)
        or any(
            not isinstance(tables.get(table), dict)
            or not isinstance(tables[table].get("sha256"), str)
            or _HEX64.fullmatch(tables[table]["sha256"]) is None
            for table in _FIT_TABLES
        )
    ):
        raise ValueError("backtest report snapshot inputs are invalid")
    return {"pl_evaluation": pl, "snapshot": snapshot}


def _settings(config: Mapping[str, object]) -> BettingBacktestSettings:
    from models.betting.policy import BettingPolicy
    from models.experiments.betting_backtest import BettingBacktestSettings

    policy = cast(dict[str, object], config["policy"])
    final_odds = cast(dict[str, object], config["final_odds"])
    bootstrap = cast(dict[str, object], config["bootstrap"])
    estimation = cast(dict[str, object], config["estimation"])
    return BettingBacktestSettings(
        test_years=tuple(cast(list[int], config["test_years"])),
        policy=BettingPolicy(
            min_expected_return=float(cast(float, policy["min_expected_return"])),
            kelly_fraction=float(cast(float, policy["kelly_fraction"])),
            bankroll_yen=cast(int, policy["bankroll_yen"]),
            annual_budget_yen=cast(int, policy["annual_budget_yen"]),
            race_budget_yen=cast(int, policy["race_budget_yen"]),
            unit_yen=cast(int, policy["unit_yen"]),
        ),
        train_start_year=cast(int, final_odds["train_start_year"]),
        max_publication_age_seconds=cast(int, final_odds["max_publication_age_seconds"]),
        place_bands=tuple(float(v) for v in cast(list[float], final_odds["place_mid_bands"])),
        quantiles=tuple(float(v) for v in cast(list[float], final_odds["quantiles"])),
        min_hits=cast(int, final_odds["min_hits"]),
        graded_shrinkage_k=cast(int, final_odds["graded_shrinkage_k"]),
        bootstrap_resamples=cast(int, bootstrap["resamples"]),
        bootstrap_seed=cast(int, bootstrap["seed"]),
        bootstrap_confidence=float(cast(float, bootstrap["confidence"])),
        blend_min_races=cast(int, estimation["blend_min_races"]),
        blend_tolerance=float(cast(float, estimation["blend_tolerance"])),
        blend_max_iterations=cast(int, estimation["blend_max_iterations"]),
        place_width_bands=tuple(
            float(v) for v in cast(list[float], estimation["place_width_bands"])
        ),
    )


def _reject_output_inside(
    output_path: Path, inputs: Sequence[Path], *, what: str = "backtest output"
) -> None:
    """Reject an output that equals or lies inside an input directory, after resolution."""
    target = output_path.resolve()
    for path in inputs:
        if target.is_relative_to(path.resolve()):
            raise ValueError(f"{what} must stay outside every input directory")


def _pinned_bytes(
    path: Path, expected_sha256: str, *, source: str = "the configured value"
) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"{path.name} SHA-256 differs from {source}")
    return data


def _pl_report(data: bytes, variant: str, test_years: Sequence[int]) -> dict[str, object]:
    """Return the identities the backtest needs from a pinned PL evaluation report."""
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
    if report.get("test_years") != list(test_years):
        raise ValueError("PL evaluation test_years differ from the configured test_years")
    variants = report.get("config", {}).get("variants")
    if not isinstance(variants, list) or variant not in [
        item.get("name") for item in variants if isinstance(item, dict)
    ]:
        raise ValueError(f"PL evaluation has no variant {variant!r}")
    try:
        source = report["race_subsets"]["jra_flat_graded_stakes_v1"]["source"]
        datamart_path = report["config"]["datamart_path"]
        manifest_sha256 = report["datamart"]["manifest_sha256"]
    except (KeyError, TypeError) as exc:
        raise ValueError("PL evaluation report lacks the graded source or datamart") from exc
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("snapshot_id"), str)
        or not isinstance(source.get("sha256"), str)
        or not isinstance(datamart_path, str)
        or not isinstance(manifest_sha256, str)
    ):
        raise ValueError("PL evaluation report lacks the graded source or datamart")
    return {
        "source": source,
        "datamart_path": datamart_path,
        "datamart_manifest_sha256": manifest_sha256,
    }


def _target_hold_stages(held: Sequence[Mapping[str, object]]) -> dict[str, str]:
    stages: dict[str, str] = {}
    for item in held:
        race_id = cast(str, item["race_id"])
        if race_id in stages:
            raise ValueError(f"datamart holds target race {race_id} more than once")
        stages[race_id] = cast(str, item["stage"])
    return stages


def _by_race(
    rows: Sequence[dict[str, object]], identity: _Identity
) -> dict[str, list[dict[str, object]]]:
    """Group rows by their complete race key; a malformed key fails the run."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(identity(row), []).append(row)
    return grouped


def _distinct(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Return rows with identical copies counted once, as ``race_freeze`` does."""
    unique: dict[tuple[tuple[str, object], ...], dict[str, object]] = {}
    for row in rows:
        unique.setdefault(tuple(sorted(row.items())), row)
    return list(unique.values())


@dataclass(frozen=True)
class _Training:
    """Hold the rows and hit observations that fit the place corrections."""

    ra_by_race: dict[str, list[dict[str, object]]]
    hr_by_race: dict[str, list[dict[str, object]]]
    graded_ids: frozenset[str]
    hits: list[HitObservation]
    graded_o1: dict[str, list[dict[str, object]]]


def _read_training(
    snapshot: FixedSnapshot,
    *,
    first_year: int,
    last_year: int,
    max_publication_age_seconds: int,
    graded_o1_years: frozenset[int],
    started: float,
) -> _Training:
    """Read RA, HR and O1 from ``first_year`` through ``last_year`` (inclusive).

    Returns the races grouped by key, the graded subset (races with one distinct RA row,
    classified by ``jra_flat_graded_stakes_v1``), every race's ``place_mid`` and
    ``place_low`` hits, and the freeze-time O1 rows of graded races in
    ``graded_o1_years``. O1 is read per year in ADR-042's two passes.
    """
    from make_features.real_market import KEY_COLUMNS
    from make_features.reference_raw import race_identity
    from make_features.reference_rules import REFERENCE_BASES
    from models.serialization.final_odds_observations import (
        HR_COLUMNS,
        HR_TABLE,
        O1_COLUMNS,
        O1_TABLE,
        RA_COLUMNS,
        RA_TABLE,
        ObservationHold,
        build_race_observations,
        race_freeze,
    )
    from models.serialization.race_subsets import (
        JRA_FLAT_GRADED_STAKES_V1,
        classify_nl_ra_race_rows,
    )

    venues = cast(list[str], REFERENCE_BASES["venues"])
    start, end = f"{first_year}0101", f"{last_year}1231"
    ra_by_race = _by_race(
        snapshot.read_period(RA_TABLE, columns=RA_COLUMNS, start=start, end=end, venues=venues),
        race_identity,
    )
    hr_by_race = _by_race(
        snapshot.read_period(HR_TABLE, columns=HR_COLUMNS, start=start, end=end, venues=venues),
        race_identity,
    )
    graded_ids = classify_nl_ra_race_rows(
        [rows[0] for rows in (_distinct(rows) for rows in ra_by_race.values()) if len(rows) == 1]
    ).subsets[JRA_FLAT_GRADED_STAKES_V1]
    _progress("read_races", started, races=len(ra_by_race), graded_races=len(graded_ids))
    o1 = snapshot.publication_reader(
        O1_TABLE, key_columns=KEY_COLUMNS, value_columns=O1_COLUMNS, venues=venues
    )
    hits: list[HitObservation] = []
    graded_o1: dict[str, list[dict[str, object]]] = {}
    for year in range(first_year, last_year + 1):
        race_ids = sorted(race_id for race_id in ra_by_race if race_id[:4] == f"{year:04d}")
        freezes: dict[str, datetime] = {}
        for race_id in race_ids:
            try:
                freezes[race_id] = race_freeze(race_id, ra_by_race[race_id])
            except ObservationHold:
                continue  # the race has no freeze; it gives no hits and is held if graded
        o1_rows = _publications(o1, year, freezes, started, race_identity)
        for race_id in race_ids:
            observations = build_race_observations(
                race_id,
                ra_rows=ra_by_race[race_id],
                o1_rows=o1_rows.get(race_id, ()),
                o2_rows=(),
                hr_rows=hr_by_race.get(race_id, ()),
                max_publication_age_seconds=max_publication_age_seconds,
            )
            hits.extend(
                hit for hit in observations.hits if hit.bet_type in ("place_mid", "place_low")
            )
            if year in graded_o1_years and race_id in graded_ids:
                graded_o1[race_id] = o1_rows.get(race_id, [])
        del o1_rows
    return _Training(ra_by_race, hr_by_race, frozenset(graded_ids), hits, graded_o1)


def _publications(
    reader: PublicationReader,
    year: int,
    freezes: Mapping[str, datetime],
    started: float,
    identity: _Identity,
) -> dict[str, list[dict[str, object]]]:
    """Read one year's selected O1 rows in ADR-042's two passes, grouped by race."""
    from models.serialization.final_odds_observations import select_publication_pairs

    scan_started = perf_counter()
    scanned = reader.scan(year)
    pairs = select_publication_pairs(scanned, freezes)
    scan_seconds = perf_counter() - scan_started
    scan_rows = len(scanned)
    del scanned
    read_started = perf_counter()
    rows = reader.read_pairs(year, sorted(pairs, key=lambda pair: (pair[0], pair[1] or "")))
    _progress(
        "publications",
        started,
        table="o1",
        year=year,
        scan_rows=scan_rows,
        scan_seconds=round(scan_seconds, 1),
        pairs=len(pairs),
        rows=len(rows),
        read_seconds=round(perf_counter() - read_started, 1),
    )
    return _by_race(rows, identity)


def _summary(output_path: Path, graded: int, report: Mapping[str, object], started: float) -> str:
    total = cast(dict[str, object], report["all_test_years"])
    rate = total["recovery_rate"]
    recovery = "none" if rate is None else f"{cast(float, rate):.4f}"
    return (
        f"ev betting backtest: {output_path} graded_races={graded} "
        f"purchased_races={total['purchased_races']} stake_yen={total['stake_yen']} "
        f"receipt_yen={total['receipt_yen']} recovery_rate={recovery} "
        f"seconds={perf_counter() - started:.1f}"
    )


def _progress(phase: str, started: float, **values: object) -> None:
    """Print one stderr line; ``seconds`` is always the time since the command started."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    typer.echo(
        f"phase={phase}{' ' + fields if fields else ''} seconds={perf_counter() - started:.1f}",
        err=True,
    )
