"""Run `model compare-pl-variants` against a pinned synthetic PL evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pytest
from typer.testing import CliRunner, Result

from configuration.pl_comparison import load_pl_comparison_config
from data.loader.file_hash import file_sha256
from data.loader.read_parquet import read_parquet
from data.saver.write_parquet import write_parquet
from main import app
from models.experiments.pl_comparison import normalize_pl_predictions
from tests.integration.test_pl_evaluation_cli import (
    YEARS,
    _write_datamart,
    _write_snapshot,
)
from tests.integration.test_pl_evaluation_cli import (
    _invoke as invoke_evaluation,
)
from tests.integration.test_pl_evaluation_cli import (
    _overrides as evaluation_overrides,
)
from tests.reference_fixtures import ROOT

CONFIGS = ROOT / "configs/pl_comparison"
_DISTANCE_COLUMN = "basic_conditions_and_weight__race_distance_m"
_PRIOR_POSITION_COLUMN = "recent_performance__past_finish_lag1"
_LOSS_METRICS = (
    "winner_log_loss",
    "multiclass_brier",
    "exacta_log_loss",
    "quinella_log_loss",
    "trifecta_log_loss",
    "trio_log_loss",
)


def _race_ids() -> list[str]:
    """Return the three fixture years' fixed six-horse race identities."""
    return [f"{year}0101010101{race + 1:02d}" for year in YEARS for race in range(30)]


def _write_start_list(
    snapshot: dict[str, object],
    race_ids: list[str],
    *,
    age_offset: int = 0,
    omit_key: tuple[str, str] | None = None,
) -> None:
    """Add the start-list columns required for residual-segment joins."""
    snapshot_path = Path(str(snapshot["snapshot_path"]))
    rows = [
        {
            "idYear": race_id[:4],
            "idMonthDay": race_id[4:8],
            "idJyoCD": race_id[8:10],
            "idKaiji": race_id[10:12],
            "idNichiji": race_id[12:14],
            "idRaceNum": race_id[14:16],
            "KettoNum": f"{horse:010d}",
            "Umaban": str(horse + 1),
            "Barei": str(3 + (horse + age_offset) % 5),
        }
        for race_id in race_ids
        for horse in range(6)
        if (race_id, f"{horse:010d}") != omit_key
    ]
    path = snapshot_path / "NL_SE_RACE_UMA.parquet"
    write_parquet(
        pa.Table.from_pylist(rows, schema=pa.schema([(name, pa.string()) for name in rows[0]])),
        path,
    )
    tables = snapshot["tables"]
    assert isinstance(tables, dict)
    tables["NL_SE_RACE_UMA"] = {"file": path.name, "sha256": file_sha256(path)}


def _write_segment_race_rows(snapshot: dict[str, object], race_ids: list[str]) -> None:
    """Set fixture tracks so all fixed track-and-distance segments have members."""
    snapshot_path = Path(str(snapshot["snapshot_path"]))
    rows = [
        {
            "idYear": race_id[:4],
            "idMonthDay": race_id[4:8],
            "idJyoCD": race_id[8:10],
            "idKaiji": race_id[10:12],
            "idNichiji": race_id[12:14],
            "idRaceNum": race_id[14:16],
            "GradeCD": "A",
            "TrackCD": "23" if race % 4 in (0, 1) else "11",
        }
        for race, race_id in enumerate(race_ids)
    ]
    path = snapshot_path / "NL_RA_RACE.parquet"
    write_parquet(
        pa.Table.from_pylist(rows, schema=pa.schema([(name, pa.string()) for name in rows[0]])),
        path,
    )
    tables = snapshot["tables"]
    assert isinstance(tables, dict)
    tables["NL_RA_RACE"] = {"file": path.name, "sha256": file_sha256(path)}


def _change_snapshot_race_track(snapshot: dict[str, object]) -> Path:
    """Change one fixed-snapshot track code without updating its recorded identity."""
    path = Path(str(snapshot["snapshot_path"])) / "NL_RA_RACE.parquet"
    table = read_parquet(path)
    tracks = table["TrackCD"].to_pylist()
    assert isinstance(tracks[0], str)
    tracks[0] = "24" if tracks[0] != "24" else "23"
    updated = table.set_column(
        table.schema.get_field_index("TrackCD"),
        "TrackCD",
        pa.array(tracks, type=pa.string()),
    )
    write_parquet(updated, path)
    return path


def _segment_feature_values(year: int, race: int, horse: int) -> dict[str, float]:
    """Return valid fixture values spanning the evaluated residual segments."""
    del year
    return {
        _DISTANCE_COLUMN: 1200.0 if race % 4 in (0, 2) else 1600.0,
        _PRIOR_POSITION_COLUMN: float(horse % 5 + 1),
    }


def _evaluation_inputs(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    """Publish one small two-variant evaluation with both raw snapshot tables pinned."""
    datamart = tmp_path / "datamart"
    processed_root = tmp_path / "processed"
    race_ids = _race_ids()
    snapshot = _write_snapshot(processed_root, race_ids)
    _write_segment_race_rows(snapshot, race_ids)
    _write_start_list(snapshot, race_ids)
    datamart_digest = _write_datamart(
        datamart,
        snapshot,
        feature_values=_segment_feature_values,
    )
    evaluation = tmp_path / "evaluation"
    result = invoke_evaluation(
        evaluation,
        evaluation_overrides(datamart, datamart_digest, processed_root),
    )
    assert result.exit_code == 0, result.output
    return evaluation, datamart, processed_root, snapshot


def _overrides(evaluation: Path, processed_root: Path, *extra: str) -> list[str]:
    """Return comparison CLI overrides that pin the generated evaluation artifacts."""
    values = [
        f"evaluation_path={evaluation.as_posix()}",
        f"pl_report_sha256={file_sha256(evaluation / 'report.json')}",
        f"pl_predictions_sha256={file_sha256(evaluation / 'predictions.parquet')}",
        f"processed_root={processed_root.as_posix()}",
        "comparisons=[{candidate:all_columns,baseline:without_market}]",
        "bootstrap.resamples=20",
        *extra,
    ]
    return [item for value in values for item in ("--override", value)]


def _invoke(output: Path, overrides: list[str], config_name: str = "compare") -> Result:
    """Invoke the comparison CLI through its registered public command."""
    return CliRunner().invoke(
        app,
        [
            "model",
            "compare-pl-variants",
            "--output",
            str(output),
            "--config-dir",
            str(CONFIGS),
            "--config-name",
            config_name,
            *overrides,
        ],
    )


def _json_object(path: Path) -> dict[str, object]:
    """Read one JSON object used as a mutable pinned fixture artifact."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json_object(path: Path, value: dict[str, object]) -> None:
    """Rewrite one fixture JSON object before its caller re-pins its digest."""
    path.write_text(json.dumps(value), encoding="utf-8")


def _object(value: object) -> dict[str, object]:
    """Return a JSON-object fixture node with an assertion for its fixed shape."""
    assert isinstance(value, dict)
    return value


def _refresh_datamart_snapshot_hash(datamart: Path, table: str, digest: str) -> str:
    """Update a fixture datamart's raw-table identity after editing that raw table."""
    manifest_path = datamart / "manifest.json"
    manifest = _json_object(manifest_path)
    snapshot = _object(manifest["snapshot"])
    tables = _object(snapshot["tables"])
    entry = _object(tables[table])
    entry["sha256"] = digest
    _write_json_object(manifest_path, manifest)
    return file_sha256(manifest_path)


def _refresh_evaluation_datamart_hash(evaluation: Path, manifest_sha256: str) -> None:
    """Update a fixture evaluation after repinning the referenced datamart manifest."""
    path = evaluation / "report.json"
    report = _json_object(path)
    _object(report["datamart"])["manifest_sha256"] = manifest_sha256
    _write_json_object(path, report)


def _recompute_evaluation_pooled_means(evaluation: Path) -> None:
    """Keep the fixture report pinned to an intentionally edited predictions artifact."""
    normalized = normalize_pl_predictions(read_parquet(evaluation / "predictions.parquet"))
    path = evaluation / "report.json"
    report = _json_object(path)
    pooled = _object(report["pooled"])
    for name, variant in normalized.variants.items():
        calibrated = _object(_object(_object(pooled[name])["all_test_races"])["calibrated"])
        for metric in _LOSS_METRICS:
            calibrated[metric] = float(getattr(variant.metrics, metric).mean())
        calibrated["stage_nll"] = [
            float(variant.metrics.stage_nll[:, index].mean()) for index in range(3)
        ]
    _write_json_object(path, report)


def _swap_first_prediction_finishes(evaluation: Path) -> None:
    """Swap two fixture outcomes while preserving valid within-race positions."""
    path = evaluation / "predictions.parquet"
    predictions = read_parquet(path)
    finishes = predictions["finish_position"].to_pylist()
    variants = predictions["variant"].to_pylist()
    race_ids = predictions["race_id"].to_pylist()
    first_race = race_ids[0]
    assert isinstance(first_race, str)
    for variant in set(variants):
        indexes = [
            index
            for index, (name, race_id) in enumerate(zip(variants, race_ids, strict=True))
            if name == variant and race_id == first_race
        ]
        assert len(indexes) >= 2
        first, second = indexes[:2]
        finishes[first], finishes[second] = finishes[second], finishes[first]
    replacement = pa.array(finishes, type=pa.int64())
    updated = predictions.set_column(
        predictions.schema.get_field_index("finish_position"), "finish_position", replacement
    )
    write_parquet(updated, path)


def _replace_first_prediction_horse_id(evaluation: Path) -> None:
    """Change one shared prediction key without changing its race probabilities."""
    path = evaluation / "predictions.parquet"
    predictions = read_parquet(path)
    horse_ids = predictions["horse_id"].to_pylist()
    race_ids = predictions["race_id"].to_pylist()
    first_race = race_ids[0]
    assert isinstance(first_race, str)
    changed = 0
    for index, (race_id, horse_id) in enumerate(zip(race_ids, horse_ids, strict=True)):
        if race_id == first_race and horse_id == "0000000000":
            horse_ids[index] = "9999999999"
            changed += 1
    assert changed == 2
    updated = predictions.set_column(
        predictions.schema.get_field_index("horse_id"),
        "horse_id",
        pa.array(horse_ids, type=pa.string()),
    )
    write_parquet(updated, path)


def test_compare_pl_variants_publishes_a_pinned_report(tmp_path: Path) -> None:
    evaluation, datamart, processed_root, _ = _evaluation_inputs(tmp_path)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in output.iterdir()) == ["report.json"]
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["format"] == "pl_variant_comparison"
    assert report["format_version"] == 1
    assert report["inputs"]["evaluation"] == {
        "path": str(evaluation.resolve()),
        "report_sha256": file_sha256(evaluation / "report.json"),
        "predictions_sha256": file_sha256(evaluation / "predictions.parquet"),
    }
    assert report["inputs"]["datamart"] == {
        "path": str(datamart.resolve()),
        "manifest_sha256": file_sha256(datamart / "manifest.json"),
    }
    snapshot_tables = report["inputs"]["snapshot"]["tables"]
    assert set(snapshot_tables) == {"NL_RA_RACE", "NL_SE_RACE_UMA"}
    snapshot_path = Path(report["inputs"]["snapshot"]["snapshot_path"])
    for _table, entry in snapshot_tables.items():
        assert entry["sha256"] == file_sha256(snapshot_path / entry["file"])
    assert report["segments"]["prior_win_margin_ge_0_3s"]["available"] is False
    dirt_inner = report["segments"]["dirt_le1400_inner"]
    assert dirt_inner["available"] is True
    assert dirt_inner["variants"]["all_columns"]["horses"] == 16
    assert dirt_inner["variants"]["all_columns"]["win"]["expected"] > 0.0
    assert report["segments"]["dirt_gt1400_outer"]["variants"]["all_columns"]["horses"] > 0
    assert report["segments"]["turf_outer"]["variants"]["all_columns"]["horses"] == 28
    assert report["segments"]["age_3"]["variants"]["all_columns"]["horses"] == 60
    comparison = report["comparisons"][0]["all_test_races"]["pooled"]
    assert comparison["race_count"] == 30
    assert isinstance(comparison["winner_log_loss"]["mean_difference"], float)
    assert result.stdout.strip() == (
        f"Compared PL variants: comparisons=1 variants=2 test_races=30 output={output}"
    )
    assert "phase=publish" in result.stderr


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("comparisons=[]", "nonempty list"),
        (
            "comparisons=[{candidate:all_columns,baseline:without_market},"
            "{candidate:all_columns,baseline:without_market}]",
            "unique",
        ),
        ("comparisons=[{candidate:all_columns,baseline:all_columns}]", "must differ"),
        ("bootstrap.resamples=0", "positive integer"),
        ("bootstrap.confidence=1.0", "between zero and one"),
    ],
)
def test_comparison_config_rejects_invalid_values(extra: str, message: str) -> None:
    base = (
        "evaluation_path=evaluation",
        "pl_report_sha256=" + "a" * 64,
        "pl_predictions_sha256=" + "b" * 64,
        "processed_root=processed",
        "comparisons=[{candidate:candidate,baseline:baseline}]",
    )

    with pytest.raises(ValueError, match=message):
        load_pl_comparison_config(CONFIGS, overrides=(*base, extra))


def test_compare_pl_variants_rejects_empty_comparisons_before_reading_inputs(
    tmp_path: Path,
) -> None:
    output = tmp_path / "comparison"
    result = _invoke(
        output,
        [
            "--override",
            f"evaluation_path={(tmp_path / 'evaluation').as_posix()}",
            "--override",
            "pl_report_sha256=" + "a" * 64,
            "--override",
            "pl_predictions_sha256=" + "b" * 64,
            "--override",
            f"processed_root={(tmp_path / 'processed').as_posix()}",
            "--override",
            "comparisons=[]",
        ],
    )

    assert result.exit_code == 1
    assert "comparisons must be a nonempty list" in result.stderr
    assert result.stdout == ""
    assert not output.exists()


def test_compare_pl_variants_rejects_invalid_input_before_reading_the_datamart_manifest(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    overrides = _overrides(
        evaluation,
        processed_root,
        "comparisons=[{candidate:missing,baseline:without_market}]",
    )

    with patch(
        "make_datamart.tables.reference.read_reference_datamart_manifest",
        side_effect=AssertionError("read"),
    ):
        result = _invoke(tmp_path / "comparison", overrides)

    assert result.exit_code == 1
    assert "no variants" in result.stderr
    assert not (tmp_path / "comparison").exists()


def test_compare_pl_variants_rejects_out_of_period_report_year_before_normalization(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    path = evaluation / "report.json"
    report = _json_object(path)
    report["test_years"] = [YEARS[0] - 1]
    _write_json_object(path, report)

    with patch(
        "models.experiments.pl_comparison.normalize_pl_predictions",
        side_effect=AssertionError("normalized"),
    ):
        result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "outside the datamart target period" in result.stderr
    assert not (tmp_path / "comparison").exists()


def test_compare_pl_variants_rejects_a_mismatched_report_sha256(tmp_path: Path) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    output = tmp_path / "comparison"

    result = _invoke(
        output,
        _overrides(evaluation, processed_root, "pl_report_sha256=" + "0" * 64),
    )

    assert result.exit_code == 1
    assert "report.json SHA-256 differs" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [("format", "unexpected_format"), ("format_version", 2)],
    ids=("format", "format_version"),
)
def test_compare_pl_variants_rejects_an_invalid_evaluation_report_format(
    tmp_path: Path, field: str, value: object
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    report_path = evaluation / "report.json"
    report = _json_object(report_path)
    report[field] = value
    _write_json_object(report_path, report)

    result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "report format is not pl_probability_evaluation v1" in result.stderr
    assert not (tmp_path / "comparison").exists()


def test_compare_pl_variants_rejects_a_mismatched_predictions_sha256(tmp_path: Path) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    output = tmp_path / "comparison"

    with patch(
        "models.experiments.pl_comparison.normalize_pl_predictions",
        side_effect=AssertionError("normalized"),
    ):
        result = _invoke(
            output,
            _overrides(evaluation, processed_root, "pl_predictions_sha256=" + "0" * 64),
        )

    assert result.exit_code == 1
    assert "predictions.parquet SHA-256 differs" in result.stderr
    assert not output.exists()


def _assert_output_inside_input_is_rejected(tmp_path: Path, parent: str) -> None:
    """Require CLI rejection when output is nested below one pinned input."""
    evaluation, datamart, processed_root, _ = _evaluation_inputs(tmp_path)
    output = {
        "evaluation": evaluation,
        "processed_root": processed_root,
        "datamart": datamart,
    }[parent] / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "output must stay outside every input directory" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_output_inside_evaluation_directory(tmp_path: Path) -> None:
    _assert_output_inside_input_is_rejected(tmp_path, "evaluation")


def test_compare_pl_variants_rejects_output_inside_processed_root(tmp_path: Path) -> None:
    _assert_output_inside_input_is_rejected(tmp_path, "processed_root")


def test_compare_pl_variants_rejects_output_inside_datamart(tmp_path: Path) -> None:
    _assert_output_inside_input_is_rejected(tmp_path, "datamart")


def test_compare_pl_variants_rejects_an_existing_output_path(tmp_path: Path) -> None:
    output = tmp_path / "comparison"
    output.mkdir()

    result = _invoke(output, [])

    assert result.exit_code == 1
    assert "output must be a new non-symbolic-link path" in result.stderr
    assert list(output.iterdir()) == []


def test_compare_pl_variants_rejects_a_snapshot_start_list_hash_mismatch(tmp_path: Path) -> None:
    evaluation, _, processed_root, snapshot = _evaluation_inputs(tmp_path)
    _write_start_list(snapshot, _race_ids(), age_offset=1)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "snapshot NL_SE_RACE_UMA SHA-256 differs from datamart manifest" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_a_snapshot_race_hash_mismatch_from_datamart(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, snapshot = _evaluation_inputs(tmp_path)
    _change_snapshot_race_track(snapshot)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "snapshot NL_RA_RACE SHA-256 differs from datamart manifest" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_a_snapshot_race_hash_mismatch_from_evaluation(
    tmp_path: Path,
) -> None:
    evaluation, datamart, processed_root, snapshot = _evaluation_inputs(tmp_path)
    race_path = _change_snapshot_race_track(snapshot)
    manifest_sha256 = _refresh_datamart_snapshot_hash(
        datamart,
        "NL_RA_RACE",
        file_sha256(race_path),
    )
    _refresh_evaluation_datamart_hash(evaluation, manifest_sha256)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "snapshot NL_RA_RACE differs from the PL evaluation's graded source" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_a_datamart_snapshot_different_from_evaluation(
    tmp_path: Path,
) -> None:
    evaluation, datamart, processed_root, _ = _evaluation_inputs(tmp_path)
    manifest_path = datamart / "manifest.json"
    manifest = _json_object(manifest_path)
    snapshot = _object(manifest["snapshot"])
    snapshot_id = snapshot["snapshot_id"]
    assert isinstance(snapshot_id, str)
    snapshot["snapshot_id"] = "0" * 32 if snapshot_id != "0" * 32 else "1" * 32
    _write_json_object(manifest_path, manifest)
    _refresh_evaluation_datamart_hash(evaluation, file_sha256(manifest_path))

    result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "datamart snapshot differs from the PL evaluation's graded source" in result.stderr
    assert not (tmp_path / "comparison").exists()


def test_compare_pl_variants_rejects_different_pooled_calibration(tmp_path: Path) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    report_path = evaluation / "report.json"
    report = _json_object(report_path)
    calibrated = _object(
        _object(_object(_object(report["pooled"])["all_columns"])["all_test_races"])["calibrated"]
    )
    winner_log_loss = calibrated["winner_log_loss"]
    assert isinstance(winner_log_loss, (int, float))
    calibrated["winner_log_loss"] = float(winner_log_loss) + 0.01
    _write_json_object(report_path, report)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "pooled calibrated winner_log_loss differs" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_predictions_with_report_test_year_mismatch(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    path = evaluation / "report.json"
    report = _json_object(path)
    report["test_years"] = list(YEARS[:-1])
    _write_json_object(path, report)
    output = tmp_path / "comparison"

    with patch(
        "models.experiments.pl_comparison.normalize_pl_predictions",
        side_effect=AssertionError("normalized"),
    ):
        result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "prediction test_years differ from the PL evaluation report" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_predictions_with_report_variant_mismatch_before_normalizing(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    report_path = evaluation / "report.json"
    report = _json_object(report_path)
    variants = report["variants"]
    assert isinstance(variants, list)
    variants.append({"name": "report_only_variant"})
    _write_json_object(report_path, report)

    with patch(
        "models.experiments.pl_comparison.normalize_pl_predictions",
        side_effect=AssertionError("normalized"),
    ):
        result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "prediction variants differ from the PL evaluation report" in result.stderr
    assert not (tmp_path / "comparison").exists()


def test_compare_pl_variants_rejects_prediction_finish_different_from_datamart(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    _swap_first_prediction_finishes(evaluation)
    _recompute_evaluation_pooled_means(evaluation)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "prediction finish_position differs from datamart" in result.stderr
    assert not output.exists()


def test_compare_pl_variants_rejects_a_prediction_row_missing_from_datamart(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    _replace_first_prediction_horse_id(evaluation)

    result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "prediction row has no matching datamart row" in result.stderr
    assert not (tmp_path / "comparison").exists()


def test_compare_pl_variants_rejects_a_missing_snapshot_start_list_row(tmp_path: Path) -> None:
    evaluation, datamart, processed_root, snapshot = _evaluation_inputs(tmp_path)
    _write_start_list(
        snapshot,
        _race_ids(),
        omit_key=(f"{YEARS[-1]}010101010101", "0000000000"),
    )
    manifest_sha256 = _refresh_datamart_snapshot_hash(
        datamart,
        "NL_SE_RACE_UMA",
        file_sha256(Path(str(snapshot["snapshot_path"])) / "NL_SE_RACE_UMA.parquet"),
    )
    _refresh_evaluation_datamart_hash(evaluation, manifest_sha256)
    output = tmp_path / "comparison"

    result = _invoke(output, _overrides(evaluation, processed_root))

    assert result.exit_code == 1
    assert "prediction row has no matching NL_SE_RACE_UMA row" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("target", "error", "exit_code", "message"),
    [
        ("data.saver.write_json.write_json", KeyboardInterrupt(), 130, "interrupted"),
        ("data.saver.write_json.write_json", RuntimeError("disk full"), 1, "disk full"),
    ],
)
def test_compare_pl_variants_publish_failures_leave_no_output_or_staging(
    tmp_path: Path, target: str, error: BaseException, exit_code: int, message: str
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    with patch(target, side_effect=error):
        result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == exit_code
    assert message in result.stderr
    assert result.stdout == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_compare_pl_variants_computation_interrupt_leaves_no_output_or_staging(
    tmp_path: Path,
) -> None:
    evaluation, _, processed_root, _ = _evaluation_inputs(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    with patch(
        "models.experiments.pl_comparison.build_pl_comparison_report",
        side_effect=KeyboardInterrupt(),
    ):
        result = _invoke(tmp_path / "comparison", _overrides(evaluation, processed_root))

    assert result.exit_code == 130
    assert "interrupted" in result.stderr
    assert result.stdout == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_compare_pl_variants_help_and_import_do_not_load_heavy_modules() -> None:
    script = """
import sys
import cli.pl_comparison
for name in ("numpy", "pyarrow", "configuration.pl_comparison", "models.experiments.pl_comparison"):
    assert name not in sys.modules, name
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "compare-pl-variants", "--help"])
assert result.exit_code == 0, result.output
for name in ("configuration.pl_comparison", "models.experiments.pl_comparison"):
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
