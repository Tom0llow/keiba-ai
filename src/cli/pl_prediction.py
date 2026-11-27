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
    from domain.race_key import RaceKey
    from models.artifacts.betting_estimator import BettingEstimator
    from models.artifacts.pl_model import PLModel
    from models.betting.purchase_ledger import PurchaseLedger
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
        targets, startup, _ = plan_race_day(snapshot, target_day)
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
            missing=_features_not_published,
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
) -> tuple[list[RaceTarget], list[PredictionOutcome], dict[str, datetime]]:
    """Return the date's graded races to watch, the lines decided before watching, and
    the scheduled start of every graded race whose card gives one.

    Cards come from the feature build's own normalization (``label_free_target_cards``).
    A race outside ``jra_flat_graded_stakes_v1`` is ``out_of_scope``; a graded race whose
    card is held, whose grade or track rows differ, or that has fewer than three horses
    is held at once. Only the last of those holds still has a known start.
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
    graded_starts: dict[str, datetime] = {}
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
        graded_starts[identity] = card.scheduled_start_at
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
    return targets, outcomes, graded_starts


def watch_races[Outcome](
    targets: Sequence[RaceTarget],
    *,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    poll_seconds: int,
    published: Callable[[RaceTarget], bool],
    complete: Callable[[RaceTarget], Outcome],
    missing: Callable[[RaceTarget], Outcome],
    report: Callable[[Outcome], None],
) -> list[Outcome]:
    """Poll the graded races in freeze order until each is completed or held.

    A race is examined only after its freeze. The clock is read again just before each
    race is examined: an input published by then is completed even after sales close
    (``complete`` records it); a race without its input after sales close (strictly
    later than two minutes before the start) gets the ``missing`` outcome.
    """
    pending = sorted(targets, key=lambda target: (target.freeze_at, target.race_id))
    outcomes: list[Outcome] = []
    while pending:
        current = now()
        for target in list(pending):
            if current < target.freeze_at:
                break
            seen = now()
            outcome: Outcome | None = None
            if published(target):
                outcome = complete(target)
            elif seen > target.sales_close_at:
                outcome = missing(target)
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


def _features_not_published(target: RaceTarget) -> PredictionOutcome:
    return PredictionOutcome(
        target.race_id,
        "held",
        FEATURES_STAGE,
        FEATURES_NOT_PUBLISHED,
        "features were not published before sales close",
    )


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


def _check_apart(
    output_path: Path,
    features_root: Path,
    processed_root: Path,
    *,
    option: str = "--features-root",
) -> None:
    output = output_path.expanduser().resolve()
    features = features_root.expanduser().resolve()
    if output.is_relative_to(features) or features.is_relative_to(output):
        raise ValueError(f"--output and {option} must not contain each other")
    if output.is_relative_to(processed_root.expanduser().resolve()):
        raise ValueError("--output must stay outside processed_root")


def _check_same_variant(
    estimator_sources: Mapping[str, object], model_manifest: Mapping[str, object]
) -> None:
    """Reject an estimator measured on another PL variant than the model's (ADR-051).

    Both readers validated their manifests, so the variants are nonempty strings. Only the
    names are compared: the estimator does not record the variant's columns.
    """
    measured = cast(Mapping[str, object], estimator_sources["pl_evaluation"])["variant"]
    trained = cast(Mapping[str, object], model_manifest["features"])["variant"]
    if measured != trained:
        raise ValueError(
            f"the estimator was measured on PL variant {measured!r}, "
            f"but the PL model uses variant {trained!r}"
        )


def _check_ledger(ledger_path: Path, *roots: Path) -> None:
    if ledger_path.is_symlink():
        raise ValueError("--ledger must not be a symbolic link")
    ledger = ledger_path.expanduser().resolve()
    for root in roots:
        if ledger.is_relative_to(root.expanduser().resolve()):
            raise ValueError(
                "--ledger must stay outside --output, --predictions-root, "
                "--features-root and processed_root"
            )


def _emit(outcome: PredictionOutcome) -> None:
    typer.echo(outcome.as_json())


def _clock() -> datetime:
    return datetime.now(UTC)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


_PROPOSE_COMMAND = "model propose-bets-live"
PREDICTION_NOT_PUBLISHED = "prediction_not_published"


@dataclass(frozen=True)
class ProposalOutcome:
    """One race's proposal result, printed as one JSON line on stdout (ADR-045)."""

    race_id: str
    status: Literal["proposed", "held", "out_of_scope"]
    stage: str | None = None
    reason: str | None = None
    detail: str | None = None
    output: str | None = None
    after_sales_close: bool | None = None
    bets: int | None = None
    reference_stake_yen: int | None = None
    race_remaining_yen: int | None = None
    annual_remaining_yen: int | None = None

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
                "bets": self.bets,
                "reference_stake_yen": self.reference_stake_yen,
                "race_remaining_yen": self.race_remaining_yen,
                "annual_remaining_yen": self.annual_remaining_yen,
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
        )


def model_propose_bets_live(
    predictions_root: Annotated[Path, typer.Option("--predictions-root")],
    features_root: Annotated[Path, typer.Option("--features-root")],
    estimator_path: Annotated[Path, typer.Option("--estimator")],
    estimator_manifest_sha256: Annotated[str, typer.Option("--estimator-manifest-sha256")],
    pl_model: Annotated[Path, typer.Option("--pl-model")],
    pl_model_manifest_sha256: Annotated[str, typer.Option("--pl-model-manifest-sha256")],
    race_datetime: Annotated[
        datetime, typer.Option("--date", formats=["%Y-%m-%d"], help="Race date (JST).")
    ],
    processed_root: Annotated[Path, typer.Option("--processed-root")],
    output_path: Annotated[Path, typer.Option("--output")],
    ledger_path: Annotated[
        Path, typer.Option("--ledger", help="Purchase ledger of model record-purchases.")
    ],
    snapshot_id: Annotated[str | None, typer.Option("--snapshot-id")] = None,
    poll_interval_seconds: Annotated[int, typer.Option("--poll-interval-seconds")] = 2,
) -> None:
    """Add a zero-yen expected-value proposal to each graded race's published prediction.

    ``--predictions-root`` is the ``--output`` of ``model predict-pl-live``; pass the same
    ``--features-root``, ``--pl-model`` and ``--snapshot-id`` as that command. A race
    whose prediction is not published by sales close is held as
    ``prediction_not_published``. Reference stakes are capped by the actual purchases in
    ``--ledger`` (ADR-046); a race waits until the ledger is confirmed since the sales
    close of the day's earlier-starting graded races, and is held at its sales close.
    """
    # Keep NumPy, Arrow, LightGBM and the model modules out of imports and CLI help.
    import data.loader.race_version  # noqa: F401  (load Arrow before the first race)
    from data.loader.fixed_snapshot import FixedSnapshot
    from models.artifacts.betting_estimator import read_betting_estimator
    from models.artifacts.pl_model import read_pl_model
    from models.betting.purchase_ledger import parse_ledger
    from models.experiments.provenance import experiment_provenance

    started = perf_counter()
    target_day = race_datetime.date()
    outcomes: list[ProposalOutcome] = []
    try:
        if type(poll_interval_seconds) is not int or poll_interval_seconds < 1:
            raise ValueError("--poll-interval-seconds must be a positive integer")
        for name, value in (
            ("--estimator-manifest-sha256", estimator_manifest_sha256),
            ("--pl-model-manifest-sha256", pl_model_manifest_sha256),
        ):
            if _HEX64.fullmatch(value) is None:
                raise ValueError(f"{name} must be 64 lowercase hex digits")
        _check_new_output(output_path)
        _check_apart(output_path, predictions_root, processed_root, option="--predictions-root")
        _check_apart(output_path, features_root, processed_root)
        _check_ledger(ledger_path, output_path, predictions_root, features_root, processed_root)
        parse_ledger(ledger_path.read_bytes())
        estimator = read_betting_estimator(
            estimator_path, expected_manifest_sha256=estimator_manifest_sha256
        )
        if target_day.year != estimator.record.target_year:
            raise ValueError(
                f"the estimator is for {estimator.record.target_year}, "
                f"not {target_day.year}; build the estimator for this year"
            )
        model = read_pl_model(pl_model, expected_manifest_sha256=pl_model_manifest_sha256)
        _check_same_variant(estimator.record.sources, model.manifest)
        snapshot = FixedSnapshot(processed_root, snapshot_id=snapshot_id)
        snapshot.pin(_TABLES)
        targets, startup, graded_starts = plan_race_day(snapshot, target_day)
        pinned = snapshot.manifest()
        provenance = experiment_provenance()
        _check_new_output(output_path)
        output_path.mkdir()
        for item in startup:
            # Startup lines are only out-of-scope races and card holds.
            outcome = ProposalOutcome(
                item.race_id,
                "out_of_scope" if item.status == "out_of_scope" else "held",
                item.stage,
                item.reason,
                item.detail,
            )
            _emit_proposal(outcome)
            outcomes.append(outcome)
        if not targets:
            typer.echo(f"no graded race to watch on {target_day.isoformat()}", err=True)
        required = ledger_required_since(target_day, targets, graded_starts)
        watcher = _ProposalWatcher(
            predictions_root,
            features_root,
            processed_root,
            output_path,
            estimator=estimator,
            model_manifest=model.manifest,
            pl_model_manifest_sha256=pl_model_manifest_sha256,
            snapshot=_snapshot_identity(pinned),
            provenance=provenance,
            now=_clock,
            ledger_path=ledger_path,
            ledger_required_since=required,
        )
        outcomes += watch_races(
            targets,
            now=_clock,
            sleep=_sleep,
            poll_seconds=poll_interval_seconds,
            published=watcher.published,
            complete=watcher.complete,
            missing=watcher.missing,
            report=_emit_proposal,
        )
    except KeyboardInterrupt as exc:
        typer.echo(f"{_PROPOSE_COMMAND} failed: interrupted", err=True)
        raise typer.Exit(code=130) from exc
    except Exception as exc:
        # Published races stay; any staging of an unfinished race is removed.
        typer.echo(f"{_PROPOSE_COMMAND} failed: {' '.join(str(exc).split())}", err=True)
        raise typer.Exit(code=1) from exc
    counts = {
        status: sum(outcome.status == status for outcome in outcomes)
        for status in ("proposed", "held", "out_of_scope")
    }
    typer.echo(
        f"ev_race_proposal date={target_day.isoformat()} "
        f"graded={counts['proposed'] + counts['held']} proposed={counts['proposed']} "
        f"held={counts['held']} out_of_scope={counts['out_of_scope']} "
        f"seconds={perf_counter() - started:.3f}",
        err=True,
    )


def ledger_required_since(
    day: date, targets: Sequence[RaceTarget], graded_starts: Mapping[str, datetime]
) -> dict[str, datetime]:
    """Return each target's earliest acceptable ledger confirmation (ADR-046).

    It is the latest sales close among the day's graded races with a known start that
    start strictly earlier than the target, including races held at startup, or the
    day's midnight (JST) when that is later or there is none.
    """
    from models.betting.purchase_ledger import required_confirmed_since
    from models.experiments.pl_prediction import SALES_CLOSE_BEFORE_START

    return {
        target.race_id: required_confirmed_since(
            day,
            (
                start - SALES_CLOSE_BEFORE_START
                for start in graded_starts.values()
                if start < target.scheduled_start_at
            ),
        )
        for target in targets
    }


class _ProposalWatcher:
    """Read one race's prediction, features and race-day O1, then publish its proposal.

    A race is ready when its prediction is published and the purchase ledger, read once
    per check, is valid and confirmed since the race's required time. The ledger read
    that made a race ready is the one its proposal uses.
    """

    def __init__(
        self,
        predictions_root: Path,
        features_root: Path,
        processed_root: Path,
        output_path: Path,
        *,
        estimator: BettingEstimator,
        model_manifest: Mapping[str, object],
        pl_model_manifest_sha256: str,
        snapshot: Mapping[str, object],
        provenance: Mapping[str, object],
        now: Callable[[], datetime],
        ledger_path: Path,
        ledger_required_since: Mapping[str, datetime],
    ) -> None:
        source = cast(Mapping[str, object], model_manifest["source_datamart"])
        columns = cast(list[dict[str, str]], source["columns"])
        self.predictions_root = predictions_root
        self.features_root = features_root
        self.processed_root = processed_root
        self.output_path = output_path
        self.estimator = estimator
        self.pl_model_manifest_sha256 = pl_model_manifest_sha256
        self.snapshot = snapshot
        self.provenance = provenance
        self.now = now
        self.columns = tuple(_Column(**column) for column in columns)
        self.ledger_path = ledger_path
        self.ledger_required_since = ledger_required_since
        self._warned_missing_root = False
        self._ledgers: dict[str, PurchaseLedger] = {}
        self._ledger_holds: dict[str, tuple[str, str]] = {}

    def published(self, target: RaceTarget) -> bool:
        """Return whether the race's prediction is published and the ledger is ready.

        The root is never listed: ``predict-pl-live`` stages unfinished races beside the
        published ones. A missing root at a due race is reported once on stderr. When the
        prediction is published but the ledger is not ready, the reason is kept for
        ``missing``; every check starts afresh.
        """
        from models.betting.purchase_ledger import LedgerError, parse_ledger

        race_id = target.race_id
        self._ledgers.pop(race_id, None)
        self._ledger_holds.pop(race_id, None)
        if not self.predictions_root.is_dir():
            if not self._warned_missing_root:
                typer.echo(
                    f"warning: --predictions-root does not exist yet: {self.predictions_root}",
                    err=True,
                )
                self._warned_missing_root = True
            return False
        if not (self.predictions_root / race_id).is_dir():
            return False
        required = self.ledger_required_since[race_id]
        try:
            ledger = parse_ledger(self.ledger_path.read_bytes())
        except OSError as exc:
            # The OSError text names the ledger's local path; keep it out of the stdout log.
            reason = exc.strerror or type(exc).__name__
            self._ledger_holds[race_id] = (
                "ledger_unavailable",
                f"the ledger cannot be read: {reason}",
            )
            return False
        except LedgerError as exc:
            self._ledger_holds[race_id] = ("ledger_invalid", str(exc))
            return False
        confirmed = ledger.latest_confirmation
        if confirmed is None or confirmed < required:
            self._ledger_holds[race_id] = (
                "ledger_unconfirmed",
                f"the purchase ledger is not confirmed since {required.astimezone(UTC).isoformat()}",
            )
            return False
        self._ledgers[race_id] = ledger
        return True

    def missing(self, target: RaceTarget) -> ProposalOutcome:
        """Hold a race not ready by sales close, by its ledger reason when it has one."""
        from models.experiments.bet_proposal import PROPOSAL_STAGE

        reason, detail = self._ledger_holds.get(
            target.race_id,
            (PREDICTION_NOT_PUBLISHED, "the prediction was not published by sales close"),
        )
        return ProposalOutcome(
            target.race_id, "held", PROPOSAL_STAGE, reason, " ".join(detail.split())
        )

    def complete(self, target: RaceTarget) -> ProposalOutcome:
        """Propose one race, or hold it with a reason; other races keep being watched."""
        from data.loader.race_version import read_race_version
        from data.storage.directory_publisher import publish_directory
        from make_datamart.tables.reference import read_reference_prediction_features
        from make_features.real_market import MARKET_COLUMN
        from make_features.reference_raw import MARKET_O1_COLUMNS
        from models.experiments.bet_proposal import (
            O1_TABLE,
            PROPOSAL_STAGE,
            ProposalHold,
            build_race_proposal,
            proposal_json,
            read_prediction,
        )

        def hold(reason: str, detail: str) -> ProposalOutcome:
            return ProposalOutcome(
                target.race_id, "held", PROPOSAL_STAGE, reason, " ".join(detail.split())
            )

        ledger = self._ledgers.pop(target.race_id, None)
        if ledger is None:
            return hold("ledger_unavailable", "the race was not made ready by a ledger read")
        try:
            # One read: the hash and the parse see the same bytes.
            data = (self.predictions_root / target.race_id / "prediction.json").read_bytes()
        except OSError as exc:
            return hold("prediction_invalid", str(exc))
        try:
            prediction = read_prediction(data, target)
        except ProposalHold as exc:
            return hold(exc.reason, exc.detail)
        if prediction.model_manifest_sha256 != self.pl_model_manifest_sha256:
            return hold("prediction_mismatch", "the prediction's PL model differs from --pl-model")
        if dict(prediction.snapshot) != dict(self.snapshot):
            return hold("prediction_mismatch", "the prediction's snapshot differs from the pin")
        try:
            read = read_reference_prediction_features(
                self.features_root / target.race_id,
                expected_columns=self.columns,
                expected_manifest_sha256=prediction.features_manifest_sha256,
            )
        except (OSError, ValueError) as exc:
            return hold("features_invalid", str(exc))
        market: dict[str, float | None] = {}
        for row in read.rows.to_pylist():
            if row.get("race_id") == target.race_id:
                value = row.get(MARKET_COLUMN)
                market[str(row.get("horse_id"))] = None if value is None else float(value)
        try:
            version = read_race_version(
                self.processed_root,
                _race_key(target.race_id),
                columns={O1_TABLE: MARKET_O1_COLUMNS},
                snapshot_id=prediction.market_snapshot_id,
            )
        except (OSError, ValueError) as exc:
            return hold("market_source_unavailable", str(exc))
        if version is None:
            return hold("market_source_unavailable", "the race-day fetch version is missing")
        if version.sha256.get(O1_TABLE) != prediction.market_o1_sha256:
            return hold("market_source_mismatch", "the race-day O1 differs from the prediction's")
        # One clock reading decides both computed_at and after_sales_close.
        try:
            proposal = build_race_proposal(
                target=target,
                prediction=prediction,
                market_win_odds=market,
                o1_rows=version.rows[O1_TABLE],
                estimator=self.estimator,
                computed_at=self.now(),
                snapshot=self.snapshot,
                provenance=self.provenance,
                ledger=ledger,
                ledger_required_since=self.ledger_required_since[target.race_id],
            )
        except ProposalHold as exc:
            return hold(exc.reason, exc.detail)
        except ValueError as exc:
            return hold("market_invalid", str(exc))
        destination = self.output_path / target.race_id
        try:
            payload = proposal_json(proposal.payload)
            with publish_directory(destination) as staging:
                (staging / "proposal.json").write_bytes(payload)
        except (OSError, ValueError) as exc:
            # publish_directory removes its staging; the other races keep being watched.
            return hold("publish_failed", str(exc))
        return ProposalOutcome(
            target.race_id,
            "proposed",
            output=str(destination / "proposal.json"),
            after_sales_close=proposal.after_sales_close,
            bets=proposal.bets,
            reference_stake_yen=proposal.reference_stake_yen,
            race_remaining_yen=proposal.race_remaining_yen,
            annual_remaining_yen=proposal.annual_remaining_yen,
        )


def _race_key(race_id: str) -> RaceKey:
    from domain.race_key import RaceKey

    return RaceKey(
        datetime.strptime(race_id[:8], "%Y%m%d").date(),
        race_id[8:10],
        race_id[10:12],
        race_id[12:14],
        race_id[14:16],
    )


def _emit_proposal(outcome: ProposalOutcome) -> None:
    typer.echo(outcome.as_json())
