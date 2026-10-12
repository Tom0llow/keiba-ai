"""Build explanatory-variable middle rows through their individual modules."""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType

from features.common.audit import audit_feature_inputs as _audit_feature_inputs
from features.common.normalization import normalize_batch
from features.common.registry import (
    FEATURE_BUILDERS,
    FEATURE_GROUP_IDS,
    FEATURE_GROUP_SPECS,
    FEATURE_INPUT_TYPES,
)
from features.common.types import (
    FeatureAudit,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureBuildResult,
    FeatureGroupInput,
    FeatureGroupSpec,
    FeatureScalar,
    FeatureViolation,
)
from features.market_characteristics import validate_market_batches


def audit_feature_inputs(records: Sequence[FeatureBatchInput]) -> FeatureAudit:
    """Combine shared auditing with feature-owned market validation."""
    audit = _audit_feature_inputs(records)
    return validate_market_batches(records, audit)


def build_explanatory_variables(
    records: Sequence[FeatureBatchInput],
) -> FeatureBuildResult:
    """Generate individual common middle rows without choosing business formulas."""
    if not records:
        raise ValueError("feature generation requires at least one record")
    audit = audit_feature_inputs(records)
    if not audit.valid:
        raise FeatureBuildError(audit)
    inputs = tuple(normalize_batch(record) for record in records)
    rows = {}
    for feature_id, builder in FEATURE_BUILDERS.items():
        input_type = FEATURE_INPUT_TYPES[feature_id]
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
        rows[feature_id] = tuple(builder.build_rows(feature_inputs))
    return FeatureBuildResult(inputs=inputs, rows=MappingProxyType(rows), audit=audit)


__all__ = [
    "FEATURE_GROUP_IDS",
    "FEATURE_GROUP_SPECS",
    "FeatureAudit",
    "FeatureBatchInput",
    "FeatureBuildError",
    "FeatureBuildResult",
    "FeatureGroupInput",
    "FeatureGroupSpec",
    "FeatureScalar",
    "FeatureViolation",
    "audit_feature_inputs",
    "build_explanatory_variables",
]
