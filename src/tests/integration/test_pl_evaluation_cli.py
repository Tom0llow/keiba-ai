"""Run `model evaluate-pl` against a small synthetic three-year reference datamart."""

from __future__ import annotations

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
from typer.testing import CliRunner, Result

from configuration.pl_evaluation import load_pl_evaluation_config
from data.loader.file_hash import file_sha256
from data.saver.write_parquet import write_parquet
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


def _codes(race_id: str) -> tuple[str | None, str]:
    """Mix qualifying and non-qualifying grade/track codes by race number."""
    number = int(race_id[14:16])
    return {0: ("E", "11"), 1: ("A", "52"), 2: (None, "11")}.get(number % 5, ("A", "11"))


def _graded(race_id: str) -> bool:
    return _codes(race_id) == ("A", "11")


def _write_snapshot(
    processed_root: Path,
    race_ids: list[str],
    *,
    omit: str | None = None,
    extra_graded: tuple[str, ...] = (),
    extra_rows: tuple[tuple[str, str | None, str], ...] = (),
) -> dict[str, object]:
    snapshot_id = "fixture-snapshot-v1"
    snapshot_path = processed_root / "snapshots" / snapshot_id
    snapshot_path.mkdir(parents=True)
    codes = {race_id: _codes(race_id) for race_id in race_ids}
    codes.update({race_id: ("A", "11") for race_id in extra_graded})
    codes.update({race_id: (grade, track) for race_id, grade, track in extra_rows})
    rows = [
        {
            "idYear": race_id[:4],
            "idMonthDay": race_id[4:8],
            "idJyoCD": race_id[8:10],
            "idKaiji": race_id[10:12],
            "idNichiji": race_id[12:14],
            "idRaceNum": race_id[14:16],
            "GradeCD": codes[race_id][0],
            "TrackCD": codes[race_id][1],
        }
        for race_id in sorted(codes)
        if race_id != omit
    ]
    schema = pa.schema([(name, pa.string()) for name in rows[0]])
    race_path = snapshot_path / "NL_RA_RACE.parquet"
    write_parquet(pa.Table.from_pylist(rows, schema=schema), race_path)
    return {
        "snapshot_id": snapshot_id,
        "snapshot_path": str(snapshot_path),
        "tables": {
            "NL_RA_RACE": {
                "file": "NL_RA_RACE.parquet",
                "sha256": file_sha256(race_path),
            }
        },
    }


def _write_datamart(path: Path, snapshot: dict[str, object]) -> str:
    """Write a valid three-year datamart with the rich fixture's columns and contract."""
    raw = rich_raw_input()
    raw["snapshot"] = snapshot
    builder, _ = datamart_from_raw(
        raw,
        registry=create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml")),
        target_start=RICH_TARGET_DAYS[0],
        target_end=RICH_TARGET_DAYS[-1],
    )
    manifest = builder.manifest(
        snapshot=snapshot,
        provenance={"fixture": True},
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
                if race == 0 and horse == 0:
                    row[MARKET_COLUMN] = None
                for group in builder.available_at_groups:
                    row[f"{group}__available_at"] = freeze
                rows.append(row)
        writer.write_year(year, rows, races)
    return writer.finish(manifest, [])


def _overrides(path: Path, digest: str, processed_root: Path, *extra: str) -> list[str]:
    values = [
        f"datamart_path={path.as_posix()}",
        f"datamart_manifest_sha256={digest}",
        f"processed_root={processed_root.as_posix()}",
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
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    # One graded test-year race exists only in the snapshot (as if the datamart held it).
    # The other snapshot-only rows must not count: a non-graded test-year race, a graded
    # race at a venue outside the datamart, a graded test-year race after the target
    # period (which ends 2026-06-30) and a graded race in a non-test year.
    held_graded = "2026010101010131"
    snapshot = _write_snapshot(
        processed_root,
        race_ids,
        extra_graded=(held_graded,),
        extra_rows=(
            ("2026010101010132", "E", "11"),
            ("2026010130010101", "A", "11"),
            ("2026070101010101", "A", "11"),
            ("2025010101010131", "A", "11"),
        ),
    )
    digest = _write_datamart(datamart, snapshot)
    output = tmp_path / "evaluation"

    result = _invoke(output, _overrides(datamart, digest, processed_root))

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
    snapshot_tables = cast(dict[str, object], snapshot["tables"])
    snapshot_race = cast(dict[str, object], snapshot_tables["NL_RA_RACE"])
    assert report["race_subsets"]["jra_flat_graded_stakes_v1"]["source"] == {
        "table": "NL_RA_RACE",
        "sha256": snapshot_race["sha256"],
        "snapshot_id": "fixture-snapshot-v1",
    }
    subset = report["race_subsets"]["jra_flat_graded_stakes_v1"]
    assert subset["definition"] == "GradeCD A, B, or C and TrackCD 10 through 24"
    assert subset["not_in_datamart_by_test_year"] == {"2026": 1}
    test_ids = [race_id for race_id in race_ids if race_id.startswith("2026")]
    graded_test_ids = {race_id for race_id in test_ids if _graded(race_id)}
    assert len(graded_test_ids) == 12
    fold_subset = report["folds"][0]["subsets"]["jra_flat_graded_stakes_v1"]
    assert fold_subset["race_count"] == len(graded_test_ids)
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
    assert all(
        row["in_jra_flat_graded_stakes"] is (row["race_id"] in graded_test_ids)
        for row in predictions.to_pylist()
    )
    assert "phase=publish" in result.stderr


def test_evaluate_pl_rejects_missing_snapshot_test_races(tmp_path: Path) -> None:
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    snapshot = _write_snapshot(processed_root, race_ids, omit=race_ids[-1])
    digest = _write_datamart(datamart, snapshot)

    # The check must run before the long, fully validated datamart read.
    with patch(
        "make_datamart.tables.reference.read_reference_datamart",
        side_effect=AssertionError("datamart was read before the snapshot check"),
    ) as full_read:
        result = _invoke(tmp_path / "evaluation", _overrides(datamart, digest, processed_root))

    full_read.assert_not_called()
    assert result.exit_code == 1
    assert "NL_RA_RACE is missing 1 datamart test races" in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "processed"]


def test_evaluate_pl_checks_test_race_files_against_the_manifest_before_reading(
    tmp_path: Path,
) -> None:
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    digest = _write_datamart(datamart, _write_snapshot(processed_root, race_ids))
    races_path = datamart / "year=2026" / "races.parquet"
    table = pq.read_table(races_path)
    write_parquet(table.slice(0, table.num_rows - 1), races_path)

    with patch(
        "make_datamart.tables.reference.read_reference_datamart",
        side_effect=AssertionError("datamart was read before the race-file check"),
    ) as full_read:
        result = _invoke(tmp_path / "evaluation", _overrides(datamart, digest, processed_root))

    full_read.assert_not_called()
    assert result.exit_code == 1
    assert "reference datamart partition file hash mismatch" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "processed"]


def test_evaluate_pl_rejects_changed_snapshot_table_before_datamart_read(
    tmp_path: Path,
) -> None:
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    snapshot = _write_snapshot(processed_root, race_ids)
    digest = _write_datamart(datamart, snapshot)
    race_path = processed_root / "snapshots" / "fixture-snapshot-v1" / "NL_RA_RACE.parquet"
    table = pq.read_table(race_path)
    grades = ["B"] + ["A"] * (table.num_rows - 1)
    write_parquet(
        table.set_column(table.schema.get_field_index("GradeCD"), "GradeCD", pa.array(grades)),
        race_path,
    )

    result = _invoke(tmp_path / "evaluation", _overrides(datamart, digest, processed_root))

    assert result.exit_code == 1
    assert "snapshot NL_RA_RACE SHA-256 differs" in result.stderr
    assert "phase=read" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "processed"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("datamart_manifest_sha256=" + "0" * 64,), "SHA-256 differs"),
        (("variants=[{name:bad,excluded_columns:[missing_column]}]",), "unknown columns"),
        (("test_years=[2027]",), "outside the datamart target period"),
        (("train_start_year=2025",), "at most test_year - 2"),
        (("train_start_year=2023",), "outside the datamart target period"),
        (("+lightgbm.objective=lambdarank",), "reserved"),
        (("+lightgbm.boosting=dart",), "gbdt"),
        ((), "leaves no feature column"),
    ],
)
def test_evaluate_pl_failures_leave_no_output_or_staging(
    tmp_path: Path, extra: tuple[str, ...], message: str
) -> None:
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    # One graded test-year race exists only in the snapshot (as if the datamart held it).
    held_graded = "2026010101010131"
    snapshot = _write_snapshot(processed_root, race_ids, extra_graded=(held_graded,))
    digest = _write_datamart(datamart, snapshot)
    output = tmp_path / "evaluation"

    if message == "leaves no feature column":
        manifest = json.loads((datamart / "manifest.json").read_text(encoding="utf-8"))
        names = ",".join(column["name"] for column in manifest["columns"])
        extra = (f"variants=[{{name:empty,excluded_columns:[{names}]}}]",)

    # Settings, fold years and variants are rejected before the full datamart read.
    with patch(
        "make_datamart.tables.reference.read_reference_datamart",
        side_effect=AssertionError("datamart was read before the settings check"),
    ) as full_read:
        result = _invoke(output, _overrides(datamart, digest, processed_root, *extra))

    full_read.assert_not_called()
    assert result.exit_code == 1
    assert message in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "processed"]


def test_evaluate_pl_rejects_existing_output_and_unresolved_settings(tmp_path: Path) -> None:
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    snapshot = _write_snapshot(processed_root, race_ids)
    digest = _write_datamart(datamart, snapshot)
    existing = tmp_path / "existing"
    existing.mkdir()

    result = _invoke(existing, _overrides(datamart, digest, processed_root))
    assert result.exit_code == 1
    assert "new non-symbolic-link path" in result.stderr
    assert list(existing.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "existing", "processed"]

    unresolved = _invoke(
        tmp_path / "out", _overrides(datamart, digest, processed_root), config_name="evaluate"
    )
    assert unresolved.exit_code == 1
    assert "Missing mandatory value" in unresolved.stderr
    assert len(unresolved.stderr.strip().splitlines()) == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "existing", "processed"]


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


_BASE = (
    "datamart_path=dm",
    "datamart_manifest_sha256=" + "a" * 64,
    "processed_root=processed",
)


def test_evaluate_pl_requires_processed_root(tmp_path: Path) -> None:
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]
    digest = _write_datamart(datamart, _write_snapshot(processed_root, race_ids))
    overrides = [
        item
        for value in _overrides(datamart, digest, processed_root)[1::2]
        if not value.startswith("processed_root=")
        for item in ("--override", value)
    ]

    result = _invoke(tmp_path / "evaluation", overrides)

    assert result.exit_code == 1
    assert "processed_root" in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert sorted(path.name for path in tmp_path.iterdir()) == ["datamart", "processed"]


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
