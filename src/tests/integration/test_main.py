"""Tests for the Typer data CLI."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest
from typer import Typer
from typer.testing import CliRunner

from main import app, register_feature_commands
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from models.evaluation.metrics import RankingMetrics

REGISTRY = create_feature_registry(
    load_feature_definitions(Path(__file__).resolve().parents[3] / "configs/features.toml")
)


FEATURE_GROUP_IDS = REGISTRY.feature_ids


runner = CliRunner()


def _feature_payload(*, future_odds: bool = False) -> dict[str, object]:
    records = []
    for position in range(1, 4):
        records.append(
            {
                "race_id": "race-1",
                "horse_id": f"horse-{position}",
                "freeze_at": "2026-01-01T12:00:00+00:00",
                "features": {
                    "ability": float(4 - position),
                    "historical_odds": 5.0 if future_odds else None,
                },
                "available_at": {
                    "ability": "2025-12-31T12:00:00+00:00",
                    **({"historical_odds": "2026-01-01T13:00:00+00:00"} if future_odds else {}),
                },
                "finish_position": position,
            }
        )
    return {
        "schema_id": "cli-v1",
        "feature_names": ["ability", "historical_odds"],
        "records": records,
    }


def _explanatory_payload(*, target_result: bool = False) -> dict[str, object]:
    return {
        "records": [
            {
                "race_id": "race-1",
                "horse_id": "horse-1",
                "freeze_at": "2026-01-01T12:00:00+00:00",
                "groups": {
                    feature_id: {
                        "values": (
                            {"market_win_odds": 1.0}
                            if feature_id == "F19"
                            else {"feature_value": 1.0}
                        ),
                        "available_at": "2025-12-31T12:00:00+00:00",
                        "source_event_at": "2025-12-31T00:00:00+00:00",
                        "source_scope": "historical",
                        "status": "confirmed",
                        "source_race_ids": ["past-race-1"],
                        "contains_target_result": target_result if feature_id == "F01" else False,
                        "contains_future_data": False,
                    }
                    for feature_id in FEATURE_GROUP_IDS
                },
            }
        ]
    }


@pytest.mark.parametrize("command", ["audit", "features", "explanatory-variables"])
def test_feature_commands_can_run_on_a_fresh_typer_app(tmp_path: Path, command: str) -> None:
    feature_app = Typer(no_args_is_help=True)
    register_feature_commands(feature_app)
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    payload = _explanatory_payload() if command == "explanatory-variables" else _feature_payload()
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        feature_app, [command, "--input", str(input_path), "--output", str(output_path)]
    )

    assert result.exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["audit"]["valid"] is True


def test_model_explanatory_variables_cli_writes_all_feature_groups(tmp_path: Path) -> None:
    input_path = tmp_path / "variables.json"
    output_path = tmp_path / "generated.json"
    input_path.write_text(json.dumps(_explanatory_payload()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "model",
            "explanatory-variables",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["feature_ids"] == list(FEATURE_GROUP_IDS)
    assert payload["audit"]["valid"] is True
    assert set(payload["records"][0]["groups"]) == set(FEATURE_GROUP_IDS)


def test_model_explanatory_variables_cli_rejects_target_race_result(tmp_path: Path) -> None:
    input_path = tmp_path / "variables.json"
    output_path = tmp_path / "generated.json"
    input_path.write_text(json.dumps(_explanatory_payload(target_result=True)), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "model",
            "explanatory-variables",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["audit"]["valid"] is False
    assert any(
        "target race result is not allowed" in violation["reason"]
        for violation in payload["audit"]["violations"]
    )


def test_model_explanatory_variables_cli_rejects_unspecified_boundary_flags(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "variables.json"
    output_path = tmp_path / "generated.json"
    payload = _explanatory_payload()
    records = cast(list[dict[str, object]], payload["records"])
    groups = cast(dict[str, object], records[0]["groups"])
    group = cast(dict[str, object], groups["F01"])
    del group["contains_target_result"]
    del group["contains_future_data"]
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "model",
            "explanatory-variables",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 1
    error_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert error_payload["error"]["type"] == "input"
    assert "contains_future_data" in error_payload["error"]["message"]
    assert "contains_target_result" in error_payload["error"]["message"]


def test_model_explanatory_variables_cli_reports_source_event_at_separately(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "variables.json"
    output_path = tmp_path / "generated.json"
    payload = _explanatory_payload()
    records = cast(list[dict[str, object]], payload["records"])
    groups = cast(dict[str, object], records[0]["groups"])
    group = cast(dict[str, object], groups["F01"])
    group["source_event_at"] = "2026-01-01T12:01:00+00:00"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "model",
            "explanatory-variables",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 1
    error_payload = json.loads(output_path.read_text(encoding="utf-8"))
    violation = next(
        item
        for item in error_payload["audit"]["violations"]
        if item["reason"] == "source_event_at is after freeze_at"
    )
    assert violation["source_event_at"] == "2026-01-01T12:01:00+00:00"
    assert violation["available_at"] is None


def test_model_features_cli_writes_audited_missing_features(tmp_path: Path) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "generated.json"
    input_path.write_text(json.dumps(_feature_payload()), encoding="utf-8")

    result = runner.invoke(
        app,
        ["model", "features", "--input", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["audit"]["valid"] is True
    assert payload["records"][0]["available_at"]["ability"] == ("2025-12-31T12:00:00+00:00")
    assert payload["records"][0]["available_at"]["historical_odds"] is None
    assert payload["records"][0]["features"]["historical_odds"] is None


def test_model_features_cli_serializes_nan_as_json_null(tmp_path: Path) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "generated.json"
    payload = _feature_payload()
    records = cast(list[dict[str, object]], payload["records"])
    for record in records:
        features = cast(dict[str, object], record["features"])
        features["historical_odds"] = float("nan")
    input_path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")

    result = runner.invoke(
        app,
        ["model", "features", "--input", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0
    output_text = output_path.read_text(encoding="utf-8")
    assert "NaN" not in output_text
    output = json.loads(output_text)
    assert output["records"][0]["features"]["historical_odds"] is None


def test_model_audit_cli_writes_structured_error_for_invalid_json(tmp_path: Path) -> None:
    input_path = tmp_path / "invalid.json"
    output_path = tmp_path / "audit.json"
    input_path.write_text("{", encoding="utf-8")

    result = runner.invoke(
        app,
        ["model", "audit", "--input", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["error"]["type"] == "input"
    assert "cannot read input JSON" in payload["error"]["message"]


def test_model_audit_cli_returns_nonzero_for_future_feature(tmp_path: Path) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "audit.json"
    input_path.write_text(json.dumps(_feature_payload(future_odds=True)), encoding="utf-8")

    result = runner.invoke(
        app,
        ["model", "audit", "--input", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert list(payload) == ["schema_id", "feature_names", "freeze_at", "audit"]
    assert payload["audit"]["valid"] is False
    assert payload["feature_names"] == ["ability", "historical_odds"]
    assert payload["freeze_at"] == ["2026-01-01T12:00:00+00:00"] * 3
    assert "after freeze_at" in payload["audit"]["violations"][0]["reason"]


@pytest.mark.parametrize("command", ["features", "walk-forward"])
def test_model_generation_errors_preserve_schema_and_audit_context(
    tmp_path: Path, command: str
) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "error.json"
    input_path.write_text(json.dumps(_feature_payload(future_odds=True)), encoding="utf-8")
    arguments = ["model", command, "--input", str(input_path), "--output", str(output_path)]
    if command == "walk-forward":
        arguments.extend(
            ["--min-train-races=1", "--validation-races=1", "--test-races=1", "--step-races=1"]
        )

    result = runner.invoke(app, arguments)

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert list(payload) == ["schema_id", "audit", "error"]
    assert payload["schema_id"] == "cli-v1"
    assert payload["audit"]["valid"] is False
    assert payload["audit"]["violations"][0]["feature_name"] == "historical_odds"
    assert payload["error"]["type"] == "input"
    assert "after freeze_at" in payload["error"]["message"]


def test_model_audit_cli_writes_structured_error_for_invalid_utf8(tmp_path: Path) -> None:
    input_path = tmp_path / "invalid-encoding.json"
    output_path = tmp_path / "audit.json"
    input_path.write_bytes(b"\xff")

    result = runner.invoke(
        app,
        ["model", "audit", "--input", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["error"]["type"] == "input"
    assert "cannot read input JSON" in payload["error"]["message"]


@pytest.mark.parametrize("command", ["audit", "features", "explanatory-variables", "walk-forward"])
@pytest.mark.parametrize(
    ("source", "message"),
    [
        pytest.param(None, "cannot read input JSON", id="file-error"),
        pytest.param(b"\xff", "cannot read input JSON", id="invalid-utf8"),
        pytest.param(b"{", "cannot read input JSON", id="invalid-json"),
        pytest.param(b"[]", "input JSON must be an object", id="non-object-root"),
    ],
)
def test_model_commands_preserve_json_input_errors(
    tmp_path: Path, command: str, source: bytes | None, message: str
) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "results" / "output.json"
    if source is not None:
        input_path.write_bytes(source)
    arguments = ["model", command, "--input", str(input_path), "--output", str(output_path)]
    if command == "walk-forward":
        arguments.extend(
            [
                "--min-train-races",
                "1",
                "--validation-races",
                "1",
                "--test-races",
                "1",
                "--step-races",
                "1",
            ]
        )

    result = runner.invoke(app, arguments)

    assert result.exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"type", "message"}
    assert payload["error"]["type"] == "input"
    if message == "input JSON must be an object":
        assert payload["error"]["message"] == message
    else:
        assert payload["error"]["message"].startswith(f"{message}: ")


def test_model_generated_features_can_be_audited_again(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    generated_path = tmp_path / "generated.json"
    audit_path = tmp_path / "audit.json"
    input_path.write_text(json.dumps(_feature_payload()), encoding="utf-8")

    generated = runner.invoke(
        app,
        ["model", "features", "--input", str(input_path), "--output", str(generated_path)],
    )
    assert generated.exit_code == 0
    audited = runner.invoke(
        app,
        ["model", "audit", "--input", str(generated_path), "--output", str(audit_path)],
    )

    assert audited.exit_code == 0
    generation_payload = json.loads(generated_path.read_text(encoding="utf-8"))
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit_payload["schema_id"] == generation_payload["schema_id"]
    assert audit_payload["feature_names"] == generation_payload["feature_names"]
    assert audit_payload["audit"] == generation_payload["audit"]
    assert audit_payload["audit"]["missing_values"] == 3


def test_model_walk_forward_cli_writes_structured_input_error(tmp_path: Path) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "walk-forward.json"
    payload = _feature_payload()
    records = cast(list[dict[str, object]], payload["records"])
    records[0].pop("finish_position")
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "model",
            "walk-forward",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--min-train-races",
            "1",
            "--validation-races",
            "1",
            "--test-races",
            "1",
            "--step-races",
            "1",
        ],
    )

    assert result.exit_code == 1
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["error"]["type"] == "input"
    assert "finish_position" in output["error"]["message"]


def test_model_walk_forward_cli_includes_schema_and_freeze_times(tmp_path: Path) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "walk-forward.json"
    input_path.write_text(json.dumps(_feature_payload()), encoding="utf-8")

    metrics = RankingMetrics(ndcg_at_3=0.75, top1_accuracy=0.5, top3_overlap=1.0)
    fold = Mock()
    fold.fold_index = 0
    fold.train_race_ids = ("race-1",)
    fold.validation_race_ids = ("race-2",)
    fold.test_race_ids = ("race-3",)
    fold.train_freeze_at = (datetime(2026, 1, 1, 12, tzinfo=UTC),)
    fold.validation_freeze_at = (datetime(2026, 1, 2, 12, tzinfo=UTC),)
    fold.test_freeze_at = (datetime(2026, 1, 3, 12, tzinfo=UTC),)
    fold_result = Mock(fold=fold, metrics=metrics)
    evaluation = Mock(fold_results=(fold_result,), metrics=metrics)
    with patch("cli.models.evaluate_walk_forward", return_value=evaluation):
        result = runner.invoke(
            app,
            [
                "model",
                "walk-forward",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--min-train-races",
                "1",
                "--validation-races",
                "1",
                "--test-races",
                "1",
                "--step-races",
                "1",
            ],
        )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["feature_names"] == ["ability", "historical_odds"]
    assert payload["evaluation"]["folds"][0]["train_freeze_at"] == ["2026-01-01T12:00:00+00:00"]


def test_model_walk_forward_cli_writes_structured_error_for_invalid_window(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "features.json"
    output_path = tmp_path / "walk-forward.json"
    input_path.write_text(json.dumps(_feature_payload()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "model",
            "walk-forward",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--min-train-races",
            "0",
            "--validation-races",
            "1",
            "--test-races",
            "1",
            "--step-races",
            "1",
        ],
    )

    assert result.exit_code == 1
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["error"]["type"] == "input"
    assert "positive integer" in output["error"]["message"]
