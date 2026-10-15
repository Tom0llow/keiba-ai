"""Validate retrieval options and compose acquisition with publication."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from domain.race_key import RaceKey
from preprocesser.data_preprocesser import DataPreprocesser
from retriever.data_retriever import DataRetriever
from retriever.setting import JVLinkConfig

DataConfigOption = Annotated[
    Path,
    typer.Option("--data-config", help="Path to the shared data TOML configuration."),
]
JVLinkConfigOption = Annotated[
    Path,
    typer.Option("--jvlink-config", help="Path to the JVLink retrieval profile TOML."),
]


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
