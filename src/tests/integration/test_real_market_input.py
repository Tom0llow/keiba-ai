"""Small Parquet snapshots exercise the published market and result-use boundary."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from configuration.experiments import load_experiment_config
from data.loader.fixed_snapshot import FixedSnapshot
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from main import app
from make_features.real_market import (
    KEY_COLUMNS,
    MARKET_COLUMN,
    O1_COLUMNS,
    O1_TABLE,
    RA_COLUMNS,
    RA_TABLE,
    RECEPTION_BASIS,
    SE_COLUMNS,
    SE_TABLE,
    latest_o1,
    win_quotes,
)
from models.dataset.builder import build_features
from models.evaluation.walk_forward import WalkForwardConfig, make_walk_forward_folds
from models.experiments.runner import run_experiment
from models.serialization.inputs import parse_feature_inputs

_ROOT = Path(__file__).resolve().parents[3]


def _race(day: int) -> dict[str, object]:
    return {
        "race_id": f"202601{day:02d}01010101",
        "scheduled_start_at": f"2026-01-{day:02d}T15:00:00+09:00",
        "freeze_at": f"2026-01-{day:02d}T14:55:00+09:00",
        "schedule_known_at": None,
        "result_known_at": None,
    }


def _key(day: int) -> dict[str, object]:
    return dict(zip(KEY_COLUMNS, ("2026", f"01{day:02d}", "01", "01", "01", "01"), strict=True))


def _odds(day: int, *, clock: str = "1455", phase: str = "1") -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(O1_COLUMNS)
    row.update(_key(day))
    row.update(
        headDataKubun=phase,
        headMakeDate=f"202601{day:02d}",
        HappyoTime=f"01{day:02d}{clock}",
        other_original_field="preserved",
    )
    for i in range(4):
        row[f"OddsTansyoInfo{i}Umaban"] = f"{i + 1:02d}"
        row[f"OddsTansyoInfo{i}Odds"] = f"{20 + i * 10:04d}"
    return row


def _snapshot(root: Path, days: tuple[int, ...]) -> Path:
    version = root / "snapshots" / "fixed-v1"
    version.mkdir(parents=True)
    odds: list[dict[str, object]] = []
    ra: list[dict[str, object]] = []
    se: list[dict[str, object]] = []
    for day in days:
        odds.extend(
            (
                _odds(day, clock="1450"),
                _odds(day),
                _odds(day, clock="1456"),
                _odds(day, clock="1454", phase="4"),
            )
        )
        race: dict[str, object] = dict.fromkeys(RA_COLUMNS)
        race.update(_key(day))
        race.update(
            headDataKubun="7",
            headMakeDate=f"202601{day:02d}",
            HassoTime="1500",
            SyussoTosu="04",
            NyusenTosu="04",
        )
        ra.append(race)
        for horse in range(1, 5):
            runner: dict[str, object] = dict.fromkeys(SE_COLUMNS)
            runner.update(_key(day))
            runner.update(
                headDataKubun="7",
                headMakeDate=f"202601{day:02d}",
                Umaban=f"{horse:02d}",
                KakuteiJyuni=f"{horse:02d}",
                IJyoCD="0",
                DochakuKubun="0",
            )
            se.append(runner)
    for name, rows in ((O1_TABLE, odds), (RA_TABLE, ra), (SE_TABLE, se)):
        schema = pa.schema([(key, pa.string()) for key in rows[0]])
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), version / f"{name}.parquet")
    (root / "CURRENT").write_text("fixed-v1", encoding="utf-8")
    return version


def _prepare(
    tmp_path: Path, days: tuple[int, ...] = (1,), *, labels: bool = False
) -> tuple[dict[str, object], Path]:
    root = tmp_path / "processed"
    if not root.exists():
        _snapshot(root, days)
    manifest = tmp_path / "manifest.json"
    write_json(manifest, {"races": [_race(day) for day in days]})
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    write_json(
        config / "prepare.yaml",
        {
            "processed_root": str(root),
            "snapshot_id": None,
            "parameters": {
                "freeze_offset_seconds": 300,
                "reception_basis": RECEPTION_BASIS,
                "schedule_basis": "assumed_stored_schedule",
            },
            "labels": {"basis": "assumed_snapshot_results", "result_delay_days": 1}
            if labels
            else None,
        },
    )
    output = tmp_path / "prepared.json"
    result = CliRunner().invoke(
        app,
        [
            "model",
            "prepare-real-input",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--config-dir",
            str(config),
        ],
    )
    assert result.exit_code == 0, result.output
    return read_json(output), output


def test_prepare_pins_snapshot_preserves_original_and_rejects_overwrite(tmp_path: Path) -> None:
    payload, path = _prepare(tmp_path)
    schema, records = parse_feature_inputs(payload)
    assert schema.feature_names == (MARKET_COLUMN,)
    assert records[0].features[MARKET_COLUMN] == 2.0
    calculation = cast(dict[str, object], payload["calculation"])
    race = cast(list[dict[str, object]], calculation["races"])[0]
    assert cast(dict[str, object], race["selected_o1"])["other_original_field"] == "preserved"
    assert race["published_at"] == "2026-01-01T14:55:00+09:00"
    assert race["received_at"] is None
    assert cast(dict[str, object], payload["assurance"])["historical_reception_verified"] is False
    original = path.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "model",
            "prepare-real-input",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output",
            str(path),
            "--config-dir",
            str(tmp_path / "config"),
        ],
    )
    assert result.exit_code == 1
    assert path.read_bytes() == original
    pinned = FixedSnapshot(tmp_path / "processed")
    (tmp_path / "processed" / "CURRENT").write_text("nonexistent", encoding="utf-8")
    assert (
        len(pinned.read_races(O1_TABLE, [cast(str, _race(1)["race_id"])], columns=O1_COLUMNS)) == 4
    )


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("0000", "no_votes"),
        ("----", "cancelled_before_sale"),
        ("****", "cancelled_after_sale"),
        ("9999", "upper_censored"),
        (None, "source_null"),
    ],
)
def test_special_quotes_preserve_native_missing_with_reason(code: str | None, reason: str) -> None:
    row = _odds(1)
    row["OddsTansyoInfo0Odds"] = code
    assert win_quotes(row)[0] == ("01", None, reason)


def test_future_final_missing_clock_and_conflicting_publications_are_rejected() -> None:
    race = _race(1)
    with pytest.raises(ValueError, match="no intermediate"):
        latest_o1([_odds(1, clock="1456"), _odds(1, phase="4")], race)
    invalid = _odds(1)
    invalid["HappyoTime"] = "00000000"
    with pytest.raises(ValueError, match="HappyoTime"):
        latest_o1([invalid], race)
    first, second = _odds(1), _odds(1)
    second["OddsTansyoInfo0Odds"] = "0123"
    with pytest.raises(ValueError, match="conflicting"):
        latest_o1([first, second], race)
    assert latest_o1([first, copy.deepcopy(first)], race) == first


@pytest.mark.parametrize(
    "change",
    ["value", "available", "source", "label", "missing-label", "horse", "delay", "assurance"],
)
def test_prepared_values_and_se_labels_cannot_bypass_recomputation(
    tmp_path: Path, change: str
) -> None:
    payload, _ = _prepare(tmp_path, labels=True)
    records = cast(list[dict[str, object]], payload["records"])
    sources = cast(list[dict[str, object]], payload["label_sources"])
    if change == "value":
        cast(dict[str, object], records[0]["features"])[MARKET_COLUMN] = 9.0
    elif change == "available":
        cast(dict[str, object], records[0]["available_at"])[MARKET_COLUMN] = (
            "2026-01-01T14:56:00+09:00"
        )
    elif change == "source":
        calculation = cast(dict[str, object], payload["calculation"])
        entry = cast(list[dict[str, object]], calculation["races"])[0]
        cast(dict[str, object], entry["selected_o1"])["OddsTansyoInfo0Odds"] = "0123"
    elif change == "label":
        records[0]["finish_position"] = 4
    elif change == "missing-label":
        payload.pop("label_sources")
    elif change == "horse":
        records[0]["horse_id"] = "05"
    elif change == "delay":
        sources[0]["usable_after"] = "2026-01-01T16:00:00+09:00"
    else:
        payload["assurance"] = "strict"
    with pytest.raises(ValueError, match=r"differ|hash|label_sources"):
        parse_feature_inputs(payload)


def test_real_fixture_train_register_and_new_freeze_predict_keep_assumptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    payload, training = _prepare(tmp_path, (1, 5, 9), labels=True)
    schema, rows = parse_feature_inputs(payload)
    dataset = build_features(rows, feature_schema=schema).dataset
    assert dataset is not None
    with pytest.raises(ValueError, match="label-use audit"):
        make_walk_forward_folds(dataset, WalkForwardConfig(1, 1, 1, 1))
    config_dir = _ROOT / "configs/experiments"
    config = load_experiment_config(
        config_dir,
        action="train",
        overrides=[
            f"data.input='{training.as_posix()}'",
            "model.parameters.n_estimators=2",
            "model.parameters.min_child_samples=1",
        ],
    )
    result = run_experiment(config)
    assert result["model_version"] == "1"
    output = Path(str(result["output_dir"]))
    context = read_json(output / "native/training.json")
    assert context["label_known_through"] == "2026-01-07T00:00:00+09:00"
    assert context["label_assurance"] == "assumed_snapshot_results_revision_time_unverified"
    assert cast(dict[str, object], context["input_assurance"])["received_at"] is None
    prediction_root = tmp_path / "prediction"
    prediction_root.mkdir()
    _, future = _prepare(prediction_root, (13,))
    predict = load_experiment_config(
        config_dir,
        action="predict",
        overrides=[f"data.input='{future.as_posix()}'", "model.version=1"],
    )
    predicted = run_experiment(predict)
    saved = read_json(Path(str(predicted["output_dir"])) / "predictions.json")
    assert len(cast(list[object], saved["predictions"])) == 4
    assert saved["input_assurance"] == context["input_assurance"]
