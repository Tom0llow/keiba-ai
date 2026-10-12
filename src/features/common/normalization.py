"""Normalize audited explicit feature inputs into the common middle-row type."""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType
from typing import cast

from features.common.audit import audit_feature_inputs
from features.common.availability import parse_timestamp, require_timestamp
from features.common.feature_table import FeatureTableRow
from features.common.types import (
    FEATURE_GROUP_IDS,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureGroupInput,
    FeatureSourceScope,
    FeatureStatus,
    FeatureValuesInput,
)
from features.common.validation import _is_missing


def input_batches(
    records: Sequence[FeatureValuesInput], feature_id: str
) -> tuple[FeatureBatchInput, ...]:
    """Represent individual inputs as batches for reusable source auditing."""
    return tuple(
        FeatureBatchInput(row.race_id, row.horse_id, row.freeze_at, {feature_id: row})
        for row in records
    )


def normalize_feature_inputs(
    records: Sequence[FeatureValuesInput],
    feature_id: str,
    input_type: type[FeatureValuesInput],
) -> list[FeatureTableRow]:
    """Validate explicit inputs and preserve unavailable values as null."""
    if any(not isinstance(record, input_type) for record in records):
        raise TypeError(f"records must contain {input_type.__name__} values")
    audit = audit_feature_inputs(
        input_batches(records, feature_id), required_feature_ids=(feature_id,)
    )
    if not audit.valid:
        raise FeatureBuildError(audit)
    rows = []
    for record in records:
        available_at, _ = parse_timestamp(record.available_at)
        rows.append(
            FeatureTableRow(
                record.race_id,
                record.horse_id,
                require_timestamp(record.freeze_at, "freeze_at"),
                available_at,
                {
                    name: None if _is_missing(value) else value
                    for name, value in record.values.items()
                },
            )
        )
    return rows


def normalize_batch(record: FeatureBatchInput) -> FeatureBatchInput:
    """Copy validated source inputs with UTC timestamps and immutable value mappings."""
    freeze_at, error = parse_timestamp(record.freeze_at)
    if error is not None or freeze_at is None:
        raise AssertionError("validated feature audit must contain freeze_at")
    groups: dict[str, FeatureGroupInput] = {}
    for feature_id in FEATURE_GROUP_IDS:
        group = record.groups[feature_id]
        available_at, available_error = parse_timestamp(group.available_at)
        if available_error is not None:
            raise AssertionError("validated feature audit must contain valid available_at")
        source_event_at, source_event_error = parse_timestamp(group.source_event_at)
        if source_event_error is not None:
            raise AssertionError("validated feature audit must contain valid source_event_at")
        groups[feature_id] = FeatureGroupInput(
            feature_id=feature_id,
            values=MappingProxyType(dict(group.values)),
            available_at=available_at,
            source_event_at=source_event_at,
            source_scope=cast(FeatureSourceScope, group.source_scope),
            status=cast(FeatureStatus, group.status),
            source_race_ids=tuple(group.source_race_ids),
            contains_target_result=False,
            contains_future_data=False,
        )
    return FeatureBatchInput(
        race_id=record.race_id,
        horse_id=record.horse_id,
        freeze_at=freeze_at,
        groups=MappingProxyType(groups),
    )
