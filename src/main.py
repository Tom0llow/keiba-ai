"""Command-line entry point for keiba-ai data workflows."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from data.data_retriever import DataRetriever

app = typer.Typer(no_args_is_help=True)
retrieve_app = typer.Typer(no_args_is_help=True, help="Retrieve JRA-VAN race data.")
app.add_typer(retrieve_app, name="retrieve")

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


@retrieve_app.command("historical")
def retrieve_historical(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Build the historical database and retrieve configured historical odds."""
    count = _retriever(data_config, jvlink_config).retrieve_historical()
    typer.echo(f"historical odds retrieved for {count} races")


@retrieve_app.command("latest")
def retrieve_latest(
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Retrieve the latest configured incremental and realtime data."""
    _retriever(data_config, jvlink_config).retrieve_latest()
    typer.echo("latest race data retrieved")


@retrieve_app.command("realtime")
def retrieve_realtime(
    race_date: Annotated[date, typer.Option("--date", help="Race date (YYYY-MM-DD).")],
    jyo_code: Annotated[str, typer.Option("--jyo", help="Two-digit JRA venue code.")],
    kaiji: Annotated[str, typer.Option("--kaiji", help="Two-digit meeting number.")],
    nichiji: Annotated[str, typer.Option("--nichiji", help="Two-digit meeting day.")],
    race_number: Annotated[str, typer.Option("--race", help="Two-digit race number.")],
    data_config: DataConfigOption = Path("config/data.toml"),
    jvlink_config: JVLinkConfigOption = Path("config/jvlink.toml"),
) -> None:
    """Retrieve prediction-time history and current odds for one target race."""
    inserted = _retriever(data_config, jvlink_config).retrieve_realtime(
        race_date=race_date,
        jyo_code=jyo_code,
        kaiji=kaiji,
        nichiji=nichiji,
        race_number=race_number,
    )
    typer.echo(f"realtime odds archived: {inserted} rows")


if __name__ == "__main__":
    app()
