"""Convert model features, audits, and evaluations to JSON-ready values."""

from __future__ import annotations

from datetime import datetime

from models.dataset_builder import AvailabilityAudit, FeatureGenerationResult, TimestampInput
from models.evaluate_model import RankingMetrics
from models.walk_forward import WalkForwardEvaluation


def freeze_at_payload(value: TimestampInput) -> str:
    """Return the input freeze timestamp as an ISO-8601 string."""
    return value.isoformat() if isinstance(value, datetime) else value


def audit_payload(audit: AvailabilityAudit) -> dict[str, object]:
    """Return a JSON-ready feature availability audit with violation timestamps."""
    return {
        "records_checked": audit.records_checked,
        "non_missing_values": audit.non_missing_values,
        "missing_values": audit.missing_values,
        "valid": audit.valid,
        "violations": [
            {
                "row_index": violation.row_index,
                "race_id": violation.race_id,
                "horse_id": violation.horse_id,
                "feature_name": violation.feature_name,
                "reason": violation.reason,
                "freeze_at": (
                    violation.freeze_at.isoformat() if violation.freeze_at is not None else None
                ),
                "available_at": (
                    violation.available_at.isoformat()
                    if violation.available_at is not None
                    else None
                ),
            }
            for violation in audit.violations
        ],
    }


def generated_records(result: FeatureGenerationResult) -> list[dict[str, object]]:
    """Return generated model features with optional ranking labels."""
    ranking_by_key = {
        (row.race_id, row.horse_id): row.finish_position for row in result.ranking_rows
    }
    return [
        {
            "race_id": row.race_id,
            "horse_id": row.horse_id,
            "freeze_at": row.freeze_at.isoformat() if row.freeze_at is not None else None,
            "available_at": {
                feature_name: (available_at.isoformat() if available_at is not None else None)
                for feature_name, available_at in row.available_at.items()
            },
            "features": dict(row.features),
            **(
                {"finish_position": ranking_by_key[(row.race_id, row.horse_id)]}
                if (row.race_id, row.horse_id) in ranking_by_key
                else {}
            ),
        }
        for row in result.feature_rows
    ]


def walk_forward_payload(evaluation: WalkForwardEvaluation) -> dict[str, object]:
    """Return evaluation metrics and race-disjoint fold boundaries."""
    return {
        "metrics": metrics_payload(evaluation.metrics),
        "folds": [
            {
                "fold_index": result.fold.fold_index,
                "train_race_ids": list(result.fold.train_race_ids),
                "validation_race_ids": list(result.fold.validation_race_ids),
                "test_race_ids": list(result.fold.test_race_ids),
                "train_freeze_at": [
                    freeze_at.isoformat() for freeze_at in result.fold.train_freeze_at
                ],
                "validation_freeze_at": [
                    freeze_at.isoformat() for freeze_at in result.fold.validation_freeze_at
                ],
                "test_freeze_at": [
                    freeze_at.isoformat() for freeze_at in result.fold.test_freeze_at
                ],
                "metrics": metrics_payload(result.metrics),
            }
            for result in evaluation.fold_results
        ],
    }


def metrics_payload(metrics: RankingMetrics) -> dict[str, float]:
    """Return ranking metrics with their existing JSON field names."""
    value = metrics
    return {
        "ndcg_at_3": value.ndcg_at_3,
        "top1_accuracy": value.top1_accuracy,
        "top3_overlap": value.top3_overlap,
    }
