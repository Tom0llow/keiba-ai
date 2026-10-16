"""Convert decoded JSON objects into model feature input contracts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from models.dataset_builder import FeatureInput, TimestampInput
from models.ranking_dataset import FeatureSchema, FeatureValue


def parse_feature_inputs(
    payload: Mapping[str, object],
) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    """Convert a decoded JSON object into the model schema and input rows."""
    schema_id = payload.get("schema_id")
    feature_names = payload.get("feature_names")
    raw_records = payload.get("records")
    if not isinstance(schema_id, str) or not isinstance(feature_names, list):
        raise ValueError("input JSON requires schema_id and feature_names")
    if not all(isinstance(name, str) for name in feature_names):
        raise ValueError("feature_names must be a list of strings")
    if not isinstance(raw_records, list):
        raise ValueError("input JSON requires a records list")
    schema = FeatureSchema.from_names(tuple(cast(list[str], feature_names)), schema_id=schema_id)
    records = tuple(_feature_input(value) for value in raw_records)
    return schema, records


def _feature_input(value: object) -> FeatureInput:
    if not isinstance(value, dict):
        raise ValueError("each record must be a JSON object")
    record = cast(dict[str, object], value)
    features = record.get("features")
    available_at = record.get("available_at")
    if not isinstance(features, dict) or not isinstance(available_at, dict):
        raise ValueError("each record requires features and available_at objects")
    return FeatureInput(
        race_id=cast(str, record.get("race_id")),
        horse_id=cast(str, record.get("horse_id")),
        freeze_at=cast(datetime | str, record.get("freeze_at")),
        features=cast(Mapping[str, FeatureValue], features),
        available_at=cast(Mapping[str, TimestampInput | None], available_at),
        finish_position=cast(int | None, record.get("finish_position")),
    )
