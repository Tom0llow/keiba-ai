"""Define and execute the keiba-ai command-line interface."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from domain.race_key import RaceKey
from features.catalog.loader import load_feature_definitions
from features.catalog.registry import create_feature_registry
from features.contracts.types import FeatureBatchInput
from features.explanatory_variables import FeatureBuildError, build_explanatory_variables
from features.serialization.inputs import parse_explanatory_inputs
from features.serialization.outputs import explanatory_payload, feature_audit_payload
from models.dataset_builder import (
    FeatureGenerationError,
    FeatureInput,
    audit_feature_availability,
    build_features,
    build_ranking_dataset,
)
from models.ranking_dataset import FeatureSchema
from models.serialization.inputs import parse_feature_inputs
from models.serialization.outputs import (
    audit_payload,
    model_audit_payload,
    model_evaluation_payload,
    model_features_payload,
)
from models.walk_forward import WalkForwardConfig, evaluate_walk_forward
from preprocesser.data_preprocesser import DataPreprocesser
from retriever.data_retriever import DataRetriever
from retriever.setting import JVLinkConfig
from utils.json_output import write_json
from utils.loader.read_json import read_json

DataConfigOption = Annotated[
    Path,
    typer.Option("--data-config", help="Path to the shared data TOML configuration."),
]
JVLinkConfigOption = Annotated[
    Path,
    typer.Option("--jvlink-config", help="Path to the JVLink retrieval profile TOML."),
]


@dataclass(frozen=True)
class _RaceOptions:
    race_datetime: datetime | None
    jyo_code: str | None
    kaiji: str | None
    nichiji: str | None
    race_number: str | None

    @property
    def specified(self) -> bool:
        return any(
            value is not None
            for value in (
                self.race_datetime,
                self.jyo_code,
                self.kaiji,
                self.nichiji,
                self.race_number,
            )
        )

    def require_complete(self, message: str) -> RaceKey:
        if (
            self.race_datetime is None
            or self.jyo_code is None
            or self.kaiji is None
            or self.nichiji is None
            or self.race_number is None
        ):
            raise typer.BadParameter(message)
        return RaceKey(
            self.race_datetime.date(), self.jyo_code, self.kaiji, self.nichiji, self.race_number
        )


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
    race = _RaceOptions(race_datetime, jyo_code, kaiji, nichiji, race_number)
    odds_options = bool(plan_only or recover or confirm_provider_missing or data_spec)
    retrieval_options = odds_options or race.specified
    if ctx.invoked_subcommand is not None:
        if retrieve or mode is not None or retrieval_options:
            raise typer.BadParameter("retrieval options cannot be used with a subcommand")
        return

    if not retrieve and mode is None:
        if retrieval_options:
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
    if mode in {"historical-basic", "latest"}:
        if retrieval_options:
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        if mode == "historical-basic":
            retrieve_historical_basic(data_config, jvlink_config)
        else:
            retrieve_latest(data_config, jvlink_config)
        return
    if mode == "historical-odds":
        if confirm_provider_missing:
            race_key = _require_provider_missing_race(race)
            specs = _provider_missing_specs(data_spec)
            confirm_historical_odds_provider_missing(race_key, specs, data_config, jvlink_config)
            return
        if race.specified or data_spec:
            raise typer.BadParameter(
                "race options and --data-spec require --confirm-provider-missing"
            )
        retrieve_historical_odds(data_config, jvlink_config, plan_only=plan_only, recover=recover)
        return
    if mode == "realtime":
        if odds_options:
            raise typer.BadParameter("odds-only options require --mode historical-odds")
        race_key = _resolve_realtime_race(jvlink_config, race)
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
    race: _RaceOptions,
) -> RaceKey:
    if race.specified:
        return race.require_complete(
            "realtime CLI options must include --date, --jyo, --kaiji, --nichiji, and --race"
        )

    configured_race = JVLinkConfig.from_toml(jvlink_config).realtime_race
    if configured_race is None:
        raise typer.BadParameter(
            "realtime requires CLI race options or a [realtime] section in the JVLink config"
        )
    return configured_race


def _require_provider_missing_race(race: _RaceOptions) -> RaceKey:
    """Require an explicit complete RaceKey for a provider-gap confirmation."""
    try:
        return race.require_complete(
            "--confirm-provider-missing requires --date, --jyo, --kaiji, --nichiji, and --race"
        )
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


def preprocess_rebuild(
    data_config: DataConfigOption = Path("config/data.toml"),
) -> None:
    """Rebuild a complete Parquet snapshot without retrieving new raw data."""
    tables = _preprocesser(data_config).rebuild()
    typer.echo(f"processed snapshot published: {len(tables)} tables")


def register_feature_commands(model_app: typer.Typer) -> None:
    """Register the audit, features, and explanatory-variables commands."""
    model_app.command("audit")(model_audit)
    model_app.command("features")(model_features)
    model_app.command("explanatory-variables")(model_explanatory_variables)


def model_audit(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Audit output JSON path.")],
) -> None:
    """Audit feature availability at each row's freeze time."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    audit = audit_feature_availability(records, feature_schema=schema)
    write_json(output_path, model_audit_payload(schema, records, audit))
    if not audit.valid:
        raise typer.Exit(code=1)


def model_features(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Generated feature JSON path.")],
) -> None:
    """Generate validated feature rows without imputing missing values."""
    schema, records = read_feature_inputs_or_exit(input_path, output_path)
    try:
        result = build_features(records, feature_schema=schema)
    except FeatureGenerationError as exc:
        _exit_input_error(
            output_path, exc, schema_id=schema.schema_id, audit=audit_payload(exc.audit)
        )
    except ValueError as exc:
        _exit_input_error(output_path, exc, schema_id=schema.schema_id)
    write_json(output_path, model_features_payload(schema, result))


def model_explanatory_variables(
    input_path: Annotated[Path, typer.Option("--input", help="Feature input JSON path.")],
    output_path: Annotated[Path, typer.Option("--output", help="Feature output JSON path.")],
    features_config: Annotated[
        Path, typer.Option("--features-config", help="Feature registration TOML path.")
    ] = Path("config/features.toml"),
) -> None:
    """Validate F01-F21 feature values without using the model schema."""
    try:
        registry = create_feature_registry(load_feature_definitions(features_config))
        records = _read_explanatory_inputs(input_path)
        result = build_explanatory_variables(records, registry=registry)
    except typer.BadParameter as exc:
        _exit_input_error(output_path, exc)
    except FeatureBuildError as exc:
        _exit_input_error(
            output_path,
            exc,
            feature_ids=list(registry.feature_ids),
            audit=feature_audit_payload(exc.audit),
        )
    except (OSError, TypeError, ValueError) as exc:
        _exit_input_error(output_path, exc)
    write_json(output_path, explanatory_payload(result, feature_ids=registry.feature_ids))


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
        _exit_input_error(
            output_path, exc, schema_id=schema.schema_id, audit=audit_payload(exc.audit)
        )
    except ValueError as exc:
        _exit_input_error(output_path, exc, schema_id=schema.schema_id)
    write_json(
        output_path,
        model_evaluation_payload(
            schema, audit_feature_availability(records, feature_schema=schema), evaluation
        ),
    )


def read_feature_inputs_or_exit(
    input_path: Path,
    output_path: Path,
) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    """Read feature inputs, or write the input error and exit with code 1."""
    try:
        return _read_feature_inputs(input_path)
    except typer.BadParameter as exc:
        _exit_input_error(output_path, exc)


def _read_feature_inputs(path: Path) -> tuple[FeatureSchema, tuple[FeatureInput, ...]]:
    return _parse_inputs(path, parse_feature_inputs)


def _read_explanatory_inputs(path: Path) -> tuple[FeatureBatchInput, ...]:
    return _parse_inputs(path, parse_explanatory_inputs)


def _parse_inputs[T](path: Path, parser: Callable[[dict[str, object]], T]) -> T:
    payload = _read_json_object(path)
    try:
        return parser(payload)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        return read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"cannot read input JSON: {exc}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def input_error_payload(error: Exception) -> dict[str, str]:
    """Return the structured input error used by model commands."""
    return {"type": "input", "message": str(error)}


def _exit_input_error(output_path: Path, error: Exception, **context: object) -> NoReturn:
    write_json(output_path, {**context, "error": input_error_payload(error)})
    raise typer.Exit(code=1) from error


app = typer.Typer(no_args_is_help=True)
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
model_app = typer.Typer(no_args_is_help=True, help="Build features and evaluate ranking models.")
app.add_typer(preprocess_app, name="preprocess")
app.add_typer(model_app, name="model")
app.callback(invoke_without_command=True)(main)
preprocess_app.command("rebuild")(preprocess_rebuild)
model_app.command("walk-forward")(model_walk_forward)
register_feature_commands(model_app)


if __name__ == "__main__":
    app()
