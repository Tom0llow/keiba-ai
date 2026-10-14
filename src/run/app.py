"""Register the user-facing Typer applications without executing workflows."""

import typer

from run.features import register_feature_commands
from run.models import model_walk_forward
from run.preprocess import preprocess_rebuild
from run.retrieval import main

app = typer.Typer(no_args_is_help=True)
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
model_app = typer.Typer(no_args_is_help=True, help="Build features and evaluate ranking models.")
app.add_typer(preprocess_app, name="preprocess")
app.add_typer(model_app, name="model")
app.callback(invoke_without_command=True)(main)
preprocess_app.command("rebuild")(preprocess_rebuild)
model_app.command("walk-forward")(model_walk_forward)
register_feature_commands(model_app)
