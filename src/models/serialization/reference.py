"""Prepare and replay all-group snapshot reference inputs with shared source catalogs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from make_features.catalog.registry import FeatureRegistry, create_feature_registry
from make_features.contracts.observations import Evidence
from make_features.contracts.types import FeatureDefinition
from make_features.generation.calculate import (
    FeatureCalculationResult,
    calculate_reference_features,
)
from make_features.real_market import canonical_hash, timestamp
from make_features.reference_raw import normal_result, validate_reference_projections
from make_features.reference_rules import REFERENCE_IMPLEMENTATION, validate_reference_rules
from make_features.reference_snapshot import normalize_reference_input
from make_features.serialization.observations import normalized_payload
from make_features.serialization.outputs import explanatory_payload
from make_features.validation.observations import validate_evidence_version
from models.dataset.calculated import CalculationContract
from models.dataset.rows import FeatureInput
from models.dataset.schema import FeatureSchema
from models.serialization.real_market import SnapshotResultLabel

REFERENCE_LABEL_ASSURANCE = "assumed_snapshot_results_revision_time_unverified"


def reference_assurance(rules: Mapping[str, object]) -> dict[str, object]:
    """Describe declared use boundaries without claiming historical clock certification."""
    return {
        "implementation": REFERENCE_IMPLEMENTATION,
        "rules": validate_reference_rules(rules),
        "received_at": None,
        "historical_reception_verified": False,
        "revision_time_verified": False,
        "target_going": "unknown_preserved_null",
        "class_mapping": "unknown_preserved_null",
        "label_boundary_meaning": "declared_usable_after_not_observed_result_clock",
    }


def _calculation_payload(
    result: FeatureCalculationResult, registry: FeatureRegistry
) -> dict[str, object]:
    payload = explanatory_payload(result.built, feature_ids=registry.feature_ids)
    catalog: dict[str, object] = {}
    source_sets: dict[str, object] = {}
    history_sets: dict[str, object] = {}
    dependencies = []
    versions: dict[tuple[str, str, int], Evidence] = {}
    source_ids: dict[Evidence, str] = {}
    dependency_ids: dict[tuple[Evidence, ...], str] = {}
    history_ids: dict[tuple[str, ...], str] = {}
    for batch, manifest in zip(result.built.inputs, result.manifests, strict=True):
        groups: dict[str, object] = {}
        for feature_id, group in manifest.items():
            source_set = dependency_ids.get(group.dependencies)
            if source_set is None:
                references = []
                for source in group.dependencies:
                    reference = source_ids.get(source)
                    if reference is None:
                        validate_evidence_version(source, versions)
                        serialized = normalized_payload(source)
                        reference = canonical_hash(serialized)
                        source_ids[source] = reference
                        catalog[reference] = serialized
                    references.append(reference)
                source_set = canonical_hash(references)
                dependency_ids[group.dependencies] = source_set
                source_sets[source_set] = references
            history_set = history_ids.get(group.historical_race_ids)
            if history_set is None:
                history_set = canonical_hash(group.historical_race_ids)
                history_ids[group.historical_race_ids] = history_set
                history_sets[history_set] = list(group.historical_race_ids)
            groups[feature_id] = {
                "rule_id": result.parameters.rule_id,
                "source_set_id": source_set,
                "historical_race_set_id": history_set,
                "missing_reasons": dict(group.missing_reasons),
                "diagnostics": dict(group.diagnostics),
            }
        dependencies.append(
            {"race_id": batch.race_id, "horse_id": batch.horse_id, "groups": groups}
        )
    payload.update(
        calculation_schema_version=2,
        feature_definitions=normalized_payload(registry.definitions),
        parameters=normalized_payload(result.parameters),
        source_missing_reasons=normalized_payload(result.source_missing_reasons),
        source_catalog=catalog,
        source_sets=source_sets,
        historical_race_sets=history_sets,
        dependencies=dependencies,
    )
    return payload


def prepare_reference_payload(
    raw: Mapping[str, object], *, registry: FeatureRegistry, selected_columns: Sequence[str]
) -> dict[str, object]:
    """Normalize raw projections, run all 21 calculators, then project selected numbers."""
    _validate_snapshot(raw.get("snapshot"))
    normalized = normalize_reference_input(raw)
    rules = validate_reference_rules(raw["rules"])
    calculated = calculate_reference_features(
        normalized.observations, normalized.parameters, registry=registry
    )
    contract = CalculationContract.reference(normalized.parameters, rules, selected_columns)
    schema = FeatureSchema.calculated(contract)
    labels = {cast(str, label["race_id"]): label for label in normalized.labels}
    records: list[dict[str, object]] = []
    for batch, manifest in zip(calculated.built.inputs, calculated.manifests, strict=True):
        values: dict[str, object] = {}
        available: dict[str, object] = {}
        for column in contract.columns():
            group = manifest[registry.by_name(column.group).definition.feature_id]
            if column.column not in group.values:
                raise ValueError(f"selected reference calculation column is missing: {column.name}")
            value = group.values[column.column]
            if value is not None and type(value) not in (int, float):
                raise ValueError("selected reference columns require native numeric values or null")
            values[column.name] = value
            available[column.name] = max(e.available_at for e in group.dependencies).isoformat()
        record: dict[str, object] = {
            "race_id": batch.race_id,
            "horse_id": batch.horse_id,
            "freeze_at": batch.freeze_at.isoformat()
            if not isinstance(batch.freeze_at, str)
            else batch.freeze_at,
            "features": values,
            "available_at": available,
        }
        if batch.race_id in labels:
            label = labels[batch.race_id]
            result = cast(dict[str, object], label["raw"])
            _, _, finishes, _ = normal_result(
                cast(dict[str, object], result["ra"]),
                cast(list[dict[str, object]], result["se"]),
                days=cast(int, rules["result_delay_days"]),
            )
            record["finish_position"] = finishes[batch.horse_id]
        records.append(record)
    payload: dict[str, object] = {
        "schema_id": schema.schema_id,
        "feature_names": list(schema.feature_names),
        "feature_schema": schema.as_metadata(),
        "records": records,
        "calculation": _calculation_payload(calculated, registry),
        "reference_input": dict(raw),
        "reference_input_sha256": canonical_hash(raw),
        "assurance": reference_assurance(rules),
        "held_races": list(normalized.held_races),
    }
    if raw["include_labels"]:
        payload["label_sources"] = list(normalized.labels)
    return payload


def validate_reference_payload(
    payload: Mapping[str, object], schema: FeatureSchema, rows: Sequence[FeatureInput]
) -> None:
    """Recompute from raw source projections, sharing catalogued immutable evidence."""
    raw, calculation = payload.get("reference_input"), payload.get("calculation")
    if (
        not isinstance(raw, dict)
        or payload.get("reference_input_sha256") != canonical_hash(raw)
        or not isinstance(calculation, dict)
    ):
        raise ValueError("reference input original row or manifest hash mismatch")
    definitions = calculation.get("feature_definitions")
    if not isinstance(definitions, list) or any(
        not isinstance(d, dict)
        or set(d) != {"feature_id", "name"}
        or not all(isinstance(v, str) for v in d.values())
        for d in definitions
    ):
        raise ValueError("reference calculation requires explicit feature definitions")
    registry = create_feature_registry(
        tuple(FeatureDefinition(d["feature_id"], d["name"]) for d in definitions)
    )
    expected = prepare_reference_payload(
        raw, registry=registry, selected_columns=schema.feature_names
    )
    for key in ("feature_schema", "calculation", "assurance", "held_races", "label_sources"):
        if canonical_hash(payload.get(key)) != canonical_hash(expected.get(key)):
            raise ValueError(f"reference {key} differs from source recomputation")
    actual = [
        {
            "race_id": row.race_id,
            "horse_id": row.horse_id,
            "freeze_at": timestamp(row.freeze_at).isoformat(),
            "features": dict(row.features),
            "available_at": {k: timestamp(v).isoformat() for k, v in row.available_at.items()},
            **({"finish_position": row.finish_position} if row.finish_position is not None else {}),
        }
        for row in rows
    ]
    if canonical_hash(actual) != canonical_hash(expected["records"]):
        raise ValueError("reference model values, labels or availability differ from original rows")


def parse_reference_labels(
    payload: Mapping[str, object], *, required: bool
) -> tuple[SnapshotResultLabel, ...]:
    """Check permanent IDs, complete normal results and every declared label-use boundary."""
    sources = payload.get("label_sources")
    if sources is None and not required:
        return ()
    if (
        not isinstance(sources, list)
        or not sources
        or any(not isinstance(s, dict) for s in sources)
    ):
        raise ValueError("reference training requires complete label_sources")
    raw = payload.get("reference_input")
    records = payload.get("records")
    if (
        not isinstance(raw, dict)
        or not isinstance(records, list)
        or any(not isinstance(r, dict) for r in records)
    ):
        raise ValueError("reference labels require original input and model records")
    rules = validate_reference_rules(raw["rules"])
    labels = []
    label_results: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for source in sources:
        if set(source) != {
            "kind",
            "race_id",
            "raw",
            "raw_sha256",
            "usable_after",
            "result_delay_days",
            "received_at",
            "result_published_at",
            "revision_time_verified",
            "horse_mapping",
        }:
            raise ValueError("reference label evidence fields differ from its contract")
        result = source.get("raw")
        if (
            not isinstance(result, dict)
            or source.get("raw_sha256") != canonical_hash(result)
            or source.get("result_delay_days") != rules["result_delay_days"]
            or source.get("received_at") is not None
            or source.get("result_published_at") is not None
            or source.get("revision_time_verified") is not False
        ):
            raise ValueError("reference result original row hash or assumptions differ")
        identity, usable, finishes, _ = normal_result(
            cast(dict[str, object], result["ra"]),
            cast(list[dict[str, object]], result["se"]),
            days=cast(int, rules["result_delay_days"]),
        )
        mapping = {
            row["Umaban"]: row["KettoNum"] for row in cast(list[dict[str, object]], result["se"])
        }
        if source["horse_mapping"] != mapping:
            raise ValueError("reference label horse mapping differs from original SE")
        chosen = [r for r in records if r.get("race_id") == identity]
        if (
            source.get("kind") != "reference_result_v1"
            or source.get("race_id") != identity
            or identity in seen
            or not chosen
            or source.get("usable_after") != usable.isoformat()
            or set(finishes) != {r["horse_id"] for r in chosen}
            or any(
                type(r.get("finish_position")) is not int
                or r["finish_position"] != finishes[r["horse_id"]]
                for r in chosen
            )
        ):
            raise ValueError("reference labels differ from complete original results")
        seen.add(identity)
        label_results.append(result)
        labels.append(SnapshotResultLabel(identity, usable, REFERENCE_LABEL_ASSURANCE, source))
    if seen != {r["race_id"] for r in records}:
        raise ValueError("reference labels must cover every model race")
    validate_reference_projections(raw.get("tables"), label_results=label_results)
    return tuple(labels)


def _validate_snapshot(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"snapshot_id", "snapshot_path", "tables"}
        or not isinstance(value["tables"], dict)
    ):
        raise ValueError("reference input requires a fixed snapshot manifest")
    required = {
        "NL_RA_RACE",
        "NL_SE_RACE_UMA",
        "ARCHIVE_O1_ODDS_TANFUKUWAKU",
        "ARCHIVE_O2_ODDS_UMAREN",
        "NL_HC_HANRO",
        "NL_WC_WOOD",
        "NL_UM_UMA",
    }
    if set(value["tables"]) != required:
        raise ValueError("reference snapshot table sources differ")
    for name, entry in value["tables"].items():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"file", "sha256"}
            or entry["file"] != f"{name}.parquet"
            or not isinstance(entry["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
        ):
            raise ValueError("reference snapshot table files require exact SHA-256 identities")
