"""Assemble, register and start the keiba-ai command-line interface."""

import typer

from cli.cli_data_preprocessor import preprocess_rebuild
from cli.cli_jra_van_retriever import main
from cli.cli_make_datamart import datamart_build
from cli.cli_make_features import register_feature_commands as register_feature_commands
from cli.cli_models import model_walk_forward

app = typer.Typer(no_args_is_help=True)
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
model_app = typer.Typer(no_args_is_help=True, help="Build features and evaluate ranking models.")
datamart_app = typer.Typer(
    no_args_is_help=True, help="Build a datamart from feature Parquet tables."
)
app.add_typer(preprocess_app, name="preprocess")
app.add_typer(model_app, name="model")
app.add_typer(datamart_app, name="datamart")
app.callback(invoke_without_command=True)(main)
preprocess_app.command("rebuild")(preprocess_rebuild)
model_app.command("walk-forward")(model_walk_forward)
register_feature_commands(model_app)
datamart_app.command("build")(datamart_build)

if __name__ == "__main__":
    app()
