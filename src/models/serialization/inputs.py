"""Convert decoded JSON objects into model feature input contracts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from typing import cast

from make_features.catalog.registry import FeatureRegistry, create_feature_registry
from make_features.contracts.observations import Evidence
from make_features.contracts.types import FeatureDefinition
from make_features.explanatory_variables import build_explanatory_variables
from make_features.real_market import MARKET_IMPLEMENTATION
from make_features.reference_rules import REFERENCE_IMPLEMENTATION
from make_features.serialization.inputs import parse_explanatory_inputs
from make_features.serialization.observations import (
    parse_calculation_dependencies,
    parse_calculation_parameters,
)
from make_features.serialization.outputs import feature_audit_payload
from make_features.validation.observations import validate_evidence_version, validate_parameters
from models.dataset.calculated import CalculationContract
from models.dataset.rows import FeatureInput, FeatureValue, TimestampInput
from models.dataset.schema import FeatureSchema
from models.serialization.real_market import validate_real_market_payload
from models.serialization.reference import validate_reference_payload


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
    if "feature_schema" in payload:
        schema = FeatureSchema.from_metadata(payload["feature_schema"])
        if schema.schema_id != schema_id or schema.feature_names != tuple(feature_names):
            raise ValueError("feature_schema does not match schema_id and feature_names")
    else:
        schema = FeatureSchema.from_names(
            tuple(cast(list[str], feature_names)), schema_id=schema_id
        )
    records = tuple(_feature_input(value) for value in raw_records)
    if schema.calculation_contract is not None:
        if schema.calculation_contract.settings["implementation"] == MARKET_IMPLEMENTATION:
            validate_real_market_payload(payload, schema, records)
        elif schema.calculation_contract.settings["implementation"] == REFERENCE_IMPLEMENTATION:
            validate_reference_payload(payload, schema, records)
        else:
            _validate_calculation(payload.get("calculation"), schema, records)
    return schema, records


def _calculation_registry(value: object) -> FeatureRegistry:
    if not isinstance(value, list):
        raise ValueError("calculation requires complete feature_definitions")
    definitions = []
    for entry in value:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"feature_id", "name"}
            or any(not isinstance(v, str) or not v or v != v.strip() for v in entry.values())
        ):
            raise ValueError("invalid calculation feature_definitions")
        definitions.append(FeatureDefinition(entry["feature_id"], entry["name"]))
    return create_feature_registry(definitions)


def _validate_calculation(
    value: object, schema: FeatureSchema, records: tuple[FeatureInput, ...]
) -> None:
    contract = schema.calculation_contract
    if contract is None:
        raise ValueError("calculation contract is required")
    required = {
        "calculation_schema_version",
        "feature_definitions",
        "feature_ids",
        "parameters",
        "records",
        "audit",
        "dependencies",
        "source_missing_reasons",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("calculated inputs require the complete calculation payload")
    calculation = cast(dict[str, object], value)
    if (
        type(calculation["calculation_schema_version"]) is not int
        or calculation["calculation_schema_version"] != 1
    ):
        raise ValueError("calculation_schema_version must be 1")
    if not isinstance(calculation["parameters"], dict):
        raise ValueError("calculation requires parameters")
    parameters = parse_calculation_parameters(cast(dict[str, object], calculation["parameters"]))
    validate_parameters(parameters)
    if CalculationContract.create(parameters, schema.feature_names) != schema.calculation_contract:
        raise ValueError("calculation parameters differ from feature_schema contract")
    registry = _calculation_registry(calculation["feature_definitions"])
    if calculation["feature_ids"] != list(registry.feature_ids):
        raise ValueError("calculation feature IDs differ from definitions")
    built = build_explanatory_variables(parse_explanatory_inputs(calculation), registry=registry)
    if calculation["audit"] != feature_audit_payload(built.audit):
        raise ValueError("calculation audit differs from recomputed audit")
    dependencies = parse_calculation_dependencies(calculation["dependencies"])
    if len(records) != len(built.inputs) or len(dependencies) != len(built.inputs):
        raise ValueError("calculation and model record counts differ")
    source_reasons = calculation["source_missing_reasons"]
    if not isinstance(source_reasons, list) or not source_reasons:
        raise ValueError("calculation requires source_missing_reasons")
    for observation in source_reasons:
        if not isinstance(observation, dict) or any(
            not isinstance(key, str)
            or not isinstance(reasons, dict)
            or any(
                not isinstance(k, str) or not isinstance(v, str) or not v
                for k, v in reasons.items()
            )
            for key, reasons in observation.items()
        ):
            raise ValueError("invalid calculation source_missing_reasons")
    seen: set[tuple[str, str]] = set()
    source_versions: dict[tuple[str, str, int], Evidence] = {}
    for row, batch, manifest in zip(records, built.inputs, dependencies, strict=True):
        identity = (batch.race_id, batch.horse_id)
        if (
            identity in seen
            or identity != (row.race_id, row.horse_id)
            or identity != (manifest.race_id, manifest.horse_id)
        ):
            raise ValueError("calculation and model race/horse identities differ")
        seen.add(identity)
        freeze = _timestamp(batch.freeze_at)
        if _timestamp(row.freeze_at) != freeze:
            raise ValueError("calculation and model freeze_at differ")
        if set(manifest.groups) != set(registry.feature_ids):
            raise ValueError("calculation dependency groups differ from definitions")
        available: dict[str, datetime] = {}
        for feature_id, group in batch.groups.items():
            dependency = manifest.groups[feature_id]
            if dependency.rule_id != parameters.rule_id or not dependency.sources:
                raise ValueError("calculation requires matching rules and source dependencies")
            if dependency.historical_race_ids != tuple(group.source_race_ids):
                raise ValueError("calculation historical race dependencies differ")
            if parameters.evidence not in dependency.sources:
                raise ValueError(
                    "calculation dependencies must include parameter selection evidence"
                )
            references = set()
            for source in dependency.sources:
                validate_evidence_version(source, source_versions)
                if source.available_at > freeze or source.event_at > freeze:
                    raise ValueError("calculation source evidence is later than freeze_at")
                reference = (source.source, source.observation_id, source.version)
                if reference in references:
                    raise ValueError("duplicate calculation source version")
                references.add(reference)
            maximum = max(source.available_at for source in dependency.sources)
            available[feature_id] = maximum
            nonmissing = any(v is not None for v in group.values.values())
            if (
                (None if group.available_at is None else _timestamp(group.available_at))
                != (maximum if nonmissing else None)
                or _timestamp(group.source_event_at)
                != max(source.event_at for source in dependency.sources)
                or group.status != ("confirmed" if nonmissing else "missing")
                or group.source_scope
                != (
                    "pre_race"
                    if registry.by_id(feature_id).definition.name == "market_characteristics"
                    else "historical"
                )
            ):
                raise ValueError(
                    "calculation group timestamps or boundaries differ from dependencies"
                )
            if any(
                v is None and not dependency.missing_reasons.get(k) for k, v in group.values.items()
            ):
                raise ValueError("calculation missing values require dependency reasons")
        if set(row.features) != set(schema.feature_names) or set(row.available_at) != set(
            schema.feature_names
        ):
            raise ValueError("calculation model columns differ from selection")
        for column in contract.columns():
            feature_id = registry.by_name(column.group).definition.feature_id
            if column.column not in batch.groups[feature_id].values:
                raise ValueError("selected calculation column is missing")
            actual = row.features[column.name]
            expected = batch.groups[feature_id].values[column.column]
            for numeric in (actual, expected):
                if numeric is not None and (
                    type(numeric) not in (int, float) or not isfinite(cast(float, numeric))
                ):
                    raise ValueError("selected calculation values must be finite numeric or null")
            if (
                actual != expected
                or _timestamp(row.available_at[column.name]) != available[feature_id]
            ):
                raise ValueError("calculation model values or availability differ from group")


def _timestamp(value: object) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("calculation requires timezone-aware timestamps")
    return value


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
