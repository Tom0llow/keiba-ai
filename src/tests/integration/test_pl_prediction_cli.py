"""Watch race-day features and publish graded-race PL probabilities (ADR-039)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner, Result

from cli.pl_prediction import PredictionOutcome, _RaceWatcher
from data.loader.file_hash import file_sha256
from data.loader.fixed_snapshot import FixedSnapshot
from main import app
from make_datamart.tables.reference import (
    ReferenceDatamartWriter,
    read_reference_prediction_features,
)
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.real_market import canonical_hash
from models.artifacts.pl_model import PLModel, read_pl_model, write_pl_model
from models.experiments.pl_evaluation import PLVariant
from models.experiments.pl_prediction import RaceTarget
from models.experiments.pl_training import PLTrainingSettings, pl_model_record, train_final_pl
from models.serialization.reference_datamart import ReferenceDatamartBuilder
from tests.pl_fixtures import pl_parameters, synthetic_race_arrays
from tests.reference_fixtures import (
    RICH_TARGET_DAYS,
    ROOT,
    add_post_freeze_markets,
    day_markets,
    parquet_snapshot,
    prepared_from_raw,
    rich_raw_input,
)

DAY = RICH_TARGET_DAYS[-1]
RACE_09, RACE_10, RACE_11, RACE_12, RACE_13, RACE_14, RACE_15 = (
    f"{DAY:%Y%m%d}010101{n}" for n in ("09", "10", "11", "12", "13", "14", "15")
)
# Race 09 starts at 15:00 JST and race 10 at 15:30 JST.
FREEZE_09 = datetime(2027, 1, 3, 5, 55, tzinfo=UTC)
CLOSE_09 = datetime(2027, 1, 3, 5, 58, tzinfo=UTC)
FREEZE_10 = datetime(2027, 1, 3, 6, 25, tzinfo=UTC)
CLOSE_10 = datetime(2027, 1, 3, 6, 28, tzinfo=UTC)
MORNING = datetime(2027, 1, 3, 5, 0, tzinfo=UTC)
_TABLES = ("NL_RA_RACE", "NL_SE_RACE_UMA")
Row = dict[str, object]


@dataclass(frozen=True)
class World:
    processed: Path
    features: Path
    held: Path
    model_path: Path
    model_digest: str
    model: PLModel
    builder: ReferenceDatamartBuilder
    pinned: dict[str, object]


def _race_id(row: Row) -> str:
    keys = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
    return "".join(cast(str, row[k]) for k in keys)


def _add_grades(version: Path) -> None:
    """Give the snapshot GradeCD and more races on DAY that only the watcher reads.

    Races 09 and 10 are graded. Race 11 is not graded. Graded race 12 has no valid
    HassoTime, so its card is held before freeze. Race 13 has two rows whose GradeCD
    differ and one of them is graded; race 15 has two differing rows that are both
    not graded. Graded race 14 has only two runners.
    """
    path = version / "NL_RA_RACE.parquet"
    rows = pq.read_table(path).to_pylist()
    grades = {RACE_09: "A", RACE_10: "B"}
    for row in rows:
        row["GradeCD"] = grades.get(_race_id(row))
    template = next(row for row in rows if _race_id(row) == RACE_09)
    for number, clock, grade in (
        ("11", "1600", None),
        ("12", "0000", "A"),
        ("13", "1630", "A"),
        ("13", "1630", None),
        ("14", "1700", "C"),
        ("15", "1730", "E"),
        ("15", "1730", None),
    ):
        rows.append({**template, "idRaceNum": number, "HassoTime": clock, "GradeCD": grade})
    schema = pa.schema([(column, pa.string()) for column in rows[0]])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    path = version / "NL_SE_RACE_UMA.parquet"
    runners = pq.read_table(path).to_pylist()
    runners += [{**row, "idRaceNum": "14"} for row in runners if _race_id(row) == RACE_09][:2]
    schema = pa.schema([(column, pa.string()) for column in runners[0]])
    pq.write_table(pa.Table.from_pylist(runners, schema=schema), path)


def _train_model(directory: Path, names: list[str], source: dict[str, object]) -> str:
    """Fit a small PL model whose columns are the features' columns, all nullable."""
    arrays = synthetic_race_arrays((2020, 2021, 2022), races_per_year=40, seed=7)
    rng = np.random.default_rng(1)
    matrix = rng.normal(size=(arrays.features.shape[0], len(names)))
    matrix[:, 0] = arrays.features[:, 0]
    matrix[rng.random(size=matrix.shape) < 0.2] = np.nan
    arrays = replace(arrays, features=matrix, feature_names=tuple(names))
    settings = PLTrainingSettings(
        train_start_year=2020,
        valid_year=2022,
        variant=PLVariant("all_columns"),
        lightgbm={**pl_parameters(), "bin_construct_sample_cnt": 100000},
        num_boost_round=20,
        early_stopping_rounds=5,
        temperature_bounds=(0.05, 20.0),
    )
    final = train_final_pl(arrays, settings)
    record = pl_model_record(final, source_datamart=source, provenance={}, config={})
    directory.mkdir()
    return write_pl_model(directory, record, final.fit.booster)


def _manifest(
    builder: ReferenceDatamartBuilder,
    raw: dict[str, object],
    race_id: str,
    pinned: dict[str, object],
    binding: dict[str, object],
) -> dict[str, object]:
    freeze = FREEZE_09 if race_id == RACE_09 else FREEZE_10
    source: dict[str, object] = {
        "kind": "race_day_prediction_fetch",
        "race_id": race_id,
        "scheduled_start_at": (freeze + timedelta(minutes=5)).isoformat(),
        "freeze_at": freeze.isoformat(),
        "capture_id": "c" * 32,
        "data_specs": ["0B41", "0B42"],
        "started_at": (freeze + timedelta(seconds=5)).isoformat(),
        "snapshot_id": "d" * 32,
        "tables": {
            "ARCHIVE_O1_ODDS_TANFUKUWAKU": "1" * 64,
            "ARCHIVE_O2_ODDS_UMAREN": "2" * 64,
            "ARCHIVE_CAPTURE_LOG": "3" * 64,
        },
    }
    manifest = builder.prediction_manifest(
        snapshot=cast(dict[str, object], raw["snapshot"]),
        provenance={"fixture": True},
        preparation_config={"fixture": True},
        source_datamart=binding,
        market_source=source,
    )
    # The live features command records the snapshot it pinned, as the watcher does.
    manifest["snapshot"] = pinned
    return manifest


def _writer(path: Path, builder: ReferenceDatamartBuilder) -> ReferenceDatamartWriter:
    path.mkdir()
    return ReferenceDatamartWriter(
        path,
        columns=builder.columns,
        available_at_groups=builder.available_at_groups,
        contract=builder.contract.as_metadata(),
        labeled=False,
    )


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    base = Path(tmp_path_factory.mktemp("pl-live"))
    raw = rich_raw_input()
    add_post_freeze_markets(raw, cancelled_after_freeze=False)
    processed = base / "processed"
    _add_grades(parquet_snapshot(processed, raw))
    snapshot = FixedSnapshot(processed)
    snapshot.pin(_TABLES)
    pinned = snapshot.manifest()
    registry = create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml"))
    builder, prepared = prepared_from_raw(raw, registry=registry, day=DAY)
    contract = builder.contract.as_metadata()
    columns = [
        {
            "name": c.name,
            "group": c.group,
            "column": c.column,
            "meaning": c.meaning,
            "unit": c.unit,
        }
        for c in builder.columns
    ]
    source: dict[str, object] = {
        "manifest_sha256": "a" * 64,
        "contract_sha256": contract["sha256"],
        "target_period": {"start": "2020-01-01", "end": "2022-12-31"},
        "label_usable_through": "2023-01-10T00:00:00+00:00",
        "provenance_source_sha256": "c" * 64,
        "columns": columns,
    }
    binding = {key: value for key, value in source.items() if key != "columns"}
    model_path = base / "model"
    digest = _train_model(model_path, [c.name for c in builder.columns], source)
    features = base / "features"
    features.mkdir()
    o1_rows, o2_rows = day_markets(raw)(DAY)
    for schedule in prepared.schedules:
        result = prepared.calculate(
            schedule.race_id,
            [row for row in o1_rows if _race_id(row) == schedule.race_id],
            [row for row in o2_rows if _race_id(row) == schedule.race_id],
            observed_through=schedule.freeze_at + timedelta(seconds=5),
        )
        assert result.race is not None
        writer = _writer(features / schedule.race_id, builder)
        writer.write_year(DAY.year, result.rows, [result.race])
        writer.finish(_manifest(builder, raw, schedule.race_id, pinned, binding), [])
    assert sorted(path.name for path in features.iterdir()) == [RACE_09, RACE_10]
    held = base / "held"
    held.mkdir()
    writer = _writer(held / RACE_09, builder)
    writer.write_year(DAY.year, [], [])
    hold = {
        "race_id": RACE_09,
        "role": "target",
        "stage": "calculation",
        "reason": "fixture calculation hold",
        "whole_race": True,
    }
    writer.finish(_manifest(builder, raw, RACE_09, pinned, binding), [hold])
    model = read_pl_model(model_path, expected_manifest_sha256=digest)
    return World(processed, features, held, model_path, digest, model, builder, pinned)


class _Clock:
    """A UTC clock that moves only when the watcher sleeps or a test advances it."""

    def __init__(self, now: datetime, events: list[tuple[datetime, Callable[[], None]]]) -> None:
        self.now = now
        self.events = sorted(events, key=lambda event: event[0])

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        while self.events and self.events[0][0] <= self.now:
            self.events.pop(0)[1]()

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


def _features_root(tmp_path: Path, world: World, *races: str) -> Path:
    root = tmp_path / "features"
    root.mkdir()
    for race in races:
        shutil.copytree(world.features / race, root / race)
    return root


def _publish_later(world: World, root: Path, race: str) -> Callable[[], None]:
    def publish() -> None:
        shutil.copytree(world.features / race, root / race)

    return publish


def _arguments(world: World, root: Path, output: Path, *extra: str) -> list[str]:
    return [
        "model",
        "predict-pl-live",
        "--features-root",
        str(root),
        "--pl-model",
        str(world.model_path),
        "--pl-model-manifest-sha256",
        world.model_digest,
        "--date",
        DAY.isoformat(),
        "--processed-root",
        str(world.processed),
        "--output",
        str(output),
        *extra,
    ]


def _run(world: World, root: Path, output: Path, clock: _Clock, *extra: str) -> Result:
    with (
        patch("cli.pl_prediction._clock", clock),
        patch("cli.pl_prediction._sleep", clock.sleep),
        patch(
            "models.experiments.provenance.experiment_provenance",
            return_value={"fixture": "provenance"},
        ),
    ):
        return CliRunner().invoke(app, _arguments(world, root, output, *extra))


def _lines(result: Result) -> dict[str, dict[str, object]]:
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    keys = {"race_id", "status", "stage", "reason", "detail", "output", "after_sales_close", "win"}
    assert all(set(line) == keys for line in lines)
    by_race = {cast(str, line["race_id"]): line for line in lines}
    assert len(by_race) == len(lines)
    return by_race


def _payload(output: Path, race: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((output / race / "prediction.json").read_bytes()))


def test_each_graded_race_is_predicted_from_its_published_features(
    tmp_path: Path, world: World
) -> None:
    root = _features_root(tmp_path, world, RACE_09, RACE_10)
    output = tmp_path / "predictions"
    result = _run(world, root, output, _Clock(MORNING, []))

    assert result.exit_code == 0, result.output
    assert [json.loads(line)["race_id"] for line in result.stdout.splitlines()] == [
        RACE_11,
        RACE_12,
        RACE_13,
        RACE_14,
        RACE_15,
        RACE_09,
        RACE_10,
    ]
    lines = _lines(result)
    assert lines[RACE_11] == {
        "race_id": RACE_11,
        "status": "out_of_scope",
        "stage": None,
        "reason": None,
        "detail": None,
        "output": None,
        "after_sales_close": None,
        "win": None,
    }
    assert (lines[RACE_12]["status"], lines[RACE_12]["stage"], lines[RACE_12]["reason"]) == (
        "held",
        "target_pre_freeze",
        "stored HassoTime is missing or invalid",
    )
    # A race is in scope when any of its stored code pairs is graded.
    assert lines[RACE_15]["status"] == "out_of_scope"
    assert (lines[RACE_13]["status"], lines[RACE_13]["stage"], lines[RACE_13]["reason"]) == (
        "held",
        "card",
        "schedule_ambiguous",
    )
    assert (lines[RACE_14]["status"], lines[RACE_14]["stage"], lines[RACE_14]["reason"]) == (
        "held",
        "prediction",
        "unsupported_field_size",
    )
    assert sorted(path.name for path in output.iterdir()) == [RACE_09, RACE_10]
    assert (
        "pl_race_day_prediction date=2027-01-03 graded=5 predicted=2 held=3 out_of_scope=2"
        in result.stderr
    )
    tables = cast(dict[str, dict[str, object]], world.pinned["tables"])
    for race, freeze in ((RACE_09, FREEZE_09), (RACE_10, FREEZE_10)):
        line = lines[race]
        assert (line["status"], line["after_sales_close"]) == ("predicted", False)
        assert line["output"] == str(output / race / "prediction.json")
        payload = _payload(output, race)
        # Each race is computed at its first look, right at its freeze.
        assert payload["computed_at"] == freeze.isoformat()
        assert payload["after_sales_close"] is False
        assert payload["snapshot"] == {
            "snapshot_id": "fixture-v1",
            "tables": {name: tables[name]["sha256"] for name in _TABLES},
        }
        assert payload["provenance"] == {"fixture": "provenance"}
        assert cast(dict[str, object], payload["model"])["manifest_sha256"] == world.model_digest
        features = read_reference_prediction_features(
            root / race, expected_columns=world.builder.columns
        )
        assert cast(dict[str, object], payload["features"])["manifest_sha256"] == (
            features.manifest_sha256
        )
        horses = cast(list[dict[str, object]], payload["horses"])
        mapping = {cast(str, h["horse_number"]): cast(str, h["horse_id"]) for h in horses}
        assert canonical_hash(mapping) == features.races.column("horse_mapping_sha256")[0].as_py()
        rows = {row["horse_id"]: row for row in features.rows.to_pylist()}
        names = world.model.feature_names
        matrix = np.asarray(
            [
                [np.nan if rows[horse][name] is None else rows[horse][name] for name in names]
                for horse in mapping.values()
            ],
            dtype=np.float64,
        )
        scores = world.model.predict_scores(matrix, names)
        direct = world.model.probabilities(scores, [len(mapping)])
        for index, horse in enumerate(horses):
            assert horse["score"] == scores[index]
            assert (horse["win"], horse["top2"], horse["top3"]) == (
                direct.win[index],
                direct.top2[index],
                direct.top3[index],
            )
        assert line["win"] == {h["horse_number"]: h["win"] for h in horses}


def test_held_and_unpublished_graded_races_are_held_with_their_reasons(
    tmp_path: Path, world: World
) -> None:
    root = tmp_path / "features"
    root.mkdir()
    shutil.copytree(world.held / RACE_09, root / RACE_09)
    output = tmp_path / "predictions"
    clock = _Clock(MORNING, [])
    result = _run(world, root, output, clock)

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert (lines[RACE_09]["status"], lines[RACE_09]["stage"], lines[RACE_09]["reason"]) == (
        "held",
        "calculation",
        "fixture calculation hold",
    )
    assert (lines[RACE_10]["stage"], lines[RACE_10]["reason"]) == (
        "features",
        "features_not_published",
    )
    # Race 10 is held at the first look strictly after its sales close.
    assert clock.now == CLOSE_10 + timedelta(seconds=2)
    assert list(output.iterdir()) == []
    assert "graded=5 predicted=0 held=5 out_of_scope=2" in result.stderr


def test_a_missing_features_root_is_reported_once_and_holds_each_race(
    tmp_path: Path, world: World
) -> None:
    root = tmp_path / "features"
    output = tmp_path / "predictions"
    result = _run(world, root, output, _Clock(MORNING, []))

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert [lines[race]["reason"] for race in (RACE_09, RACE_10)] == [
        "features_not_published",
        "features_not_published",
    ]
    assert result.stderr.count(f"warning: --features-root does not exist yet: {root}") == 1


@pytest.mark.parametrize(
    ("start", "publish_at", "jump", "computed_at", "after"),
    [
        # Found exactly at sales close: still before it.
        (MORNING, CLOSE_09, 0, CLOSE_09, False),
        # First found after sales close: predicted and recorded as late.
        (MORNING, CLOSE_09 + timedelta(seconds=1), 0, CLOSE_09 + timedelta(seconds=2), True),
        # Found just before sales close, but the calculation starts after it.
        (
            MORNING,
            CLOSE_09 - timedelta(seconds=2),
            3,
            CLOSE_09 + timedelta(seconds=1),
            True,
        ),
    ],
)
def test_sales_close_follows_the_clock_read_before_each_look_and_calculation(
    tmp_path: Path,
    world: World,
    start: datetime,
    publish_at: datetime,
    jump: int,
    computed_at: datetime,
    after: bool,
) -> None:
    root = _features_root(tmp_path, world, RACE_10)
    clock = _Clock(start, [(publish_at, _publish_later(world, root, RACE_09))])
    original = _RaceWatcher.published

    def published(self: _RaceWatcher, target: RaceTarget) -> bool:
        found = original(self, target)
        if found and target.race_id == RACE_09:
            clock.advance(jump)
        return found

    output = tmp_path / "predictions"
    with patch.object(_RaceWatcher, "published", published):
        result = _run(world, root, output, clock)

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert (lines[RACE_09]["status"], lines[RACE_09]["after_sales_close"]) == ("predicted", after)
    payload = _payload(output, RACE_09)
    assert (payload["computed_at"], payload["after_sales_close"]) == (
        computed_at.isoformat(),
        after,
    )
    assert lines[RACE_10]["after_sales_close"] is False


@pytest.mark.parametrize("next_published", [False, True])
def test_a_long_calculation_can_pass_the_next_race_sales_close(
    tmp_path: Path, world: World, next_published: bool
) -> None:
    races = (RACE_09, RACE_10) if next_published else (RACE_09,)
    root = _features_root(tmp_path, world, *races)
    # Started late: both races are due in the first pass.
    clock = _Clock(CLOSE_10 - timedelta(seconds=1), [])
    original = _RaceWatcher.complete

    def slow(self: _RaceWatcher, target: RaceTarget) -> PredictionOutcome:
        outcome = original(self, target)
        clock.advance(3)
        return outcome

    output = tmp_path / "predictions"
    with patch.object(_RaceWatcher, "complete", slow):
        result = _run(world, root, output, clock)

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert (lines[RACE_09]["status"], lines[RACE_09]["after_sales_close"]) == ("predicted", True)
    if next_published:
        assert (lines[RACE_10]["status"], lines[RACE_10]["after_sales_close"]) == (
            "predicted",
            True,
        )
        assert (
            _payload(output, RACE_10)["computed_at"]
            == (CLOSE_10 + timedelta(seconds=2)).isoformat()
        )
    else:
        assert (lines[RACE_10]["status"], lines[RACE_10]["reason"]) == (
            "held",
            "features_not_published",
        )
        # Held in the same pass, from the clock read after race 09's calculation.
        assert clock.now == CLOSE_10 + timedelta(seconds=2)


def _edit_manifest(path: Path, change: Callable[[dict[str, object]], None]) -> None:
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    change(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _tables(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    return cast(
        dict[str, dict[str, object]], cast(dict[str, object], manifest["snapshot"])["tables"]
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda m: cast(dict[str, object], m["snapshot"]).update(snapshot_id="fixture-v2"),
        lambda m: _tables(m)["NL_RA_RACE"].update(sha256="0" * 64),
        lambda m: _tables(m)["NL_SE_RACE_UMA"].update(sha256="0" * 64),
        lambda m: _tables(m).pop("NL_SE_RACE_UMA"),
        lambda m: cast(dict[str, object], m["snapshot"]).update(tables=[]),
        lambda m: m.update(snapshot=None),
    ],
)
def test_features_from_another_snapshot_are_held(
    tmp_path: Path, world: World, change: Callable[[dict[str, object]], None]
) -> None:
    root = _features_root(tmp_path, world, RACE_09, RACE_10)
    _edit_manifest(root / RACE_09, change)
    output = tmp_path / "predictions"
    result = _run(world, root, output, _Clock(MORNING, []))

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert (lines[RACE_09]["status"], lines[RACE_09]["stage"], lines[RACE_09]["reason"]) == (
        "held",
        "features",
        "snapshot_mismatch",
    )
    assert lines[RACE_10]["status"] == "predicted"
    assert sorted(path.name for path in output.iterdir()) == [RACE_10]


def _rewrite_column(race_dir: Path, file: str, column: str, value: object) -> None:
    """Change one column of a published partition and re-pin its hash in the manifest."""
    path = race_dir / f"year={DAY.year}" / file
    table = pq.read_table(path)
    field = table.schema.field(column)
    table = table.set_column(
        table.schema.get_field_index(column), field, pa.array([value] * table.num_rows, field.type)
    )
    pq.write_table(table, path)
    key = "rows_sha256" if file == "part-0.parquet" else "races_sha256"

    def repin(manifest: dict[str, object]) -> None:
        cast(list[dict[str, object]], manifest["partitions"])[0][key] = file_sha256(path)

    _edit_manifest(race_dir, repin)


def _late_fetch(race_dir: Path) -> None:
    def change(manifest: dict[str, object]) -> None:
        source = cast(dict[str, object], manifest["market_source"])
        source["started_at"] = (FREEZE_09 - timedelta(seconds=1)).isoformat()

    _edit_manifest(race_dir, change)


def _late_group(race_dir: Path) -> None:
    group = json.loads((race_dir / "manifest.json").read_bytes())["available_at_groups"][0]
    _rewrite_column(
        race_dir, "part-0.parquet", f"{group}__available_at", FREEZE_09 + timedelta(seconds=1)
    )


def _late_history(race_dir: Path) -> None:
    _rewrite_column(
        race_dir, "races.parquet", "history_usable_through", datetime(2027, 1, 3, 1, tzinfo=UTC)
    )


def _changed_bytes(race_dir: Path) -> None:
    path = race_dir / f"year={DAY.year}" / "part-0.parquet"
    path.write_bytes(path.read_bytes() + b"\0")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_late_fetch, "started before freeze_at"),
        (_late_group, "row time boundary"),
        (_late_history, "history"),
        (_changed_bytes, "hash mismatch"),
    ],
)
def test_features_the_reader_rejects_hold_only_their_race(
    tmp_path: Path, world: World, edit: Callable[[Path], None], message: str
) -> None:
    root = _features_root(tmp_path, world, RACE_09, RACE_10)
    edit(root / RACE_09)
    output = tmp_path / "predictions"
    result = _run(world, root, output, _Clock(MORNING, []))

    assert result.exit_code == 0, result.output
    lines = _lines(result)
    assert (lines[RACE_09]["status"], lines[RACE_09]["stage"], lines[RACE_09]["reason"]) == (
        "held",
        "features",
        "features_invalid",
    )
    assert message in cast(str, lines[RACE_09]["detail"])
    assert lines[RACE_10]["status"] == "predicted"


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("exists", "output must be a new non-symbolic-link path"),
        ("poll", "--poll-interval-seconds must be a positive integer"),
        ("sha_format", "must be 64 lowercase hex digits"),
        ("sha_value", "SHA-256"),
        ("inside_features", "must not contain each other"),
        ("boundary", "label boundary"),
        ("no_races", "snapshot has no races on 2027-01-04"),
    ],
)
def test_startup_checks_fail_before_creating_the_output(
    tmp_path: Path, world: World, case: str, message: str
) -> None:
    root = _features_root(tmp_path, world, RACE_09, RACE_10)
    output = tmp_path / "predictions"
    arguments = _arguments(world, root, output)
    if case == "exists":
        output.mkdir()
    elif case == "poll":
        arguments += ["--poll-interval-seconds", "0"]
    elif case == "sha_format":
        arguments[arguments.index(world.model_digest)] = "X" * 64
    elif case == "sha_value":
        arguments[arguments.index(world.model_digest)] = "0" * 64
    elif case == "inside_features":
        arguments[arguments.index(str(output))] = str(root / "predictions")
    elif case == "no_races":
        arguments[arguments.index(DAY.isoformat())] = "2027-01-04"
    checked: list[datetime] = []

    def reject(freeze: datetime) -> None:
        checked.append(freeze)
        raise ValueError("prediction freeze_at must be after the PL model label boundary")

    clock = _Clock(MORNING, [])
    with ExitStack() as stack:
        stack.enter_context(patch("cli.pl_prediction._clock", clock))
        stack.enter_context(patch("cli.pl_prediction._sleep", clock.sleep))
        if case == "boundary":
            stack.enter_context(
                patch.object(PLModel, "require_prediction_after", side_effect=reject)
            )
        result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("model predict-pl-live failed: ")
    assert message in result.stderr
    assert output.exists() == (case == "exists")
    if case == "exists":
        assert list(output.iterdir()) == []
    assert not (root / "predictions").exists()
    assert clock.now == MORNING
    # Only the earliest freeze of the watched races is checked against the label boundary.
    assert checked == ([FREEZE_09] if case == "boundary" else [])


def test_a_date_without_graded_races_reports_them_and_finishes(
    tmp_path: Path, world: World
) -> None:
    root = _features_root(tmp_path, world)
    output = tmp_path / "predictions"
    arguments = _arguments(world, root, output)
    arguments[arguments.index(DAY.isoformat())] = RICH_TARGET_DAYS[0].isoformat()
    clock = _Clock(MORNING, [])
    with (
        patch("cli.pl_prediction._clock", clock),
        patch("cli.pl_prediction._sleep", clock.sleep),
    ):
        result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [line["status"] for line in lines] == ["out_of_scope", "out_of_scope"]
    assert "no graded race to watch on 2026-12-20" in result.stderr
    assert list(output.iterdir()) == []


def test_an_interrupt_keeps_published_races_and_exits_130(tmp_path: Path, world: World) -> None:
    root = _features_root(tmp_path, world, RACE_09)
    output = tmp_path / "predictions"

    def interrupt() -> None:
        raise KeyboardInterrupt

    result = _run(world, root, output, _Clock(MORNING, [(FREEZE_10, interrupt)]))

    assert result.exit_code == 130
    assert result.stderr.rstrip().endswith("model predict-pl-live failed: interrupted")
    assert sorted(path.name for path in output.iterdir()) == [RACE_09]
    assert [path.name for path in output.glob(".*")] == []


def test_predict_pl_live_help_does_not_import_the_model_or_lightgbm() -> None:
    script = """
import sys
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "predict-pl-live", "--help"])
assert result.exit_code == 0, result.output
for name in (
    "lightgbm",
    "models.artifacts.pl_model",
    "models.experiments.pl_prediction",
):
    assert name not in sys.modules, name
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "src",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
