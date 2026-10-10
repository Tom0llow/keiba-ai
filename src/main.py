"""Command-line entry point for keiba-ai data workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from math import isnan
from pathlib import Path
from typing import Annotated, cast

import typer

from data.data_preprocesser import DataPreprocesser
from data.data_retriever import DataRetriever
from data.race_key import RaceKey
from data.retriever.setting import JVLinkConfig
from features.builder import (
    AvailabilityAudit,
    FeatureGenerationError,
    FeatureGenerationResult,
    FeatureInput,
    TimestampInput,
    audit_feature_availability,
    build_features,
    build_ranking_dataset,
)
from models.evaluate_model import RankingMetrics
from models.ranking_dataset import FeatureSchema, FeatureValue
from models.walk_forward import WalkForwardConfig, WalkForwardEvaluation, evaluate_walk_forward

app = typer.Typer(no_args_is_help=True)
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
model_app = typer.Typer(no_args_is_help=True, help="Build features and evaluate ranking models.")
app.add_typer(preprocess_app, name="preprocess")
app.add_typer(model_app, name="model")

DataConfigOption = Annotated[
    Path,
    typer.Option("--data-config", help="Path to the shared data TOML configuration."),
]
JVLinkConfigOption = Annotated[
    Path,
    typer.Option("--jvlink-config", help="Path to the JVLink retrieval profile TOML."),
]


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    retrieve: Annotated[
        bool,
        typer.Option("--retrieve", help="Run a retrieval workflow selected by --mode."),
    ] = False,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="Retrieval mode for the flag-based interface."),
    ] = None,
    plan_only: Annotated[
        bool,
        typer.Option("--plan-only", help="Inspect a historical-odds plan without writing."),
    ] = False,
    recover: Annotated[
        bool,
        typer.Option(
            "--recover", help="Quarantine and recover an interrupted historical-odds request."
        ),
    ] = False,
    confirm_provider_missing: Annotated[
        bool,
        typer.Option(
            "--confirm-provider-missing",
            help="Confirm a failed empty response as a JRA-VAN-side gap.",
        ),
    ] = False,
    data_spec: Annotated[
        list[str] | None,
        typer.Option("--data-spec", help="DataSpec to confirm; repeat for multiple specs."),
    ] = None,
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
    race_datetime: Annotated[
        datetime | None,
        typer.Option("--date", formats=["%Y-%m-%d"], help="Race date (YYYY-MM-DD)."),
    ] = None,
    jyo_code: Annotated[str | None, typer.Option("--jyo", help="Two-digit JRA venue code.")] = None,
    kaiji: Annotated[str | None, typer.Option("--kaiji", help="Two-digit meeting number.")] = None,
    nichiji: Annotated[str | None, typer.Option("--nichiji", help="Two-digit meeting day.")] = None,
    race_number: Annotated[
        str | None, typer.Option("--race", help="Two-digit race number.")
    ] = None,
) -> None:
    """Run a retrieval workflow selected by the mode option."""
    if ctx.invoked_subcommand is not None:
        if (
            retrieve
            or mode is not None
            or plan_only
            or recover
            or confirm_provider_missing
            or data_spec
            or any(
                value is not None
                for value in (race_datetime, jyo_code, kaiji, nichiji, race_number)
            )
        ):
            raise typer.BadParameter("retrieval options cannot be used with a subcommand")
        return

    if not retrieve and mode is None:
        if (
            plan_only
            or recover
            or confirm_provider_missing
            or data_spec
            or any(
                value is not None
                for value in (race_datetime, jyo_code, kaiji, nichiji, race_number)
            )
        ):
            raise typer.BadParameter("retrieval options require --retrieve --mode")
        return
    if plan_only and recover:
        raise typer.BadParameter("--plan-only cannot be combined with --recover")
    if confirm_provider_missing and (plan_only or recover):
        raise typer.BadParameter(
            "--confirm-provider-missing cannot be combined with --plan-only/--recover"
        )
    if not retrieve:
        raise typer.BadParameter("--mode requires --retrieve")
    if mode == "historical-basic":
        if (
            plan_only
            or recover
            or confirm_provider_missing
            or data_spec
            or any(
                value is not None
                for value in (race_datetime, jyo_code, kaiji, nichiji, race_number)
            )
        ):
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        retrieve_historical_basic(data_config, jvlink_config)
        return
    if mode == "historical-odds":
        if confirm_provider_missing:
            race_key = _require_provider_missing_race(
                race_datetime, jyo_code, kaiji, nichiji, race_number
            )
            specs = _provider_missing_specs(data_spec)
            confirm_historical_odds_provider_missing(race_key, specs, data_config, jvlink_config)
            return
        if (
            any(
                value is not None
                for value in (race_datetime, jyo_code, kaiji, nichiji, race_number)
            )
            or data_spec
        ):
            raise typer.BadParameter(
                "race options and --data-spec require --confirm-provider-missing"
            )
        retrieve_historical_odds(data_config, jvlink_config, plan_only=plan_only, recover=recover)
        return
    if mode == "latest":
        if (
            plan_only
            or recover
            or confirm_provider_missing
            or data_spec
            or any(
                value is not None
                for value in (race_datetime, jyo_code, kaiji, nichiji, race_number)
            )
        ):
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        retrieve_latest(data_config, jvlink_config)
        return
    if mode == "realtime":
        if plan_only or recover or confirm_provider_missing or data_spec:
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        race_key = _resolve_realtime_race(
            jvlink_config,
            race_datetime,
            jyo_code,
            kaiji,
            nichiji,
            race_number,
        )
        retrieve_realtime(race_key, data_config, jvlink_config)
        return
    raise typer.BadParameter(
        "--mode must be 'historical-basic', 'historical-odds', 'latest', or 'realtime'"
    )


def _retriever(data_config: Path, jvlink_config: Path, *, plan_only: bool = False) -> DataRetriever:
    if not plan_only:
        return DataRetriever.from_toml(data_config=data_config, jvlink_config=jvlink_config)
    return DataRetriever.from_toml(
        data_config=data_config,
        jvlink_config=jvlink_config,
        create_runtime=not plan_only,
        validate_executable=False,
    )


def _preprocesser(data_config: Path) -> DataPreprocesser:
    return DataPreprocesser.from_toml(data_config)


def _resolve_realtime_race(
    jvlink_config: Path,
    race_datetime: datetime | None,
    jyo_code: str | None,
    kaiji: str | None,
    nichiji: str | None,
    race_number: str | None,
) -> RaceKey:
    values = (race_datetime, jyo_code, kaiji, nichiji, race_number)
    if any(value is not None for value in values):
        if any(value is None for value in values):
            raise typer.BadParameter(
                "realtime CLI options must include --date, --jyo, --kaiji, --nichiji, and --race"
            )
        assert race_datetime is not None
        assert jyo_code is not None
        assert kaiji is not None
        assert nichiji is not None
        assert race_number is not None
        return RaceKey(race_datetime.date(), jyo_code, kaiji, nichiji, race_number)

    configured_race = JVLinkConfig.from_toml(jvlink_config).realtime_race
    if configured_race is None:
        raise typer.BadParameter(
            "realtime requires CLI race options or a [realtime] section in the JVLink config"
        )
    return configured_race


def _require_provider_missing_race(
    race_datetime: datetime | None,
    jyo_code: str | None,
    kaiji: str | None,
    nichiji: str | None,
    race_number: str | None,
) -> RaceKey:
    """Require an explicit complete RaceKey for a provider-gap confirmation."""
    values = (race_datetime, jyo_code, kaiji, nichiji, race_number)
    if any(value is None for value in values):
        raise typer.BadParameter(
            "--confirm-provider-missing requires --date, --jyo, --kaiji, --nichiji, and --race"
        )
    assert race_datetime is not None
    assert jyo_code is not None
    assert kaiji is not None
    assert nichiji is not None
    assert race_number is not None
    try:
        return RaceKey(race_datetime.date(), jyo_code, kaiji, nichiji, race_number)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid provider-missing RaceKey: {exc}") from exc


def _provider_missing_specs(data_specs: list[str] | None) -> frozenset[str]:
    """Validate the explicitly confirmed realtime odds DataSpecs."""
    values = data_specs or ["0B41", "0B42"]
    if len(values) != len(set(values)) or not set(values) <= {"0B41", "0B42"}:
        raise typer.BadParameter("--data-spec accepts only unique 0B41 and 0B42 values")
    return frozenset(values)


def retrieve_historical_basic(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Retrieve historical base data and publish a complete Parquet snapshot."""
    tables: dict[str, int] = {}

    def publish() -> None:
        tables.update(_preprocesser(data_config).rebuild())

    _retriever(data_config, jvlink_config).retrieve_historical_basic(publish)
    typer.echo("historical basic data retrieved")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


def retrieve_historical_odds(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
    *,
    plan_only: bool = False,
    recover: bool = False,
) -> None:
    """Acquire historical odds years and publish one snapshot after raw completion."""
    retriever = _retriever(data_config, jvlink_config, plan_only=plan_only)
    recover_pending = recover
    while True:
        if recover_pending:
            result = retriever.retrieve_historical_odds(
                plan_only=plan_only, recover=True, raw_only=True
            )
        else:
            result = retriever.retrieve_historical_odds(plan_only=plan_only, raw_only=True)
        recover_pending = False
        if not plan_only and result.status == "completed" and result.year is not None:
            typer.echo(
                f"Historical odds raw acquisition completed for year {result.year}; "
                "Parquet publication is deferred until all years are acquired."
            )
            typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
            continue
        if not plan_only and result.status == "up_to_date":
            typer.echo("Starting complete Parquet rebuild after all historical odds are acquired.")
            try:
                tables = retriever.publish_historical_odds(
                    lambda: _preprocesser(data_config).rebuild()
                )
            except BaseException:
                typer.echo("Complete Parquet rebuild failed.", err=True)
                raise
            if tables is not None:
                typer.echo(f"Complete Parquet rebuild completed: {len(tables)} tables published.")
            typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
            return
        typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
        if result.status == "failed":
            raise typer.Exit(code=1)
        return


def confirm_historical_odds_provider_missing(
    race_key: RaceKey,
    specs: frozenset[str],
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Confirm selected empty-response failures without starting JV-Link."""
    count = _retriever(data_config, jvlink_config).confirm_historical_odds_provider_missing(
        race_key, specs
    )
    typer.echo(
        json.dumps(
            {
                "race": str(race_key),
                "data_specs": sorted(specs),
                "confirmed": count,
                "status": "provider_missing",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def retrieve_latest(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Retrieve latest raw data and refresh the complete Parquet snapshot."""
    _retriever(data_config, jvlink_config).retrieve_latest()
    tables = _preprocesser(data_config).update()
    typer.echo("latest race data retrieved")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


def retrieve_realtime(
    race_key: RaceKey,
    data_config: Path,
    jvlink_config: Path,
) -> None:
    """Retrieve and publish prediction-time Parquet for one target race."""
    inserted = _retriever(data_config, jvlink_config).retrieve_realtime(
        race_date=race_key.race_date,
        jyo_code=race_key.jyo_code,
        kaiji=race_key.kaiji,
        nichiji=race_key.nichiji,
        race_number=race_key.race_number,
    )
    tables = _preprocesser(data_config).update_race(race_key)
    typer.echo(f"realtime odds archived: {inserted} rows")
    typer.echo(f"realtime Parquet published: {sum(tables.values())} rows")


@preprocess_app.command("rebuild")
def preprocess_rebuild(
    data_config: DataConfigOption = Path("config/data.toml"),
) -> None:
    """Rebuild a complete Parquet snapshot without retrieving new raw data."""
    tables = _preprocesser(data_config).rebuild()
    typer.echo(f"processed snapshot published: {len(tables)} tables")


@model_app.command("audit")
def model_audit(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Audit output JSON path.")],
) -> None:
    """Audit feature availability at each row's freeze time."""
    schema, records = _read_feature_inputs_or_exit(input_path, output_path)
    audit = audit_feature_availability(records, feature_schema=schema)
    _write_json(
        output_path,
        {
            "schema_id": schema.schema_id,
            "feature_names": list(schema.feature_names),
            "freeze_at": [_freeze_at_payload(record.freeze_at) for record in records],
            "audit": _audit_payload(audit),
        },
    )
    if not audit.valid:
        raise typer.Exit(code=1)


@model_app.command("features")
def model_features(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Generated feature JSON path.")],
) -> None:
    """Generate validated feature rows without imputing missing values."""
    schema, records = _read_feature_inputs_or_exit(input_path, output_path)
    try:
        result = build_features(records, feature_schema=schema)
    except FeatureGenerationError as exc:
        _write_json(
            output_path,
            {
                "schema_id": schema.schema_id,
                "audit": _audit_payload(exc.audit),
                "error": _input_error_payload(exc),
            },
        )
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        _write_json(
            output_path,
            {"schema_id": schema.schema_id, "error": _input_error_payload(exc)},
        )
        raise typer.Exit(code=1) from exc
    _write_json(
        output_path,
        {
            "schema_id": schema.schema_id,
            "feature_names": list(schema.feature_names),
            "records": _generated_records(result),
            "audit": _audit_payload(result.audit),
        },
    )


@model_app.command("walk-forward")
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
    schema, records = _read_feature_inputs_or_exit(input_path, output_path)
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
        _write_json(
            output_path,
            {
                "schema_id": schema.schema_id,
                "audit": _audit_payload(exc.audit),
                "error": _input_error_payload(exc),
            },
        )
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        _write_json(
            output_path,
            {"schema_id": schema.schema_id, "error": _input_error_payload(exc)},
        )
        raise typer.Exit(code=1) from exc
    _write_json(
        output_path,
        {
            "schema_id": schema.schema_id,
            "feature_names": list(schema.feature_names),
            "audit": _audit_payload(audit_feature_availability(records, feature_schema=schema)),
            "evaluation": _walk_forward_payload(evaluation),
        },
    )


def _read_feature_inputs_or_exit(
    input_path: Path,
    output_path: Path,
) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    try:
        return _read_feature_inputs(input_path)
    except typer.BadParameter as exc:
        _write_json(output_path, {"error": _input_error_payload(exc)})
        raise typer.Exit(code=1) from exc


def _read_feature_inputs(path: Path) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    payload = _read_json_object(path)
    schema_id = payload.get("schema_id")
    feature_names = payload.get("feature_names")
    raw_records = payload.get("records")
    if not isinstance(schema_id, str) or not isinstance(feature_names, list):
        raise typer.BadParameter("input JSON requires schema_id and feature_names")
    if not all(isinstance(name, str) for name in feature_names):
        raise typer.BadParameter("feature_names must be a list of strings")
    if not isinstance(raw_records, list):
        raise typer.BadParameter("input JSON requires a records list")
    try:
        schema = FeatureSchema.from_names(
            tuple(cast(list[str], feature_names)), schema_id=schema_id
        )
        records = tuple(_feature_input(value) for value in raw_records)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    return schema, records


def _feature_input(value: object) -> FeatureInput:
    if not isinstance(value, dict):
        raise ValueError("each record must be a JSON object")
    record = cast(dict[str, object], value)
    features = record.get("features")
    available_at = record.get("available_at")
    if not isinstance(features, dict) or not isinstance(available_at, dict):
        raise ValueError("each record requires features and available_at objects")
    return FeatureInput(
        race_id=cast(str, record.get("race_id")),
        horse_id=cast(str, record.get("horse_id")),
        freeze_at=cast(datetime | str, record.get("freeze_at")),
        features=cast(Mapping[str, FeatureValue], features),
        available_at=cast(Mapping[str, TimestampInput | None], available_at),
        finish_position=cast(int | None, record.get("finish_position")),
    )


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"cannot read input JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise typer.BadParameter("input JSON must be an object")
    return cast(dict[str, object], value)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _json_safe(value: object) -> object:
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _input_error_payload(error: Exception) -> dict[str, str]:
    return {"type": "input", "message": str(error)}


def _freeze_at_payload(value: TimestampInput) -> str:
    return value.isoformat() if isinstance(value, datetime) else value


def _audit_payload(audit: AvailabilityAudit) -> dict[str, object]:
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


def _generated_records(result: FeatureGenerationResult) -> list[dict[str, object]]:
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


if __name__ == "__main__":
    app()
