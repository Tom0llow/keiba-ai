"""Add zero-yen proposals to published race-day predictions (ADR-045, ADR-046).

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
from datetime import UTC, datetime, timedelta
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
from models.betting.purchase_ledger import Purchase, append_entries, new_ledger
from models.experiments.bet_proposal import O1_TABLE
from models.experiments.pl_prediction import SALES_CLOSE_BEFORE_START
from tests.betting_estimator_fixtures import estimator_record
from tests.integration.test_pl_prediction_cli import (
    CLOSE_09,
    CLOSE_10,
    DAY,
    FREEZE_09,
    FREEZE_10,
    MORNING,
    RACE_09,
    RACE_10,
    RACE_11,
    RACE_12,
    RACE_13,
    RACE_14,
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
# Midnight JST of the race day, the earliest confirmation the first graded race accepts.
MIDNIGHT = datetime(DAY.year, DAY.month, DAY.day, tzinfo=UTC) - timedelta(hours=9)


def _ledger_bytes(*purchases: tuple[str, int], at: datetime = CLOSE_09) -> bytes:
    """Return a synthetic ledger of win bets confirmed at ``at``."""
    items = [Purchase(race, "win", "01", stake, at) for race, stake in purchases]
    return append_entries(new_ledger(), items, confirmed_at=at)


def _confirm(path: Path, at: datetime) -> Callable[[], None]:
    def write() -> None:
        path.write_bytes(append_entries(path.read_bytes(), [], confirmed_at=at))

    return write


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
    ledger: Path | None = None,
) -> tuple[Result, Path]:
    estimator, digest = _estimator(tmp_path, method, year)
    output = tmp_path / "proposals"
    if ledger is None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_bytes(_ledger_bytes())
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
                "--ledger",
                str(ledger),
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
        "race_remaining_yen",
        "annual_remaining_yen",
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
        assert (payload["format"], payload["format_version"]) == ("ev_race_proposal", 2)
        assert payload["prediction"]["sha256"] == hashlib.sha256(prediction).hexdigest()
        assert payload["estimator"]["method"] == method
        assert payload["market"]["snapshot_id"] == _VERSIONS[race]
        assert payload["decision"]["stake_yen"] == 0
        assert all(bet["stake_yen"] == 0 for bet in payload["bets"])
        assert lines[race]["bets"] == len(payload["bets"])
        assert lines[race]["reference_stake_yen"] == payload["decision"]["reference_stake_yen"]
        assert (lines[race]["race_remaining_yen"], lines[race]["annual_remaining_yen"]) == (
            5_000,
            100_000,
        )
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


def test_a_published_prediction_is_not_examined_before_its_freeze(
    tmp_path: Path, proposals: Proposals
) -> None:
    """Both predictions exist from the morning; each race is proposed only at its freeze."""
    clock = _Clock(MORNING, [])

    result, output = _run(proposals, tmp_path, clock)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    poll = timedelta(seconds=2)
    for race, freeze in ((RACE_09, FREEZE_09), (RACE_10, FREEZE_10)):
        assert lines[race]["status"] == "proposed"
        assert lines[race]["after_sales_close"] is False
        computed_at = datetime.fromisoformat(_proposal(output, race)["computed_at"])
        assert freeze <= computed_at < freeze + poll
    assert FREEZE_10 <= clock.now < FREEZE_10 + poll


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
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
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


def test_plan_race_day_gives_the_start_of_every_graded_race_with_a_card(
    proposals: Proposals,
) -> None:
    from cli.pl_prediction import plan_race_day

    snapshot = FixedSnapshot(proposals.processed)
    snapshot.pin(_TABLES)

    targets, _, starts = plan_race_day(snapshot, DAY)

    # Race 14 is held for its field size but keeps its start; 11 is not graded, and
    # 12 (no start) and 13 (ambiguous rows) have none.
    assert sorted(starts) == [RACE_09, RACE_10, RACE_14]
    assert {target.race_id: target.scheduled_start_at for target in targets} == {
        RACE_09: starts[RACE_09],
        RACE_10: starts[RACE_10],
    }
    assert starts[RACE_14] == MIDNIGHT + timedelta(hours=17)
    assert {RACE_11, RACE_12, RACE_13}.isdisjoint(starts)
    assert starts[RACE_09] - SALES_CLOSE_BEFORE_START == CLOSE_09


def test_actual_purchases_cap_the_reference_stakes_and_are_recorded(
    tmp_path: Path, proposals: Proposals
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    other_year = f"{DAY.year - 1}0105060101" + "01"
    ledger.write_bytes(_ledger_bytes((RACE_10, 1_000), (RACE_11, 2_000), (other_year, 50_000)))
    clock = _Clock(FREEZE_10 + timedelta(seconds=10), [])

    result, output = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert (lines[RACE_10]["race_remaining_yen"], lines[RACE_10]["annual_remaining_yen"]) == (
        4_000,
        97_000,
    )
    assert (lines[RACE_09]["race_remaining_yen"], lines[RACE_09]["annual_remaining_yen"]) == (
        5_000,
        97_000,
    )
    payload = _proposal(output, RACE_10)
    assert payload["budget"] == {
        "race_spent_yen": 1_000,
        "annual_spent_yen": 3_000,
        "race_remaining_yen": 4_000,
        "annual_remaining_yen": 97_000,
        "cap_yen": 4_000,
    }
    assert payload["ledger"] == {
        "sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "latest_confirmation_at": CLOSE_09.isoformat(),
        "required_confirmed_since": CLOSE_09.isoformat(),
    }
    assert payload["decision"]["reference_stake_yen"] <= 4_000
    assert _proposal(output, RACE_09)["ledger"]["required_confirmed_since"] == (
        MIDNIGHT.isoformat()
    )


def test_a_later_race_waits_for_a_confirmation_after_the_earlier_sales_close(
    tmp_path: Path, proposals: Proposals
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes(at=MORNING))
    confirmed = CLOSE_10 - timedelta(seconds=30)
    clock = _Clock(MORNING, [(confirmed, _confirm(ledger, confirmed))])

    result, output = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_09]["status"] == "proposed"
    assert lines[RACE_10]["status"] == "proposed"
    assert lines[RACE_10]["after_sales_close"] is False
    computed_at = datetime.fromisoformat(_proposal(output, RACE_10)["computed_at"])
    assert confirmed <= computed_at <= CLOSE_10


def test_a_race_without_a_confirmation_by_its_sales_close_is_held(
    tmp_path: Path, proposals: Proposals
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes(at=MORNING))
    clock = _Clock(MORNING, [])

    result, output = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_09]["status"] == "proposed"
    assert (lines[RACE_10]["status"], lines[RACE_10]["stage"], lines[RACE_10]["reason"]) == (
        "held",
        "proposal",
        "ledger_unconfirmed",
    )
    assert lines[RACE_10]["race_remaining_yen"] is None
    assert clock.now > CLOSE_10
    assert sorted(path.name for path in output.iterdir()) == [RACE_09]


def test_the_first_race_needs_a_confirmation_on_the_race_day(
    tmp_path: Path, proposals: Proposals
) -> None:
    """A prediction found after sales close with an unconfirmed ledger is held too."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes(at=MIDNIGHT - timedelta(seconds=1)))
    clock = _Clock(CLOSE_09 + timedelta(seconds=30), [])

    result, _ = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_09]["reason"] == "ledger_unconfirmed"
    assert lines[RACE_10]["reason"] == "ledger_unconfirmed"


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        (lambda path: path.unlink(), "ledger_unavailable"),
        (lambda path: path.write_bytes(b"not a ledger\n"), "ledger_invalid"),
    ],
)
def test_a_ledger_broken_after_startup_holds_races_unless_repaired_by_sales_close(
    tmp_path: Path,
    proposals: Proposals,
    damage: Callable[[Path], None],
    reason: str,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    original = _ledger_bytes()
    ledger.write_bytes(original)
    repaired = CLOSE_10 - timedelta(seconds=30)

    def repair() -> None:
        ledger.write_bytes(original)

    clock = _Clock(
        MORNING,
        [(FREEZE_09 - timedelta(seconds=1), lambda: damage(ledger)), (repaired, repair)],
    )

    result, output = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert (lines[RACE_09]["status"], lines[RACE_09]["reason"]) == ("held", reason)
    # The hold names no local path of the ledger.
    assert "ledger.jsonl" not in lines[RACE_09]["detail"]
    assert str(tmp_path) not in lines[RACE_09]["detail"]
    assert lines[RACE_10]["status"] == "proposed"
    assert sorted(path.name for path in output.iterdir()) == [RACE_10]


def test_a_proposal_uses_the_ledger_read_that_made_the_race_ready(
    tmp_path: Path, proposals: Proposals
) -> None:
    from cli.pl_prediction import _ProposalWatcher

    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes((RACE_10, 700)))
    original = _ProposalWatcher.published

    def published_then_removed(self: _ProposalWatcher, target: Any) -> bool:
        ready = original(self, target)
        if ready:
            ledger.unlink()
        return ready

    clock = _Clock(FREEZE_10 + timedelta(seconds=10), [])
    with patch.object(_ProposalWatcher, "published", published_then_removed):
        result, output = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    # Race 09 is proposed from the read that made it ready, after the file was removed;
    # race 10 then finds no ledger until its sales close.
    assert lines[RACE_09]["status"] == "proposed"
    assert _proposal(output, RACE_09)["budget"]["annual_spent_yen"] == 700
    assert (lines[RACE_10]["status"], lines[RACE_10]["reason"]) == ("held", "ledger_unavailable")


@pytest.mark.parametrize(
    ("prepare", "message"),
    [
        (lambda path: None, "No such file"),
        (lambda path: path.write_bytes(b"{}\n"), "header"),
    ],
)
def test_a_missing_or_invalid_ledger_fails_before_creating_the_output(
    tmp_path: Path,
    proposals: Proposals,
    prepare: Callable[[Path], None],
    message: str,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    prepare(ledger)

    result, output = _run(proposals, tmp_path, _Clock(MORNING, []), ledger=ledger)

    assert result.exit_code == 1
    assert message in result.stderr
    assert not output.exists()


def test_a_ledger_inside_another_root_fails_before_creating_the_output(
    tmp_path: Path, proposals: Proposals
) -> None:
    root = tmp_path / "predictions"
    shutil.copytree(proposals.predictions, root)
    ledger = root / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes())

    result, output = _run(proposals, tmp_path, _Clock(MORNING, []), predictions=root, ledger=ledger)

    assert result.exit_code == 1
    assert "--ledger must stay outside" in result.stderr
    assert not output.exists()


def test_an_earlier_graded_race_held_at_startup_still_sets_the_required_time() -> None:
    from cli.pl_prediction import ledger_required_since
    from models.experiments.pl_prediction import RaceTarget

    start_09 = CLOSE_09 + SALES_CLOSE_BEFORE_START
    start_10 = CLOSE_10 + SALES_CLOSE_BEFORE_START
    held_start = start_10 - timedelta(minutes=10)
    targets = [
        RaceTarget(RACE_09, start_09, FREEZE_09, {}, "A"),
        RaceTarget(RACE_10, start_10, FREEZE_10, {}, "B"),
    ]
    starts = {RACE_09: start_09, RACE_10: start_10, RACE_14: held_start}

    required = ledger_required_since(DAY, targets, starts)

    # Race 14 is not a target (held for its field size) but starts before race 10.
    assert required == {
        RACE_09: MIDNIGHT,
        RACE_10: held_start - SALES_CLOSE_BEFORE_START,
    }
    same_start = ledger_required_since(DAY, targets, {**starts, RACE_14: start_10})
    assert same_start[RACE_10] == CLOSE_09


def test_a_symbolic_link_ledger_fails_before_creating_the_output(
    tmp_path: Path, proposals: Proposals
) -> None:
    target = tmp_path / "real.jsonl"
    target.write_bytes(_ledger_bytes())
    ledger = tmp_path / "ledger.jsonl"
    try:
        ledger.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are not available")

    result, output = _run(proposals, tmp_path, _Clock(MORNING, []), ledger=ledger)

    assert result.exit_code == 1
    assert "--ledger must not be a symbolic link" in result.stderr
    assert not output.exists()


def test_the_cli_requires_the_sales_close_of_an_earlier_race_held_at_startup(
    tmp_path: Path, proposals: Proposals
) -> None:
    """Race 14 (held for its field size) is moved to start before race 10."""
    import cli.pl_prediction as module

    original = module.plan_race_day
    held_start = CLOSE_10 + SALES_CLOSE_BEFORE_START - timedelta(minutes=10)
    held_close = held_start - SALES_CLOSE_BEFORE_START

    def plan(snapshot: FixedSnapshot, day: object) -> object:
        targets, outcomes, starts = original(snapshot, day)  # type: ignore[arg-type]
        assert RACE_14 in starts
        return targets, outcomes, {**starts, RACE_14: held_start}

    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes(at=CLOSE_09))
    confirmed = held_close + timedelta(seconds=10)
    clock = _Clock(MORNING, [(confirmed, _confirm(ledger, confirmed))])
    with patch.object(module, "plan_race_day", side_effect=plan):
        result, output = _run(proposals, tmp_path, clock, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_10]["status"] == "proposed"
    payload = _proposal(output, RACE_10)
    assert payload["ledger"]["required_confirmed_since"] == held_close.isoformat()
    assert datetime.fromisoformat(payload["computed_at"]) >= confirmed


@pytest.mark.parametrize("root", ["output", "predictions", "features", "processed"])
def test_a_ledger_inside_any_other_root_is_refused(tmp_path: Path, root: str) -> None:
    from cli.pl_prediction import _check_ledger

    roots = {name: tmp_path / name for name in ("output", "predictions", "features", "processed")}
    ledger = roots[root] / "ledger.jsonl"

    with pytest.raises(ValueError, match="--ledger must stay outside"):
        _check_ledger(ledger, *roots.values())
    _check_ledger(tmp_path / "ledger.jsonl", *roots.values())


def test_a_ledger_hold_is_forgotten_when_the_prediction_disappears(
    tmp_path: Path, proposals: Proposals
) -> None:
    """Each check starts afresh: a stale ledger reason does not replace the missing prediction."""
    root = tmp_path / "predictions"
    shutil.copytree(proposals.predictions, root)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(_ledger_bytes(at=MIDNIGHT - timedelta(seconds=1)))
    clock = _Clock(
        MORNING,
        [(FREEZE_09 + timedelta(seconds=5), lambda: shutil.rmtree(root / RACE_09))],
    )

    result, _ = _run(proposals, tmp_path, clock, predictions=root, ledger=ledger)

    assert result.exit_code == 0, result.stderr
    lines = _lines(result)
    assert lines[RACE_09]["reason"] == "prediction_not_published"
    assert lines[RACE_10]["reason"] == "ledger_unconfirmed"
