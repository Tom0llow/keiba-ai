"""Explicit feature inputs and structured validation results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from make_features.contracts.rows import FeatureTableRow

type FeatureTimestamp = datetime | str
type FeatureScalar = str | int | float | bool | None
type FeatureStatus = Literal["confirmed", "missing", "unconfirmed"]
type FeatureSourceScope = Literal["pre_race", "historical"]


@dataclass(frozen=True, slots=True)
class FeatureGroupInput:
    """Provide one feature group from an explicit normalized boundary.

    ``values`` must contain scalar values only.  ``source_scope`` distinguishes
    values computed from the target race's pre-race state from values derived
    from historical records.  A historical source may not reference the target
    race, and its source event must not be after ``freeze_at``.
    ``status='missing'`` preserves unavailable values as ``None`` or ``NaN``;
    ``status='unconfirmed'`` is rejected rather than treated as valid.
    """

    feature_id: str
    values: Mapping[str, FeatureScalar]
    available_at: FeatureTimestamp | None
    source_event_at: FeatureTimestamp | None
    source_scope: str
    status: str
    source_race_ids: Sequence[str] = ()
    contains_target_result: bool = field(kw_only=True)
    contains_future_data: bool = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class FeatureBatchInput:
    """Represent one horse's F01-F21 feature values at a freeze time."""

    race_id: str
    horse_id: str
    freeze_at: FeatureTimestamp
    groups: Mapping[str, FeatureGroupInput]


@dataclass(frozen=True, slots=True)
class FeatureViolation:
    """Describe one feature-input contract violation."""

    row_index: int
    race_id: str
    horse_id: str
    feature_id: str | None
    field_name: str | None
    reason: str
    freeze_at: datetime | None = None
    available_at: datetime | None = None
    source_event_at: datetime | None = None

    @property
    def message(self) -> str:
        """Return a concise location and reason for the violation."""
        location = f"row {self.row_index} ({self.race_id}/{self.horse_id})"
        if self.feature_id is not None:
            location += f" group {self.feature_id!r}"
        if self.field_name is not None:
            location += f" field {self.field_name!r}"
        return f"{location}: {self.reason}"


@dataclass(frozen=True, slots=True)
class FeatureAudit:
    """Summarize feature validation without dropping input rows."""

    records_checked: int
    groups_checked: int
    non_missing_values: int
    missing_values: int
    violations: tuple[FeatureViolation, ...]

    @property
    def valid(self) -> bool:
        """Return whether all feature inputs passed validation."""
        return not self.violations


class FeatureBuildError(ValueError):
    """Indicate that feature inputs failed their explicit boundary checks."""

    def __init__(self, audit: FeatureAudit) -> None:
        self.audit = audit
        details = "; ".join(violation.message for violation in audit.violations)
        super().__init__(f"feature generation audit failed: {details}")


@dataclass(frozen=True, slots=True)
class FeatureBuildResult:
    """Hold audited source inputs and common middle rows by feature ID."""

    inputs: tuple[FeatureBatchInput, ...]
    rows: Mapping[str, tuple[FeatureTableRow, ...]]
    audit: FeatureAudit


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """Identify an explanatory-variable group independently of model adoption."""

    feature_id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureValuesInput(FeatureGroupInput):
    """Provide an individual feature input with explicit source evidence."""

    race_id: str
    horse_id: str
    freeze_at: FeatureTimestamp


def _violation(
    row_index: int,
    race_id: str,
    horse_id: str,
    feature_id: str | None,
    field_name: str | None,
    reason: str,
    *,
    freeze_at: datetime | None = None,
    available_at: datetime | None = None,
    source_event_at: datetime | None = None,
) -> FeatureViolation:
    return FeatureViolation(
        row_index=row_index,
        race_id=race_id,
        horse_id=horse_id,
        feature_id=feature_id,
        field_name=field_name,
        reason=reason,
        freeze_at=freeze_at,
        available_at=available_at,
        source_event_at=source_event_at,
    )
