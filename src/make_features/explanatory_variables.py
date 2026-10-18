"""Build explanatory-variable middle rows through their individual modules."""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING

from make_features.generation.normalization import normalize_batch
from make_features.validation.audit import audit_feature_inputs as _audit_feature_inputs

if TYPE_CHECKING:
    from make_features.catalog.registry import FeatureRegistry
from make_features.contracts.types import (
    FeatureAudit,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureBuildResult,
    FeatureDefinition,
    FeatureGroupInput,
    FeatureScalar,
    FeatureViolation,
)


def audit_feature_inputs(
    records: Sequence[FeatureBatchInput], *, registry: FeatureRegistry
) -> FeatureAudit:
    """Combine shared auditing with each registered feature's own validation."""
    audit = _audit_feature_inputs(records, required_feature_ids=registry.feature_ids)
    for registration in registry.features:
        builder = registration.builder_type(registration.definition)
        audit = builder.audit_batches(records, audit)
    return audit


def build_explanatory_variables(
    records: Sequence[FeatureBatchInput],
    *,
    registry: FeatureRegistry,
) -> FeatureBuildResult:
    """Generate individual common middle rows without choosing business formulas."""
    if not records:
        raise ValueError("feature generation requires at least one record")
    audit = audit_feature_inputs(records, registry=registry)
    if not audit.valid:
        raise FeatureBuildError(audit)
    inputs = tuple(normalize_batch(record, registry.feature_ids) for record in records)
    rows = {}
    for registration in registry.features:
        feature_id = registration.definition.feature_id
        builder = registration.builder_type(registration.definition)
        input_type = registration.input_type
        feature_inputs = [
            input_type(
                feature_id=feature_id,
                race_id=record.race_id,
                horse_id=record.horse_id,
                freeze_at=record.freeze_at,
                values=record.groups[feature_id].values,
                available_at=record.groups[feature_id].available_at,
                source_event_at=record.groups[feature_id].source_event_at,
                source_scope=record.groups[feature_id].source_scope,
                status=record.groups[feature_id].status,
                source_race_ids=record.groups[feature_id].source_race_ids,
                contains_target_result=False,
                contains_future_data=False,
            )
            for record in inputs
        ]
        rows[feature_id] = tuple(builder._build_audited_rows(feature_inputs))
    return FeatureBuildResult(inputs=inputs, rows=MappingProxyType(rows), audit=audit)


__all__ = [
    "FeatureAudit",
    "FeatureBatchInput",
    "FeatureBuildError",
    "FeatureBuildResult",
    "FeatureDefinition",
    "FeatureGroupInput",
    "FeatureScalar",
    "FeatureViolation",
    "audit_feature_inputs",
    "build_explanatory_variables",
]
