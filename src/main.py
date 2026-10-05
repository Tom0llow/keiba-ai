"""Command-line entry point for keiba-ai data workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from data.data_preprocesser import DataPreprocesser
from data.data_retriever import DataRetriever
from data.race_key import RaceKey
from data.retriever.setting import JVLinkConfig

app = typer.Typer(no_args_is_help=True)
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
app.add_typer(preprocess_app, name="preprocess")

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
            or any(
                value is not None
                for value in (race_datetime, jyo_code, kaiji, nichiji, race_number)
            )
        ):
            raise typer.BadParameter("retrieval options cannot be used with a subcommand")
        return

    if not retrieve and mode is None:
        return
    if not retrieve:
        raise typer.BadParameter("--mode requires --retrieve")
    if mode == "historical":
        retrieve_historical(data_config, jvlink_config)
        return
    if mode == "latest":
        retrieve_latest(data_config, jvlink_config)
        return
    if mode == "realtime":
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
    raise typer.BadParameter("--mode must be 'historical', 'latest', or 'realtime'")


def _retriever(data_config: Path, jvlink_config: Path) -> DataRetriever:
    return DataRetriever.from_toml(data_config=data_config, jvlink_config=jvlink_config)


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


def retrieve_historical(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Build historical raw data and publish a complete Parquet snapshot."""
    count = _retriever(data_config, jvlink_config).retrieve_historical()
    tables = _preprocesser(data_config).rebuild()
    typer.echo(f"historical odds retrieved for {count} races")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


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


if __name__ == "__main__":
    app()
