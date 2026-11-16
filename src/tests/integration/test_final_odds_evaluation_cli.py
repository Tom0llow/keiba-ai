"""Run `model evaluate-final-odds` against a small multi-year fixed snapshot (AC-15 to AC-18)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner, Result

from configuration.final_odds_evaluation import load_final_odds_evaluation_config
from data.loader.fixed_snapshot import FixedSnapshot
from main import app
from models.experiments.final_odds_evaluation import (
    FinalOddsEvaluationSettings,
    FinalOddsRaceSubset,
    evaluate_final_odds,
)
from models.experiments.provenance import experiment_provenance
from models.serialization.final_odds_observations import (
    HR_COLUMNS,
    HR_TABLE,
    O1_COLUMNS,
    O1_TABLE,
    O2_COLUMNS,
    O2_TABLE,
    RA_COLUMNS,
    RA_TABLE,
    build_race_observations,
)
from models.serialization.race_subsets import (
    JRA_FLAT_GRADED_STAKES_V1,
    JRA_FLAT_GRADED_STAKES_V1_DEFINITION,
)
from tests.reference_fixtures import ROOT

CONFIGS = ROOT / "configs/final_odds_evaluation"
SNAPSHOT_ID = "fixture-snapshot-v1"
YEARS = (2022, 2023, 2024, 2025)
RACES_PER_YEAR = 6
CANCELLED = "2025061505030106"


def _race_ids() -> list[str]:
    return [f"{year}0615050301{race + 1:02d}" for year in YEARS for race in range(RACES_PER_YEAR)]


def _key(race_id: str) -> dict[str, object]:
    return {
        "idYear": race_id[:4],
        "idMonthDay": race_id[4:8],
        "idJyoCD": race_id[8:10],
        "idKaiji": race_id[10:12],
        "idNichiji": race_id[12:14],
        "idRaceNum": race_id[14:16],
    }


def _index(race_id: str) -> int:
    return (int(race_id[:4]) - YEARS[0]) * RACES_PER_YEAR + int(race_id[14:16])


def _ra(race_id: str) -> dict[str, object]:
    graded = int(race_id[14:16]) % 2 == 0
    return {
        **_key(race_id),
        "headDataKubun": "9" if race_id == CANCELLED else "7",
        "headMakeDate": race_id[:8],
        "HassoTime": "1530",
        "GradeCD": "A" if graded else "",
        "TrackCD": "11",
    }


def _o1(race_id: str, clock: str, *, kubun: str = "1", scale: int = 1) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(O1_COLUMNS)
    row.update(_key(race_id), headDataKubun=kubun, headMakeDate=race_id[:8], HappyoTime=clock)
    index = _index(race_id)
    quotes = {"03": 30 + index * 3, "05": 80, "07": 150}
    places = {"03": (15, 24), "05": (20 + index % 5, 32), "07": (40, 64)}
    for i, (horse, tenths) in enumerate(quotes.items()):
        row[f"OddsTansyoInfo{i}Umaban"] = horse
        row[f"OddsTansyoInfo{i}Odds"] = f"{tenths * scale:04d}"
    for i, (horse, (low, high)) in enumerate(places.items()):
        row[f"OddsFukusyoInfo{i}Umaban"] = horse
        row[f"OddsFukusyoInfo{i}OddsLow"] = f"{low:04d}"
        row[f"OddsFukusyoInfo{i}OddsHigh"] = f"{high:04d}"
    for name in ("TotalHyosuTansyo", "TotalHyosuFukusyo", "TotalHyosuWakuren"):
        row[name] = "1000"
    return row


def _o2(race_id: str, clock: str) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(O2_COLUMNS)
    row.update(_key(race_id), headDataKubun="1", headMakeDate=race_id[:8], HappyoTime=clock)
    row["TotalHyosuUmaren"] = "1000"
    for i, (pair, tenths) in enumerate({"0305": 100 + _index(race_id) * 7, "0307": 456}.items()):
        row[f"OddsUmarenInfo{i}Kumi"] = pair
        row[f"OddsUmarenInfo{i}Odds"] = f"{tenths:06d}"
    return row


def _hr(race_id: str) -> dict[str, object]:
    index = _index(race_id)
    row: dict[str, object] = {name: "" for name in HR_COLUMNS}
    row.update(_key(race_id), headDataKubun="2", headMakeDate=race_id[:8], SyussoTosu="10")
    for name in HR_COLUMNS:
        if "Flag" in name:
            row[name] = "0"
    row.update(PayTansyo0Umaban="03", PayTansyo0Pay=f"{(30 + index * 3) * 9 + index % 4 * 7:09d}")
    for i, (horse, pay) in enumerate((("03", 170 + index % 3 * 10), ("05", 230), ("07", 510))):
        row[f"PayFukusyo{i}Umaban"] = horse
        row[f"PayFukusyo{i}Pay"] = f"{pay:09d}"
    row.update(PayUmaren0Kumi="0305", PayUmaren0Pay=f"{(100 + index * 7) * 10 - index:09d}")
    return row


def _tables() -> dict[str, tuple[tuple[str, ...], list[dict[str, object]]]]:
    race_ids = _race_ids()
    o1 = [_o1(race_id, f"{race_id[4:8]}1524") for race_id in race_ids]
    # Ignored rows: after freeze, a final-kind row, and an earlier publication.
    o1.extend(_o1(race_id, f"{race_id[4:8]}1527", scale=3) for race_id in race_ids)
    o1.extend(_o1(race_id, f"{race_id[4:8]}1524", kubun="2", scale=5) for race_id in race_ids)
    o1.extend(_o1(race_id, f"{race_id[4:8]}1510", scale=2) for race_id in race_ids)
    return {
        RA_TABLE: (RA_COLUMNS, [_ra(race_id) for race_id in race_ids]),
        HR_TABLE: (HR_COLUMNS, [_hr(race_id) for race_id in race_ids]),
        O1_TABLE: (O1_COLUMNS, o1),
        O2_TABLE: (O2_COLUMNS, [_o2(race_id, f"{race_id[4:8]}1524") for race_id in race_ids]),
    }


def _write_snapshot(processed_root: Path) -> None:
    path = processed_root / "snapshots" / SNAPSHOT_ID
    path.mkdir(parents=True)
    for table, (columns, rows) in _tables().items():
        schema = pa.schema([(name, pa.string()) for name in columns])
        projected = [{name: row.get(name) for name in columns} for row in rows]
        pq.write_table(
            pa.Table.from_pylist(projected, schema=schema),
            path / f"{table}.parquet",
            row_group_size=7,
        )


def _overrides(processed_root: Path, *extra: str) -> list[str]:
    values = [
        f"processed_root={processed_root.as_posix()}",
        f"snapshot_id={SNAPSHOT_ID}",
        "train_start_year=2022",
        "test_years=[2024,2025]",
        "min_hits=2",
        "graded_shrinkage_k=3",
        "bootstrap.resamples=50",
        *extra,
    ]
    return [item for value in values for item in ("--override", value)]


def _invoke(output: Path, overrides: list[str], config_name: str = "measure") -> Result:
    return CliRunner().invoke(
        app,
        [
            "model",
            "evaluate-final-odds",
            "--output",
            str(output),
            "--config-dir",
            str(CONFIGS),
            "--config-name",
            config_name,
            *overrides,
        ],
    )


def _direct_report(processed_root: Path, config: dict[str, object]) -> dict[str, object]:
    tables = _tables()
    by_race: dict[str, dict[str, list[dict[str, object]]]] = {}
    for table, (columns, rows) in tables.items():
        for row in rows:
            race_id = "".join(cast(str, row[name]) for name in RA_COLUMNS[:6])
            projected = {name: row.get(name) for name in columns}
            by_race.setdefault(race_id, {}).setdefault(table, []).append(projected)
    observations = [
        build_race_observations(
            race_id,
            ra_rows=by_race[race_id][RA_TABLE],
            o1_rows=by_race[race_id][O1_TABLE],
            o2_rows=by_race[race_id][O2_TABLE],
            hr_rows=by_race[race_id][HR_TABLE],
            max_publication_age_seconds=600,
        )
        for race_id in sorted(by_race)
    ]
    bands = cast(dict[str, list[float]], config["bands"])
    settings = FinalOddsEvaluationSettings(
        train_start_year=2022,
        test_years=(2024, 2025),
        bands={
            "win": tuple(bands["win"]),
            "place_low": tuple(bands["place_low"]),
            "place_mid": tuple(bands["place_mid"]),
            "quinella": tuple(bands["quinella"]),
        },
        quantiles=(0.1, 0.5, 0.9),
        min_hits=2,
        graded_shrinkage_k=3,
        bootstrap_resamples=50,
        bootstrap_seed=0,
        bootstrap_confidence=0.95,
    )
    snapshot = FixedSnapshot(processed_root, snapshot_id=SNAPSHOT_ID)
    snapshot.pin((RA_TABLE, HR_TABLE, O1_TABLE, O2_TABLE))
    manifest = snapshot.manifest()
    tables_manifest = cast(dict[str, dict[str, str]], manifest["tables"])
    graded = frozenset(race_id for race_id in by_race if int(race_id[14:16]) % 2 == 0)
    subsets = {
        JRA_FLAT_GRADED_STAKES_V1: FinalOddsRaceSubset(
            race_ids=graded,
            definition=JRA_FLAT_GRADED_STAKES_V1_DEFINITION,
            source={
                "table": RA_TABLE,
                "sha256": tables_manifest[RA_TABLE]["sha256"],
                "snapshot_id": SNAPSHOT_ID,
            },
        )
    }
    evaluation = evaluate_final_odds(
        observations,
        settings,
        race_subsets=subsets,
        config=config,
        snapshot=manifest,
        provenance=experiment_provenance(),
    )
    return cast(dict[str, object], json.loads(json.dumps(evaluation.report)))


def test_evaluate_final_odds_publishes_the_report_of_the_pure_evaluation(tmp_path: Path) -> None:
    processed_root = tmp_path / "processed"
    _write_snapshot(processed_root)
    output = tmp_path / "evaluation"

    result = _invoke(output, _overrides(processed_root))

    assert result.exit_code == 0, result.stderr
    assert sorted(path.name for path in output.iterdir()) == ["report.json"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["evaluation", "processed"]
    (summary,) = result.stdout.splitlines()
    assert summary.startswith(f"final odds evaluation: {output} races=24 hits=23/69/23 selected=")
    assert "seconds=" in summary
    stderr = result.stderr.splitlines()
    assert any("phase=publications table=o1 year=2024" in line for line in stderr)
    assert any("phase=publications table=o2 year=2025" in line for line in stderr)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    config = load_final_odds_evaluation_config(
        CONFIGS,
        config_name="measure",
        overrides=_overrides(processed_root)[1::2],
    )
    assert report == _direct_report(processed_root, config)
    assert report["counts"]["race_holds_by_reason"] == {"cancelled_race": 1}
    assert report["counts"]["table_holds_by_table_and_reason"] == {"o1": {}, "o2": {}}
    assert report["snapshot"]["snapshot_id"] == SNAPSHOT_ID
    assert set(report["snapshot"]["tables"]) == {RA_TABLE, HR_TABLE, O1_TABLE, O2_TABLE}


def test_evaluate_final_odds_help_and_import_do_not_load_the_evaluation_modules() -> None:
    script = """
import sys
import cli.final_odds_evaluation
from typer.testing import CliRunner
from main import app
result = CliRunner().invoke(app, ["model", "evaluate-final-odds", "--help"])
assert result.exit_code == 0, result.output
for name in (
    "configuration.final_odds_evaluation",
    "models.experiments.final_odds_evaluation",
    "models.market.final_odds_correction",
    "models.evaluation.final_odds_metrics",
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


@pytest.mark.parametrize("kind", ["existing", "symlink", "parentless"])
def test_evaluate_final_odds_rejects_the_output_before_reading(tmp_path: Path, kind: str) -> None:
    processed_root = tmp_path / "processed"
    _write_snapshot(processed_root)
    output = tmp_path / "evaluation"
    if kind == "existing":
        output.mkdir()
    elif kind == "symlink":
        try:
            output.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
        except OSError:
            pytest.skip("symbolic links are not available")
    else:
        output = tmp_path / "missing" / "evaluation"

    with patch.object(FixedSnapshot, "__init__", side_effect=AssertionError("read")) as opened:
        result = _invoke(output, _overrides(processed_root))

    opened.assert_not_called()
    assert result.exit_code == 1
    assert "output" in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ("+unknown=1", "missing or unsupported keys"),
        ("snapshot_id=../x", "snapshot_id"),
        ("train_start_year=2022.5", "train_start_year"),
        ("test_years=[2024,2024]", "strictly increasing"),
        ("test_years=[2004]", "after train_start_year"),
        ("max_publication_age_seconds=0", "max_publication_age_seconds"),
        ("bands.win=[0.9,2.0]", "start at 1.0"),
        ("bands.quinella=[1.0,1.0]", "strictly increasing"),
        ("~bands.place_mid", "exactly win, place_low, place_mid and quinella"),
        ("quantiles=[0.5,1.5]", "between zero and one"),
        ("quantiles=[0.5,0.1]", "strictly increasing"),
        ("min_hits=0", "min_hits"),
        ("graded_shrinkage_k=-1", "graded_shrinkage_k"),
        ("bootstrap.resamples=0", "bootstrap.resamples"),
        ("bootstrap.seed=-1", "bootstrap.seed"),
        ("bootstrap.confidence=1.0", "bootstrap.confidence"),
    ],
)
def test_final_odds_config_rejects_invalid_values(override: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_final_odds_evaluation_config(
            CONFIGS, config_name="measure", overrides=("processed_root=processed", override)
        )


def test_measure_profile_resolves_the_fixed_adr_042_values() -> None:
    config = load_final_odds_evaluation_config(
        CONFIGS, config_name="measure", overrides=("processed_root=processed",)
    )

    assert config["snapshot_id"] is None
    assert config["train_start_year"] == 2004
    assert config["test_years"] == list(range(2016, 2026))
    assert config["max_publication_age_seconds"] == 600
    assert config["min_hits"] == 100
    assert config["graded_shrinkage_k"] == 200
    assert config["quantiles"] == [0.1, 0.5, 0.9]
    assert config["bootstrap"] == {"resamples": 2000, "seed": 0, "confidence": 0.95}


def test_evaluate_final_odds_rejects_unresolved_settings_before_reading(tmp_path: Path) -> None:
    with patch.object(FixedSnapshot, "__init__", side_effect=AssertionError("read")) as opened:
        result = _invoke(tmp_path / "evaluation", _overrides(tmp_path), config_name="evaluate")

    opened.assert_not_called()
    assert result.exit_code == 1
    assert "Missing mandatory value" in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("error", "exit_code", "message"),
    [(KeyboardInterrupt(), 130, "interrupted"), (RuntimeError("disk full"), 1, "disk full")],
)
def test_evaluate_final_odds_failures_leave_no_output_or_staging(
    tmp_path: Path, error: BaseException, exit_code: int, message: str
) -> None:
    processed_root = tmp_path / "processed"
    _write_snapshot(processed_root)

    with patch("data.saver.write_json.write_json", side_effect=error):
        result = _invoke(tmp_path / "evaluation", _overrides(processed_root))

    assert result.exit_code == exit_code
    assert message in result.stderr
    assert result.stdout == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == ["processed"]


def test_evaluate_final_odds_rejects_a_snapshot_table_changed_while_reading(
    tmp_path: Path,
) -> None:
    processed_root = tmp_path / "processed"
    _write_snapshot(processed_root)
    original = FixedSnapshot.publication_reader

    def change_ra(self: FixedSnapshot, table: str, **kwargs: object) -> object:
        path = self.path / f"{RA_TABLE}.parquet"
        path.write_bytes(path.read_bytes() + b"\0")
        return original(self, table, **kwargs)  # type: ignore[arg-type]

    with patch.object(FixedSnapshot, "publication_reader", change_ra):
        result = _invoke(tmp_path / "evaluation", _overrides(processed_root))

    assert result.exit_code == 1
    assert "snapshot table changed while reading" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["processed"]
