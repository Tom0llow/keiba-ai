"""Project audited calculations and join separately evidenced complete result labels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from itertools import chain
from math import isfinite
from typing import cast

from make_features.catalog.registry import FeatureRegistry
from make_features.contracts.observations import (
    CalculationDependencyRecord,
    Evidence,
    HistoricalRace,
)
from make_features.generation.calculate import FeatureCalculationResult
from make_features.serialization.observations import (
    calculation_payload,
    normalized_payload,
    parse_calculation_dependencies,
    parse_historical_results,
)
from make_features.validation.observations import (
    reject_reference,
    validate_evidence,
    validate_evidence_version,
    validate_race,
)
from models.dataset.calculated import CalculationContract
from models.dataset.schema import FeatureSchema
from models.serialization.real_market import SnapshotResultLabel, parse_snapshot_labels
from models.serialization.reference import parse_reference_labels


def prepare_model_payload(
    calculated: FeatureCalculationResult,
    *,
    registry: FeatureRegistry,
    selected_columns: Sequence[str],
    results: Sequence[HistoricalRace] | None = None,
) -> dict[str, object]:
    """Preserve missingness and provenance; attach results only after projection."""
    contract = CalculationContract.create(calculated.parameters, selected_columns)
    schema = FeatureSchema.calculated(contract)
    records: list[dict[str, object]] = []
    for batch, manifest in zip(calculated.built.inputs, calculated.manifests, strict=True):
        features: dict[str, object] = {}
        availability: dict[str, object] = {}
        for column in contract.columns():
            group = manifest[registry.by_name(column.group).definition.feature_id]
            if column.column not in group.values:
                raise ValueError(f"selected calculation column is missing: {column.name}")
            value = group.values[column.column]
            if value is not None and (
                type(value) not in (int, float) or not isfinite(cast(float, value))
            ):
                raise ValueError(
                    f"selected calculation column must be finite numeric or None: {column.name}"
                )
            if not group.dependencies:
                raise ValueError("selected calculation requires source dependencies")
            features[column.name] = value
            availability[column.name] = max(e.available_at for e in group.dependencies).isoformat()
        records.append(
            {
                "race_id": batch.race_id,
                "horse_id": batch.horse_id,
                "freeze_at": batch.freeze_at.isoformat()
                if isinstance(batch.freeze_at, datetime)
                else batch.freeze_at,
                "features": features,
                "available_at": availability,
            }
        )
    payload: dict[str, object] = {
        "schema_id": schema.schema_id,
        "feature_names": list(schema.feature_names),
        "feature_schema": schema.as_metadata(),
        "records": records,
        "calculation": calculation_payload(calculated, feature_ids=registry.feature_ids),
        "assurance": "declared_timestamp_evidence_not_external_certification",
    }
    cast(dict[str, object], payload["calculation"])["feature_definitions"] = normalized_payload(
        registry.definitions
    )
    if results is not None:
        _join_results(records, results)
        payload["label_sources"] = [
            {
                "race_id": race.race_id,
                "horse_ids": [r.horse_id for r in race.runners],
                "result": normalized_payload(race),
            }
            for race in results
        ]
        _validate_label_evidence(payload, results)
    return payload


def _join_results(records: Sequence[dict[str, object]], results: Sequence[HistoricalRace]) -> None:
    by_race: dict[str, dict[str, dict[str, object]]] = {}
    for record in records:
        race_id, horse_id = cast(str, record["race_id"]), cast(str, record["horse_id"])
        horses = by_race.setdefault(race_id, {})
        if horse_id in horses:
            raise ValueError("duplicate model race/horse identity")
        horses[horse_id] = record
    seen: set[str] = set()
    for race in results:
        reject_reference(race)
        validate_evidence(race.evidence)
        validate_race(race)
        if race.evidence.event_at <= race.started_at:
            raise ValueError("result event must be strictly after the race start")
        if race.race_id in seen or race.race_id not in by_race:
            raise ValueError("duplicate or unexpected result race")
        seen.add(race.race_id)
        horses = by_race[race.race_id]
        if set(horses) != {r.horse_id for r in race.runners}:
            raise ValueError("result horse set does not match frozen model rows")
        if any(_timestamp(record["freeze_at"]) >= race.started_at for record in horses.values()):
            raise ValueError("frozen features must precede result race start")
        for runner in race.runners:
            horses[runner.horse_id]["finish_position"] = runner.finish
    if seen != set(by_race):
        raise ValueError("complete results are required for every model race")


def parse_label_sources(
    payload: Mapping[str, object], *, required: bool
) -> tuple[HistoricalRace | SnapshotResultLabel, ...]:
    """Validate the separate label manifest against every labeled input row."""
    raw = payload.get("label_sources")
    schema = payload.get("feature_schema")
    if isinstance(schema, dict):
        parsed_schema = FeatureSchema.from_metadata(schema)
        if (
            parsed_schema.calculation_contract is not None
            and parsed_schema.calculation_contract.settings["implementation"]
            == "snapshot_reference_21_groups_v1"
        ):
            return parse_reference_labels(payload, required=required)
        if (
            parsed_schema.calculation_contract is not None
            and parsed_schema.calculation_contract.settings["implementation"]
            == "published_win_market_v1"
        ):
            return parse_snapshot_labels(payload, required=required)
    if raw is None:
        if required:
            raise ValueError("calculated training inputs require label_sources")
        return ()
    if not isinstance(raw, list):
        raise ValueError("label_sources must be a list")
    results: list[object] = []
    declared: dict[str, list[str]] = {}
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"race_id", "horse_ids", "result"}:
            raise ValueError("invalid label source entry")
        race_id, horse_ids = entry["race_id"], entry["horse_ids"]
        if (
            not isinstance(race_id, str)
            or race_id in declared
            or not isinstance(horse_ids, list)
            or any(not isinstance(h, str) for h in horse_ids)
            or len(set(horse_ids)) != len(horse_ids)
        ):
            raise ValueError("label source identities must be unique")
        declared[race_id] = horse_ids
        result = parse_historical_results({"schema_version": 1, "results": [entry["result"]]})[0]
        if result.race_id != race_id or set(horse_ids) != {r.horse_id for r in result.runners}:
            raise ValueError("label source identities differ from complete result")
        results.append(entry["result"])
    races = parse_historical_results({"schema_version": 1, "results": results})
    for race in races:
        if race.race_id not in declared or set(declared[race.race_id]) != {
            r.horse_id for r in race.runners
        }:
            raise ValueError("label source identities differ from complete result")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or any(not isinstance(r, dict) for r in raw_records):
        raise ValueError("label source validation requires model records")
    records = cast(list[dict[str, object]], raw_records)
    copies = [dict(record) for record in records]
    _join_results(copies, races)
    if any(
        original.get("finish_position") != checked["finish_position"]
        for original, checked in zip(records, copies, strict=True)
    ):
        raise ValueError("record labels differ from evidenced results")
    _validate_label_evidence(payload, races)
    return races


def _validate_label_evidence(
    payload: Mapping[str, object], results: Sequence[HistoricalRace]
) -> None:
    dependencies: tuple[CalculationDependencyRecord, ...] = ()
    if "calculation" in payload:
        calculation = payload["calculation"]
        if not isinstance(calculation, Mapping):
            raise ValueError("calculation requires its dependency manifest")
        dependencies = parse_calculation_dependencies(calculation.get("dependencies"))
    source_versions: dict[tuple[str, str, int], Evidence] = {}
    for source in chain(
        (
            source
            for manifest in dependencies
            for group in manifest.groups.values()
            for source in group.sources
        ),
        (race.evidence for race in results),
    ):
        validate_evidence_version(source, source_versions)


def label_known_through(results: Sequence[HistoricalRace | SnapshotResultLabel]) -> datetime:
    """Return the latest evidenced availability or explicitly declared label-use boundary."""
    if not results:
        raise ValueError("training label evidence cannot be empty")
    return max(
        r.usable_after if isinstance(r, SnapshotResultLabel) else r.evidence.available_at
        for r in results
    )


def label_manifest(results: Sequence[HistoricalRace | SnapshotResultLabel]) -> list[object]:
    """Serialize the full evidenced results for the immutable training context."""
    return [
        r.payload if isinstance(r, SnapshotResultLabel) else normalized_payload(r) for r in results
    ]


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("model freeze requires an aware ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("model freeze requires an aware ISO timestamp")
    return parsed
