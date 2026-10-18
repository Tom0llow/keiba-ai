"""Assemble, register and start the keiba-ai command-line interface."""

import typer

from cli.jra_van_retriever import main
from cli.make_datamart import datamart_build
from cli.make_features import model_explanatory_variables
from cli.models import model_audit, model_features, model_walk_forward
from cli.preprocessor import preprocess_rebuild


def register_feature_commands(model_app: typer.Typer) -> None:
    """Register the audit, features, and explanatory-variables commands."""
    model_app.command("audit")(model_audit)
    model_app.command("features")(model_features)
    model_app.command("explanatory-variables")(model_explanatory_variables)


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
