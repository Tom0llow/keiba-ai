"""Run `model evaluate-pl` against a small synthetic three-year reference datamart."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner, Result

from configuration.pl_evaluation import load_pl_evaluation_config
from main import app
from make_datamart.tables.reference import ReferenceDatamartWriter
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.real_market import MARKET_COLUMN
from make_features.reference_raw import result_boundary
from models.experiments.pl_evaluation import PREDICTION_SCHEMA
from tests.reference_fixtures import RICH_TARGET_DAYS, ROOT, datamart_from_raw, rich_raw_input

YEARS = (2024, 2025, 2026)
CONFIGS = ROOT / "configs/pl_evaluation"


def _write_datamart(path: Path) -> str:
    """Write a valid three-year datamart with the rich fixture's columns and contract."""
    raw = rich_raw_input()
    builder, _ = datamart_from_raw(
        raw,
        registry=create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml")),
        target_start=RICH_TARGET_DAYS[0],
        target_end=RICH_TARGET_DAYS[-1],
    )
    manifest = builder.manifest(
        snapshot=cast(dict[str, object], raw["snapshot"]),
        provenance={"fixture": True},
        preparation_config={"fixture": True},
    )
    delay = cast(int, cast(dict[str, object], manifest["label"])["result_delay_days"])
    manifest["target_period"] = {"start": f"{YEARS[0]}-01-01", "end": f"{YEARS[-1]}-12-31"}
    path.mkdir()
    writer = ReferenceDatamartWriter(
        path,
        columns=builder.columns,
        available_at_groups=builder.available_at_groups,
        contract=builder.contract.as_metadata(),
    )
    generator = np.random.default_rng(5)
    names = [column.name for column in builder.columns]
    for year in YEARS:
        rows: list[dict[str, object]] = []
        races: list[dict[str, object]] = []
        for race in range(30):
            scheduled = datetime(year, 2, 1, 5, 0, tzinfo=UTC) + timedelta(days=7 * (race // 3))
            scheduled += timedelta(minutes=30 * (race % 3))
            freeze = scheduled - timedelta(seconds=300)
            race_id = f"{year}{race:012d}"
            size = 6
            strength = 1.5 * generator.normal(size=size)
            order = np.argsort(-(strength + generator.gumbel(size=size)))
            positions = np.empty(size, dtype=np.int64)
            positions[order] = np.arange(1, size + 1)
            win = np.exp(strength - strength.max())
            odds = np.maximum(0.8 / (win / win.sum()), 1.0)
            races.append(
                {
                    "race_id": race_id,
                    "scheduled_start_at": scheduled,
                    "freeze_at": freeze,
                    "field_size": size,
                    "label_usable_after": result_boundary(scheduled, delay),
                    "result_delay_days": delay,
                    "label_raw_sha256": "a" * 64,
                    "horse_mapping_sha256": "b" * 64,
                    "history_usable_through": None,
                }
            )
            for horse in range(size):
                row: dict[str, object] = {
                    "race_id": race_id,
                    "horse_id": f"{horse:010d}",
                    "scheduled_start_at": scheduled,
                    "freeze_at": freeze,
                    "finish_position": int(positions[horse]),
                }
                for name in names:
                    row[name] = float(generator.normal())
                row[names[0]] = float(strength[horse])
                row[MARKET_COLUMN] = float(odds[horse])
                if race == 0 and horse == 0:
                    row[MARKET_COLUMN] = None
                for group in builder.available_at_groups:
                    row[f"{group}__available_at"] = freeze
                rows.append(row)
        writer.write_year(year, rows, races)
    return writer.finish(manifest, [])


def _overrides(path: Path, digest: str, *extra: str) -> list[str]:
    values = [
        f"datamart_path={path.as_posix()}",
        f"datamart_manifest_sha256={digest}",
        "train_start_year=2024",
        "test_years=[2026]",
        "lightgbm={learning_rate:0.1,num_leaves:7,min_data_in_leaf:10,num_threads:1,"
        "seed:0,deterministic:true,force_col_wise:true}",
        "num_boost_round=30",
        "early_stopping_rounds=5",
        "bootstrap.resamples=50",
        *extra,
    ]
    return [item for value in values for item in ("--override", value)]


def _invoke(output: Path, overrides: list[str], config_name: str = "measure") -> Result:
    return CliRunner().invoke(
        app,
        [
            "model",
            "evaluate-pl",
            "--output",
            str(output),
            "--config-dir",
            str(CONFIGS),
            "--config-name",
            config_name,
            *overrides,
        ],
    )


def test_evaluate_pl_publishes_report_and_predictions(tmp_path: Path) -> None:
    datamart = tmp_path / "datamart"
    digest = _write_datamart(datamart)
    output = tmp_path / "evaluation"

    result = _invoke(output, _overrides(datamart, digest))

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in output.iterdir()) == ["predictions.parquet", "report.json"]
    stdout = result.stdout
    assert stdout.strip() == (
        f"Evaluated PL probabilities: folds=1 variants=2 test_races=30 output={output}"
    )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["format"] == "pl_probability_evaluation"
    assert report["format_version"] == 1
    assert report["datamart"]["manifest_sha256"] == digest
    assert [fold["test_year"] for fold in report["folds"]] == [2026]
    counts = report["folds"][0]["counts"]
    assert counts["test_market_complete_races"] == 29
    assert counts["test_market_incomplete_races"] == 1
    without_market = report["folds"][0]["variants"]["without_market"]["feature_names"]
    assert MARKET_COLUMN not in without_market
    assert MARKET_COLUMN in report["folds"][0]["variants"]["all_columns"]["feature_names"]
    predictions = pq.read_table(output / "predictions.parquet")
    assert predictions.schema.equals(PREDICTION_SCHEMA)
    assert predictions.num_rows == 2 * 30 * 6
    assert "phase=publish" in result.stderr


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("datamart_manifest_sha256=" + "0" * 64,), "SHA-256 differs"),
        (("variants=[{name:bad,excluded_columns:[missing_column]}]",), "unknown columns"),
        (("test_years=[2027]",), "not present"),
        (("+lightgbm.objective=lambdarank",), "reserved"),
        (("+lightgbm.boosting=dart",), "gbdt"),
    ],
)
def test_evaluate_pl_failures_leave_no_output_or_staging(
    tmp_path: Path, extra: tuple[str, ...], message: str
) -> None:
    datamart = tmp_path / "datamart"
    digest = _write_datamart(datamart)
    output = tmp_path / "evaluation"

    result = _invoke(output, _overrides(datamart, digest, *extra))

    assert result.exit_code == 1
    assert message in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart"]
    if message in {"reserved", "gbdt"}:
        # LightGBM settings are rejected before the datamart is read or trained on.
        assert "phase=read" not in result.stderr


def test_evaluate_pl_rejects_existing_output_and_unresolved_settings(tmp_path: Path) -> None:
    datamart = tmp_path / "datamart"
    digest = _write_datamart(datamart)
    existing = tmp_path / "existing"
    existing.mkdir()

    result = _invoke(existing, _overrides(datamart, digest))
    assert result.exit_code == 1
    assert "new non-symbolic-link path" in result.stderr
    assert list(existing.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "existing"]

    unresolved = _invoke(tmp_path / "out", _overrides(datamart, digest), config_name="evaluate")
    assert unresolved.exit_code == 1
    assert "Missing mandatory value" in unresolved.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "existing"]


def test_evaluate_pl_help_does_not_import_its_configuration_or_lightgbm() -> None:
    script = """
import sys
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "evaluate-pl", "--help"])
assert result.exit_code == 0, result.output
for name in ("lightgbm", "models.experiments.pl_evaluation", "configuration.pl_evaluation"):
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


_BASE = ("datamart_path=dm", "datamart_manifest_sha256=" + "a" * 64)


def test_measure_profile_resolves_the_full_period_folds_and_two_variants() -> None:
    config = load_pl_evaluation_config(CONFIGS, config_name="measure", overrides=_BASE)

    assert config["train_start_year"] == 2006
    assert config["test_years"] == list(range(2016, 2026))
    assert [variant["name"] for variant in cast(list[dict[str, object]], config["variants"])] == [
        "all_columns",
        "without_market",
    ]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ("datamart_manifest_sha256=ABC", "SHA-256"),
        ("test_years=[2020,2020]", "strictly increasing"),
        ("temperature_bounds=[2.0,1.0]", "temperature_bounds"),
        ("probability_bands=[0.0,1.5]", "start at zero and end at one"),
        ("probability_bands=[0.2,1.0]", "start at zero and end at one"),
        ("probability_bands=[0.0,0.8]", "start at zero and end at one"),
        ("odds_bands=[0.0,2.0]", "start above zero and no higher than one"),
        ("odds_bands=[1.1,2.0]", "start above zero and no higher than one"),
        ("bootstrap.confidence=1.0", "confidence"),
        ("bootstrap.seed=-1", "non-negative"),
        ("num_boost_round=0", "positive integer"),
        ("variants=[{name:a,excluded_columns:[]},{name:a,excluded_columns:[]}]", "unique"),
    ],
)
def test_pl_evaluation_config_rejects_invalid_values(override: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_pl_evaluation_config(CONFIGS, config_name="measure", overrides=(*_BASE, override))
