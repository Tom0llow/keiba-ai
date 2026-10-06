"""Build validated ranking features and audit their temporal availability."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite, isnan

from models.ranking_dataset import (
    FeatureRow,
    FeatureSchema,
    FeatureValue,
    RankingDataset,
    RankingRow,
    validate_feature_rows,
)

type TimestampInput = datetime | str


@dataclass(frozen=True)
class FeatureInput:
    """Describe one horse's raw feature values at an explicit freeze time."""

    race_id: str
    horse_id: str
    freeze_at: TimestampInput
    features: Mapping[str, FeatureValue]
    available_at: Mapping[str, TimestampInput | None]
    finish_position: int | None = None


FeatureRecord = FeatureInput


@dataclass(frozen=True)
class AvailabilityViolation:
    """Describe one temporal or input-contract violation."""

    row_index: int
    race_id: str
    horse_id: str
    feature_name: str | None
    reason: str
    freeze_at: datetime | None = None
    available_at: datetime | None = None

    @property
    def message(self) -> str:
        """Return a concise human-readable description of the violation."""
        location = f"row {self.row_index} ({self.race_id}/{self.horse_id})"
        if self.feature_name is not None:
            location += f" feature {self.feature_name!r}"
        return f"{location}: {self.reason}"


@dataclass(frozen=True)
class AvailabilityAudit:
    """Summarize temporal availability checks without dropping input rows."""

    records_checked: int
    non_missing_values: int
    missing_values: int
    violations: tuple[AvailabilityViolation, ...]

    @property
    def valid(self) -> bool:
        """Return whether all checked records passed the audit."""
        return not self.violations

    @property
    def is_valid(self) -> bool:
        """Return whether all checked records passed the audit."""
        return self.valid


class FeatureGenerationError(ValueError):
    """Indicate that feature inputs failed the availability audit."""

    def __init__(self, audit: AvailabilityAudit) -> None:
        self.audit = audit
        details = "; ".join(violation.message for violation in audit.violations)
        super().__init__(f"feature generation availability audit failed: {details}")


@dataclass(frozen=True)
class FeatureGenerationResult:
    """Hold generated rows, the audit, and an optional labeled dataset."""

    feature_rows: tuple[FeatureRow, ...]
    ranking_rows: tuple[RankingRow, ...]
    dataset: RankingDataset | None
    audit: AvailabilityAudit

    @property
    def rows(self) -> tuple[FeatureRow, ...]:
        """Return generated feature rows in their original race-contiguous order."""
        return self.feature_rows


def audit_feature_availability(
    records: Sequence[FeatureInput],
    *,
    feature_schema: FeatureSchema | None = None,
) -> AvailabilityAudit:
    """Audit typed feature inputs against their freeze times.

    Missing values are counted and retained.  They do not use an available-at
    timestamp and are never replaced by a value from another period.
    """
    allowed_names = None if feature_schema is None else set(feature_schema.feature_names)
    violations: list[AvailabilityViolation] = []
    non_missing_values = 0
    missing_values = 0

    for row_index, record in enumerate(records):
        if not isinstance(record, FeatureInput):
            raise TypeError("records must contain FeatureInput values")
        race_id = record.race_id if isinstance(record.race_id, str) else "<invalid>"
        horse_id = record.horse_id if isinstance(record.horse_id, str) else "<invalid>"
        if not isinstance(record.race_id, str) or not record.race_id:
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "race_id must be non-empty"
                )
            )
        if not isinstance(record.horse_id, str) or not record.horse_id:
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "horse_id must be non-empty"
                )
            )

        freeze_at, freeze_error = _parse_timestamp(record.freeze_at)
        if freeze_error is not None:
            violations.append(
                AvailabilityViolation(row_index, race_id, horse_id, None, freeze_error)
            )

        if not isinstance(record.features, Mapping):
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "features must be a mapping"
                )
            )
            continue
        if not isinstance(record.available_at, Mapping):
            violations.append(
                AvailabilityViolation(
                    row_index, race_id, horse_id, None, "available_at must be a mapping"
                )
            )
            available_values: Mapping[str, TimestampInput | None] = {}
        else:
            available_values = record.available_at

        parsed_available: dict[str, datetime | None] = {}
        for feature_name, raw_available_at in available_values.items():
            if not isinstance(feature_name, str) or not feature_name:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        "available_at feature names must be non-empty strings",
                    )
                )
                continue
            if feature_name not in record.features:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "available_at is provided without a feature value",
                    )
                )
            if raw_available_at is None:
                parsed_available[feature_name] = None
                continue
            parsed, error = _parse_timestamp(raw_available_at)
            if error is not None:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        f"available_at {error}",
                    )
                )
            parsed_available[feature_name] = parsed

        for feature_name, value in record.features.items():
            if not isinstance(feature_name, str) or not feature_name:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        "feature names must be non-empty strings",
                    )
                )
                continue
            if allowed_names is not None and feature_name not in allowed_names:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "feature is outside the approved schema",
                    )
                )
            if not _is_feature_value(value):
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "feature value must be numeric, NaN, or None",
                    )
                )
                continue
            if _is_missing(value):
                missing_values += 1
                continue
            non_missing_values += 1
            available_at = parsed_available.get(feature_name)
            if available_at is None:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "non-missing feature value requires available_at",
                        freeze_at=freeze_at,
                    )
                )
            elif freeze_at is not None and available_at > freeze_at:
                violations.append(
                    AvailabilityViolation(
                        row_index,
                        race_id,
                        horse_id,
                        feature_name,
                        "available_at is after freeze_at",
                        freeze_at=freeze_at,
                        available_at=available_at,
                    )
                )

        if feature_schema is not None:
            missing_values += sum(
                feature_name not in record.features for feature_name in feature_schema.feature_names
            )

    return AvailabilityAudit(
        records_checked=len(records),
        non_missing_values=non_missing_values,
        missing_values=missing_values,
        violations=tuple(violations),
    )


def generate_features(
    records: Sequence[FeatureInput],
    *,
    feature_schema: FeatureSchema,
) -> FeatureGenerationResult:
    """Generate validated feature rows and, when labeled, a ranking dataset.

    The input order is preserved, so rows for each race remain contiguous.  A
    labeled call must label every row; a partially labeled call is rejected.
    """
    if not records:
        raise ValueError("feature generation requires at least one record")
    audit = audit_feature_availability(records, feature_schema=feature_schema)
    if not audit.valid:
        raise FeatureGenerationError(audit)

    generated_feature_rows: list[FeatureRow] = []
    generated_ranking_rows: list[RankingRow] = []
    labeled = [record.finish_position is not None for record in records]
    if any(labeled) and not all(labeled):
        mixed_audit = replace(
            audit,
            violations=audit.violations
            + tuple(
                AvailabilityViolation(
                    row_index=index,
                    race_id=record.race_id,
                    horse_id=record.horse_id,
                    feature_name=None,
                    reason="finish_position must be provided for every row or no row",
                )
                for index, record in enumerate(records)
                if record.finish_position is None
            ),
        )
        raise FeatureGenerationError(mixed_audit)

    for record in records:
        freeze_at, error = _parse_timestamp(record.freeze_at)
        if error is not None or freeze_at is None:
            raise AssertionError("validated availability audit must contain freeze_at")
        features = {name: record.features.get(name) for name in feature_schema.feature_names}
        if all(labeled):
            if record.finish_position is None:
                raise AssertionError("validated finish positions must be present")
            generated_ranking_rows.append(
                RankingRow(
                    race_id=record.race_id,
                    horse_id=record.horse_id,
                    features=features,
                    finish_position=record.finish_position,
                    freeze_at=freeze_at,
                )
            )
        else:
            generated_feature_rows.append(
                FeatureRow(
                    race_id=record.race_id,
                    horse_id=record.horse_id,
                    features=features,
                    freeze_at=freeze_at,
                )
            )

    if all(labeled):
        dataset = RankingDataset.from_rows(
            generated_ranking_rows,
            feature_names=feature_schema.feature_names,
            feature_schema=feature_schema,
        )
        generated_ranking_rows = list(dataset.rows)
        generated_feature_rows = [
            FeatureRow(
                race_id=row.race_id,
                horse_id=row.horse_id,
                features=row.features,
                freeze_at=row.freeze_at,
            )
            for row in generated_ranking_rows
        ]
    else:
        generated_feature_rows = list(
            validate_feature_rows(generated_feature_rows, feature_schema.feature_names)
        )
        dataset = None

    return FeatureGenerationResult(
        feature_rows=tuple(generated_feature_rows),
        ranking_rows=tuple(generated_ranking_rows),
        dataset=dataset,
        audit=audit,
    )


def build_features(
    records: Sequence[FeatureInput],
    *,
    feature_schema: FeatureSchema,
) -> FeatureGenerationResult:
    """Build validated features from explicit records."""
    return generate_features(records, feature_schema=feature_schema)


def build_feature_rows(
    records: Sequence[FeatureInput],
    *,
    feature_schema: FeatureSchema,
) -> tuple[FeatureRow, ...]:
    """Return validated unlabeled feature rows from explicit inputs."""
    return generate_features(records, feature_schema=feature_schema).feature_rows


def build_ranking_dataset(
    records: Sequence[FeatureInput],
    *,
    feature_schema: FeatureSchema,
) -> RankingDataset:
    """Return a validated labeled ranking dataset from explicit inputs."""
    result = generate_features(records, feature_schema=feature_schema)
    if result.dataset is None:
        raise ValueError("ranking dataset generation requires finish_position on every row")
    return result.dataset


def _parse_timestamp(value: TimestampInput) -> tuple[datetime | None, str | None]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            return None, f"must be a valid ISO-8601 timestamp ({exc})"
    else:
        return None, "must be a datetime or ISO-8601 timestamp string"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "must be timezone-aware"
    return parsed, None


def _is_feature_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not (isinstance(value, float) and not isnan(value) and not isfinite(value))


def _is_missing(value: FeatureValue) -> bool:
    return value is None or (isinstance(value, float) and isnan(value))


__all__ = [
    "AvailabilityAudit",
    "AvailabilityViolation",
    "FeatureGenerationError",
    "FeatureGenerationResult",
    "FeatureInput",
    "FeatureRecord",
    "TimestampInput",
    "audit_feature_availability",
    "build_feature_rows",
    "build_features",
    "build_ranking_dataset",
    "generate_features",
]
