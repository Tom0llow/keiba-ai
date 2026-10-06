"""Tests for the Typer data CLI."""

import json
from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from data.race_key import RaceKey
from main import app

runner = CliRunner()


def test_historical_cli_retrieves_then_rebuilds_processed_data() -> None:
    retriever = Mock()
    retriever.retrieve_historical.return_value = 12
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    with (
        patch("main.DataRetriever.from_toml", return_value=retriever) as from_toml,
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=historical"])

    assert result.exit_code == 0
    assert "12 races" in result.stdout
    retriever.retrieve_historical.assert_called_once_with()
    preprocesser.rebuild.assert_called_once_with()
    kwargs = from_toml.call_args.kwargs
    assert kwargs["data_config"].as_posix() == "config/data.toml"
    assert kwargs["jvlink_config"].as_posix() == "config/jvlink.toml"


def test_latest_cli_retrieves_then_refreshes_processed_data() -> None:
    retriever = Mock()
    preprocesser = Mock()
    preprocesser.update.return_value = {"NL_RA_RACE": 100}
    with (
        patch("main.DataRetriever.from_toml", return_value=retriever),
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=latest"])

    assert result.exit_code == 0
    retriever.retrieve_latest.assert_called_once_with()
    preprocesser.update.assert_called_once_with()


def test_realtime_cli_retrieves_then_publishes_race_parquet() -> None:
    retriever = Mock()
    retriever.retrieve_realtime.return_value = 17
    preprocesser = Mock()
    preprocesser.update_race.return_value = {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 10,
        "ARCHIVE_O2_ODDS_UMAREN": 7,
    }
    with (
        patch("main.DataRetriever.from_toml", return_value=retriever),
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(
            app,
            [
                "--retrieve",
                "--mode=realtime",
                "--date",
                "2026-10-04",
                "--jyo",
                "05",
                "--kaiji",
                "04",
                "--nichiji",
                "08",
                "--race",
                "11",
            ],
        )

    assert result.exit_code == 0
    assert "17 rows" in result.stdout
    retriever.retrieve_realtime.assert_called_once_with(
        race_date=date(2026, 10, 4),
        jyo_code="05",
        kaiji="04",
        nichiji="08",
        race_number="11",
    )
    preprocesser.update_race.assert_called_once_with(
        RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    )


def test_realtime_cli_uses_race_config_when_options_are_omitted() -> None:
    retriever = Mock()
    retriever.retrieve_realtime.return_value = 17
    preprocesser = Mock()
    preprocesser.update_race.return_value = {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": 10,
        "ARCHIVE_O2_ODDS_UMAREN": 7,
    }
    race_key = RaceKey(date(2026, 10, 4), "05", "04", "08", "11")
    with (
        patch("main.JVLinkConfig.from_toml", return_value=Mock(realtime_race=race_key)),
        patch("main.DataRetriever.from_toml", return_value=retriever),
        patch("main.DataPreprocesser.from_toml", return_value=preprocesser),
    ):
        result = runner.invoke(app, ["--retrieve", "--mode=realtime"])

    assert result.exit_code == 0
    retriever.retrieve_realtime.assert_called_once_with(
        race_date=date(2026, 10, 4),
        jyo_code="05",
        kaiji="04",
        nichiji="08",
        race_number="11",
    )
    preprocesser.update_race.assert_called_once_with(race_key)


def test_retrieve_subcommand_is_removed() -> None:
    result = runner.invoke(app, ["retrieve", "historical"])

    assert result.exit_code == 2


def test_preprocess_rebuild_can_run_without_retrieval() -> None:
    preprocesser = Mock()
    preprocesser.rebuild.return_value = {"NL_RA_RACE": 100}
    with patch("main.DataPreprocesser.from_toml", return_value=preprocesser):
        result = runner.invoke(app, ["preprocess", "rebuild"])

    assert result.exit_code == 0
    preprocesser.rebuild.assert_called_once_with()


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
    assert payload["audit"]["valid"] is False
    assert "after freeze_at" in payload["audit"]["violations"][0]["reason"]


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
