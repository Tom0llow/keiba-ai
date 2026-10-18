"""Define option types shared by data retrieval and preprocessing CLIs."""

from pathlib import Path
from typing import Annotated

import typer

DataConfigOption = Annotated[
    Path,
    typer.Option("--data-config", help="Path to the shared data TOML configuration."),
]

JVLinkConfigOption = Annotated[
    Path,
    typer.Option("--jvlink-config", help="Path to the JVLink retrieval profile TOML."),
]
