"""Add zero-yen proposals to published race-day predictions (ADR-045).

The fixture builds race-day features whose market comes from a real race-scoped O1
version, publishes their predictions with ``model predict-pl-live`` and then runs
``model propose-bets-live`` on them with an injected clock.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner, Result

from data.loader.file_hash import file_sha256
from data.loader.fixed_snapshot import FixedSnapshot
from data.storage.snapshot_store import SnapshotStore
from domain.race_key import RaceKey
from main import app
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.reference_raw import MARKET_O1_COLUMNS
from models.artifacts.betting_estimator import write_betting_estimator
from models.betting.methods import Method
from models.experiments.bet_proposal import O1_TABLE
from tests.betting_estimator_fixtures import estimator_record
from tests.integration.test_pl_prediction_cli import (
    CLOSE_09,
    CLOSE_10,
    DAY,
    FREEZE_10,
    MORNING,
    RACE_09,
    RACE_10,
    _add_grades,
    _Clock,
    _race_id,
    _train_model,
    _writer,
)
from tests.reference_fixtures import (
    ROOT,
    add_post_freeze_markets,
    day_markets,
    parquet_snapshot,
    prepared_from_raw,
    rich_raw_input,
)

_TABLES = ("NL_RA_RACE", "NL_SE_RACE_UMA")
_VERSIONS = {RACE_09: "9" * 32, RACE_10: "a" * 32}
Payload = dict[str, Any]


@dataclass(frozen=True)
class Proposals:
    base: Path
    processed: Path
    features: Path
    predictions: Path
    model_path: Path
    model_digest: str


def _write_version(processed: Path, race: str, rows: list[dict[str, object]]) -> str:
    """Publish one race-scoped O1 version as race-day-odds does, and return its hash."""
    key = RaceKey(DAY, race[8:10], race[10:12], race[12:14], race[14:16])
    versions, pointer = SnapshotStore(processed).locations(key)
    version = versions / _VERSIONS[race]
    version.mkdir(parents=True)
    schema = pa.schema([(name, pa.string()) for name in MARKET_O1_COLUMNS])
    projected = [
        {name: None if row.get(name) is None else str(row.get(name)) for name in MARKET_O1_COLUMNS}
        for row in rows
    ]
    path = version / f"{O1_TABLE}.parquet"
    pq.write_table(pa.Table.from_pylist(projected, schema=schema), path)
    pointer.write_text(_VERSIONS[race], encoding="utf-8")
    return file_sha256(path)


@pytest.fixture(scope="module")
def proposals(tmp_path_factory: pytest.TempPathFactory) -> Proposals:
    base = Path(tmp_path_factory.mktemp("proposal-live"))
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
        {"name": c.name, "group": c.group, "column": c.column, "meaning": c.meaning, "unit": c.unit}
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
        race_o1 = [row for row in o1_rows if _race_id(row) == schedule.race_id]
        o1_sha256 = _write_version(processed, schedule.race_id, race_o1)
        result = prepared.calculate(
            schedule.race_id,
            race_o1,
            [row for row in o2_rows if _race_id(row) == schedule.race_id],
            observed_through=schedule.freeze_at + timedelta(seconds=5),
        )
        assert result.race is not None
        manifest = builder.prediction_manifest(
            snapshot=cast(dict[str, object], raw["snapshot"]),
            provenance={"fixture": True},
            preparation_config={"fixture": True},
            source_datamart=binding,
            market_source={
                "kind": "race_day_prediction_fetch",
                "race_id": schedule.race_id,
                "scheduled_start_at": schedule.scheduled_start_at.isoformat(),
                "freeze_at": schedule.freeze_at.isoformat(),
                "capture_id": "c" * 32,
                "data_specs": ["0B41", "0B42"],
                "started_at": (schedule.freeze_at + timedelta(seconds=5)).isoformat(),
                "snapshot_id": _VERSIONS[schedule.race_id],
                "tables": {
                    O1_TABLE: o1_sha256,
                    "ARCHIVE_O2_ODDS_UMAREN": "2" * 64,
                    "ARCHIVE_CAPTURE_LOG": "3" * 64,
                },
            },
        )
        manifest["snapshot"] = pinned
        writer = _writer(features / schedule.race_id, builder)
        writer.write_year(DAY.year, result.rows, [result.race])
        writer.finish(manifest, [])
    predictions = base / "predictions"
    clock = _Clock(FREEZE_10 + timedelta(seconds=10), [])
    with (
        patch("cli.pl_prediction._clock", clock),
        patch("cli.pl_prediction._sleep", clock.sleep),
        patch("models.experiments.provenance.experiment_provenance", return_value={}),
    ):
        published = CliRunner().invoke(
            app,
            [
                "model",
                "predict-pl-live",
                "--features-root",
                str(features),
                "--pl-model",
                str(model_path),
                "--pl-model-manifest-sha256",
                digest,
                "--date",
                DAY.isoformat(),
                "--processed-root",
                str(processed),
                "--output",
                str(predictions),
            ],
        )
    assert published.exit_code == 0, published.stderr
    assert sorted(path.name for path in predictions.iterdir()) == [RACE_09, RACE_10]
    return Proposals(base, processed, features, predictions, model_path, digest)


def _estimator(
    tmp_path: Path, method: Method = "blend_mid", year: int = DAY.year
) -> tuple[Path, str]:
    directory = tmp_path / f"estimator-{method}-{year}"
    directory.mkdir()
    return directory, write_betting_estimator(directory, estimator_record(year, method))


def _run(
    world: Proposals,
    tmp_path: Path,
    clock: _Clock,
    *,
    predictions: Path | None = None,
    features: Path | None = None,
    method: Method = "blend_mid",
    year: int = DAY.year,
    pl_digest: str | None = None,
) -> tuple[Result, Path]:
    estimator, digest = _estimator(tmp_path, method, year)
    output = tmp_path / "proposals"
    with (
        patch("cli.pl_prediction._clock", clock),
        patch("cli.pl_prediction._sleep", clock.sleep),
        patch(
            "models.experiments.provenance.experiment_provenance",
            return_value={"fixture": "provenance"},
        ),
    ):
        result = CliRunner().invoke(
            app,
            [
                "model",
                "propose-bets-live",
                "--predictions-root",
                str(predictions or world.predictions),
                "--features-root",
                str(features or world.features),
                "--estimator",
                str(estimator),
                "--estimator-manifest-sha256",
                digest,
                "--pl-model",
                str(world.model_path),
                "--pl-model-manifest-sha256",
                pl_digest or world.model_digest,
                "--date",
                DAY.isoformat(),
                "--processed-root",
                str(world.processed),
                "--output",
                str(output),
            ],
        )
    return result, output


def _lines(result: Result) -> dict[str, Payload]:
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    keys = {
        "race_id",
        "status",
        "stage",
        "reason",
        "detail",
        "output",
        "after_sales_close",
        "bets",
        "reference_stake_yen",
    }
    assert all(set(line) == keys for line in lines)
    return {line["race_id"]: line for line in lines}


def _proposal(output: Path, race: str) -> Payload:
    return cast(Payload, json.loads((output / race / "proposal.json").read_bytes()))


@pytest.mark.parametrize("method", ["pl_mid", "blend_mid"])
def test_each_published_prediction_gets_a_zero_yen_proposal(
    tmp_path: Path, proposals: Proposals, method: Method
) -> None:
    clock = _Clock(CLOSE_09 + timedelta(seconds=30), [])

    result, output = _run(proposals, tmp_path, clock, method=method)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_09]["status"] == "proposed"
    assert lines[RACE_09]["after_sales_close"] is True
    assert lines[RACE_10]["status"] == "proposed"
    assert lines[RACE_10]["after_sales_close"] is False
    statuses = {race: line["status"] for race, line in lines.items()}
    assert set(statuses.values()) == {"proposed", "held", "out_of_scope"}
    assert sorted(path.name for path in output.iterdir()) == [RACE_09, RACE_10]
    for race in (RACE_09, RACE_10):
        payload = _proposal(output, race)
        prediction = (proposals.predictions / race / "prediction.json").read_bytes()
        assert payload["format"] == "ev_race_proposal"
        assert payload["prediction"]["sha256"] == hashlib.sha256(prediction).hexdigest()
        assert payload["estimator"]["method"] == method
        assert payload["market"]["snapshot_id"] == _VERSIONS[race]
        assert payload["decision"]["stake_yen"] == 0
        assert all(bet["stake_yen"] == 0 for bet in payload["bets"])
        assert lines[race]["bets"] == len(payload["bets"])
        assert lines[race]["reference_stake_yen"] == payload["decision"]["reference_stake_yen"]
        numbers = [horse["horse_number"] for horse in payload["horses"]]
        assert numbers == sorted(numbers)
        assert payload["provenance"] == {"fixture": "provenance"}
    assert "proposed=2" in result.stderr


def test_a_prediction_not_published_by_sales_close_is_held(
    tmp_path: Path, proposals: Proposals
) -> None:
    root = tmp_path / "predictions"
    root.mkdir()
    shutil.copytree(proposals.predictions / RACE_10, root / RACE_10)
    clock = _Clock(MORNING, [])

    result, output = _run(proposals, tmp_path, clock, predictions=root)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_09]["reason"] == "prediction_not_published"
    assert lines[RACE_09]["stage"] == "proposal"
    assert lines[RACE_10]["status"] == "proposed"
    assert clock.now > CLOSE_09
    assert clock.now <= CLOSE_10
    assert sorted(path.name for path in output.iterdir()) == [RACE_10]


def _copied(proposals: Proposals, tmp_path: Path, edit: Callable[[Payload], None]) -> Path:
    root = tmp_path / "predictions"
    shutil.copytree(proposals.predictions, root)
    path = root / RACE_10 / "prediction.json"
    payload = json.loads(path.read_bytes())
    edit(payload)
    path.write_text(json.dumps(payload), encoding="ascii")
    return root


def _source(**changes: object) -> Callable[[Payload], None]:
    def edit(payload: Payload) -> None:
        payload["features"]["market_source"].update(changes)

    return edit


@pytest.mark.parametrize(
    ("edit", "reason"),
    [
        (lambda payload: payload.update(format_version=9), "prediction_invalid"),
        (lambda payload: payload["model"].update(manifest_sha256="0" * 64), "prediction_mismatch"),
        (lambda payload: payload["snapshot"].update(snapshot_id="other"), "prediction_mismatch"),
        (_source(snapshot_id="e" * 32), "market_source_unavailable"),
        (_source(tables={O1_TABLE: "0" * 64}), "market_source_mismatch"),
        (lambda payload: payload["features"].update(manifest_sha256="0" * 64), "features_invalid"),
    ],
)
def test_one_race_that_fails_a_check_is_held_and_the_others_continue(
    tmp_path: Path, proposals: Proposals, edit: Callable[[Payload], None], reason: str
) -> None:
    root = _copied(proposals, tmp_path, edit)
    clock = _Clock(FREEZE_10 + timedelta(seconds=10), [])

    result, output = _run(proposals, tmp_path, clock, predictions=root)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_10]["status"] == "held"
    assert lines[RACE_10]["stage"] == "proposal"
    assert lines[RACE_10]["reason"] == reason
    assert lines[RACE_09]["status"] == "proposed"
    assert sorted(path.name for path in output.iterdir()) == [RACE_09]


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        ("models.experiments.bet_proposal.build_race_proposal", "market_invalid"),
        ("data.storage.directory_publisher.publish_directory", "publish_failed"),
    ],
)
def test_an_unexpected_error_of_one_race_holds_it_and_the_others_continue(
    tmp_path: Path, proposals: Proposals, target: str, reason: str
) -> None:
    """``market_invalid`` and ``publish_failed`` are defensive: no checked input reaches them."""
    module_name, name = target.rsplit(".", 1)
    module = __import__(module_name, fromlist=[name])
    original = getattr(module, name)

    def failing(*args: object, **kwargs: object) -> object:
        race = cast(Any, kwargs.get("target") or args[0])
        race_id = race.race_id if hasattr(race, "race_id") else Path(race).name
        if race_id == RACE_10:
            raise (
                OSError("fixture failure") if reason == "publish_failed" else ValueError("fixture")
            )
        return original(*args, **kwargs)

    clock = _Clock(FREEZE_10 + timedelta(seconds=10), [])
    with patch(target, side_effect=failing):
        result, output = _run(proposals, tmp_path, clock)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_10]["status"] == "held"
    assert lines[RACE_10]["reason"] == reason
    assert lines[RACE_09]["status"] == "proposed"
    assert sorted(path.name for path in output.iterdir()) == [RACE_09]


def test_an_output_inside_the_predictions_root_names_that_option(
    tmp_path: Path, proposals: Proposals
) -> None:
    estimator, digest = _estimator(tmp_path)
    root = tmp_path / "predictions"
    root.mkdir()

    result = CliRunner().invoke(
        app,
        [
            "model",
            "propose-bets-live",
            "--predictions-root",
            str(root),
            "--features-root",
            str(proposals.features),
            "--estimator",
            str(estimator),
            "--estimator-manifest-sha256",
            digest,
            "--pl-model",
            str(proposals.model_path),
            "--pl-model-manifest-sha256",
            proposals.model_digest,
            "--date",
            DAY.isoformat(),
            "--processed-root",
            str(proposals.processed),
            "--output",
            str(root / "proposals"),
        ],
    )

    assert result.exit_code == 1
    assert "--output and --predictions-root must not contain each other" in result.stderr
    assert not (root / "proposals").exists()


def test_an_estimator_for_another_year_fails_before_creating_the_output(
    tmp_path: Path, proposals: Proposals
) -> None:
    clock = _Clock(MORNING, [])

    result, output = _run(proposals, tmp_path, clock, year=DAY.year - 1)

    assert result.exit_code == 1
    assert f"the estimator is for {DAY.year - 1}" in result.stderr
    assert not output.exists()


def test_a_wrong_pl_model_identity_fails_before_creating_the_output(
    tmp_path: Path, proposals: Proposals
) -> None:
    clock = _Clock(MORNING, [])

    result, output = _run(proposals, tmp_path, clock, pl_digest="0" * 64)

    assert result.exit_code == 1
    assert not output.exists()
