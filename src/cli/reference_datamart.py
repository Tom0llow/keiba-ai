"""Build and atomically publish reference features, one calendar year at a time.

``build-reference`` publishes the labeled datamart (ADR-034). ``build-reference-prediction``
publishes label-free features for one race date (ADR-036), with the calculation settings
of a labeled datamart pinned by its manifest SHA-256. ``build-reference-prediction-live``
(ADR-037) prepares that date once, then publishes each race as soon as race-day-odds has
published its 0B41/0B42 time series fetched at or after freeze.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Annotated, Literal, NamedTuple, cast

import typer

from configuration.reference_datamart import (
    load_reference_datamart_config,
    validate_reference_datamart_config,
)
from data.loader.fixed_snapshot import FixedSnapshot, PeriodReader
from data.loader.race_version import (
    RaceVersion,
    current_race_version_id,
    read_race_version,
)
from data.loader.reference_input import read_reference_workouts, read_reference_year
from data.storage.directory_publisher import publish_directory
from domain.race_key import RaceKey
from jra_van_retriever.contracts.odds import PREDICTION_SPECS
from make_datamart.tables.reference import (
    ReferenceDatamartWriter,
    read_reference_datamart_label_usable_through,
    read_reference_datamart_manifest,
)
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import FeatureRegistry, create_feature_registry
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
    PreparedTargets,
    ReferenceDatamartBuilder,
    ReferenceYearOutput,
    TargetSchedule,
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
# The live command never reads the pinned snapshot's odds archives (about 3 GB).
_LIVE_TABLES = ("NL_RA_RACE", "NL_SE_RACE_UMA", "NL_HC_HANRO", "NL_WC_WOOD", "NL_UM_UMA")
_O1 = "ARCHIVE_O1_ODDS_TANFUKUWAKU"
_O2 = "ARCHIVE_O2_ODDS_UMAREN"
_LOG = "ARCHIVE_CAPTURE_LOG"
_LOG_COLUMNS = (
    *KEY_COLUMNS,
    "capture_id",
    "data_spec",
    "scheduled_start_at",
    "started_at",
    "status",
    "reason",
)
_FETCH_SPECS = PREDICTION_SPECS
# Freeze is five minutes and JRA sales close two minutes before the start.
_SALES_CLOSE_AFTER_FREEZE_SECONDS = 180
_LIVE = "datamart build-reference-prediction-live"


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
        pinned = _pinned_source(
            reference_datamart, reference_datamart_manifest_sha256, target, features_config
        )
        settings, rules, registry = pinned.settings, pinned.rules, pinned.registry
        source_binding = pinned.binding
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
        if builder.contract.as_metadata() != pinned.contract:
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
                market_source={"kind": "complete_snapshot"},
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


def datamart_build_reference_prediction_live(
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
    poll_interval_seconds: Annotated[int, typer.Option("--poll-interval-seconds")] = 5,
    deadline_seconds: Annotated[int, typer.Option("--deadline-seconds")] = 150,
) -> None:
    """Prepare one race date once, then publish each race after its freeze (ADR-037).

    Each race is calculated from the 0B41/0B42 time series that race-day-odds fetched at
    or after freeze and published with its capture log. One JSON line per race goes to
    stdout; races without such a fetch by freeze + ``--deadline-seconds`` are held.
    """
    started = perf_counter()
    target = race_datetime.date()
    try:
        if type(poll_interval_seconds) is not int or poll_interval_seconds < 1:
            raise ValueError("--poll-interval-seconds must be a positive integer")
        if not 1 <= deadline_seconds <= _SALES_CLOSE_AFTER_FREEZE_SECONDS:
            raise ValueError(
                f"--deadline-seconds must be from 1 through {_SALES_CLOSE_AFTER_FREEZE_SECONDS}"
            )
        _check_new_output(output_path)
        _check_outside(output_path, processed_root)
        pinned = _pinned_source(
            reference_datamart, reference_datamart_manifest_sha256, target, features_config
        )
        settings, rules = pinned.settings, pinned.rules
        snapshot = FixedSnapshot(processed_root, snapshot_id=snapshot_id)
        snapshot.pin(_LIVE_TABLES)
        _progress("hash", started)
        stamp = target.strftime("%Y%m%d")
        _require_races(
            snapshot.read_period(
                "NL_RA_RACE",
                columns=KEY_COLUMNS,
                start=stamp,
                end=stamp,
                venues=cast(list[str], rules["venues"]),
            ),
            target,
        )
        builder = ReferenceDatamartBuilder(
            settings=settings,
            rules=rules,
            registry=pinned.registry,
            target_start=target,
            target_end=target,
            snapshot=snapshot.pinned_manifest(),
            pedigree_rows=snapshot.read_all("NL_UM_UMA", columns=UM_COLUMNS),
            labeled=False,
        )
        if builder.contract.as_metadata() != pinned.contract:
            raise ValueError("calculation contract differs from the reference datamart")
        history_held: list[dict[str, object]] = []
        for year in builder.years:
            year_started = perf_counter()
            inputs = _year_inputs(snapshot, builder, year, settings, rules, require_date=target)
            if year < target.year:
                output = builder.add_year(year, **inputs._asdict(), markets=_no_markets)
                history_held.extend(output.held)
                _progress("year", year_started, year=year, held=len(output.held))
                del output
        prepared = builder.prepare_targets(target.year, **inputs._asdict())
        history_held.extend(h for h in prepared.held if h["role"] == "history")
        _progress("prepare", started, targets=len(prepared.schedules))
        context = _LiveContext(
            builder=builder,
            prepared=prepared,
            history_held=tuple(history_held),
            snapshot=snapshot.manifest(),
            provenance=experiment_provenance(),
            source_binding=pinned.binding,
            processed_root=processed_root,
            output_path=output_path,
            preparation_config={
                "reference_datamart": str(reference_datamart.resolve()),
                "reference_datamart_manifest_sha256": reference_datamart_manifest_sha256,
                "date": target.isoformat(),
                "processed_root": str(processed_root.expanduser().resolve()),
                "snapshot_id": snapshot.path.name,
                "features_config": str(features_config.resolve()),
                "calculation_settings": settings,
                "reference_rules": rules,
                "poll_interval_seconds": poll_interval_seconds,
                "deadline_seconds": deadline_seconds,
            },
        )
        _check_new_output(output_path)
        output_path.mkdir()
        freshness = builder.freshness()
        typer.echo(
            "freshness " + " ".join(f"{k}={freshness[k]}" for k in sorted(freshness)), err=True
        )
        outcomes = [
            LiveOutcome.held(cast(str, item["race_id"]), item)
            for item in prepared.held
            if item["role"] == "target"
        ]
        for outcome in outcomes:
            _emit(outcome)
        outcomes += run_live_races(
            prepared.schedules,
            now=_clock,
            sleep=_sleep,
            poll_seconds=poll_interval_seconds,
            deadline_seconds=deadline_seconds,
            find_fetch=_FetchFinder(processed_root).find,
            complete=context.complete,
            report=_emit,
        )
    except KeyboardInterrupt as exc:
        typer.echo(f"{_LIVE} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Published races stay; any staging of an unfinished race is removed.
        typer.echo(f"{_LIVE} failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    published = sum(outcome.status == "published" for outcome in outcomes)
    typer.echo(
        f"race_day_features date={target.isoformat()} targets={len(outcomes)} "
        f"published={published} held={len(outcomes) - published} "
        f"seconds={perf_counter() - started:.3f}",
        err=True,
    )


def _clock() -> datetime:
    return datetime.now(UTC)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


@dataclass(frozen=True)
class LiveOutcome:
    """One race's result, printed as one JSON line on stdout."""

    race_id: str
    status: Literal["published", "held"]
    stage: str | None
    reason: str | None
    output: str | None
    manifest_sha256: str | None
    rows: int

    @classmethod
    def held(cls, race_id: str, hold: Mapping[str, object]) -> LiveOutcome:
        """Return an unpublished hold."""
        return cls(race_id, "held", str(hold["stage"]), str(hold["reason"]), None, None, 0)

    def as_json(self) -> str:
        """Return the stdout line with sorted keys."""
        return json.dumps(
            {
                "race_id": self.race_id,
                "status": self.status,
                "stage": self.stage,
                "reason": self.reason,
                "output": self.output,
                "manifest_sha256": self.manifest_sha256,
                "rows": self.rows,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


def _emit(outcome: LiveOutcome) -> None:
    typer.echo(outcome.as_json())


@dataclass(frozen=True)
class ReadyFetch:
    """A race version holding one complete prediction fetch that started after freeze."""

    version: RaceVersion
    capture_id: str
    started_at: datetime
    # Seconds spent reading and hashing the race version, for the per-race progress line.
    read_seconds: float = 0.0


@dataclass(frozen=True)
class FetchLookup:
    """What a race's published version says about its prediction fetch."""

    kind: Literal["pending", "ready", "terminal"]
    ready: ReadyFetch | None = None
    reason: str | None = None


def find_prediction_fetch(version: RaceVersion | None, schedule: TargetSchedule) -> FetchLookup:
    """Select the race's completed 0B41/0B42 fetch from its published capture log.

    A fetch qualifies when both DataSpecs of one capture are archived for the scheduled
    start and it started at or after freeze. A terminal fetch that is not archived is
    reported, and two qualifying fetches are ambiguous.
    """
    if version is None:
        return FetchLookup("pending")
    by_capture: dict[str, list[dict[str, object]]] = {}
    for row in version.rows.get(_LOG, []):
        if row["data_spec"] in _FETCH_SPECS:
            by_capture.setdefault(cast(str, row["capture_id"]), []).append(row)
    ready: list[ReadyFetch] = []
    failure: str | None = None
    for capture_id, rows in sorted(by_capture.items()):
        if {row["data_spec"] for row in rows} != _FETCH_SPECS or len(rows) != 2:
            continue
        statuses = {cast(str, row["status"]) for row in rows}
        if "running" in statuses:
            continue
        if statuses != {"archived"}:
            row = next(row for row in rows if row["status"] != "archived")
            failure = f"race_day_fetch_{row['status']}: {row['reason']}"
            continue
        if any(_aware(row["scheduled_start_at"]) != schedule.scheduled_start_at for row in rows):
            continue
        started = max(_aware(row["started_at"]) for row in rows)
        if started >= schedule.freeze_at:
            ready.append(ReadyFetch(version, capture_id, started))
    if len(ready) > 1:
        return FetchLookup("terminal", reason="ambiguous_race_day_fetch")
    if ready:
        return FetchLookup("ready", ready=ready[0])
    if failure is not None:
        return FetchLookup("terminal", reason=failure)
    return FetchLookup("pending")


def _aware(value: object) -> datetime:
    parsed = datetime.fromisoformat(cast(str, value))
    if parsed.tzinfo is None:
        raise ValueError("race-day capture log clocks must be timezone-aware")
    return parsed


class _FetchFinder:
    """Read a race's version only when its CURRENT pointer has changed.

    CURRENT is opened once per poll: race-day-odds replaces it, and on Windows an open
    reader makes that replacement retry (``publish_pointer``).
    """

    def __init__(self, processed_root: Path) -> None:
        self._processed_root = processed_root
        self._seen: dict[str, tuple[str, FetchLookup]] = {}

    def find(self, schedule: TargetSchedule) -> FetchLookup:
        key = _race_key(schedule.race_id)
        try:
            current = current_race_version_id(self._processed_root, key)
        except PermissionError:
            # On Windows CURRENT can be unreadable while race-day-odds replaces it; the
            # next poll reads the new pointer.
            return FetchLookup("pending")
        if current is None:
            return FetchLookup("pending")
        cached = self._seen.get(schedule.race_id)
        if cached is not None and cached[0] == current:
            return cached[1]
        started = perf_counter()
        version = read_race_version(
            self._processed_root,
            key,
            columns={_O1: MARKET_O1_COLUMNS, _O2: MARKET_O2_COLUMNS, _LOG: _LOG_COLUMNS},
            optional=frozenset({_LOG}),
            snapshot_id=current,
        )
        read_seconds = perf_counter() - started
        lookup = find_prediction_fetch(version, schedule)
        if lookup.ready is not None:
            lookup = FetchLookup("ready", ready=replace(lookup.ready, read_seconds=read_seconds))
        self._seen[schedule.race_id] = (current, lookup)
        return lookup


def _race_key(race_id: str) -> RaceKey:
    return RaceKey(
        datetime.strptime(race_id[:8], "%Y%m%d").date(),
        race_id[8:10],
        race_id[10:12],
        race_id[12:14],
        race_id[14:16],
    )


@dataclass(frozen=True)
class _LiveContext:
    builder: ReferenceDatamartBuilder
    prepared: PreparedTargets
    history_held: tuple[dict[str, object], ...]
    snapshot: dict[str, object]
    provenance: dict[str, object]
    source_binding: dict[str, object]
    processed_root: Path
    output_path: Path
    preparation_config: dict[str, object]

    def complete(self, schedule: TargetSchedule, fetch: ReadyFetch) -> LiveOutcome:
        """Calculate one race from its pinned fetch and publish it as its own output."""
        started = perf_counter()
        rows = fetch.version.rows
        result = self.prepared.calculate(
            schedule.race_id, rows[_O1], rows[_O2], observed_through=fetch.started_at
        )
        calculated = perf_counter()
        destination = self.output_path / schedule.race_id
        builder = self.builder
        with publish_directory(destination) as staging:
            writer = ReferenceDatamartWriter(
                staging,
                columns=builder.columns,
                available_at_groups=builder.available_at_groups,
                contract=builder.contract.as_metadata(),
                labeled=False,
            )
            writer.write_year(
                builder.target_start.year,
                result.rows,
                [] if result.race is None else [result.race],
            )
            manifest = builder.prediction_manifest(
                snapshot=self.snapshot,
                provenance=self.provenance,
                preparation_config=self.preparation_config,
                source_datamart=self.source_binding,
                market_source={
                    "kind": "race_day_prediction_fetch",
                    "race_id": schedule.race_id,
                    "scheduled_start_at": schedule.scheduled_start_at.isoformat(),
                    "freeze_at": schedule.freeze_at.isoformat(),
                    "capture_id": fetch.capture_id,
                    "data_specs": sorted(_FETCH_SPECS),
                    "started_at": fetch.started_at.isoformat(),
                    "snapshot_id": fetch.version.snapshot_id,
                    "tables": dict(fetch.version.sha256),
                },
            )
            held = [*self.history_held, *([] if result.hold is None else [result.hold])]
            manifest_sha256 = writer.finish(manifest, held)
        _progress(
            "race",
            started,
            race=schedule.race_id,
            read_seconds=f"{fetch.read_seconds:.3f}",
            calculate_seconds=f"{calculated - started:.3f}",
            publish_seconds=f"{perf_counter() - calculated:.3f}",
        )
        hold = result.hold
        return LiveOutcome(
            schedule.race_id,
            "published",
            None if hold is None else str(hold["stage"]),
            None if hold is None else str(hold["reason"]),
            str(destination),
            manifest_sha256,
            len(result.rows),
        )


def run_live_races(
    schedules: Sequence[TargetSchedule],
    *,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    poll_seconds: int,
    deadline_seconds: int,
    find_fetch: Callable[[TargetSchedule], FetchLookup],
    complete: Callable[[TargetSchedule, ReadyFetch], LiveOutcome],
    report: Callable[[LiveOutcome], None],
) -> list[LiveOutcome]:
    """Poll the prepared races in freeze order until each is published or held.

    A race is examined only after its freeze. A ready fetch is calculated and published,
    unless it is first seen after sales close (freeze + 180 s), when it is held as
    ``race_day_sales_closed``. A terminal unarchived fetch is held at once. A race whose
    fetch is still not published after freeze + ``deadline_seconds`` is held as
    ``race_day_fetch_not_published``. Races already late when the loop starts follow the
    same rules after one look at their version.
    """
    pending = sorted(schedules, key=lambda s: (s.freeze_at, s.race_id))
    outcomes: list[LiveOutcome] = []
    while pending:
        current = now()
        for schedule in list(pending):
            if current < schedule.freeze_at:
                break
            outcome: LiveOutcome | None = None
            lookup = find_fetch(schedule)
            # Judge the race at the moment its version was seen, not at the start of the
            # pass: earlier races calculated in the same pass take time.
            seen = now()
            closed = seen > schedule.freeze_at + timedelta(
                seconds=_SALES_CLOSE_AFTER_FREEZE_SECONDS
            )
            if lookup.kind == "ready" and closed:
                # Features first seen after sales close are useless and look on-time.
                outcome = _live_hold(schedule.race_id, SALES_CLOSED)
            elif lookup.kind == "ready":
                assert lookup.ready is not None
                outcome = complete(schedule, lookup.ready)
            elif lookup.kind == "terminal":
                outcome = _live_hold(schedule.race_id, cast(str, lookup.reason))
            elif seen > schedule.freeze_at + timedelta(seconds=deadline_seconds):
                outcome = _live_hold(schedule.race_id, NOT_PUBLISHED)
            if outcome is not None:
                report(outcome)
                outcomes.append(outcome)
                pending.remove(schedule)
        if pending:
            due = [s for s in pending if s.freeze_at <= current]
            wait = (
                poll_seconds
                if due
                else min(poll_seconds, (pending[0].freeze_at - current).total_seconds())
            )
            sleep(max(wait, 0.0))
    return outcomes


NOT_PUBLISHED = "race_day_fetch_not_published"
SALES_CLOSED = "race_day_sales_closed"


def _live_hold(race_id: str, reason: str) -> LiveOutcome:
    return LiveOutcome(race_id, "held", "target_pre_freeze", reason, None, None, 0)


@dataclass(frozen=True)
class _PinnedSource:
    settings: dict[str, object]
    rules: dict[str, object]
    registry: FeatureRegistry
    contract: object
    binding: dict[str, object]


def _pinned_source(
    reference_datamart: Path, manifest_sha256: str, target: date, features_config: Path
) -> _PinnedSource:
    """Validate the labeled datamart's settings, contract, columns and definitions."""
    if _HEX64.fullmatch(manifest_sha256) is None:
        raise ValueError("--reference-datamart-manifest-sha256 must be 64 lowercase hex digits")
    source = read_reference_datamart_manifest(
        reference_datamart, expected_manifest_sha256=manifest_sha256
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
    binding = _source_binding(source, reference_datamart, manifest_sha256)
    return _PinnedSource(settings, rules, registry, source["contract"], binding)


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
    venues = cast(list[str], rules["venues"])
    inputs = _year_inputs(snapshot, builder, year, settings, rules, require_date=require_date)
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
    return builder.add_year(year, **inputs._asdict(), markets=markets)


def _year_inputs(
    snapshot: FixedSnapshot,
    builder: ReferenceDatamartBuilder,
    year: int,
    settings: dict[str, object],
    rules: dict[str, object],
    *,
    require_date: date | None = None,
) -> _YearInputs:
    """Read one calendar year's history projections and workout sessions."""
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
    return _YearInputs(ra_rows, se_rows, workouts)


class _YearInputs(NamedTuple):
    ra_rows: list[dict[str, object]]
    se_rows: list[dict[str, object]]
    workout_rows: list[tuple[str, dict[str, object]]]


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


def _progress(phase: str, started: float, **values: int | str) -> None:
    details = "".join(f" {name}={value}" for name, value in values.items())
    typer.echo(f"phase={phase}{details} seconds={perf_counter() - started:.3f}", err=True)
