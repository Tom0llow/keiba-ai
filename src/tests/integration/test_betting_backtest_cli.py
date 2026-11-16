"""Run `model backtest-betting` on a small fixed snapshot and PL evaluation (AC-12 to AC-16)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from omegaconf import OmegaConf
from typer.testing import CliRunner, Result

from configuration.betting_backtest import load_betting_backtest_config
from data.loader.fixed_snapshot import FixedSnapshot
from main import app
from make_datamart.tables.reference import (
    ReferenceDatamartWriter,
    read_reference_datamart_target_holds,
)
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.reference_raw import result_boundary
from models.experiments.betting_backtest import BETS_SCHEMA, RACES_SCHEMA
from models.serialization.betting_inputs import SE_COLUMNS, SE_TABLE
from models.serialization.final_odds_observations import (
    HR_COLUMNS,
    HR_TABLE,
    O1_COLUMNS,
    O1_TABLE,
    RA_COLUMNS,
    RA_TABLE,
)
from tests.betting_fixtures import (
    hr_row,
    o1_row,
    prediction_rows,
    ra_row,
    race_id,
    se_rows,
)
from tests.reference_fixtures import RICH_TARGET_DAYS, ROOT, datamart_from_raw, rich_raw_input

CONFIGS = ROOT / "configs/betting_backtest"
SNAPSHOT_ID = "fixture-snapshot-v1"
YEARS = (2023, 2024, 2025)
TEST_YEARS = (2024, 2025)
# Races 01 and 02 are graded; 03 is not. Race 02 has no prediction in either test year:
# in 2025 the datamart holds it at target_outcome, in 2024 it is unattributed.
HELD = race_id(2025, 2)


def _race_ids() -> list[str]:
    return [race_id(year, number) for year in YEARS for number in (1, 2, 3)]


def _tables() -> dict[str, tuple[tuple[str, ...], list[dict[str, object]]]]:
    race_ids = _race_ids()
    ra = [ra_row(race, GradeCD="A" if race[-2:] != "03" else "") for race in race_ids]
    o1 = [o1_row(race) for race in race_ids]
    o1.extend(o1_row(race, clock="1527", win_codes=("0099",) * 8) for race in race_ids)
    return {
        RA_TABLE: (RA_COLUMNS, ra),
        SE_TABLE: (SE_COLUMNS, [row for race in race_ids for row in se_rows(race)]),
        HR_TABLE: (HR_COLUMNS, [hr_row(race) for race in race_ids]),
        O1_TABLE: (O1_COLUMNS, o1),
    }


def _write_snapshot(processed_root: Path) -> str:
    path = processed_root / "snapshots" / SNAPSHOT_ID
    path.mkdir(parents=True)
    for table, (columns, rows) in _tables().items():
        schema = pa.schema([(name, pa.string()) for name in columns])
        projected = [{name: row.get(name) for name in columns} for row in rows]
        pq.write_table(
            pa.Table.from_pylist(projected, schema=schema),
            path / f"{table}.parquet",
            row_group_size=5,
        )
    return hashlib.sha256((path / f"{RA_TABLE}.parquet").read_bytes()).hexdigest()


def _write_datamart(path: Path, held: list[dict[str, object]]) -> str:
    """Write a valid one-year datamart whose held races are ``held``."""
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
    manifest["target_period"] = {"start": "2024-01-01", "end": "2024-12-31"}
    path.mkdir()
    writer = ReferenceDatamartWriter(
        path,
        columns=builder.columns,
        available_at_groups=builder.available_at_groups,
        contract=builder.contract.as_metadata(),
    )
    generator = np.random.default_rng(5)
    names = [column.name for column in builder.columns]
    rows: list[dict[str, object]] = []
    races: list[dict[str, object]] = []
    for number in range(3):
        scheduled = datetime(2024, 2, 1, 5, 0, tzinfo=UTC) + timedelta(days=7 * number)
        freeze = scheduled - timedelta(seconds=300)
        identity = f"20240201010101{number + 1:02d}"
        races.append(
            {
                "race_id": identity,
                "scheduled_start_at": scheduled,
                "freeze_at": freeze,
                "field_size": 3,
                "label_usable_after": result_boundary(scheduled, delay),
                "result_delay_days": delay,
                "label_raw_sha256": "a" * 64,
                "horse_mapping_sha256": "b" * 64,
                "history_usable_through": None,
            }
        )
        for horse in range(3):
            row: dict[str, object] = {
                "race_id": identity,
                "horse_id": f"{horse:010d}",
                "scheduled_start_at": scheduled,
                "freeze_at": freeze,
                "finish_position": horse + 1,
            }
            for name in names:
                row[name] = float(generator.normal())
            for group in builder.available_at_groups:
                row[f"{group}__available_at"] = freeze
            rows.append(row)
    writer.write_year(2024, rows, races)
    return writer.finish(manifest, held)


def _write_pl_evaluation(
    path: Path, *, datamart: Path, manifest_sha256: str, ra_sha256: str
) -> tuple[str, str]:
    path.mkdir()
    rows = [row for year in TEST_YEARS for row in prediction_rows(race_id(year, 1))]
    pq.write_table(pa.Table.from_pylist(rows), path / "predictions.parquet")
    report = {
        "format": "pl_probability_evaluation",
        "format_version": 1,
        "test_years": list(TEST_YEARS),
        "config": {
            "datamart_path": datamart.as_posix(),
            "variants": [{"name": "all_columns", "excluded_columns": []}],
        },
        "datamart": {"manifest_sha256": manifest_sha256},
        "race_subsets": {
            "jra_flat_graded_stakes_v1": {
                "source": {"table": RA_TABLE, "sha256": ra_sha256, "snapshot_id": SNAPSHOT_ID}
            }
        },
    }
    (path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return (
        hashlib.sha256((path / "predictions.parquet").read_bytes()).hexdigest(),
        hashlib.sha256((path / "report.json").read_bytes()).hexdigest(),
    )


def _inputs(tmp_path: Path) -> list[str]:
    processed_root = tmp_path / "processed"
    ra_sha256 = _write_snapshot(processed_root)
    datamart = tmp_path / "datamart"
    manifest_sha256 = _write_datamart(
        datamart,
        [
            {
                "race_id": HELD,
                "role": "target",
                "stage": "target_outcome",
                "reason": "non_normal_or_tied_result",
                "whole_race": True,
            },
            {
                "race_id": race_id(2024, 2),
                "role": "history",
                "stage": "history_result",
                "reason": "non_normal_or_tied_result",
                "whole_race": True,
            },
        ],
    )
    predictions_sha256, report_sha256 = _write_pl_evaluation(
        tmp_path / "pl",
        datamart=datamart,
        manifest_sha256=manifest_sha256,
        ra_sha256=ra_sha256,
    )
    return [
        f"processed_root={processed_root.as_posix()}",
        f"pl_evaluation_path={(tmp_path / 'pl').as_posix()}",
        f"pl_predictions_sha256={predictions_sha256}",
        f"pl_report_sha256={report_sha256}",
        "test_years=[2024,2025]",
        "final_odds.train_start_year=2023",
        "final_odds.place_mid_bands=[1.0]",
        "final_odds.min_hits=1",
        "final_odds.graded_shrinkage_k=2",
        "bootstrap.resamples=50",
    ]


def _invoke(output: Path, overrides: list[str], config_name: str = "measure") -> Result:
    return CliRunner().invoke(
        app,
        [
            "model",
            "backtest-betting",
            "--output",
            str(output),
            "--config-dir",
            str(CONFIGS),
            "--config-name",
            config_name,
            *[item for value in overrides for item in ("--override", value)],
        ],
    )


def test_backtest_betting_publishes_the_report_and_both_tables(tmp_path: Path) -> None:
    overrides = _inputs(tmp_path)
    output = tmp_path / "backtest"

    result = _invoke(output, overrides)

    assert result.exit_code == 0, result.stderr
    assert sorted(path.name for path in output.iterdir()) == [
        "bets.parquet",
        "races.parquet",
        "report.json",
    ]
    (summary,) = result.stdout.splitlines()
    assert summary.startswith(f"ev betting backtest: {output} graded_races=4 purchased_races=2 ")
    assert any(
        "phase=publications table=o1 year=2023" in line for line in result.stderr.splitlines()
    )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["format"] == "ev_betting_backtest"
    counts = report["counts"]
    assert counts["2024"]["no_prediction"]["unattributed"] == 1
    assert counts["2025"]["no_prediction"]["target_outcome"] == 1
    assert [counts[year]["purchased"] for year in ("2024", "2025")] == [1, 1]
    assert [counts[year]["graded_races"] for year in ("2024", "2025")] == [2, 2]
    bets = pq.read_table(output / "bets.parquet")
    races = pq.read_table(output / "races.parquet")
    assert bets.schema.equals(BETS_SCHEMA)
    assert races.schema.equals(RACES_SCHEMA)
    total = report["all_test_years"]
    assert total["stake_yen"] == sum(bets.column("stake_yen").to_pylist())
    assert total["receipt_yen"] == sum(races.column("receipt_yen").to_pylist())
    assert report["inputs"]["snapshot"]["snapshot_id"] == SNAPSHOT_ID
    assert set(report["inputs"]["snapshot"]["tables"]) == {RA_TABLE, SE_TABLE, HR_TABLE, O1_TABLE}


def test_held_reader_returns_only_target_entries_and_checks_the_hash(tmp_path: Path) -> None:
    datamart = tmp_path / "datamart"
    digest = _write_datamart(
        datamart,
        [
            {
                "race_id": HELD,
                "role": "target",
                "stage": "target_outcome",
                "reason": "x",
                "whole_race": True,
            },
            {
                "race_id": HELD,
                "role": "history",
                "stage": "history_result",
                "reason": "x",
                "whole_race": True,
            },
        ],
    )

    held = read_reference_datamart_target_holds(datamart, expected_manifest_sha256=digest)

    assert [(item["race_id"], item["role"]) for item in held] == [(HELD, "target")]
    payload = json.loads((datamart / "held_races.json").read_text(encoding="utf-8"))
    payload["held_races"][1]["stage"] = "target_pre_freeze"
    (datamart / "held_races.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="held-race file hash mismatch"):
        read_reference_datamart_target_holds(datamart, expected_manifest_sha256=digest)


def test_backtest_betting_help_and_import_do_not_load_the_backtest_modules() -> None:
    script = """
import sys
import cli.betting_backtest
# The command module alone loads no heavy library; main's other commands may.
for name in ("pyarrow", "numpy", "pandas", "hydra"):
    assert name not in sys.modules, name
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "backtest-betting", "--help"])
assert result.exit_code == 0, result.output
for name in (
    "configuration.betting_backtest",
    "models.experiments.betting_backtest",
    "models.betting.policy",
    "models.evaluation.betting_metrics",
    "models.serialization.betting_inputs",
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


@pytest.mark.parametrize("kind", ["existing", "symlink", "parentless", "processed", "pl"])
def test_backtest_betting_rejects_the_output_before_reading(tmp_path: Path, kind: str) -> None:
    overrides = _inputs(tmp_path)
    output = tmp_path / "backtest"
    if kind == "existing":
        output.mkdir()
    elif kind == "symlink":
        try:
            output.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
        except OSError:
            pytest.skip("symbolic links are not available")
    elif kind == "parentless":
        output = tmp_path / "missing" / "backtest"
    elif kind == "processed":
        output = tmp_path / "processed" / "backtest"
    else:
        output = tmp_path / "pl" / "backtest"

    with patch.object(FixedSnapshot, "__init__", side_effect=AssertionError("read")) as opened:
        result = _invoke(output, overrides)

    opened.assert_not_called()
    assert result.exit_code == 1
    assert "output" in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


def test_backtest_betting_rejects_an_output_inside_the_datamart(tmp_path: Path) -> None:
    overrides = _inputs(tmp_path)

    with patch.object(FixedSnapshot, "__init__", side_effect=AssertionError("read")) as opened:
        result = _invoke(tmp_path / "datamart" / "backtest", overrides)

    opened.assert_not_called()
    assert result.exit_code == 1
    assert "outside every input directory" in result.stderr


@pytest.mark.parametrize("name", ["pl_predictions_sha256", "pl_report_sha256"])
def test_backtest_betting_rejects_pl_files_that_differ_from_the_pins(
    tmp_path: Path, name: str
) -> None:
    overrides = [
        f"{name}={'0' * 64}" if value.startswith(f"{name}=") else value
        for value in _inputs(tmp_path)
    ]

    with patch.object(FixedSnapshot, "pin", side_effect=AssertionError("read")) as pinned:
        result = _invoke(tmp_path / "backtest", overrides)

    pinned.assert_not_called()
    assert result.exit_code == 1
    assert "SHA-256 differs" in result.stderr
    assert not (tmp_path / "backtest").exists()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ("+unknown=1", "missing or unsupported keys"),
        ("pl_report_sha256=abc", "pl_report_sha256"),
        ("test_years=[2024,2024]", "strictly increasing"),
        ("bet_types=[win,place,quinella]", "bet_types"),
        ("policy.kelly_fraction=0", "policy.kelly_fraction"),
        ("policy.unit_yen=0", "policy.unit_yen"),
        ("policy.unit_yen=50", "multiple of 100"),
        ("policy.min_expected_return=0.9", "at least 1.0"),
        ("final_odds.train_start_year=2016", "before every test year"),
        ("final_odds.place_mid_bands=[0.9]", "place_mid_bands"),
        ("final_odds.quantiles=[0.5,0.1]", "strictly increasing"),
        ("bootstrap.confidence=1.0", "bootstrap.confidence"),
    ],
)
def test_backtest_config_rejects_invalid_values(override: str, message: str) -> None:
    fixed = (
        "processed_root=processed",
        "pl_evaluation_path=pl",
        f"pl_predictions_sha256={'a' * 64}",
        f"pl_report_sha256={'b' * 64}",
    )
    with pytest.raises(ValueError, match=message):
        load_betting_backtest_config(CONFIGS, config_name="measure", overrides=(*fixed, override))


def test_measure_profile_repeats_the_fixed_adr042_place_settings() -> None:
    config = load_betting_backtest_config(
        CONFIGS,
        config_name="measure",
        overrides=(
            "processed_root=processed",
            "pl_evaluation_path=pl",
            f"pl_predictions_sha256={'a' * 64}",
            f"pl_report_sha256={'b' * 64}",
        ),
    )
    adr042 = OmegaConf.to_container(
        OmegaConf.load(ROOT / "configs/final_odds_evaluation/measure.yaml"), resolve=True
    )
    assert isinstance(adr042, dict)
    final_odds = cast(dict[str, object], config["final_odds"])
    assert final_odds == {
        "train_start_year": adr042["train_start_year"],
        "max_publication_age_seconds": adr042["max_publication_age_seconds"],
        "place_mid_bands": cast(dict[str, object], adr042["bands"])["place_mid"],
        "quantiles": adr042["quantiles"],
        "min_hits": adr042["min_hits"],
        "graded_shrinkage_k": adr042["graded_shrinkage_k"],
    }
    assert config["policy"] == {
        "min_expected_return": 1.10,
        "kelly_fraction": 0.25,
        "bankroll_yen": 100000,
        "annual_budget_yen": 100000,
        "race_budget_yen": 5000,
        "unit_yen": 100,
    }
    assert config["test_years"] == list(range(2016, 2026))


@pytest.mark.parametrize(
    ("target", "error", "exit_code", "message"),
    [
        ("data.saver.write_parquet.write_parquet", KeyboardInterrupt(), 130, "interrupted"),
        ("data.saver.write_parquet.write_parquet", RuntimeError("disk full"), 1, "disk full"),
        (
            "models.experiments.betting_backtest.run_betting_backtest",
            KeyboardInterrupt(),
            130,
            "interrupted",
        ),
    ],
)
def test_backtest_betting_failures_leave_no_output_or_staging(
    tmp_path: Path, target: str, error: BaseException, exit_code: int, message: str
) -> None:
    overrides = _inputs(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    with patch(target, side_effect=error):
        result = _invoke(tmp_path / "backtest", overrides)

    assert result.exit_code == exit_code
    assert message in result.stderr
    assert result.stdout == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_backtest_betting_rejects_an_output_inside_the_snapshot(tmp_path: Path) -> None:
    overrides = _inputs(tmp_path)
    output = tmp_path / "processed" / "snapshots" / SNAPSHOT_ID / "backtest"

    with patch.object(FixedSnapshot, "pin", side_effect=AssertionError("read")) as pinned:
        result = _invoke(output, overrides)

    pinned.assert_not_called()
    assert result.exit_code == 1
    assert "outside every input directory" in result.stderr


@pytest.mark.parametrize(
    ("config_name", "override", "message"),
    [
        ("evaluate", "processed_root=processed", "Missing mandatory value"),
        ("measure", "~policy.unit_yen", "policy has missing or unsupported keys"),
        ("measure", "~final_odds.min_hits", "final_odds has missing or unsupported keys"),
    ],
)
def test_backtest_config_rejects_missing_values_and_keys(
    config_name: str, override: str, message: str
) -> None:
    fixed = (
        "processed_root=processed",
        "pl_evaluation_path=pl",
        f"pl_predictions_sha256={'a' * 64}",
        f"pl_report_sha256={'b' * 64}",
    )
    overrides = (override,) if config_name == "evaluate" else (*fixed, override)
    with pytest.raises(Exception, match=message):
        load_betting_backtest_config(CONFIGS, config_name=config_name, overrides=overrides)


def test_held_reader_rejects_a_held_file_format_that_the_manifest_hash_covers(
    tmp_path: Path,
) -> None:
    datamart = tmp_path / "datamart"
    _write_datamart(
        datamart,
        [
            {
                "race_id": HELD,
                "role": "target",
                "stage": "target_outcome",
                "reason": "x",
                "whole_race": True,
            }
        ],
    )
    held_path = datamart / "held_races.json"
    payload = json.loads(held_path.read_text(encoding="utf-8"))
    payload["format"] = "other_held_races"
    held_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = datamart / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["held_races"]["sha256"] = hashlib.sha256(held_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="held-race format is invalid"):
        read_reference_datamart_target_holds(datamart, expected_manifest_sha256=digest)
