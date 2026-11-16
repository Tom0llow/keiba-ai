"""Evaluate hit-conditional final-odds corrections on yearly folds of one fixed snapshot."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, cast

import typer

if TYPE_CHECKING:
    from datetime import datetime

    from data.loader.fixed_snapshot import PublicationReader
    from models.experiments.final_odds_evaluation import FinalOddsEvaluationSettings

type _Identity = Callable[[Mapping[str, object]], str]


def model_evaluate_final_odds(
    output_path: Annotated[Path, typer.Option("--output")],
    config_dir: Annotated[Path, typer.Option("--config-dir")] = Path(
        "configs/final_odds_evaluation"
    ),
    config_name: Annotated[str, typer.Option("--config-name")] = "evaluate",
    overrides: Annotated[list[str] | None, typer.Option("--override")] = None,
) -> None:
    """Correct freeze-time odds to hit-conditional final odds and evaluate them by year."""
    # Keep Hydra, NumPy and Arrow out of imports and CLI help.
    from configuration.final_odds_evaluation import load_final_odds_evaluation_config
    from data.loader.fixed_snapshot import FixedSnapshot
    from data.saver.write_json import write_json
    from data.storage.directory_publisher import publish_directory
    from make_features.real_market import KEY_COLUMNS
    from make_features.reference_raw import race_identity
    from make_features.reference_rules import REFERENCE_BASES
    from models.experiments.final_odds_evaluation import FinalOddsRaceSubset, evaluate_final_odds
    from models.experiments.provenance import experiment_provenance
    from models.serialization.final_odds_observations import (
        HR_COLUMNS,
        HR_TABLE,
        O1_COLUMNS,
        O1_TABLE,
        O2_COLUMNS,
        O2_TABLE,
        RA_COLUMNS,
        RA_TABLE,
        ObservationHold,
        RaceObservations,
        build_race_observations,
        race_freeze,
    )
    from models.serialization.race_subsets import (
        JRA_FLAT_GRADED_STAKES_V1,
        JRA_FLAT_GRADED_STAKES_V1_DEFINITION,
        classify_nl_ra_race_rows,
    )

    started = perf_counter()
    try:
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must be a new non-symbolic-link path")
        if not output_path.parent.is_dir():
            raise ValueError("output parent directory must already exist")
        config = load_final_odds_evaluation_config(
            config_dir, config_name=config_name, overrides=overrides or ()
        )
        settings = _settings(config)
        max_age = cast(int, config["max_publication_age_seconds"])
        snapshot = FixedSnapshot(
            Path(cast(str, config["processed_root"])),
            snapshot_id=cast(str | None, config["snapshot_id"]),
        )
        if output_path.resolve().is_relative_to(snapshot.path.parent.parent):
            raise ValueError("evaluation output must stay outside immutable processed data")
        # Hash every source before any row is read; manifest() rechecks them at the end.
        snapshot.pin((RA_TABLE, HR_TABLE, O1_TABLE, O2_TABLE))
        venues = cast(list[str], REFERENCE_BASES["venues"])
        first_year, last_year = settings.train_start_year, settings.test_years[-1]
        start, end = f"{first_year}0101", f"{last_year}1231"
        ra_by_race = _by_race(
            snapshot.read_period(RA_TABLE, columns=RA_COLUMNS, start=start, end=end, venues=venues),
            race_identity,
        )
        hr_by_race = _by_race(
            snapshot.read_period(HR_TABLE, columns=HR_COLUMNS, start=start, end=end, venues=venues),
            race_identity,
        )
        _progress("read_races", started, races=len(ra_by_race), payout_races=len(hr_by_race))
        classification = classify_nl_ra_race_rows(
            [
                rows[0]
                for rows in (_distinct(rows) for rows in ra_by_race.values())
                if len(rows) == 1
            ]
        )
        pinned = cast(dict[str, dict[str, str]], snapshot.pinned_manifest()["tables"])
        race_subsets = {
            JRA_FLAT_GRADED_STAKES_V1: FinalOddsRaceSubset(
                race_ids=classification.subsets[JRA_FLAT_GRADED_STAKES_V1],
                definition=JRA_FLAT_GRADED_STAKES_V1_DEFINITION,
                source={
                    "table": RA_TABLE,
                    "sha256": pinned[RA_TABLE]["sha256"],
                    "snapshot_id": snapshot.path.name,
                },
            )
        }
        o1 = snapshot.publication_reader(
            O1_TABLE, key_columns=KEY_COLUMNS, value_columns=O1_COLUMNS, venues=venues
        )
        o2 = snapshot.publication_reader(
            O2_TABLE, key_columns=KEY_COLUMNS, value_columns=O2_COLUMNS, venues=venues
        )
        observations: list[RaceObservations] = []
        for year in range(first_year, last_year + 1):
            race_ids = sorted(race_id for race_id in ra_by_race if race_id[:4] == f"{year:04d}")
            freezes: dict[str, datetime] = {}
            for race_id in race_ids:
                try:
                    freezes[race_id] = race_freeze(race_id, ra_by_race[race_id])
                except ObservationHold:
                    continue  # build_race_observations records the same race hold
            o1_rows = _publications(o1, "o1", year, freezes, started, race_identity)
            o2_rows = _publications(o2, "o2", year, freezes, started, race_identity)
            observations.extend(
                build_race_observations(
                    race_id,
                    ra_rows=ra_by_race[race_id],
                    o1_rows=o1_rows.get(race_id, ()),
                    o2_rows=o2_rows.get(race_id, ()),
                    hr_rows=hr_by_race.get(race_id, ()),
                    max_publication_age_seconds=max_age,
                )
                for race_id in race_ids
            )
            del o1_rows, o2_rows
        snapshot_manifest = snapshot.manifest()
        evaluation = evaluate_final_odds(
            observations,
            settings,
            race_subsets=race_subsets,
            config=config,
            snapshot=snapshot_manifest,
            provenance=experiment_provenance(),
        )
        _progress("evaluate", started)
        with publish_directory(output_path) as staging:
            write_json(staging / "report.json", evaluation.report, overwrite=False)
        _progress("publish", started)
    except KeyboardInterrupt as exc:
        typer.echo("model evaluate-final-odds failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Every failure, expected or not, removes staging and reports one line.
        typer.echo(f"model evaluate-final-odds failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(_summary(output_path, len(observations), evaluation.report, started))


def _settings(config: Mapping[str, object]) -> FinalOddsEvaluationSettings:
    from models.experiments.final_odds_evaluation import FinalOddsEvaluationSettings

    bands = cast(dict[str, list[float]], config["bands"])
    bootstrap = cast(dict[str, object], config["bootstrap"])
    return FinalOddsEvaluationSettings(
        train_start_year=cast(int, config["train_start_year"]),
        test_years=tuple(cast(list[int], config["test_years"])),
        bands={
            "win": tuple(float(value) for value in bands["win"]),
            "place_low": tuple(float(value) for value in bands["place_low"]),
            "place_mid": tuple(float(value) for value in bands["place_mid"]),
            "quinella": tuple(float(value) for value in bands["quinella"]),
        },
        quantiles=tuple(float(value) for value in cast(list[float], config["quantiles"])),
        min_hits=cast(int, config["min_hits"]),
        graded_shrinkage_k=cast(int, config["graded_shrinkage_k"]),
        bootstrap_resamples=cast(int, bootstrap["resamples"]),
        bootstrap_seed=cast(int, bootstrap["seed"]),
        bootstrap_confidence=float(cast(float, bootstrap["confidence"])),
    )


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


def _publications(
    reader: PublicationReader,
    name: str,
    year: int,
    freezes: Mapping[str, datetime],
    started: float,
    identity: _Identity,
) -> dict[str, list[dict[str, object]]]:
    """Read one year's selected publication rows in two passes, grouped by race."""
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
        table=name,
        year=year,
        scan_rows=scan_rows,
        scan_seconds=round(scan_seconds, 1),
        pairs=len(pairs),
        rows=len(rows),
        read_seconds=round(perf_counter() - read_started, 1),
    )
    return _by_race(rows, identity)


def _summary(output_path: Path, races: int, report: Mapping[str, object], started: float) -> str:
    counts = cast(dict[str, dict[str, int]], report["counts"])
    hits = counts["hits_by_bet_type"]
    selection = cast(dict[str, dict[str, object]], report["selection"])
    selected = ",".join(
        f"{bet_type}:{value['selected_variant'] or 'unadopted'}"
        for bet_type, value in selection.items()
    )
    return (
        f"final odds evaluation: {output_path} races={races} "
        f"hits={hits['win']}/{hits['place_low']}/{hits['quinella']} "
        f"selected={selected} seconds={perf_counter() - started:.1f}"
    )


def _progress(phase: str, started: float, **values: object) -> None:
    """Print one stderr line; ``seconds`` is always the time since the command started."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    typer.echo(
        f"phase={phase}{' ' + fields if fields else ''} seconds={perf_counter() - started:.1f}",
        err=True,
    )
