"""Watch race-day features and publish each graded race's PL probabilities (ADR-039).

``model predict-pl-live`` starts once in the morning of a race date. It reads the saved
PL model (ADR-038) and the fixed snapshot's cards of that date, then watches the output
directory of ``datamart build-reference-prediction-live`` (ADR-037). Each JRA flat graded
race is predicted as soon as its features are published, and written to
``<output>/<race_id>/prediction.json``. One JSON line per race goes to stdout.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, Literal, cast

import typer

if TYPE_CHECKING:
    from data.loader.fixed_snapshot import FixedSnapshot
    from models.artifacts.pl_model import PLModel
    from models.experiments.pl_prediction import RaceTarget

_COMMAND = "model predict-pl-live"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TABLES = ("NL_RA_RACE", "NL_SE_RACE_UMA")
FEATURES_STAGE = "features"
CARD_STAGE = "card"
FEATURES_NOT_PUBLISHED = "features_not_published"
FEATURES_INVALID = "features_invalid"
SNAPSHOT_MISMATCH = "snapshot_mismatch"
SCHEDULE_AMBIGUOUS = "schedule_ambiguous"


@dataclass(frozen=True)
class PredictionOutcome:
    """One race's result, printed as one JSON line on stdout."""

    race_id: str
    status: Literal["predicted", "held", "out_of_scope"]
    stage: str | None = None
    reason: str | None = None
    detail: str | None = None
    output: str | None = None
    after_sales_close: bool | None = None
    win: Mapping[str, float] | None = None

    def as_json(self) -> str:
        """Return the stdout line with sorted keys."""
        return json.dumps(
            {
                "race_id": self.race_id,
                "status": self.status,
                "stage": self.stage,
                "reason": self.reason,
                "detail": self.detail,
                "output": self.output,
                "after_sales_close": self.after_sales_close,
                "win": None if self.win is None else dict(self.win),
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
        )


def model_predict_pl_live(
    features_root: Annotated[Path, typer.Option("--features-root")],
    pl_model: Annotated[Path, typer.Option("--pl-model")],
    pl_model_manifest_sha256: Annotated[str, typer.Option("--pl-model-manifest-sha256")],
    race_datetime: Annotated[
        datetime, typer.Option("--date", formats=["%Y-%m-%d"], help="Race date (JST).")
    ],
    processed_root: Annotated[Path, typer.Option("--processed-root")],
    output_path: Annotated[Path, typer.Option("--output")],
    snapshot_id: Annotated[str | None, typer.Option("--snapshot-id")] = None,
    poll_interval_seconds: Annotated[int, typer.Option("--poll-interval-seconds")] = 2,
) -> None:
    """Predict each graded race of one date as soon as its race-day features are published.

    ``--features-root`` is the ``--output`` of ``datamart build-reference-prediction-live``.
    A race whose features are not published by sales close (two minutes before the
    start) is held as ``features_not_published``.
    """
    # Keep NumPy, Arrow, LightGBM and the model modules out of imports and CLI help.
    from data.loader.fixed_snapshot import FixedSnapshot
    from models.artifacts.pl_model import read_pl_model
    from models.experiments.provenance import experiment_provenance

    started = perf_counter()
    target_day = race_datetime.date()
    outcomes: list[PredictionOutcome] = []
    try:
        if type(poll_interval_seconds) is not int or poll_interval_seconds < 1:
            raise ValueError("--poll-interval-seconds must be a positive integer")
        if _HEX64.fullmatch(pl_model_manifest_sha256) is None:
            raise ValueError("--pl-model-manifest-sha256 must be 64 lowercase hex digits")
        _check_new_output(output_path)
        _check_apart(output_path, features_root, processed_root)
        model = read_pl_model(pl_model, expected_manifest_sha256=pl_model_manifest_sha256)
        snapshot = FixedSnapshot(processed_root, snapshot_id=snapshot_id)
        snapshot.pin(_TABLES)
        targets, startup = plan_race_day(snapshot, target_day)
        pinned = snapshot.manifest()
        if targets:
            model.require_prediction_after(min(target.freeze_at for target in targets))
        provenance = experiment_provenance()
        _check_new_output(output_path)
        output_path.mkdir()
        for outcome in startup:
            _emit(outcome)
        outcomes.extend(startup)
        if not targets:
            typer.echo(f"no graded race to watch on {target_day.isoformat()}", err=True)
        watcher = _RaceWatcher(
            model,
            features_root,
            output_path,
            _snapshot_identity(pinned),
            provenance,
            now=_clock,
        )
        outcomes += watch_races(
            targets,
            now=_clock,
            sleep=_sleep,
            poll_seconds=poll_interval_seconds,
            published=watcher.published,
            complete=watcher.complete,
            report=_emit,
        )
    except KeyboardInterrupt as exc:
        typer.echo(f"{_COMMAND} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Published races stay; any staging of an unfinished race is removed.
        typer.echo(f"{_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    counts = {
        status: sum(outcome.status == status for outcome in outcomes)
        for status in ("predicted", "held", "out_of_scope")
    }
    typer.echo(
        f"pl_race_day_prediction date={target_day.isoformat()} "
        f"graded={counts['predicted'] + counts['held']} predicted={counts['predicted']} "
        f"held={counts['held']} out_of_scope={counts['out_of_scope']} "
        f"seconds={perf_counter() - started:.3f}",
        err=True,
    )


def plan_race_day(
    snapshot: FixedSnapshot, day: date
) -> tuple[list[RaceTarget], list[PredictionOutcome]]:
    """Return the date's graded races to watch, and the lines decided before watching.

    Cards come from the feature build's own normalization (``label_free_target_cards``).
    A race outside ``jra_flat_graded_stakes_v1`` is ``out_of_scope``; a graded race whose
    card is held, whose grade or track rows differ, or that has fewer than three horses
    is held at once.
    """
    from make_features.real_market import KEY_COLUMNS
    from make_features.reference_raw import CARD_RA_COLUMNS, CARD_SE_COLUMNS, race_identity
    from make_features.reference_rules import REFERENCE_BASES
    from models.experiments.pl_prediction import MINIMUM_FIELD_SIZE, PREDICTION_STAGE, RaceTarget
    from models.serialization.race_subsets import (
        JRA_FLAT_GRADED_STAKES_V1,
        classify_nl_ra_race_rows,
    )
    from models.serialization.reference_datamart import label_free_target_cards

    stamp = day.strftime("%Y%m%d")
    venues = cast(list[str], REFERENCE_BASES["venues"])
    ra_rows = snapshot.read_period(
        "NL_RA_RACE", columns=(*CARD_RA_COLUMNS, "GradeCD"), start=stamp, end=stamp, venues=venues
    )
    if not ra_rows:
        raise ValueError(f"snapshot has no races on {day.isoformat()} in the declared venues")
    se_rows = snapshot.read_period(
        "NL_SE_RACE_UMA", columns=CARD_SE_COLUMNS, start=stamp, end=stamp, venues=venues
    )
    codes: dict[str, set[tuple[object, object]]] = {}
    keys: dict[str, dict[str, object]] = {}
    for row in ra_rows:
        identity = race_identity(row)
        codes.setdefault(identity, set()).add((row.get("GradeCD"), row.get("TrackCD")))
        keys.setdefault(identity, {k: row[k] for k in KEY_COLUMNS})

    def graded(identity: str) -> bool:
        # A race is in scope when any of its stored code pairs is; differing pairs hold it.
        return any(
            classify_nl_ra_race_rows(
                [{**keys[identity], "GradeCD": grade, "TrackCD": track}]
            ).subsets[JRA_FLAT_GRADED_STAKES_V1]
            for grade, track in codes[identity]
        )

    cards, card_holds = label_free_target_cards(
        ra_rows,
        se_rows,
        day=day,
        freeze_offset_seconds=cast(int, REFERENCE_BASES["freeze_offset_seconds"]),
    )
    by_race = {card.race_id: card for card in cards}
    held = {str(item["race_id"]): item for item in card_holds}
    targets: list[RaceTarget] = []
    outcomes: list[PredictionOutcome] = []
    for identity in sorted(codes):
        if not graded(identity):
            outcomes.append(PredictionOutcome(identity, "out_of_scope"))
            continue
        if len(codes[identity]) != 1:
            outcomes.append(
                PredictionOutcome(
                    identity,
                    "held",
                    CARD_STAGE,
                    SCHEDULE_AMBIGUOUS,
                    "stored race rows differ in GradeCD or TrackCD",
                )
            )
            continue
        if identity in held:
            item = held[identity]
            outcomes.append(
                PredictionOutcome(identity, "held", str(item["stage"]), str(item["reason"]))
            )
            continue
        card = by_race[identity]
        if len(card.horse_mapping) < MINIMUM_FIELD_SIZE:
            outcomes.append(
                PredictionOutcome(
                    identity,
                    "held",
                    PREDICTION_STAGE,
                    "unsupported_field_size",
                    f"PL probabilities need at least {MINIMUM_FIELD_SIZE} horses; "
                    f"got {len(card.horse_mapping)}",
                )
            )
            continue
        ((grade, _),) = codes[identity]
        targets.append(
            RaceTarget(
                identity,
                card.scheduled_start_at,
                card.freeze_at,
                dict(card.horse_mapping),
                str(grade),
            )
        )
    return targets, outcomes


def watch_races(
    targets: Sequence[RaceTarget],
    *,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    poll_seconds: int,
    published: Callable[[RaceTarget], bool],
    complete: Callable[[RaceTarget], PredictionOutcome],
    report: Callable[[PredictionOutcome], None],
) -> list[PredictionOutcome]:
    """Poll the graded races in freeze order until each is predicted or held.

    A race is examined only after its freeze. The clock is read again just before each
    race is examined: features published by then are completed even after sales close
    (``complete`` records it); a race without features after sales close (strictly
    later than two minutes before the start) is held as ``features_not_published``.
    """
    pending = sorted(targets, key=lambda target: (target.freeze_at, target.race_id))
    outcomes: list[PredictionOutcome] = []
    while pending:
        current = now()
        for target in list(pending):
            if current < target.freeze_at:
                break
            seen = now()
            outcome: PredictionOutcome | None = None
            if published(target):
                outcome = complete(target)
            elif seen > target.sales_close_at:
                outcome = PredictionOutcome(
                    target.race_id,
                    "held",
                    FEATURES_STAGE,
                    FEATURES_NOT_PUBLISHED,
                    "features were not published before sales close",
                )
            if outcome is not None:
                report(outcome)
                outcomes.append(outcome)
                pending.remove(target)
        if pending:
            due = [target for target in pending if target.freeze_at <= current]
            wait = (
                poll_seconds
                if due
                else min(poll_seconds, (pending[0].freeze_at - current).total_seconds())
            )
            sleep(max(wait, 0.0))
    return outcomes


@dataclass(frozen=True)
class _Column:
    name: str
    group: str
    column: str
    meaning: str
    unit: str


class _RaceWatcher:
    """Read one race's published features, check them, predict and publish."""

    def __init__(
        self,
        model: PLModel,
        features_root: Path,
        output_path: Path,
        snapshot: Mapping[str, object],
        provenance: Mapping[str, object],
        *,
        now: Callable[[], datetime],
    ) -> None:
        source = cast(Mapping[str, object], model.manifest["source_datamart"])
        columns = cast(list[dict[str, str]], source["columns"])
        self.model = model
        self.now = now
        self.features_root = features_root
        self.output_path = output_path
        self.snapshot = snapshot
        self.provenance = provenance
        self.columns = tuple(_Column(**column) for column in columns)
        self._warned_missing_root = False

    def published(self, target: RaceTarget) -> bool:
        """Return whether the features of the race have been published.

        A missing ``--features-root`` at a due race is reported once on stderr: a wrong
        path would otherwise show only as ``features_not_published`` at each sales close.
        """
        if not self.features_root.is_dir():
            if not self._warned_missing_root:
                typer.echo(
                    f"warning: --features-root does not exist yet: {self.features_root}",
                    err=True,
                )
                self._warned_missing_root = True
            return False
        return (self.features_root / target.race_id).is_dir()

    def complete(self, target: RaceTarget) -> PredictionOutcome:
        """Predict one race from its published features, or hold it with a reason."""
        from data.storage.directory_publisher import publish_directory
        from make_datamart.tables.reference import read_reference_prediction_features
        from models.experiments.pl_prediction import (
            PREDICTION_STAGE,
            PredictionHold,
            RaceFeatures,
            build_race_prediction,
            prediction_json,
        )

        def hold(stage: str, reason: str, detail: str | None) -> PredictionOutcome:
            return PredictionOutcome(target.race_id, "held", stage, reason, detail)

        try:
            read = read_reference_prediction_features(
                self.features_root / target.race_id, expected_columns=self.columns
            )
        except (OSError, ValueError) as exc:
            # One race's broken or inconsistent features never stop the other races.
            return hold(FEATURES_STAGE, FEATURES_INVALID, " ".join(str(exc).split()))
        mismatch = _snapshot_mismatch(read.manifest.get("snapshot"), self.snapshot)
        if mismatch is not None:
            return hold(FEATURES_STAGE, SNAPSHOT_MISMATCH, mismatch)
        for item in read.held:
            if item["role"] == "target" and item["race_id"] == target.race_id:
                return hold(str(item["stage"]), str(item["reason"]), None)
        features = RaceFeatures(
            read.manifest_sha256, read.manifest, read.rows.to_pylist(), read.races.to_pylist()
        )
        # One clock reading decides both computed_at and after_sales_close.
        result = build_race_prediction(
            self.model,
            target,
            features,
            computed_at=self.now(),
            snapshot=self.snapshot,
            provenance=self.provenance,
        )
        if isinstance(result, PredictionHold):
            return hold(PREDICTION_STAGE, result.reason, result.detail)
        destination = self.output_path / target.race_id
        with publish_directory(destination) as staging:
            (staging / "prediction.json").write_bytes(prediction_json(result.payload))
        return PredictionOutcome(
            target.race_id,
            "predicted",
            output=str(destination / "prediction.json"),
            after_sales_close=result.after_sales_close,
            win=result.win,
        )


def _snapshot_identity(manifest: Mapping[str, object]) -> dict[str, object]:
    tables = cast(Mapping[str, Mapping[str, object]], manifest["tables"])
    return {
        "snapshot_id": manifest["snapshot_id"],
        "tables": {name: tables[name]["sha256"] for name in _TABLES},
    }


def _snapshot_mismatch(value: object, pinned: Mapping[str, object]) -> str | None:
    """Return why the features' snapshot differs from the watcher's pin, or None."""
    if not isinstance(value, Mapping):
        return "features carry no snapshot identity"
    if value.get("snapshot_id") != pinned["snapshot_id"]:
        return "features snapshot_id differs from the pinned snapshot"
    tables = value.get("tables")
    expected = cast(Mapping[str, object], pinned["tables"])
    for name in _TABLES:
        entry = tables.get(name) if isinstance(tables, Mapping) else None
        digest = entry.get("sha256") if isinstance(entry, Mapping) else None
        if digest != expected[name]:
            return f"features {name} SHA-256 differs from the pinned snapshot"
    return None


def _check_new_output(output_path: Path) -> None:
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("output must be a new non-symbolic-link path")
    if not output_path.parent.is_dir():
        raise ValueError("output parent directory must already exist")


def _check_apart(output_path: Path, features_root: Path, processed_root: Path) -> None:
    output = output_path.expanduser().resolve()
    features = features_root.expanduser().resolve()
    if output.is_relative_to(features) or features.is_relative_to(output):
        raise ValueError("--output and --features-root must not contain each other")
    if output.is_relative_to(processed_root.expanduser().resolve()):
        raise ValueError("--output must stay outside processed_root")


def _emit(outcome: PredictionOutcome) -> None:
    typer.echo(outcome.as_json())


def _clock() -> datetime:
    return datetime.now(UTC)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)
