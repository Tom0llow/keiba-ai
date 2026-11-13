"""Assemble, register and start the keiba-ai command-line interface."""

import typer

from cli.jra_van_retriever import main
from cli.make_datamart import datamart_build
from cli.make_features import model_calculate_features, model_explanatory_variables
from cli.model_projection import model_prepare_input
from cli.models import model_audit, model_features, model_predict, model_train, model_walk_forward
from cli.pl_evaluation import model_evaluate_pl
from cli.pl_prediction import model_predict_pl_live
from cli.pl_training import model_train_pl
from cli.preprocessor import preprocess_rebuild
from cli.real_market import model_prepare_real_input
from cli.reference_datamart import (
    datamart_build_reference,
    datamart_build_reference_prediction,
    datamart_build_reference_prediction_live,
)
from cli.reference_input import model_prepare_reference_input


def register_feature_commands(model_app: typer.Typer) -> None:
    """Register the audit, features, and explanatory-variables commands."""
    model_app.command("audit")(model_audit)
    model_app.command("features")(model_features)
    model_app.command("explanatory-variables")(model_explanatory_variables)
    model_app.command("calculate-features")(model_calculate_features)


app = typer.Typer(no_args_is_help=True)
preprocess_app = typer.Typer(no_args_is_help=True, help="Publish processed Parquet data.")
model_app = typer.Typer(no_args_is_help=True, help="Build features and evaluate ranking models.")
datamart_app = typer.Typer(
    no_args_is_help=True,
    help="Build a datamart from feature Parquet tables or a fixed processed snapshot.",
)
app.add_typer(preprocess_app, name="preprocess")
app.add_typer(model_app, name="model")
app.add_typer(datamart_app, name="datamart")
app.callback(invoke_without_command=True)(main)
preprocess_app.command("rebuild")(preprocess_rebuild)
model_app.command("walk-forward")(model_walk_forward)
register_feature_commands(model_app)
model_app.command("train")(model_train)
model_app.command("predict")(model_predict)
model_app.command("prepare-input")(model_prepare_input)
model_app.command("prepare-real-input")(model_prepare_real_input)
model_app.command("prepare-reference-input")(model_prepare_reference_input)
model_app.command("evaluate-pl")(model_evaluate_pl)
model_app.command("train-pl")(model_train_pl)
model_app.command("predict-pl-live")(model_predict_pl_live)
datamart_app.command("build")(datamart_build)
datamart_app.command("build-reference")(datamart_build_reference)
datamart_app.command("build-reference-prediction")(datamart_build_reference_prediction)
datamart_app.command("build-reference-prediction-live")(datamart_build_reference_prediction_live)

if __name__ == "__main__":
    app()
