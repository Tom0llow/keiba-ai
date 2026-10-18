"""Tests for reusable feature and model JSON contract conversion."""

import subprocess
import sys
from datetime import UTC, datetime
from math import isnan
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureAudit, FeatureBuildResult
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.outputs import explanatory_payload, explanatory_records
from models.dataset.builder import build_features
from models.evaluation.metrics import RankingMetrics
from models.evaluation.walk_forward import WalkForwardEvaluation
from models.serialization.inputs import parse_feature_inputs
from models.serialization.outputs import (
    generated_records,
    model_audit_payload,
    model_evaluation_payload,
    model_features_payload,
)


def _group() -> dict[str, object]:
    return {
        "values": {"name": "競走馬", "missing": None, "nan": float("nan")},
        "available_at": None,
        "source_event_at": "2025-12-31T12:00:00+00:00",
        "source_scope": "historical",
        "status": "missing",
        "source_race_ids": ["previous-race"],
        "contains_target_result": False,
        "contains_future_data": False,
    }


def _record(group: dict[str, object]) -> dict[str, object]:
    return {
        "race_id": "race-1",
        "horse_id": "horse-1",
        "freeze_at": "2026-01-01T12:00:00+00:00",
        "groups": {"F01": group},
    }


def test_feature_conversion_preserves_explicit_values_and_source_boundaries() -> None:
    group = _group()
    record = _record(group)
    records = parse_explanatory_inputs(MappingProxyType({"records": [record]}))

    assert len(records) == 1
    parsed = records[0]
    assert (parsed.race_id, parsed.horse_id, parsed.freeze_at) == (
        "race-1",
        "horse-1",
        "2026-01-01T12:00:00+00:00",
    )
    source = parsed.groups["F01"]
    assert source.source_race_ids == ("previous-race",)
    assert source.available_at is None
    assert source.source_event_at == group["source_event_at"]
    assert source.source_scope == "historical"
    assert source.status == "missing"
    assert source.contains_target_result is False
    assert source.contains_future_data is False
    assert source.values["name"] == "競走馬"
    assert source.values["missing"] is None
    assert isnan(cast(float, source.values["nan"]))
    assert group["source_race_ids"] == ["previous-race"]

    freeze_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    result = FeatureBuildResult(
        records,
        {"F01": (FeatureTableRow("race-1", "horse-1", freeze_at, None, dict(source.values)),)},
        FeatureAudit(1, 1, 1, 2, ()),
    )
    output = explanatory_records(result)
    output_group = cast(dict[str, object], cast(dict[str, object], output[0]["groups"])["F01"])
    assert output[0]["freeze_at"] == record["freeze_at"]
    assert output_group == group
    assert isinstance(group["source_race_ids"], list)


@pytest.mark.parametrize("field", ["contains_target_result", "contains_future_data"])
def test_feature_parser_requires_explicit_boolean_boundaries(field: str) -> None:
    group = _group()
    del group[field]
    with pytest.raises(ValueError, match="requires explicit boundary flags") as error:
        parse_explanatory_inputs({"records": [_record(group)]})
    assert type(error.value) is ValueError

    group[field] = 0
    with pytest.raises(ValueError, match="boundary flags must be boolean"):
        parse_explanatory_inputs({"records": [_record(group)]})


@pytest.mark.parametrize("field", ["finish_position", "future_result"])
def test_feature_parser_rejects_model_labels_and_unsupported_fields(field: str) -> None:
    record = _record(_group())
    record[field] = 1
    with pytest.raises(ValueError, match=r"finish_position|unsupported fields"):
        parse_explanatory_inputs({"records": [record]})


def test_model_conversion_preserves_labels_missing_values_and_timestamp_strings() -> None:
    freeze_at = "2026-01-01T12:00:00+00:00"
    payload = MappingProxyType(
        {
            "schema_id": "serialization-v1",
            "feature_names": ["historical_odds", "ability"],
            "records": [
                {
                    "race_id": "race-1",
                    "horse_id": f"horse-{position}",
                    "freeze_at": freeze_at,
                    "features": {"historical_odds": float("nan"), "ability": 2.0},
                    "available_at": {"ability": freeze_at},
                    "finish_position": position,
                }
                for position in range(1, 4)
            ],
        }
    )
    schema, records = parse_feature_inputs(payload)
    assert schema.schema_id == "serialization-v1"
    assert schema.feature_names == ("historical_odds", "ability")
    assert records[0].freeze_at == freeze_at
    assert records[0].finish_position == 1
    assert isnan(cast(float, records[0].features["historical_odds"]))

    output = generated_records(build_features(records, feature_schema=schema))
    assert output[0]["finish_position"] == 1
    assert output[0]["freeze_at"] == freeze_at
    assert cast(dict[str, object], output[0]["available_at"])["ability"] == freeze_at
    assert isnan(cast(float, cast(dict[str, object], output[0]["features"])["historical_odds"]))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "input JSON requires schema_id and feature_names"),
        ({"schema_id": "v1", "feature_names": [1]}, "feature_names must be a list of strings"),
        ({"schema_id": "v1", "feature_names": ["ability"]}, "input JSON requires a records list"),
        (
            {"schema_id": "v1", "feature_names": ["ability"], "records": [None]},
            "each record must be a JSON object",
        ),
    ],
)
def test_model_parser_raises_plain_validation_errors(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message) as error:
        parse_feature_inputs(payload)
    assert type(error.value) is ValueError
    assert str(error.value) == message


def test_explanatory_document_preserves_explicit_registration_order_without_rows() -> None:
    feature_ids = ("custom-z", "custom-a")
    result = FeatureBuildResult((), MappingProxyType({}), FeatureAudit(0, 0, 0, 0, ()))

    payload = explanatory_payload(result, feature_ids=feature_ids)

    assert list(payload) == ["feature_ids", "records", "audit"]
    assert payload == {
        "feature_ids": ["custom-z", "custom-a"],
        "records": [],
        "audit": {
            "records_checked": 0,
            "groups_checked": 0,
            "non_missing_values": 0,
            "missing_values": 0,
            "valid": True,
            "violations": [],
        },
    }


def test_model_documents_preserve_schema_order_missing_values_and_timezone_offsets() -> None:
    schema, records = parse_feature_inputs(
        {
            "schema_id": "document-v1",
            "feature_names": ["historical_odds", "ability"],
            "records": [
                {
                    "race_id": "race-1",
                    "horse_id": f"horse-{position}",
                    "freeze_at": "2026-01-01T21:00:00+09:00",
                    "features": {"ability": 2.0, "historical_odds": None},
                    "available_at": {"ability": "2025-12-31T21:00:00+09:00"},
                }
                for position in range(1, 4)
            ],
        }
    )
    result = build_features(records, feature_schema=schema)
    audit = model_audit_payload(schema, records, result.audit)
    generated = model_features_payload(schema, result)
    evaluated = model_evaluation_payload(
        schema, result.audit, WalkForwardEvaluation((), RankingMetrics(0.75, 0.5, 1.0))
    )

    assert list(audit) == ["schema_id", "feature_names", "freeze_at", "audit"]
    assert list(generated) == ["schema_id", "feature_names", "records", "audit"]
    assert list(evaluated) == ["schema_id", "feature_names", "audit", "evaluation"]
    for payload in (audit, generated, evaluated):
        assert payload["schema_id"] == "document-v1"
        assert payload["feature_names"] == ["historical_odds", "ability"]
        assert payload["audit"] == {
            "records_checked": 3,
            "non_missing_values": 3,
            "missing_values": 3,
            "valid": True,
            "violations": [],
        }
    assert audit["freeze_at"] == ["2026-01-01T21:00:00+09:00"] * 3
    assert generated["records"] == [
        {
            "race_id": "race-1",
            "horse_id": f"horse-{position}",
            "freeze_at": "2026-01-01T21:00:00+09:00",
            "available_at": {"historical_odds": None, "ability": "2025-12-31T21:00:00+09:00"},
            "features": {"historical_odds": None, "ability": 2.0},
        }
        for position in range(1, 4)
    ]
    assert evaluated["evaluation"] == {
        "metrics": {"ndcg_at_3": 0.75, "top1_accuracy": 0.5, "top3_overlap": 1.0},
        "folds": [],
    }


def test_serializers_are_usable_without_typer_or_entry_point() -> None:
    src_dir = Path(__file__).resolve().parents[1]
    script = f"""import sys
sys.path.insert(0, {str(src_dir)!r})
sys.modules['typer'] = None
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.outputs import feature_audit_payload
from models.serialization.inputs import parse_feature_inputs
from models.serialization.outputs import metrics_payload
from data.saver.write_json import write_json
assert parse_explanatory_inputs({{'records': []}}) == ()
assert 'main' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
