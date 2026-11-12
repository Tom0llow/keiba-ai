"""Train and publish the final PL model through `model train-pl` (ADR-038)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

import numpy as np
import pytest
from omegaconf import OmegaConf
from typer.testing import CliRunner, Result

from cli.reference_datamart import _source_binding
from main import app
from make_datamart.tables.reference import ReferenceDatamartWriter
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.real_market import MARKET_COLUMN
from make_features.reference_raw import result_boundary
from models.artifacts.pl_model import read_pl_model
from tests.reference_fixtures import RICH_TARGET_DAYS, ROOT, datamart_from_raw, rich_raw_input

YEARS = (2024, 2025, 2026)
CONFIGS = ROOT / "configs/pl_training"


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
        provenance={"source_sha256": "f" * 64},
        preparation_config={"fixture": True},
    )
    delay = cast(int, cast(dict[str, object], manifest["label"])["result_delay_days"])
    manifest["target_period"] = {"start": f"{YEARS[0]}-01-01", "end": f"{YEARS[-1]}-06-30"}
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
            race_id = f"{year}0101010101{race + 1:02d}"
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
        "valid_year=2026",
        "lightgbm={learning_rate:0.1,num_leaves:7,min_data_in_leaf:10,num_threads:1,"
        "seed:0,deterministic:true,force_col_wise:true}",
        "num_boost_round=30",
        "early_stopping_rounds=5",
        *extra,
    ]
    return [item for value in values for item in ("--override", value)]


def _invoke(output: Path, overrides: list[str], config_name: str = "final") -> Result:
    return CliRunner().invoke(
        app,
        [
            "model",
            "train-pl",
            "--output",
            str(output),
            "--config-dir",
            str(CONFIGS),
            "--config-name",
            config_name,
            *overrides,
        ],
    )


@pytest.fixture(scope="module")
def datamart(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    path = tmp_path_factory.mktemp("datamart") / "datamart"
    return path, _write_datamart(path)


def test_train_pl_publishes_a_model_readable_by_its_manifest_identity(
    tmp_path: Path, datamart: tuple[Path, str]
) -> None:
    path, digest = datamart
    output = tmp_path / "model"

    result = _invoke(output, _overrides(path, digest))

    assert result.exit_code == 0, result.output
    line = result.stdout.strip()
    assert line.startswith("Trained PL model: best_iteration=")
    model_sha256 = line.rsplit("manifest_sha256=", 1)[1]
    model = read_pl_model(output, expected_manifest_sha256=model_sha256)
    manifest = cast(dict[str, dict[str, object]], model.manifest)
    source = manifest["source_datamart"]
    assert source["manifest_sha256"] == digest
    assert source["provenance_source_sha256"] == "f" * 64
    datamart_manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert source["contract_sha256"] == datamart_manifest["contract"]["sha256"]
    assert source["columns"] == datamart_manifest["columns"]
    assert source["target_period"] == datamart_manifest["target_period"]
    training = manifest["training"]
    assert (training["train_start_year"], training["valid_year"]) == (2024, 2026)
    assert training["valid_races"] == 30
    assert model.feature_names == tuple(column["name"] for column in datamart_manifest["columns"])
    assert "datamart_path" not in manifest["config"]
    # Neither the native nor the POSIX form of the datamart location is persisted.
    raw = (output / "manifest.json").read_text(encoding="ascii")
    for form in (str(path), path.as_posix(), json.dumps(str(path))[1:-1]):
        assert form not in raw
    # The live prediction CLI builds its binding separately; #53 must accept it.
    binding = _source_binding(datamart_manifest, path, digest)
    model.require_compatible_features(
        {"source_datamart": binding, "columns": datamart_manifest["columns"]}
    )
    assert f"label_usable_through={model.label_usable_through.isoformat()}" in line
    for phase in ("read", "train", "publish"):
        assert f"phase={phase}" in result.stderr
    assert sorted(item.name for item in tmp_path.iterdir()) == ["model"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("datamart_manifest_sha256=" + "0" * 64,), "expected identity"),
        (("variant={name:bad,excluded_columns:[missing_column]}",), "unknown columns"),
        (("valid_year=2027",), "outside the datamart target period"),
        (("train_start_year=2026",), "at most valid_year - 1"),
        (("train_start_year=2023",), "outside the datamart target period"),
        (("+lightgbm.objective=lambdarank",), "reserved"),
        (("+lightgbm.boosting=dart",), "gbdt"),
        ((), "excludes every column"),
    ],
)
def test_train_pl_rejects_settings_before_reading_the_datamart(
    tmp_path: Path, datamart: tuple[Path, str], extra: tuple[str, ...], message: str
) -> None:
    path, digest = datamart
    if message == "excludes every column":
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        names = ",".join(column["name"] for column in manifest["columns"])
        extra = (f"variant={{name:empty,excluded_columns:[{names}]}}",)
    output = tmp_path / "model"

    with patch(
        "make_datamart.tables.reference.read_reference_datamart",
        side_effect=AssertionError("datamart was read before the settings check"),
    ) as full_read:
        result = _invoke(output, _overrides(path, digest, *extra))

    full_read.assert_not_called()
    assert result.exit_code == 1
    assert message in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert list(tmp_path.iterdir()) == []


def test_train_pl_rejects_existing_output_and_unresolved_settings(
    tmp_path: Path, datamart: tuple[Path, str]
) -> None:
    path, digest = datamart
    existing = tmp_path / "existing"
    existing.mkdir()

    result = _invoke(existing, _overrides(path, digest))
    assert result.exit_code == 1
    assert "new non-symbolic-link path" in result.stderr
    assert list(existing.iterdir()) == []

    unresolved = _invoke(tmp_path / "out", _overrides(path, digest), config_name="train")
    assert unresolved.exit_code == 1
    assert "Missing mandatory value" in unresolved.stderr
    assert len(unresolved.stderr.strip().splitlines()) == 1
    assert sorted(item.name for item in tmp_path.iterdir()) == ["existing"]


@pytest.mark.parametrize(("error", "code"), [(KeyboardInterrupt(), 130), (OSError("disk"), 1)])
def test_train_pl_failures_during_training_leave_no_output_or_staging(
    tmp_path: Path, datamart: tuple[Path, str], error: BaseException, code: int
) -> None:
    path, digest = datamart
    output = tmp_path / "model"

    with patch("models.artifacts.pl_model.write_pl_model", side_effect=error):
        result = _invoke(output, _overrides(path, digest))

    assert result.exit_code == code
    assert "model train-pl failed:" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_train_pl_help_does_not_import_its_configuration_training_or_lightgbm() -> None:
    script = """
import sys
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "train-pl", "--help"])
assert result.exit_code == 0, result.output
for name in (
    "lightgbm",
    "configuration.pl_training",
    "models.experiments.pl_training",
    "models.artifacts.pl_model",
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


def test_the_final_profile_trains_exactly_as_the_evaluation_measured() -> None:
    final = OmegaConf.to_container(OmegaConf.load(CONFIGS / "final.yaml"))
    measured = OmegaConf.to_container(OmegaConf.load(ROOT / "configs/pl_evaluation/measure.yaml"))
    assert isinstance(final, dict)
    assert isinstance(measured, dict)
    for key in ("lightgbm", "num_boost_round", "early_stopping_rounds", "temperature_bounds"):
        assert final[key] == measured[key], key
    assert final["variant"] == {"name": "all_columns", "excluded_columns": []}
    assert (final["train_start_year"], final["valid_year"]) == (2006, 2025)
