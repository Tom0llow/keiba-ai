"""Run chronological ranking evaluation at the CLI boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from models.dataset_builder import (
    FeatureGenerationError,
    audit_feature_availability,
    build_ranking_dataset,
)
from models.evaluate_model import RankingMetrics
from models.walk_forward import WalkForwardConfig, WalkForwardEvaluation, evaluate_walk_forward
from run.feature_inputs import read_feature_inputs_or_exit
from run.json_output import audit_payload, input_error_payload, write_json


def model_walk_forward(
    input_path: Annotated[Path, typer.Option("--input", help="Labeled feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Evaluation output JSON path.")],
    min_train_races: Annotated[
        int, typer.Option("--min-train-races", help="Initial training race count.")
    ],
    validation_races: Annotated[
        int, typer.Option("--validation-races", help="Validation race count per fold.")
    ],
    test_races: Annotated[int, typer.Option("--test-races", help="Test race count per fold.")],
    step_races: Annotated[
        int, typer.Option("--step-races", help="Race count by which the fold advances.")
    ],
) -> None:
    """Run race-disjoint chronological LambdaRank walk-forward evaluation."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    try:
        dataset = build_ranking_dataset(records, feature_schema=schema)
        evaluation = evaluate_walk_forward(
            dataset,
            WalkForwardConfig(
                min_train_races=min_train_races,
                validation_races=validation_races,
                test_races=test_races,
                step_races=step_races,
            ),
        )
    except FeatureGenerationError as exc:
        write_json(
            output_path,
            {
                "schema_id": schema.schema_id,
                "audit": audit_payload(exc.audit),
                "error": input_error_payload(exc),
            },
        )
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        write_json(
            output_path,
            {"schema_id": schema.schema_id, "error": input_error_payload(exc)},
        )
        raise typer.Exit(code=1) from exc
    write_json(
        output_path,
        {
            "schema_id": schema.schema_id,
            "feature_names": list(schema.feature_names),
            "audit": audit_payload(audit_feature_availability(records, feature_schema=schema)),
            "evaluation": _walk_forward_payload(evaluation),
        },
    )


def _walk_forward_payload(evaluation: WalkForwardEvaluation) -> dict[str, object]:
    return {
        "metrics": _metrics_payload(evaluation.metrics),
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
                "metrics": _metrics_payload(result.metrics),
            }
            for result in evaluation.fold_results
        ],
    }


def _metrics_payload(metrics: RankingMetrics) -> dict[str, float]:
    value = metrics
    return {
        "ndcg_at_3": value.ndcg_at_3,
        "top1_accuracy": value.top1_accuracy,
        "top3_overlap": value.top3_overlap,
    }
