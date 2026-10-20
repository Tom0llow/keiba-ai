"""Construct validated prediction rows and labeled ranking datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from models.dataset.availability import (
    AvailabilityAudit,
    AvailabilityViolation,
    FeatureGenerationError,
    _normalized_available_at,
    _parse_timestamp,
    audit_feature_availability,
)
from models.dataset.dataset import RankingDataset
from models.dataset.rows import FeatureInput, FeatureRow, RankingRow
from models.dataset.schema import FeatureSchema
from models.dataset.validation import validate_feature_rows


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
    available_at_by_key: dict[tuple[str, str], Mapping[str, datetime | None]] = {}
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
        available_at = _normalized_available_at(record, feature_schema.feature_names)
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
            available_at_by_key[(record.race_id, record.horse_id)] = available_at
        else:
            generated_feature_rows.append(
                FeatureRow(
                    race_id=record.race_id,
                    horse_id=record.horse_id,
                    features=features,
                    freeze_at=freeze_at,
                    available_at=available_at,
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
                available_at=available_at_by_key[(row.race_id, row.horse_id)],
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
