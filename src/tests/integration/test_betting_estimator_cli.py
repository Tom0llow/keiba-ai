"""Build the ADR-045 race-day estimator from a real `model backtest-betting` output.

The backtest runs on the small fixed snapshot and PL evaluation of
``test_betting_backtest_cli``; the estimator is then built from that output.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner, Result

from data.loader.fixed_snapshot import FixedSnapshot
from main import app
from models.artifacts.betting_estimator import read_betting_estimator
from models.experiments.betting_backtest import fit_year_estimators, width_observations
from models.serialization.betting_inputs import BlendTraining
from tests.integration.test_betting_backtest_cli import _inputs, _invoke
from tests.reference_fixtures import ROOT


def _backtest(tmp_path: Path) -> tuple[Path, str]:
    overrides = _inputs(tmp_path)
    output = tmp_path / "backtest"
    result = _invoke(output, overrides)
    assert result.exit_code == 0, result.stderr
    return output, hashlib.sha256((output / "report.json").read_bytes()).hexdigest()


def _fit(tmp_path: Path, output: Path, *, backtest: Path, sha256: str) -> Result:
    with patch(
        "models.experiments.provenance.experiment_provenance",
        return_value={"fixture": "provenance"},
    ):
        return CliRunner().invoke(
            app,
            [
                "model",
                "fit-betting-estimator",
                "--backtest",
                str(backtest),
                "--backtest-report-sha256",
                sha256,
                "--pl-evaluation",
                str(tmp_path / "pl"),
                "--processed-root",
                str(tmp_path / "processed"),
                "--output",
                str(output),
            ],
        )


def test_the_estimator_is_published_from_a_backtest_output(tmp_path: Path) -> None:
    backtest, sha256 = _backtest(tmp_path)
    output = tmp_path / "estimator"

    result = _fit(tmp_path, output, backtest=backtest, sha256=sha256)

    assert result.exit_code == 0, result.stderr
    assert [path.name for path in output.iterdir()] == ["manifest.json"]
    digest = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    (summary,) = result.stdout.splitlines()
    assert summary.startswith(f"ev betting estimator: {output} manifest_sha256={digest} ")
    assert "target_year=2026 " in summary
    read = read_betting_estimator(output, expected_manifest_sha256=digest)
    record = read.record
    report = json.loads((backtest / "report.json").read_text(encoding="utf-8"))
    assert record.target_year == 2026
    assert record.settings.train_start_year == 2023
    assert record.blend_fit_years == (2024, 2025)
    assert record.sources["backtest_report_sha256"] == sha256
    assert record.sources["pl_evaluation"] == {
        "report_sha256": report["inputs"]["pl_evaluation"]["report_sha256"],
        "predictions_sha256": report["inputs"]["pl_evaluation"]["predictions_sha256"],
        "variant": "all_columns",
    }
    snapshot = record.sources["snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["tables"] == {
        name: report["inputs"]["snapshot"]["tables"][name]["sha256"]
        for name in ("NL_RA_RACE", "NL_HR_PAY", "ARCHIVE_O1_ODDS_TANFUKUWAKU")
    }
    assert "path" not in json.dumps(read.manifest)
    assert read.manifest["provenance"] == {"fixture": "provenance"}


def test_the_published_fit_equals_the_backtest_fit_of_the_target_year(tmp_path: Path) -> None:
    """The CLI's own reads give the same fit as the backtest's pure fit for that year."""
    import cli.betting_backtest as command

    backtest, sha256 = _backtest(tmp_path)
    captured: dict[str, object] = {}
    original = command._read_training

    def spy(*args: object, **kwargs: object) -> object:
        training = original(*args, **kwargs)  # type: ignore[arg-type]
        captured["training"] = training
        return training

    with patch.object(command, "_read_training", side_effect=spy):
        result = _fit(tmp_path, tmp_path / "estimator", backtest=backtest, sha256=sha256)
    assert result.exit_code == 0, result.stderr
    digest = hashlib.sha256((tmp_path / "estimator/manifest.json").read_bytes()).hexdigest()
    record = read_betting_estimator(tmp_path / "estimator", expected_manifest_sha256=digest).record
    training = captured["training"]
    hits = training.hits  # type: ignore[attr-defined]
    assert all(int(hit.race_id[:4]) <= 2025 for hit in hits)
    report = json.loads((backtest / "report.json").read_text(encoding="utf-8"))
    settings = command._settings(report["config"])
    expected = fit_year_estimators(
        2026,
        settings,
        hits,
        width_observations(hits),
        _blend_training(tmp_path, settings.test_years),
        training.graded_ids,  # type: ignore[attr-defined]
    )
    for odds in (1.0, 1.4, 2.0, 3.5, 10.0):
        assert record.mid.estimate(odds) == expected.mid.estimate(odds)
    assert (record.blend.alpha, record.blend.beta) == (expected.blend.alpha, expected.blend.beta)


def _blend_training(tmp_path: Path, test_years: tuple[int, ...]) -> BlendTraining:
    from data.loader.read_parquet import read_parquet
    from models.serialization.betting_inputs import PL_BLEND_COLUMNS, blend_training_races

    rows = read_parquet(tmp_path / "pl" / "predictions.parquet", columns=PL_BLEND_COLUMNS)
    return blend_training_races(rows.to_pylist(), variant="all_columns", test_years=test_years)


@pytest.mark.parametrize("kind", ["existing", "parentless", "backtest", "processed", "pl"])
def test_an_output_that_cannot_be_created_is_rejected_before_reading(
    tmp_path: Path, kind: str
) -> None:
    backtest, sha256 = _backtest(tmp_path)
    output = {
        "existing": tmp_path / "estimator",
        "parentless": tmp_path / "missing" / "estimator",
        "backtest": backtest / "estimator",
        "processed": tmp_path / "processed" / "estimator",
        "pl": tmp_path / "pl" / "estimator",
    }[kind]
    if kind == "existing":
        output.mkdir()

    with patch.object(FixedSnapshot, "__init__", side_effect=AssertionError("read")) as opened:
        result = _fit(tmp_path, output, backtest=backtest, sha256=sha256)

    opened.assert_not_called()
    assert result.exit_code == 1
    assert "output" in result.stderr
    assert "backtest output" not in result.stderr
    assert not (output.exists() and kind != "existing")


def _rewrite_report(backtest: Path, change: object) -> str:
    report = json.loads((backtest / "report.json").read_text(encoding="utf-8"))
    change(report)  # type: ignore[operator]
    payload = json.dumps(report).encode("utf-8")
    (backtest / "report.json").write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda r: r["config"].update(bet_types=["win"]), "bet_types"),
        (lambda r: r["config"]["policy"].update(unit_yen=True), "unit_yen"),
        (lambda r: r["selection"]["2025"].update(method="blend_width"), "selection of 2025"),
        (lambda r: r["inputs"]["pl_evaluation"].update(variant="other"), "PL evaluation inputs"),
        (
            lambda r: r["inputs"]["snapshot"]["tables"]["NL_HR_PAY"].update(sha256="0" * 64),
            "NL_HR_PAY differs",
        ),
    ],
)
def test_a_report_or_input_that_breaks_a_rule_publishes_nothing(
    tmp_path: Path, change: object, message: str
) -> None:
    backtest, _ = _backtest(tmp_path)
    sha256 = _rewrite_report(backtest, change)
    output = tmp_path / "estimator"

    result = _fit(tmp_path, output, backtest=backtest, sha256=sha256)

    assert result.exit_code == 1
    assert message in result.stderr
    assert not output.exists()
    assert not any(path.name.startswith(".estimator") for path in tmp_path.iterdir())


def test_width_bands_the_artifact_cannot_store_fail_before_reading(tmp_path: Path) -> None:
    backtest, _ = _backtest(tmp_path)
    sha256 = _rewrite_report(
        backtest, lambda r: r["config"]["estimation"].update(place_width_bands=[1.0, 1.25, 2.0])
    )

    with patch.object(FixedSnapshot, "__init__", side_effect=AssertionError("read")) as opened:
        result = _fit(tmp_path, tmp_path / "estimator", backtest=backtest, sha256=sha256)

    opened.assert_not_called()
    assert result.exit_code == 1
    assert "multiples of 0.1" in result.stderr
    assert not (tmp_path / "estimator").exists()


def test_a_wrong_pin_publishes_nothing(tmp_path: Path) -> None:
    backtest, sha256 = _backtest(tmp_path)

    wrong = _fit(tmp_path, tmp_path / "a", backtest=backtest, sha256="0" * 64)
    (tmp_path / "pl" / "predictions.parquet").write_bytes(b"changed")
    changed = _fit(tmp_path, tmp_path / "b", backtest=backtest, sha256=sha256)

    assert wrong.exit_code == 1
    assert "report.json SHA-256 differs from --backtest-report-sha256" in wrong.stderr
    assert changed.exit_code == 1
    assert "predictions.parquet SHA-256 differs from the backtest report" in changed.stderr
    assert not (tmp_path / "a").exists()
    assert not (tmp_path / "b").exists()


def test_help_and_import_do_not_load_the_new_modules() -> None:
    script = """
import sys
from typer.testing import CliRunner
from main import app
for command in ("fit-betting-estimator", "propose-bets-live"):
    result = CliRunner().invoke(app, ["model", command, "--help"])
    assert result.exit_code == 0, result.output
# main's other commands may load NumPy; the new modules stay unloaded.
for name in (
    "lightgbm",
    "models.artifacts.betting_estimator",
    "models.experiments.betting_estimator",
    "models.experiments.bet_proposal",
    "models.betting.methods",
    "models.probability.market_blend",
):
    assert name not in sys.modules, name
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "src",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
