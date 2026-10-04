"""Command-line entry point for keiba-ai data workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from data.data_preprocesser import DataPreprocesser
from data.data_retriever import DataRetriever
from data.race_key import RaceKey

app = typer.Typer(no_args_is_help=True)
retrieve_app = typer.Typer(no_args_is_help=True, help="Retrieve JRA-VAN race data.")
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
app.add_typer(retrieve_app, name="retrieve")
app.add_typer(preprocess_app, name="preprocess")

DataConfigOption = Annotated[
    Path,
    typer.Option("--data-config", help="Path to the shared data TOML configuration."),
]
JVLinkConfigOption = Annotated[
    Path,
    typer.Option("--jvlink-config", help="Path to the JVLink retrieval profile TOML."),
]


def _retriever(data_config: Path, jvlink_config: Path) -> DataRetriever:
    return DataRetriever.from_toml(data_config=data_config, jvlink_config=jvlink_config)


def _preprocesser(data_config: Path) -> DataPreprocesser:
    return DataPreprocesser.from_toml(data_config)


@retrieve_app.command("historical")
def retrieve_historical(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Build historical raw data and publish a complete Parquet snapshot."""
    count = _retriever(data_config, jvlink_config).retrieve_historical()
    tables = _preprocesser(data_config).rebuild()
    typer.echo(f"historical odds retrieved for {count} races")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


@retrieve_app.command("latest")
def retrieve_latest(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Retrieve latest raw data and refresh the complete Parquet snapshot."""
    _retriever(data_config, jvlink_config).retrieve_latest()
    tables = _preprocesser(data_config).update()
    typer.echo("latest race data retrieved")
    typer.echo(f"processed snapshot published: {len(tables)} tables")


@retrieve_app.command("realtime")
def retrieve_realtime(
    race_datetime: Annotated[
        datetime,
        typer.Option("--date", formats=["%Y-%m-%d"], help="Race date (YYYY-MM-DD)."),
    ],
    jyo_code: Annotated[str, typer.Option("--jyo", help="Two-digit JRA venue code.")],
    kaiji: Annotated[str, typer.Option("--kaiji", help="Two-digit meeting number.")],
    nichiji: Annotated[str, typer.Option("--nichiji", help="Two-digit meeting day.")],
    race_number: Annotated[str, typer.Option("--race", help="Two-digit race number.")],
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Retrieve and publish prediction-time Parquet for one target race."""
    race_key = RaceKey(
        race_datetime.date(),
        jyo_code,
        kaiji,
        nichiji,
        race_number,
    )
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
