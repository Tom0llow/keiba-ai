"""Reference datamart: equivalence with the per-race path, leakage, persistence and CLI."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from configuration.data_paths import DataPaths
from data.loader.file_hash import file_sha256
from data.loader.fixed_snapshot import FixedSnapshot
from data.storage.snapshot_builder import SnapshotBuilder
from jra_van_retriever.acquisition.jvlink_runner import (
    JVLinkExecutionResult,
    JVLinkToSQLiteError,
)
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkProfile, RaceDayOddsProfile
from jra_van_retriever.workflows.race_day_odds import RaceDayOddsRetriever
from main import app
from make_datamart.tables.reference import (
    ReferenceDatamartWriter,
    read_reference_datamart,
    read_reference_datamart_label_usable_through,
    read_reference_datamart_manifest,
    read_reference_prediction_features,
)
from make_features import market_characteristics, opponent_pagerank
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import FeatureRegistry, create_feature_registry
from make_features.contracts.observations import Coverage, ObservationInput, ReferenceEvidence
from make_features.generation.chronological import (
    ChronologicalHistory,
    ChronologicalInvariantError,
    SharedCalculationContext,
    shared_context,
)
from make_features.real_market import JST, canonical_hash, publication
from make_features.reference_raw import (
    CARD_RA_COLUMNS,
    CARD_SE_COLUMNS,
    HC_COLUMNS,
    HISTORY_RA_COLUMNS,
    HISTORY_SE_COLUMNS,
    MARKET_O1_COLUMNS,
    MARKET_O2_COLUMNS,
    WC_COLUMNS,
    result_boundary,
)
from make_features.reference_snapshot import CARD_MAPPING_MISMATCH, reference_pedigree
from models.dataset.calculated import closed_numeric_columns
from models.serialization.reference import prepare_reference_payload
from models.serialization.reference_datamart import (
    MARKET_NOT_OBSERVED_AFTER_FREEZE,
    PreparedTargets,
    ReferenceDatamartBuilder,
    ReferenceYearOutput,
    label_free_target_cards,
)
from tests.reference_fixtures import (
    RICH_TARGET_DAYS,
    ROOT,
    add_post_freeze_markets,
    datamart_from_raw,
    day_markets,
    markets,
    parquet_snapshot,
    pre_race,
    prepared_from_raw,
    race_rows,
    rich_raw_input,
)

START, END = RICH_TARGET_DAYS[0], RICH_TARGET_DAYS[-1]
Row = dict[str, object]


def _registry() -> FeatureRegistry:
    return create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml"))


def _build(
    raw: dict[str, object], *, end: date = END
) -> tuple[ReferenceDatamartBuilder, list[ReferenceYearOutput]]:
    return datamart_from_raw(raw, registry=_registry(), target_start=START, target_end=end)


def _rows(outputs: list[ReferenceYearOutput]) -> dict[tuple[str, str], Row]:
    return {
        (cast(str, row["race_id"]), cast(str, row["horse_id"])): row
        for output in outputs
        for row in output.rows
    }


def _features(row: Row, builder: ReferenceDatamartBuilder) -> dict[str, object]:
    return {column.name: row[column.name] for column in builder.columns}


def _race(day: date, number: str) -> str:
    return f"{day:%Y%m%d}010101{number}"


def _se(raw: dict[str, object], race_id: str) -> list[Row]:
    tables = cast(dict[str, list[Row]], raw["tables"])
    seen: dict[int, Row] = {}
    for name in ("history_se", "label_se"):
        for row in tables[name]:
            if "".join(cast(str, row[k]) for k in ("idYear", "idMonthDay")) == race_id[:8] and (
                cast(str, row["idRaceNum"]) == race_id[-2:]
            ):
                seen[id(row)] = row
    return list(seen.values())


def _reverse_places(raw: dict[str, object], race_id: str) -> None:
    rows = _se(raw, race_id)
    places = [row["KakuteiJyuni"] for row in rows]
    times = [row["Time"] for row in rows]
    for row, place, clock in zip(rows, reversed(places), reversed(times), strict=True):
        row["KakuteiJyuni"] = place
        row["Time"] = clock


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"metric": "condition_time_advantage", "metric_direction": "higher"},
        {"graph_half_life_days": 20.0},
        {"condition_window_order": "window_then_filter", "pedigree_include_self": True},
        {"condition_keys": ["surface", "distance_m", "going"]},
    ],
)
def test_chronological_datamart_equals_the_per_race_reference_path_for_every_column(
    settings: dict[str, object],
) -> None:
    raw = rich_raw_input(settings=settings)
    _, outputs = _build(raw)
    columns = closed_numeric_columns(cast(dict[str, object], raw["calculation_settings"]))
    expected = prepare_reference_payload(
        raw, registry=_registry(), selected_columns=[column.name for column in columns]
    )
    records = {
        (cast(str, row["race_id"]), cast(str, row["horse_id"])): row
        for row in cast(list[Row], expected["records"])
    }
    actual = _rows(outputs)
    assert set(actual) == set(records)
    assert len(actual) == 20
    for key, row in actual.items():
        reference = records[key]
        features = cast(dict[str, object], reference["features"])
        available = cast(dict[str, str], reference["available_at"])
        for column in columns:
            value = features[column.name]
            if isinstance(value, float) and math.isnan(value):
                value = None
            assert row[column.name] == value, (key, column.name)
            available_at = cast(datetime, row[f"{column.group}__available_at"])
            assert available_at.isoformat() == available[column.name]
        assert row["finish_position"] == reference["finish_position"]
    held = {
        (item["race_id"], item["reason"])
        for output in outputs
        for item in output.held
        if item["role"] == "target"
    }
    assert held == {
        (item["race_id"], item["reason"])
        for item in cast(list[dict[str, object]], expected["held_races"])
        if item["role"] == "target"
    }
    if not settings:
        assert all(any(row[c.name] is not None for row in actual.values()) for c in columns)


def test_results_enter_features_only_after_their_declared_use_boundary() -> None:
    baseline_builder, baseline = _build(rich_raw_input())
    before = _rows(baseline)
    raw = rich_raw_input()
    first = _race(RICH_TARGET_DAYS[0], "09")
    _reverse_places(raw, first)
    _, changed = _build(raw)
    after = _rows(changed)
    for (race_id, horse), row in after.items():
        unchanged = race_id[:8] != f"{RICH_TARGET_DAYS[2]:%Y%m%d}"
        same = _features(row, baseline_builder) == _features(
            before[(race_id, horse)], baseline_builder
        )
        assert same is unchanged or race_id == first, (race_id, horse)
    assert any(
        after[key]["finish_position"] != before[key]["finish_position"]
        for key in after
        if key[0] == first
    )
    # The 2026-12-19 result becomes usable at 2026-12-27 00:00, exactly eight days later.
    boundary = rich_raw_input()
    _reverse_places(boundary, _race(date(2026, 12, 19), "11"))
    _, positive = _build(boundary)
    moved = _rows(positive)
    target = _race(RICH_TARGET_DAYS[1], "09")
    assert any(
        _features(moved[key], baseline_builder) != _features(before[key], baseline_builder)
        for key in moved
        if key[0] == target
    )
    assert all(
        moved[key] == before[key] for key in moved if key[0][:8] == f"{RICH_TARGET_DAYS[0]:%Y%m%d}"
    )


def test_target_outcomes_post_freeze_markets_and_same_day_workouts_never_change_features() -> None:
    baseline_builder, baseline = _build(rich_raw_input())
    before = _rows(baseline)
    raw = rich_raw_input()
    last = _race(RICH_TARGET_DAYS[2], "09")
    tables = cast(dict[str, list[Row]], raw["tables"])
    for row in _se(raw, last):
        row.update(Time="1599", TimeDiff="+099", BaTaijyu="520", Jyuni4c="09")
    _reverse_places(raw, last)
    for row in tables["label_ra"]:
        if row["idMonthDay"] == f"{RICH_TARGET_DAYS[2]:%m%d}" and row["idRaceNum"] == "09":
            row.update(TenkoBabaSibaBabaCD="4", LapTime0="999")
    late = dict(next(row for row in tables["o1"] if row["idMonthDay"] == "0103"))
    late.update(HappyoTime="01031458", OddsTansyoInfo0Odds="9990")
    other = dict(late, HappyoTime="01031455", headDataKubun="2")
    tables["o1"].extend((late, other))
    tables["hc"] = [row for row in tables["hc"] if row["ChokyoTime"] != "0500"]
    builder, changed = _build(raw)
    after = _rows(changed)
    assert {key: _features(row, builder) for key, row in after.items()} == {
        key: _features(row, baseline_builder) for key, row in before.items()
    }
    assert any(after[key]["finish_position"] != before[key]["finish_position"] for key in after)


def test_a_new_publication_inside_the_freeze_window_changes_only_market_columns() -> None:
    builder, baseline = _build(rich_raw_input())
    before = _rows(baseline)
    raw = rich_raw_input()
    tables = cast(dict[str, list[Row]], raw["tables"])
    for name in ("o1", "o2"):
        latest = next(
            row
            for row in tables[name]
            if (row["idMonthDay"], row["idRaceNum"], row["HappyoTime"])
            == ("0103", "09", "01031454")
        )
        newer = dict(latest, HappyoTime="01031455")
        if name == "o1":
            newer["OddsTansyoInfo0Odds"] = "0123"
        tables[name].append(newer)
    _, outputs = _build(raw)
    after = _rows(outputs)
    target = _race(RICH_TARGET_DAYS[2], "09")
    market = {c.name for c in builder.columns if c.group == "market_characteristics"}
    for key, row in after.items():
        changed = {name for name in _features(row, builder) if row[name] != before[key][name]}
        assert changed <= (market if key[0] == target else set()), (key, changed)
    assert any(after[key] != before[key] for key in after if key[0] == target)


def test_rows_do_not_depend_on_later_targets_or_on_unordered_table_rows() -> None:
    _, full = _build(rich_raw_input())
    _, short = _build(rich_raw_input(), end=RICH_TARGET_DAYS[1])
    complete, prefix = _rows(full), _rows(short)
    assert prefix
    assert all(complete[key] == row for key, row in prefix.items())
    shuffled = rich_raw_input()
    tables = cast(dict[str, list[Row]], shuffled["tables"])
    # Workout rows are excluded: their physical order is part of the per-race summation order.
    for name in ("history_ra", "history_se", "label_ra", "label_se", "o1", "o2", "um"):
        tables[name].reverse()
    _, reordered = _build(shuffled)
    assert _rows(reordered) == complete


def test_calculator_value_errors_hold_one_race_and_leave_other_rows_unchanged() -> None:
    builder, baseline = _build(rich_raw_input())
    before = _rows(baseline)
    raw = rich_raw_input()
    tables = cast(dict[str, list[Row]], raw["tables"])
    stale = _race(RICH_TARGET_DAYS[0], "10")
    # Moving the first publication to 15:00 leaves the 15:15 anchor with a 15-minute-old quote.
    for name in ("o1", "o2"):
        for row in tables[name]:
            if (row["idMonthDay"], row["idRaceNum"], row["HappyoTime"]) == (
                "1220",
                "10",
                "12201514",
            ):
                row["HappyoTime"] = "12201500"

    _, outputs = _build(raw)
    held = [item for output in outputs for item in output.held if item["race_id"] == stale]
    assert [(item["stage"], item["role"]) for item in held] == [("calculation", "target")]
    assert "market_characteristics" in cast(str, held[0]["reason"])
    after = _rows(outputs)
    assert all(key[0] != stale for key in after)
    assert all(after[key] == before[key] for key in after)
    columns = [column.name for column in builder.columns]
    with pytest.raises(ValueError, match="maximum age"):
        prepare_reference_payload(raw, registry=_registry(), selected_columns=columns)


def test_conflicting_market_anchors_hold_the_race_instead_of_failing_the_build() -> None:
    _, baseline = _build(rich_raw_input())
    before = _rows(baseline)
    raw = rich_raw_input()
    tables = cast(dict[str, list[Row]], raw["tables"])
    shared = _race(RICH_TARGET_DAYS[0], "10")
    # Without the 15:24 win quote both anchors resolve to the 15:14 O1 publication while the
    # quinella quotes still differ, so the two market observations conflict.
    tables["o1"] = [
        row
        for row in tables["o1"]
        if (row["idMonthDay"], row["idRaceNum"], row["HappyoTime"]) != ("1220", "10", "12201524")
    ]
    _, outputs = _build(raw)
    held = [item for output in outputs for item in output.held if item["race_id"] == shared]
    assert [(item["stage"], item["role"]) for item in held] == [("target_pre_freeze", "target")]
    assert "conflicting source version" in cast(str, held[0]["reason"])
    after = _rows(outputs)
    assert all(key[0] != shared for key in after)
    assert all(after[key] == before[key] for key in after)
    columns = [
        column.name
        for column in closed_numeric_columns(cast(dict[str, object], raw["calculation_settings"]))
    ]
    with pytest.raises(ValueError, match="conflicting source version"):
        prepare_reference_payload(raw, registry=_registry(), selected_columns=columns)


def test_invariant_and_unexpected_errors_during_calculation_fail_the_whole_build() -> None:
    def broken_baseline(*args: object, **kwargs: object) -> object:
        raise ChronologicalInvariantError("baseline prefix crosses its start date")

    with (
        patch.object(ChronologicalHistory, "baseline_statistics", broken_baseline),
        pytest.raises(ChronologicalInvariantError),
    ):
        _build(rich_raw_input())

    def unexpected(*args: object, **kwargs: object) -> object:
        raise RuntimeError("unexpected")

    with (
        patch.object(SharedCalculationContext, "population_prior", unexpected),
        pytest.raises(RuntimeError),
    ):
        _build(rich_raw_input())


def test_card_evidence_usable_after_freeze_fails_the_whole_build() -> None:
    original = shared_context

    def late_card(source: ObservationInput, **kwargs: object) -> object:
        evidence = source.card.evidence
        assert isinstance(evidence, ReferenceEvidence)
        shifted = replace(evidence, usable_after=source.freeze_at + timedelta(microseconds=1))
        return original(replace(source, card=replace(source.card, evidence=shifted)), **kwargs)  # type: ignore[arg-type]

    with (
        patch("models.serialization.reference_datamart.shared_context", late_card),
        pytest.raises(ChronologicalInvariantError, match="card"),
    ):
        _build(rich_raw_input())


def test_a_date_shared_pagerank_failure_holds_every_target_of_that_date() -> None:
    raw = rich_raw_input(settings={"graph_max_iterations": 1})
    _, outputs = _build(raw)
    held = [item for output in outputs for item in output.held if item["role"] == "target"]
    assert not [row for output in outputs for row in output.rows]
    calculation = [item for item in held if item["stage"] == "calculation"]
    assert len(calculation) == 5
    assert all(
        "opponent_pagerank: PageRank did not converge" in cast(str, item["reason"])
        for item in calculation
    )


def _write(tmp_path: Path) -> tuple[Path, str, ReferenceDatamartBuilder]:
    builder, outputs = _build(rich_raw_input())
    path = tmp_path / "datamart"
    path.mkdir()
    writer = ReferenceDatamartWriter(
        path,
        columns=builder.columns,
        available_at_groups=builder.available_at_groups,
        contract=builder.contract.as_metadata(),
    )
    held: list[dict[str, object]] = []
    for output in outputs:
        held.extend(output.held)
        if output.year in builder.target_years():
            writer.write_year(output.year, output.rows, output.races)
    manifest = builder.manifest(
        snapshot=cast(dict[str, object], rich_raw_input()["snapshot"]),
        provenance={"fixture": True},
        preparation_config={"fixture": True},
    )
    return path, writer.finish(manifest, held), builder


def test_written_datamart_round_trips_with_its_manifest_identity(tmp_path: Path) -> None:
    path, digest, builder = _write(tmp_path)
    loaded = read_reference_datamart(
        path, expected_columns=builder.columns, expected_manifest_sha256=digest
    )
    assert loaded.manifest_sha256 == digest == file_sha256(path / "manifest.json")
    assert loaded.rows.num_rows == 20
    assert loaded.races.num_rows == 5
    assert sorted(p.name for p in path.iterdir()) == [
        "held_races.json",
        "manifest.json",
        "year=2026",
        "year=2027",
    ]
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["held_races"]["by_stage"] == {"history_result": 2, "target_outcome": 1}
    with pytest.raises(ValueError, match="expected identity"):
        read_reference_datamart(
            path, expected_columns=builder.columns, expected_manifest_sha256="0" * 64
        )


def _rewrite_rows(path: Path, file: str, change: object) -> None:
    """Rewrite one Parquet file and every hash that covers it, so only meaning checks remain."""
    target = path / file
    table = pq.read_table(target)
    rows = table.to_pylist()
    cast(Callable[[list[Row]], None], change)(rows)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), target)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["partitions"]:
        for kind in ("rows", "races"):
            if entry[f"{kind}_file"] == file:
                entry[f"{kind}_sha256"] = file_sha256(target)
                entry["row_count" if kind == "rows" else "race_count"] = len(rows)
                if kind == "races":
                    freezes = [cast(datetime, row["freeze_at"]) for row in rows]
                    entry["first_freeze_at"] = min(freezes).isoformat()
                    entry["last_freeze_at"] = max(freezes).isoformat()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _shift(name: str, seconds: int) -> Callable[[list[Row]], None]:
    def change(rows: list[Row]) -> None:
        rows[0][name] = cast(datetime, rows[0][name]) + timedelta(seconds=seconds)

    return change


def _drop_last_place(rows: list[Row]) -> None:
    race = rows[0]["race_id"]
    field = [index for index, row in enumerate(rows) if row["race_id"] == race]
    rows.pop(max(field, key=lambda index: cast(int, rows[index]["finish_position"])))


def _without_delay(rows: list[Row]) -> None:
    rows[0]["result_delay_days"] = 0
    rows[0]["label_usable_after"] = result_boundary(
        cast(datetime, rows[0]["scheduled_start_at"]), 0
    )


@pytest.mark.parametrize(
    ("file", "change", "message"),
    [
        (
            "year=2026/part-0.parquet",
            _shift("market_characteristics__available_at", 1),
            "time boundary",
        ),
        ("year=2026/part-0.parquet", _shift("freeze_at", -60), "time boundary"),
        ("year=2026/races.parquet", _shift("freeze_at", -60), "freeze boundary"),
        ("year=2026/races.parquet", _shift("label_usable_after", 1), "label-use boundary"),
        ("year=2026/races.parquet", _shift("history_usable_through", 10**7), "history crosses"),
        ("year=2026/part-0.parquet", lambda rows: rows.insert(1, dict(rows[0])), "duplicated"),
        ("year=2026/part-0.parquet", _drop_last_place, "differ from its field size"),
        ("year=2026/races.parquet", _without_delay, "label-use boundary"),
        (
            "year=2026/part-0.parquet",
            lambda rows: rows[0].update(finish_position=9),
            "noncontiguous",
        ),
    ],
)
def test_reader_rejects_meaning_changes_even_when_every_hash_is_recomputed(
    tmp_path: Path, file: str, change: object, message: str
) -> None:
    path, _, builder = _write(tmp_path)
    _rewrite_rows(path, file, change)
    with pytest.raises(ValueError, match=message):
        read_reference_datamart(path, expected_columns=builder.columns)


@pytest.mark.parametrize(
    "file", ["year=2026/part-0.parquet", "year=2027/races.parquet", "held_races.json"]
)
def test_reader_rejects_changed_bytes_and_manifest_contract_changes(
    tmp_path: Path, file: str
) -> None:
    path, _, builder = _write(tmp_path)
    target = path / file
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        read_reference_datamart(path, expected_columns=builder.columns)
    (tmp_path / "second").mkdir()
    path, _, builder = _write(tmp_path / "second")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, value in (("format_version", 2), ("verification", "recomputed"), ("extra", 1)):
        changed = dict(manifest)
        changed[key] = value
        manifest_path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match=r"format|fields"):
            read_reference_datamart(path, expected_columns=builder.columns)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="columns differ"):
        read_reference_datamart(path, expected_columns=builder.columns[:-1])
    manifest["contract"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="contract"):
        read_reference_datamart(path, expected_columns=builder.columns)


def test_reader_rejects_a_changed_contract_even_with_its_hash_recomputed(tmp_path: Path) -> None:
    path, _, builder = _write(tmp_path)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    settings = manifest["contract"]["settings"]
    settings["parameters"]["calculation"]["days_window"] += 1
    canonical = json.dumps(
        settings, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    manifest["contract"]["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="schema or metadata differs"):
        read_reference_datamart(path, expected_columns=builder.columns)


def _cli(processed: Path, output: Path) -> list[str]:
    return [
        "datamart",
        "build-reference",
        "--output",
        str(output),
        "--config-dir",
        str(ROOT / "configs/reference_datamart"),
        "--config-name",
        "measure",
        "--features-config",
        str(ROOT / "configs/features.toml"),
        "--override",
        f"processed_root='{processed.as_posix()}'",
        "--override",
        "snapshot_id=fixture-v1",
        "--override",
        f"target_start={START.isoformat()}",
        "--override",
        f"target_end={END.isoformat()}",
        "--override",
        "calculation_settings.history_start=2026-11-01",
    ]


def test_cli_reads_the_snapshot_by_year_and_publishes_the_same_rows(tmp_path: Path) -> None:
    raw = rich_raw_input()
    processed = tmp_path / "processed"
    parquet_snapshot(processed, raw)
    output = tmp_path / "reference-datamart"
    result = CliRunner().invoke(app, _cli(processed, output))
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("Built reference datamart: years=2 races=5 rows=20 held=3 ")
    assert "phase=year year=2026" in result.stderr
    assert "phase=publish" in result.stderr
    builder, outputs = _build(raw)
    loaded = read_reference_datamart(output, expected_columns=builder.columns)
    expected = _rows(outputs)
    for row in loaded.rows.to_pylist():
        reference = expected[(row["race_id"], row["horse_id"])]
        assert _features(row, builder) == _features(reference, builder)
    assert [p.name for p in tmp_path.iterdir() if ".staging-" in p.name] == []


def test_cli_rejects_unsafe_outputs_without_writing(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    parquet_snapshot(processed, rich_raw_input())
    existing = tmp_path / "existing"
    existing.mkdir()
    for output in (existing, processed / "inside", tmp_path / "missing" / "datamart"):
        result = CliRunner().invoke(app, _cli(processed, output))
        assert result.exit_code == 1
        assert "datamart build-reference failed" in result.stderr
    assert not (processed / "inside").exists()
    assert not (tmp_path / "missing").exists()


def test_cli_rejects_a_symbolic_link_output(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    parquet_snapshot(processed, rich_raw_input())
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links cannot be created in this environment")
    result = CliRunner().invoke(app, _cli(processed, link))
    assert result.exit_code == 1
    assert "non-symbolic-link" in result.stderr
    assert not (tmp_path / "missing-target").exists()


@pytest.mark.parametrize(
    ("error", "code"),
    [(ValueError("boom"), 1), (RuntimeError("unexpected"), 1), (KeyboardInterrupt(), 130)],
)
def test_cli_failures_leave_neither_output_nor_staging(
    tmp_path: Path, error: BaseException, code: int
) -> None:
    processed = tmp_path / "processed"
    parquet_snapshot(processed, rich_raw_input())
    output = tmp_path / "reference-datamart"
    original = ReferenceDatamartBuilder.add_year

    def fail_in_target_year(self: ReferenceDatamartBuilder, year: int, **kwargs: object) -> object:
        if year == END.year:
            raise error
        return original(self, year, **kwargs)  # type: ignore[arg-type]

    with patch.object(ReferenceDatamartBuilder, "add_year", fail_in_target_year):
        result = CliRunner().invoke(app, _cli(processed, output))
    assert result.exit_code == code
    if code == 1:
        assert "datamart build-reference failed" in result.stderr
    assert not output.exists()
    assert [p.name for p in tmp_path.iterdir() if ".staging-" in p.name] == []


# ADR-036: label-free features for races that have no result yet.

RACE_COLUMNS = ("field_size", "horse_mapping_sha256", "history_usable_through")
CARD_COLUMNS = frozenset((*CARD_RA_COLUMNS, *CARD_SE_COLUMNS))


def _label_free(
    raw: dict[str, object], day: date
) -> tuple[ReferenceDatamartBuilder, list[ReferenceYearOutput]]:
    return datamart_from_raw(
        raw, registry=_registry(), target_start=day, target_end=day, labeled=False
    )


def _races(outputs: list[ReferenceYearOutput]) -> dict[str, Row]:
    return {cast(str, race["race_id"]): race for output in outputs for race in output.races}


def _target_holds(outputs: list[ReferenceYearOutput]) -> dict[str, tuple[str, str]]:
    return {
        cast(str, item["race_id"]): (cast(str, item["stage"]), cast(str, item["reason"]))
        for output in outputs
        for item in output.held
        if item["role"] == "target"
    }


def _history_holds(outputs: list[ReferenceYearOutput]) -> dict[str, tuple[str, str]]:
    return {
        cast(str, item["race_id"]): (cast(str, item["stage"]), cast(str, item["reason"]))
        for output in outputs
        for item in output.held
        if item["role"] == "history"
    }


def _comparable(row: Row, builder: ReferenceDatamartBuilder) -> dict[str, object]:
    groups = [f"{name}__available_at" for name in builder.available_at_groups]
    keys = ["race_id", "horse_id", "scheduled_start_at", "freeze_at", *groups]
    return {**{key: row[key] for key in keys}, **_features(row, builder)}


def _race_id(row: Row) -> str:
    return "".join(
        cast(str, row[k])
        for k in ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
    )


def _add_late_horse_race(raw: dict[str, object]) -> str:
    """Add a last-date race whose runners appear nowhere else, one with ambiguous UM rows."""
    tables = cast(dict[str, list[Row]], raw["tables"])
    day = RICH_TARGET_DAYS[-1]
    ra, se = race_rows(day, offset=10, race_number="12")
    ra["HassoTime"] = "1600"
    tables["label_ra"].append(ra)
    tables["label_se"].extend(se)
    for clock, total in (("1544", 1000), ("1554", 2000), ("1558", 3000)):
        o1, o2 = markets(day, clock=clock, total=total, race_number="12")
        tables["o1"].append(o1)
        tables["o2"].append(o2)
    horse = cast(str, se[0]["KettoNum"])
    for sire in ("SIREX", "SIREY"):
        tables["um"].append(
            {
                "KettoNum": horse,
                "headMakeDate": "20261031",
                "Ketto3Info0HansyokuNum": sire,
                "Ketto3Info4HansyokuNum": "DAMX",
            }
        )
    return _race(day, "12")


def _rich_with_late_markets() -> tuple[dict[str, object], str]:
    raw = rich_raw_input()
    add_post_freeze_markets(raw)
    late = _add_late_horse_race(raw)
    tables = cast(dict[str, list[Row]], raw["tables"])
    _add_same_year_late_horse(tables)
    # A session on the day before each target date is the workout window's last day.
    for day in RICH_TARGET_DAYS:
        for kind in ("hc", "wc"):
            tables[kind].append(_workout(kind, "2020100002", day - timedelta(days=1)))
    return raw, late


def _add_same_year_late_horse(tables: dict[str, list[Row]]) -> None:
    """Add a 2026-12-28 history race whose new runner has ambiguous UM rows.

    A labeled build over 2026-12-20..2027-01-03 registers that horse while reading 2026,
    before it calculates the 2026-12-20 and 2026-12-27 targets; a label-free build for
    those dates never reads it. Its result becomes usable at 2027-01-05 00:00 JST (eight
    days later), after every target date, so no target sees the race itself. Inside the
    labeled period it is also a target without any O1, held outside RICH_TARGET_DAYS.
    """
    ra, se = race_rows(date(2026, 12, 28), offset=20, race_number="11")
    tables["history_ra"].append(ra)
    tables["history_se"].extend(se)
    horse = cast(str, se[0]["KettoNum"])
    for sire in ("SIREP", "SIREQ"):
        tables["um"].append(
            {
                "KettoNum": horse,
                "headMakeDate": "20261031",
                "Ketto3Info0HansyokuNum": sire,
                "Ketto3Info4HansyokuNum": "DAMP",
            }
        )


def _workout(kind: str, horse: str, day: date) -> Row:
    row: Row = dict.fromkeys(HC_COLUMNS if kind == "hc" else WC_COLUMNS)
    row.update(
        headDataKubun="1",
        headMakeDate="20270110",
        TresenKubun="0",
        ChokyoDate=day.strftime("%Y%m%d"),
        ChokyoTime="0700",
        KettoNum=horse,
    )
    if kind == "wc":
        row.update(Course="0", BabaAround="0")
    for section in range(1, 5):
        row[f"LapTime{section}"] = "117"
    return row


def test_label_free_rows_equal_the_labeled_datamart_for_every_target_date() -> None:
    raw, late = _rich_with_late_markets()
    labeled_builder, labeled = _build(raw)
    rows, races, holds = _rows(labeled), _races(labeled), _target_holds(labeled)
    assert holds[late][0] == "target_pre_freeze"
    outcome = {r for r, (stage, _) in holds.items() if stage == "target_outcome"}
    assert outcome
    compared = 0
    for day in RICH_TARGET_DAYS:
        builder, outputs = _label_free(raw, day)
        assert builder.columns == labeled_builder.columns
        free_rows, free_races = _rows(outputs), _races(outputs)
        prefix = f"{day:%Y%m%d}"
        for race_id, race in free_races.items():
            assert not {"label_usable_after", "result_delay_days", "label_raw_sha256"} & set(race)
            if race_id not in races:
                continue
            for column in RACE_COLUMNS:
                assert race[column] == races[race_id][column], (race_id, column)
        for key, row in free_rows.items():
            assert "finish_position" not in row
            if key[0] in races:
                assert _comparable(row, builder) == _comparable(rows[key], labeled_builder), key
                compared += 1
        assert {key for key in free_rows if key[0] in races} == {
            key for key in rows if key[0].startswith(prefix)
        }
        ordered = [
            (row["race_id"], row["horse_id"])
            for output in outputs
            for row in output.rows
            if row["race_id"] in races
        ]
        assert ordered == [
            (row["race_id"], row["horse_id"])
            for output in labeled
            for row in output.rows
            if cast(str, row["race_id"]).startswith(prefix)
        ]
        # Labeled races plus outcome holds equal the label-free races plus the extra
        # races the label-free build held at calculation instead; other holds agree.
        free_holds = _target_holds(outputs)
        day_outcome = {r for r in outcome if r.startswith(prefix)}
        extra_calc = {
            r for r, (stage, _) in free_holds.items() if stage == "calculation" and r in day_outcome
        }
        day_races = {r for r in races if r.startswith(prefix)}
        assert day_races | day_outcome == set(free_races) | extra_calc
        assert {r: h for r, h in free_holds.items() if r not in day_outcome} == {
            r: h for r, h in holds.items() if r.startswith(prefix) and r not in day_outcome
        }
        assert _history_holds(outputs) == {
            r: h for r, h in _history_holds(labeled).items() if r[:8] < prefix
        }
    assert compared == len(rows)


def test_a_label_free_builder_covers_exactly_one_target_date() -> None:
    with pytest.raises(ValueError, match="exactly one target date"):
        datamart_from_raw(
            rich_raw_input(),
            registry=_registry(),
            target_start=START,
            target_end=END,
            labeled=False,
        )


# ADR-037: prepare the date once, then calculate each race from its own market.


def _one_shot(
    raw: dict[str, object], day: date
) -> tuple[dict[str, list[Row]], dict[str, Row], dict[str, Row]]:
    _, outputs = _label_free(raw, day)
    rows: dict[str, list[Row]] = {}
    for output in outputs:
        for row in output.rows:
            rows.setdefault(cast(str, row["race_id"]), []).append(row)
    holds = {
        cast(str, item["race_id"]): item
        for output in outputs
        for item in output.held
        if item["role"] == "target"
    }
    return rows, _races(outputs), holds


def _race_markets(raw: dict[str, object], day: date, race_id: str) -> tuple[list[Row], list[Row]]:
    o1, o2 = day_markets(raw)(day)
    return (
        [row for row in o1 if _race_id(row) == race_id],
        [row for row in o2 if _race_id(row) == race_id],
    )


@pytest.mark.parametrize("day", RICH_TARGET_DAYS)
@pytest.mark.parametrize("order", ["reversed", "last_only"])
def test_prepared_races_in_any_order_or_subset_equal_the_one_shot_build(
    day: date, order: str
) -> None:
    raw, late = _rich_with_late_markets()
    rows, races, holds = _one_shot(raw, day)
    _, prepared = prepared_from_raw(raw, registry=_registry(), day=day)
    schedules = list(reversed(prepared.schedules))
    if order == "last_only":
        schedules = schedules[:1]
    if day == RICH_TARGET_DAYS[-1]:
        # The debut-runner race with ambiguous pedigrees is prepared on this date.
        assert late in {s.race_id for s in prepared.schedules}
    assert {
        h["race_id"]: h for h in prepared.held if h["role"] == "target"
    }.items() <= holds.items()
    for schedule in schedules:
        result = prepared.calculate(
            schedule.race_id,
            *_race_markets(raw, day, schedule.race_id),
            observed_through=None,
        )
        assert result.race_id == schedule.race_id
        if result.hold is not None:
            assert result.hold == holds[schedule.race_id]
            assert result.rows == ()
            assert result.race is None
            continue
        assert result.race == races[schedule.race_id]
        assert list(result.rows) == rows[schedule.race_id]
        assert result.race["freeze_at"] == schedule.freeze_at
        assert result.race["scheduled_start_at"] == schedule.scheduled_start_at


def test_prepare_targets_and_calculate_reject_misuse() -> None:
    raw, _ = _rich_with_late_markets()
    labeled, _ = _build(raw)
    with pytest.raises(ValueError, match="only a builder without labels"):
        labeled.prepare_targets(END.year, ra_rows=[], se_rows=[], workout_rows=[])
    day = RICH_TARGET_DAYS[0]
    builder, prepared = prepared_from_raw(raw, registry=_registry(), day=day)
    with pytest.raises(ValueError, match="only for the target year"):
        builder.prepare_targets(day.year - 1, ra_rows=[], se_rows=[], workout_rows=[])
    with pytest.raises(ValueError, match="not a prepared target"):
        prepared.calculate(_race(day, "11"), [], [], observed_through=None)
    first, second = prepared.schedules[0].race_id, prepared.schedules[1].race_id
    o1, o2 = _race_markets(raw, day, first)
    with pytest.raises(ValueError, match="another race"):
        prepared.calculate(
            first, o1 + _race_markets(raw, day, second)[0], o2, observed_through=None
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        prepared.calculate(first, o1, o2, observed_through=datetime(2026, 12, 20, 15, 0))
    prepared.calculate(first, o1, o2, observed_through=None)
    with pytest.raises(ValueError, match="already calculated"):
        prepared.calculate(first, o1, o2, observed_through=None)


@pytest.mark.parametrize("day", RICH_TARGET_DAYS)
def test_a_fetch_started_after_freeze_replaces_the_later_publication_evidence(day: date) -> None:
    raw, _ = _rich_with_late_markets()
    rows, races, _ = _one_shot(raw, day)
    _, prepared = prepared_from_raw(raw, registry=_registry(), day=day)
    for schedule in prepared.schedules:
        if schedule.race_id not in races:
            continue
        o1, o2 = _race_markets(raw, day, schedule.race_id)
        # A time series fetched at freeze holds no publication after it.
        o1 = [row for row in o1 if publication(row) <= schedule.freeze_at]
        o2 = [row for row in o2 if publication(row) <= schedule.freeze_at]
        early = prepared.calculate(
            schedule.race_id, o1, o2, observed_through=schedule.freeze_at - timedelta(seconds=1)
        )
        assert early.hold is not None
        assert (early.hold["stage"], early.hold["reason"]) == (
            "target_pre_freeze",
            MARKET_NOT_OBSERVED_AFTER_FREEZE,
        )
    _, prepared = prepared_from_raw(raw, registry=_registry(), day=day)
    for schedule in prepared.schedules:
        if schedule.race_id not in races:
            continue
        o1, o2 = _race_markets(raw, day, schedule.race_id)
        o1 = [row for row in o1 if publication(row) <= schedule.freeze_at]
        o2 = [row for row in o2 if publication(row) <= schedule.freeze_at]
        result = prepared.calculate(schedule.race_id, o1, o2, observed_through=schedule.freeze_at)
        assert result.race == races[schedule.race_id]
        assert list(result.rows) == rows[schedule.race_id]


@pytest.mark.parametrize("day", RICH_TARGET_DAYS)
def test_label_free_features_never_read_target_date_results(day: date) -> None:
    raw, _ = _rich_with_late_markets()
    _, baseline = _label_free(raw, day)
    assert _rows(baseline)
    changed, _ = _rich_with_late_markets()
    pre_race(changed, day)
    _, rewritten = _label_free(changed, day)
    assert _rows(rewritten) == _rows(baseline)
    assert _races(rewritten) == _races(baseline)
    assert [output.held for output in rewritten] == [output.held for output in baseline]
    # Every result-only column may hold any value; nothing reads it.
    scrambled, _ = _rich_with_late_markets()
    tables = cast(dict[str, list[Row]], scrambled["tables"])
    stamp = (str(day.year), day.strftime("%m%d"))
    for name, columns in (
        ("label_ra", HISTORY_RA_COLUMNS),
        ("label_se", HISTORY_SE_COLUMNS),
        ("history_ra", HISTORY_RA_COLUMNS),
        ("history_se", HISTORY_SE_COLUMNS),
    ):
        for row in tables[name]:
            if (row["idYear"], row["idMonthDay"]) == stamp:
                row.update({c: "X" for c in columns if c not in CARD_COLUMNS})
    _, garbage = _label_free(scrambled, day)
    assert _rows(garbage) == _rows(baseline)
    assert _races(garbage) == _races(baseline)
    assert [output.held for output in garbage] == [output.held for output in baseline]
    # The labeled datamart cannot label the same unfinished races.
    _, labeled = datamart_from_raw(changed, registry=_registry(), target_start=day, target_end=day)
    outcome = {r for r, (stage, _) in _target_holds(labeled).items() if stage == "target_outcome"}
    assert outcome == set(_races(baseline))


def test_race_day_rows_hold_single_targets_instead_of_failing_the_build() -> None:
    day = RICH_TARGET_DAYS[-1]
    race_09, race_10 = _race(day, "09"), _race(day, "10")
    for table, column, value in (
        ("label_se", "KettoNum", "          "),
        ("label_se", "Umaban", "00"),
        ("label_ra", "HassoTime", ""),
    ):
        raw, late = _rich_with_late_markets()
        pre_race(raw, day)
        rows = cast(dict[str, list[Row]], raw["tables"])[table]
        next(row for row in rows if _race_id(row) == race_09)[column] = value
        _, outputs = _label_free(raw, day)
        holds = _target_holds(outputs)
        assert holds[race_09][0] == "target_pre_freeze", column
        assert holds[late][0] == "target_pre_freeze", column
        assert race_10 in _races(outputs), column
    # A day mixing a finished race with an unfinished one.
    mixed, _ = _rich_with_late_markets()
    pre_race(mixed, day, race_number="10")
    _, both = _label_free(mixed, day)
    assert {race_09, race_10} <= set(_races(both))


def test_targets_without_a_market_observed_after_freeze_are_held() -> None:
    day = RICH_TARGET_DAYS[0]
    raw = rich_raw_input()
    _, outputs = _label_free(raw, day)
    assert not _races(outputs)
    assert set(_target_holds(outputs).values()) == {
        ("target_pre_freeze", "market_not_observed_after_freeze")
    }
    add_post_freeze_markets(raw)
    tables = cast(dict[str, list[Row]], raw["tables"])
    tables["o1"] = [row for row in tables["o1"] if _race_id(row) != _race(day, "09")]
    _, bare = _label_free(raw, day)
    assert _target_holds(bare)[_race(day, "09")] == (
        "target_pre_freeze",
        "market_not_observed_after_freeze",
    )
    assert _race(day, "10") in _races(bare)
    at_freeze = rich_raw_input()
    o1, o2 = markets(day, clock="1455", total=2500, race_number="09")
    cast(dict[str, list[Row]], at_freeze["tables"])["o1"].append(o1)
    cast(dict[str, list[Row]], at_freeze["tables"])["o2"].append(o2)
    _, boundary = _label_free(at_freeze, day)
    assert _target_holds(boundary)[_race(day, "09")] == (
        "target_pre_freeze",
        "market_not_observed_after_freeze",
    )
    # A later row with an unparsable publication clock is no evidence and is skipped.
    unparsable = rich_raw_input()
    o1, _ = markets(day, clock="1458", total=2500, race_number="09")
    o1["HappyoTime"] = "00000000"
    o1["headDataKubun"] = "4"
    cast(dict[str, list[Row]], unparsable["tables"])["o1"].append(o1)
    _, skipped = _label_free(unparsable, day)
    assert _target_holds(skipped)[_race(day, "09")] == (
        "target_pre_freeze",
        "market_not_observed_after_freeze",
    )
    # Any parsable publication after freeze counts, whatever its headDataKubun; a row
    # after freeze never becomes the freeze value.
    other_kind = rich_raw_input()
    o1, _ = markets(day, clock="1458", total=2500, race_number="09")
    o1["headDataKubun"] = "2"
    o1["OddsTansyoInfo0Odds"] = "0999"
    cast(dict[str, list[Row]], other_kind["tables"])["o1"].append(o1)
    _, observed = _label_free(other_kind, day)
    assert _race(day, "09") in _races(observed)
    reference = rich_raw_input()
    add_post_freeze_markets(reference)
    _, expected = _label_free(reference, day)
    race_09 = _race(day, "09")
    assert {k: v for k, v in _rows(observed).items() if k[0] == race_09} == {
        k: v for k, v in _rows(expected).items() if k[0] == race_09
    }


def test_freshness_reports_workouts_pedigrees_and_recent_history_holds() -> None:
    raw, _ = _rich_with_late_markets()
    builder, _ = _label_free(raw, RICH_TARGET_DAYS[-1])
    assert builder.freshness() == {
        "latest_workout_date": {"hc": "2027-01-02", "wc": "2027-01-02"},
        "card_horses": 10,
        "card_horses_without_pedigree_row": 3,
        "history_held_recent": 1,
        "history_held_recent_window_days": 7,
    }


def test_manifest_kinds_follow_the_builder_mode() -> None:
    raw, _ = _rich_with_late_markets()
    snapshot = cast(dict[str, object], raw["snapshot"])
    free, _ = _label_free(raw, RICH_TARGET_DAYS[0])
    labeled, _ = _build(raw)
    with pytest.raises(ValueError, match="prediction_manifest"):
        free.manifest(snapshot=snapshot, provenance={}, preparation_config={})
    with pytest.raises(ValueError, match="manifest instead"):
        labeled.prediction_manifest(
            snapshot=snapshot,
            provenance={},
            preparation_config={},
            source_datamart={},
            market_source={"kind": "complete_snapshot"},
        )
    manifest = free.prediction_manifest(
        snapshot=snapshot,
        provenance={},
        preparation_config={},
        source_datamart={"a": 1},
        market_source={"kind": "complete_snapshot"},
    )
    assert manifest["format"] == "reference_prediction_features"
    assert manifest["format_version"] == 2
    assert manifest["market_source"] == {"kind": "complete_snapshot"}
    assert "label" not in manifest
    assert manifest["source_datamart"] == {"a": 1}
    assert manifest["freshness"] == free.freshness()
    expected = labeled.manifest(snapshot=snapshot, provenance={}, preparation_config={})
    assert manifest["contract"] == expected["contract"]


def _source_binding(contract_sha256: str) -> dict[str, object]:
    return {
        "manifest_sha256": "a" * 64,
        "contract_sha256": contract_sha256,
        "target_period": {"start": "2026-12-20", "end": "2027-01-03"},
        "label_usable_through": "2027-01-11T00:00:00+09:00",
        "provenance_source_sha256": "b" * 64,
    }


def _write_prediction(tmp_path: Path) -> tuple[Path, str, ReferenceDatamartBuilder]:
    raw, _ = _rich_with_late_markets()
    builder, outputs = _label_free(raw, RICH_TARGET_DAYS[-1])
    path = tmp_path / "prediction"
    path.mkdir()
    writer = ReferenceDatamartWriter(
        path,
        columns=builder.columns,
        available_at_groups=builder.available_at_groups,
        contract=builder.contract.as_metadata(),
        labeled=False,
    )
    held: list[dict[str, object]] = []
    for output in outputs:
        held.extend(output.held)
        if output.year in builder.target_years():
            writer.write_year(output.year, output.rows, output.races)
    manifest = builder.prediction_manifest(
        snapshot=cast(dict[str, object], raw["snapshot"]),
        provenance={"fixture": True},
        preparation_config={"fixture": True},
        source_datamart=_source_binding(cast(str, builder.contract.as_metadata()["sha256"])),
        market_source={"kind": "complete_snapshot"},
    )
    return path, writer.finish(manifest, held), builder


def test_written_prediction_features_round_trip_without_label_columns(tmp_path: Path) -> None:
    path, digest, builder = _write_prediction(tmp_path)
    loaded = read_reference_prediction_features(
        path, expected_columns=builder.columns, expected_manifest_sha256=digest
    )
    assert loaded.manifest_sha256 == digest == file_sha256(path / "manifest.json")
    assert loaded.races.num_rows == 2
    assert loaded.rows.num_rows == 8
    assert "finish_position" not in loaded.rows.column_names
    assert not {"label_usable_after", "result_delay_days", "label_raw_sha256"} & set(
        loaded.races.column_names
    )
    manifest = loaded.manifest
    assert manifest["format"] == "reference_prediction_features"
    assert manifest["format_version"] == 2
    assert manifest["market_source"] == {"kind": "complete_snapshot"}
    assert "label" not in manifest
    held = json.loads((path / "held_races.json").read_text(encoding="utf-8"))
    assert held["format"] == "reference_prediction_features_held_races"
    assert held["format_version"] == 2
    assert {item["stage"] for item in held["held_races"]} <= {
        "history_result",
        "target_pre_freeze",
        "calculation",
    }
    schema = pq.read_schema(path / "year=2027" / "part-0.parquet")
    identity = json.loads(schema.metadata[b"keiba_ai.reference_datamart"])
    assert identity["format"] == "reference_prediction_features"
    assert identity["format_version"] == 2
    assert schema.metadata[b"keiba_ai.table_kind"] == b"reference_prediction_rows"


def test_labeled_datamart_parquet_metadata_bytes_are_unchanged(tmp_path: Path) -> None:
    path, _, builder = _write(tmp_path)
    contract = cast(str, builder.contract.as_metadata()["sha256"])
    for year in (2026, 2027):
        identity = (
            '{"contract_sha256":"' + contract + '","format_version":1,"year":' + str(year) + "}"
        ).encode()
        for file, kind in (
            ("part-0.parquet", b"reference_datamart_rows"),
            ("races.parquet", b"reference_datamart_races"),
        ):
            assert pq.read_schema(path / f"year={year}" / file).metadata == {
                b"keiba_ai.timestamp_timezone": b"UTC",
                b"keiba_ai.reference_datamart": identity,
                b"keiba_ai.table_kind": kind,
            }


def test_each_reader_rejects_the_other_format(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    datamart, _, builder = _write(tmp_path / "a")
    prediction, _, _ = _write_prediction(tmp_path / "b")
    with pytest.raises(ValueError, match=r"fields|format"):
        read_reference_prediction_features(datamart, expected_columns=builder.columns)
    with pytest.raises(ValueError, match=r"fields|format"):
        read_reference_datamart(prediction, expected_columns=builder.columns)


def _write_one_race(
    tmp_path: Path, *, held: bool = False
) -> tuple[Path, ReferenceDatamartBuilder, dict[str, object]]:
    """Publish one prepared race as the live command does, with a race-day fetch source.

    ``held=True`` publishes the debut-runner race, which calculation holds.
    """
    raw, late = _rich_with_late_markets()
    day = RICH_TARGET_DAYS[-1]
    builder, prepared = prepared_from_raw(raw, registry=_registry(), day=day)
    schedule = next(s for s in prepared.schedules if (s.race_id == late) == held)
    o1, o2 = _race_markets(raw, day, schedule.race_id)
    result = prepared.calculate(
        schedule.race_id, o1, o2, observed_through=schedule.freeze_at + timedelta(seconds=5)
    )
    assert (result.race is None) == held
    source: dict[str, object] = {
        "kind": "race_day_prediction_fetch",
        "race_id": schedule.race_id,
        "scheduled_start_at": schedule.scheduled_start_at.isoformat(),
        "freeze_at": schedule.freeze_at.isoformat(),
        "capture_id": "c" * 32,
        "data_specs": ["0B41", "0B42"],
        "started_at": (schedule.freeze_at + timedelta(seconds=5)).astimezone(UTC).isoformat(),
        "snapshot_id": "d" * 32,
        "tables": {
            "ARCHIVE_O1_ODDS_TANFUKUWAKU": "1" * 64,
            "ARCHIVE_O2_ODDS_UMAREN": "2" * 64,
            "ARCHIVE_CAPTURE_LOG": "3" * 64,
        },
    }
    path = tmp_path / "race"
    path.mkdir()
    writer = ReferenceDatamartWriter(
        path,
        columns=builder.columns,
        available_at_groups=builder.available_at_groups,
        contract=builder.contract.as_metadata(),
        labeled=False,
    )
    writer.write_year(day.year, result.rows, [] if result.race is None else [result.race])
    manifest = builder.prediction_manifest(
        snapshot=cast(dict[str, object], raw["snapshot"]),
        provenance={"fixture": True},
        preparation_config={"fixture": True},
        source_datamart=_source_binding(cast(str, builder.contract.as_metadata()["sha256"])),
        market_source=source,
    )
    hold = [] if result.hold is None else [result.hold]
    writer.finish(manifest, [*prepared.held, *hold])
    return path, builder, source


def test_one_race_with_a_race_day_fetch_source_round_trips(tmp_path: Path) -> None:
    path, builder, source = _write_one_race(tmp_path)
    loaded = read_reference_prediction_features(path, expected_columns=builder.columns)
    assert loaded.manifest["market_source"] == source
    assert loaded.races.column("race_id").to_pylist() == [source["race_id"]]


def test_one_held_race_with_a_race_day_fetch_source_round_trips(tmp_path: Path) -> None:
    path, builder, source = _write_one_race(tmp_path, held=True)
    loaded = read_reference_prediction_features(path, expected_columns=builder.columns)
    held = json.loads((path / "held_races.json").read_text(encoding="utf-8"))["held_races"]
    assert loaded.races.num_rows == 0
    assert [item["race_id"] for item in held if item["role"] == "target"] == [source["race_id"]]
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["market_source"]["race_id"] = "2027010301010109"
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="differ from their market source"):
        read_reference_prediction_features(path, expected_columns=builder.columns)


def _set(name: str, value: object) -> Callable[[dict[str, object]], None]:
    def change(source: dict[str, object]) -> None:
        source[name] = value

    return change


def _drop(name: str) -> Callable[[dict[str, object]], None]:
    def change(source: dict[str, object]) -> None:
        del source[name]

    return change


def _other_race(source: dict[str, object]) -> None:
    source["race_id"] = cast(str, source["race_id"])[:-2] + "11"


def _started_before_freeze(source: dict[str, object]) -> None:
    freeze = datetime.fromisoformat(cast(str, source["freeze_at"]))
    source["started_at"] = (freeze - timedelta(seconds=1)).isoformat()


def _clocks_shifted(source: dict[str, object]) -> None:
    for name in ("scheduled_start_at", "freeze_at", "started_at"):
        clock = datetime.fromisoformat(cast(str, source[name]))
        source[name] = (clock + timedelta(minutes=1)).isoformat()


def _three_tables_with_one_missing(source: dict[str, object]) -> None:
    tables = dict(cast(dict[str, object], source["tables"]))
    del tables["ARCHIVE_CAPTURE_LOG"]
    source["tables"] = tables


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_set("kind", "pinned_snapshot"), "market source is invalid"),
        (_set("extra", 1), "market source is invalid"),
        (_drop("capture_id"), "market source is invalid"),
        (_set("capture_id", "c" * 31), "market source is invalid"),
        (_set("snapshot_id", 1), "market source is invalid"),
        (_set("data_specs", ["0B31", "0B32"]), "market source is invalid"),
        (_three_tables_with_one_missing, "market source is invalid"),
        (_set("started_at", "2027-01-03T15:00:00"), "clock is invalid"),
        (_other_race, "differ from their market source"),
        (_started_before_freeze, "started before freeze_at"),
        (_clocks_shifted, "race clocks differ"),
        (_set("freeze_at", "2027-01-03T14:56:00+09:00"), "freeze boundary differs"),
    ],
)
def test_prediction_reader_rejects_an_invalid_market_source(
    tmp_path: Path, change: Callable[[dict[str, object]], None], message: str
) -> None:
    path, builder, _ = _write_one_race(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    change(manifest["market_source"])
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_reference_prediction_features(path, expected_columns=builder.columns)


def test_prediction_reader_rejects_a_complete_snapshot_source_with_extra_keys(
    tmp_path: Path,
) -> None:
    path, _, builder = _write_prediction(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["market_source"]["race_id"] = "2027010301010109"
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="market source is invalid"):
        read_reference_prediction_features(path, expected_columns=builder.columns)


def test_prediction_reader_rejects_format_version_1_outputs(tmp_path: Path) -> None:
    path, _, builder = _write_prediction(tmp_path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest["format_version"] = 1
    del manifest["market_source"]
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="format_version 1 has no market source"):
        read_reference_prediction_features(path, expected_columns=builder.columns)


def _shift_to_next_day(rows: list[Row]) -> None:
    for name in ("scheduled_start_at", "freeze_at"):
        rows[-1][name] = cast(datetime, rows[-1][name]) + timedelta(days=1)


def _history_into_target_date(rows: list[Row]) -> None:
    rows[0]["history_usable_through"] = datetime(2027, 1, 3, 1, 0, tzinfo=JST)


def _drop_first(rows: list[Row]) -> None:
    rows.pop(0)


@pytest.mark.parametrize(
    ("file", "change", "message"),
    [
        (
            "year=2027/part-0.parquet",
            _shift("market_characteristics__available_at", 1),
            "time boundary",
        ),
        ("year=2027/races.parquet", _shift("freeze_at", -60), "freeze boundary"),
        ("year=2027/part-0.parquet", _drop_first, "differ from its field size"),
        ("year=2027/races.parquet", _shift_to_next_day, "outside its target period"),
        ("year=2027/races.parquet", _history_into_target_date, "target date"),
        ("year=2027/part-0.parquet", lambda rows: rows.insert(1, dict(rows[0])), "duplicated"),
    ],
)
def test_prediction_reader_rejects_meaning_changes_even_when_every_hash_is_recomputed(
    tmp_path: Path, file: str, change: object, message: str
) -> None:
    path, _, builder = _write_prediction(tmp_path)
    _rewrite_rows(path, file, change)
    with pytest.raises(ValueError, match=message):
        read_reference_prediction_features(path, expected_columns=builder.columns)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda source: source.pop("label_usable_through"), "binding is invalid"),
        (lambda source: source.update(contract_sha256="c" * 64), "contract differs"),
        (lambda source: source.update(manifest_sha256="short"), "binding is invalid"),
        (lambda source: source.update(label_usable_through="2027-01-11"), "label boundary"),
    ],
)
def test_prediction_reader_rejects_an_invalid_source_datamart_binding(
    tmp_path: Path, change: Callable[[dict[str, object]], object], message: str
) -> None:
    path, _, builder = _write_prediction(tmp_path)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    change(manifest["source_datamart"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_reference_prediction_features(path, expected_columns=builder.columns)


def test_partial_readers_pin_the_labeled_datamart_manifest(tmp_path: Path) -> None:
    path, digest, builder = _write(tmp_path)
    manifest = read_reference_datamart_manifest(path, expected_manifest_sha256=digest)
    assert manifest["contract"] == builder.contract.as_metadata()
    races = read_reference_datamart(path, expected_columns=builder.columns).races
    through = read_reference_datamart_label_usable_through(path, expected_manifest_sha256=digest)
    assert through == max(races.column("label_usable_after").to_pylist())
    for reader in (read_reference_datamart_manifest, read_reference_datamart_label_usable_through):
        with pytest.raises(ValueError, match="expected identity"):
            reader(path, expected_manifest_sha256="0" * 64)
    (tmp_path / "p").mkdir()
    prediction, prediction_digest, _ = _write_prediction(tmp_path / "p")
    with pytest.raises(ValueError, match=r"fields|format"):
        read_reference_datamart_manifest(prediction, expected_manifest_sha256=prediction_digest)


def _train(tmp_path: Path, raw: dict[str, object]) -> tuple[Path, Path, str]:
    """Publish a labeled training datamart from a fixture snapshot; return its identity."""
    processed = tmp_path / "processed"
    parquet_snapshot(processed, raw)
    datamart = tmp_path / "training"
    result = CliRunner().invoke(app, _cli(processed, datamart))
    assert result.exit_code == 0, result.output
    return processed, datamart, result.stdout.strip().rsplit("manifest_sha256=", 1)[1]


def _predict_cli(
    datamart: Path,
    digest: str,
    processed: Path,
    output: Path,
    day: date = END,
    *extra: str,
) -> list[str]:
    return [
        "datamart",
        "build-reference-prediction",
        "--reference-datamart",
        str(datamart),
        "--reference-datamart-manifest-sha256",
        digest,
        "--date",
        day.isoformat(),
        "--processed-root",
        str(processed),
        "--output",
        str(output),
        "--features-config",
        str(ROOT / "configs/features.toml"),
        *extra,
    ]


def _rewrite_manifest(path: Path, change: Callable[[dict[str, object]], None]) -> str:
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    change(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return file_sha256(manifest_path)


def test_prediction_cli_publishes_the_labeled_values_and_binds_the_training_datamart(
    tmp_path: Path,
) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    output = tmp_path / "prediction"
    result = CliRunner().invoke(app, _predict_cli(datamart, digest, processed, output))
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith(
        "Built reference prediction features: date=2027-01-03 targets=3 races=2 rows=8 "
        "held_targets=1 "
    )
    assert "freshness " in result.stderr
    assert "target_holds target_pre_freeze=1" in result.stderr
    builder, _ = _label_free(raw, END)
    loaded = read_reference_prediction_features(output, expected_columns=builder.columns)
    training = read_reference_datamart(datamart, expected_columns=builder.columns)
    labeled = {(row["race_id"], row["horse_id"]): row for row in training.rows.to_pylist()}
    assert loaded.rows.num_rows == 8
    for row in loaded.rows.to_pylist():
        assert _comparable(row, builder) == _comparable(
            labeled[(row["race_id"], row["horse_id"])], builder
        )
    source = cast(dict[str, object], loaded.manifest["source_datamart"])
    assert source["manifest_sha256"] == digest
    assert source["contract_sha256"] == training.manifest["contract"]["sha256"]  # type: ignore[index]
    assert source["target_period"] == training.manifest["target_period"]
    assert (
        source["label_usable_through"]
        == max(training.races.column("label_usable_after").to_pylist()).isoformat()
    )
    assert source["provenance_source_sha256"] == training.manifest["provenance"]["source_sha256"]  # type: ignore[index]
    assert [p.name for p in tmp_path.iterdir() if ".staging-" in p.name] == []


def test_prediction_cli_reads_a_newer_race_day_snapshot_without_its_results(
    tmp_path: Path,
) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    race_day, _ = _rich_with_late_markets()
    pre_race(race_day, END)
    parquet_snapshot(processed, race_day, snapshot_id="race-day")
    same = tmp_path / "same"
    newer = tmp_path / "newer"
    pinned = CliRunner().invoke(
        app, _predict_cli(datamart, digest, processed, same, END, "--snapshot-id", "fixture-v1")
    )
    current = CliRunner().invoke(app, _predict_cli(datamart, digest, processed, newer))
    assert pinned.exit_code == 0, pinned.output
    assert current.exit_code == 0, current.output
    builder, _ = _label_free(raw, END)
    first = read_reference_prediction_features(same, expected_columns=builder.columns)
    second = read_reference_prediction_features(newer, expected_columns=builder.columns)
    assert second.manifest["snapshot"]["snapshot_id"] == "race-day"  # type: ignore[index]
    assert first.rows.to_pylist() == second.rows.to_pylist()


def test_prediction_cli_publishes_zero_rows_when_every_target_is_held(tmp_path: Path) -> None:
    processed, datamart, digest = _train(tmp_path, rich_raw_input())
    output = tmp_path / "prediction"
    result = CliRunner().invoke(
        app, _predict_cli(datamart, digest, processed, output, RICH_TARGET_DAYS[0])
    )
    assert result.exit_code == 0, result.output
    assert "races=0 rows=0 held_targets=2 " in result.stdout
    assert "target_pre_freeze=2" in result.stderr


def _days_window_plus_one(manifest: dict[str, object]) -> None:
    config = cast(dict[str, dict[str, int]], manifest["preparation_config"])
    config["calculation_settings"]["days_window"] += 1


def _other_column_meaning(manifest: dict[str, object]) -> None:
    columns = cast(list[dict[str, object]], manifest["columns"])
    columns[0]["meaning"] = "changed meaning"


def _other_definitions(manifest: dict[str, object]) -> None:
    definitions = cast(list[dict[str, object]], manifest["feature_definitions"])
    definitions.reverse()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("digest", "expected identity"),
        ("contract", "calculation contract differs"),
        ("definitions", "feature definitions differ"),
        ("early", "history_start"),
        ("no_races", "no races on 2027-01-04"),
        ("columns", "closed numeric columns differ"),
        ("existing", "new non-symbolic-link"),
        ("inside", "outside processed_root"),
    ],
)
def test_prediction_cli_rejects_without_publishing(tmp_path: Path, case: str, message: str) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    output = tmp_path / "prediction"
    day = END
    if case == "digest":
        digest = "0" * 64
    elif case == "contract":
        digest = _rewrite_manifest(datamart, _days_window_plus_one)
    elif case == "definitions":
        digest = _rewrite_manifest(datamart, _other_definitions)
    elif case == "columns":
        digest = _rewrite_manifest(datamart, _other_column_meaning)
    elif case == "early":
        day = date(2026, 10, 1)
    elif case == "no_races":
        day = date(2027, 1, 4)
    elif case == "existing":
        output.mkdir()
    elif case == "inside":
        output = processed / "prediction"
    result = CliRunner().invoke(app, _predict_cli(datamart, digest, processed, output, day))
    assert result.exit_code == 1
    assert "datamart build-reference-prediction failed" in result.stderr
    assert message in result.stderr
    if case == "no_races":
        assert "phase=year" not in result.stderr
    if case != "existing":
        assert not output.exists()
    assert [p.name for p in tmp_path.iterdir() if ".staging-" in p.name] == []


def test_prediction_cli_interrupt_leaves_neither_output_nor_staging(tmp_path: Path) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    output = tmp_path / "prediction"
    original = ReferenceDatamartBuilder.add_year

    def interrupt(self: ReferenceDatamartBuilder, year: int, **kwargs: object) -> object:
        if year == END.year:
            raise KeyboardInterrupt
        return original(self, year, **kwargs)  # type: ignore[arg-type]

    with patch.object(ReferenceDatamartBuilder, "add_year", interrupt):
        result = CliRunner().invoke(app, _predict_cli(datamart, digest, processed, output))
    assert result.exit_code == 130
    assert not output.exists()
    assert [p.name for p in tmp_path.iterdir() if ".staging-" in p.name] == []


def _rewrite_held(path: Path, change: Callable[[list[Row]], None]) -> None:
    """Rewrite held races and the manifest entry that covers them, so only meaning checks remain."""
    held_path = path / "held_races.json"
    payload = json.loads(held_path.read_text(encoding="utf-8"))
    change(payload["held_races"])
    payload["held_races"].sort(key=lambda item: (item["race_id"], item["role"]))
    held_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = payload["held_races"]
    manifest["held_races"].update(
        sha256=file_sha256(held_path),
        count=len(items),
        by_role=dict(sorted(Counter(item["role"] for item in items).items())),
        by_stage=dict(sorted(Counter(item["stage"] for item in items).items())),
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _history_hold_on(day: date) -> Callable[[list[Row]], None]:
    def change(items: list[Row]) -> None:
        items.append(
            {
                "race_id": _race(day, "11"),
                "role": "history",
                "stage": "history_result",
                "reason": "tampered",
                "whole_race": True,
            }
        )

    return change


def _target_as_history_result(items: list[Row]) -> None:
    target = next(item for item in items if item["role"] == "target")
    target["stage"] = "history_result"


@pytest.mark.parametrize(
    "change",
    [_history_hold_on(END), _history_hold_on(END + timedelta(days=1)), _target_as_history_result],
    ids=["history_on_target_date", "history_after_target_date", "target_as_history_result"],
)
def test_prediction_reader_rejects_holds_outside_their_role_and_date(
    tmp_path: Path, change: Callable[[list[Row]], None]
) -> None:
    path, _, builder = _write_prediction(tmp_path)
    read_reference_prediction_features(path, expected_columns=builder.columns)
    _rewrite_held(path, change)
    with pytest.raises(ValueError, match="held race role, stage or date"):
        read_reference_prediction_features(path, expected_columns=builder.columns)


# Issue #45: build-time invariants and reader checks of the reference datamart.


def _with_coverage(change: Callable[[tuple[Coverage, ...]], tuple[Coverage, ...]]) -> object:
    original = shared_context

    def patched(source: ObservationInput, **kwargs: object) -> object:
        return original(replace(source, coverage=change(source.coverage)), **kwargs)  # type: ignore[arg-type]

    return patch("models.serialization.reference_datamart.shared_context", patched)


def _replace_kind(
    target_kind: str, **changes: object
) -> Callable[[tuple[Coverage, ...]], tuple[Coverage, ...]]:
    def change(coverage: tuple[Coverage, ...]) -> tuple[Coverage, ...]:
        return tuple(
            replace(item, **changes) if item.kind == target_kind else item  # type: ignore[arg-type]
            for item in coverage
        )

    return change


def _copied_population(coverage: tuple[Coverage, ...]) -> tuple[Coverage, ...]:
    # An equal but distinct population object breaks the identity the shared views rely on.
    return tuple(
        replace(item, horse_ids=tuple(list(item.horse_ids))) if item.kind == "history" else item
        for item in coverage
    )


def _later_history_start(coverage: tuple[Coverage, ...]) -> tuple[Coverage, ...]:
    return tuple(
        replace(item, start_at=item.start_at + timedelta(days=1))
        if item.kind == "history"
        else item
        for item in coverage
    )


def _inverted_market_interval(coverage: tuple[Coverage, ...]) -> tuple[Coverage, ...]:
    return tuple(
        replace(item, start_at=item.end_at + timedelta(seconds=1))
        if item.kind == "market"
        else item
        for item in coverage
    )


@pytest.mark.parametrize("labeled", [True, False], ids=["labeled", "label_free"])
@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_replace_kind("market", kind="unknown"), "unsupported coverage kind"),
        (_inverted_market_interval, "coverage scope or interval"),
        (_later_history_start, "must span history_start"),
        (_copied_population, "complete required horse population"),
    ],
    ids=["kind", "interval", "span", "population"],
)
def test_coverage_violations_fail_the_whole_build(
    labeled: bool,
    change: Callable[[tuple[Coverage, ...]], tuple[Coverage, ...]],
    message: str,
) -> None:
    raw = rich_raw_input() if labeled else _rich_with_late_markets()[0]

    def build() -> object:
        return _build(raw) if labeled else _label_free(raw, END)

    with (
        _with_coverage(change),  # type: ignore[attr-defined]
        pytest.raises(ChronologicalInvariantError, match=message),
    ):
        build()


def test_readers_reject_a_closed_column_group_without_its_availability_clock(
    tmp_path: Path,
) -> None:
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    datamart, _, builder = _write(tmp_path / "a")
    prediction, _, _ = _write_prediction(tmp_path / "b")
    for path, reader in (
        (datamart, read_reference_datamart),
        (prediction, read_reference_prediction_features),
    ):
        _rewrite_manifest(
            path,
            lambda manifest: cast(list[str], manifest["available_at_groups"]).remove(
                "market_characteristics"
            ),
        )
        with pytest.raises(ValueError, match="miss a closed column group"):
            reader(path, expected_columns=builder.columns)


def test_a_date_shared_pagerank_failure_holds_only_that_dates_targets() -> None:
    _, baseline = _build(rich_raw_input())
    before = _rows(baseline)
    failing_day = RICH_TARGET_DAYS[1]
    original = opponent_pagerank._fit

    def fail_on_one_date(context: object) -> object:
        start = cast(datetime, context.source.card.scheduled_start_at)  # type: ignore[attr-defined]
        if start.astimezone(JST).date() == failing_day:
            raise ValueError("PageRank did not converge")
        return original(context)  # type: ignore[arg-type]

    with patch.object(opponent_pagerank, "_fit", fail_on_one_date):
        _, outputs = _build(rich_raw_input())
    stamp = f"{failing_day:%Y%m%d}"
    calculation = {
        race_id: reason
        for race_id, (stage, reason) in _target_holds(outputs).items()
        if stage == "calculation"
    }
    assert set(calculation) == {
        race_id for race_id in {key[0] for key in before} if race_id.startswith(stamp)
    }
    assert all("opponent_pagerank: PageRank did not converge" in r for r in calculation.values())
    after = _rows(outputs)
    assert after == {key: row for key, row in before.items() if not key[0].startswith(stamp)}
    assert {key[0][:8] for key in after} == {
        f"{day:%Y%m%d}" for day in RICH_TARGET_DAYS if day != failing_day
    }


def test_the_anchor_market_stays_when_a_quote_arrives_at_freeze() -> None:
    chosen: list[tuple[str, datetime, str]] = []
    original = market_characteristics._market_at

    def spy(context: object, anchor: datetime) -> object:
        market = original(context, anchor)  # type: ignore[arg-type]
        race_id = cast(str, context.source.card.race_id)  # type: ignore[attr-defined]
        chosen.append((race_id, anchor, market.evidence.observation_id))
        return market

    target = _race(RICH_TARGET_DAYS[2], "09")
    with patch.object(market_characteristics, "_market_at", spy):
        _build(rich_raw_input())
    baseline = _selections(chosen, target)
    chosen.clear()
    raw = rich_raw_input()
    tables = cast(dict[str, list[Row]], raw["tables"])
    # 14:55 is the freeze of the 15:00 race; its anchor (14:45) still sees only 14:44.
    o1, o2 = markets(RICH_TARGET_DAYS[2], clock="1455", total=2500, race_number="09")
    o1["OddsTansyoInfo0Odds"] = "0123"
    tables["o1"].append(o1)
    tables["o2"].append(o2)
    with patch.object(market_characteristics, "_market_at", spy):
        _build(raw)
    changed = _selections(chosen, target)
    anchor = datetime(2027, 1, 3, 14, 45, tzinfo=JST)
    freeze = datetime(2027, 1, 3, 14, 55, tzinfo=JST)
    # Every horse of the race reads the same two anchors.
    assert set(baseline) == set(changed) == {anchor, freeze}
    assert all(len(ids) == 1 for ids in (*baseline.values(), *changed.values()))
    assert changed[anchor] == baseline[anchor]
    assert changed[freeze] != baseline[freeze]


def _selections(chosen: list[tuple[str, datetime, str]], race_id: str) -> dict[datetime, set[str]]:
    result: dict[datetime, set[str]] = {}
    for identity, anchor, observation in chosen:
        if identity == race_id:
            result.setdefault(anchor, set()).add(observation)
    return result


def test_pedigree_evidence_usable_after_freeze_fails_the_whole_build() -> None:
    original = reference_pedigree

    def late(horse: str, rows: object, *, start: datetime) -> object:
        pedigree = original(horse, rows, start=start)  # type: ignore[arg-type]
        evidence = pedigree.evidence
        assert isinstance(evidence, ReferenceEvidence)
        shifted = replace(evidence, usable_after=datetime(2030, 1, 1, tzinfo=JST))
        return replace(pedigree, evidence=shifted)

    with (
        patch("models.serialization.reference_datamart.reference_pedigree", late),
        pytest.raises(ChronologicalInvariantError, match="pedigree"),
    ):
        _build(rich_raw_input())


# ADR-037: race-day-odds publishes each race after its prediction fetch; the live
# command calculates that race from the pinned version as soon as it appears.

LIVE_SPECS = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36", "0B41", "0B42"})
LIVE_TABLES = ("ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN", "ARCHIVE_CAPTURE_LOG")


class _RaceDayClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _SeriesRunner:
    """Stage the fixture's 0B41/0B42 rows published by the fetch time; fail captures."""

    def __init__(self, raw: dict[str, object], database: Path, clock: _RaceDayClock) -> None:
        self.tables = cast(dict[str, list[Row]], raw["tables"])
        self.database = database
        self.clock = clock
        self.assert_not_running = Mock()

    def execute(self, setting: Path, *, skip_last_modified_update: bool = False) -> object:
        race = next(
            spec.findtext("JVRaceKey/RaceNum") or ""
            for spec in ET.parse(setting).getroot().iter("JVDataSpecSetting")
            if spec.findtext("IsEnabled") == "true"
        )
        if setting.name != "race-day-prediction.xml":
            raise JVLinkToSQLiteError("captures are not part of this test", returncode=1)
        fetched = self.clock.now
        with sqlite3.connect(self.database) as connection:
            for name, table, columns in (
                ("o1", "RT_O1_ODDS_TANFUKUWAKU", MARKET_O1_COLUMNS),
                ("o2", "RT_O2_ODDS_UMAREN", MARKET_O2_COLUMNS),
            ):
                placeholders = ", ".join("?" for _ in columns)
                for row in self.tables[name]:
                    if (
                        row["idRaceNum"] == race
                        and row["idMonthDay"] == END.strftime("%m%d")
                        and publication(row) <= fetched
                    ):
                        connection.execute(
                            f'INSERT INTO "{table}" VALUES ({placeholders})',
                            [row[column] for column in columns],
                        )
        self.clock.now += timedelta(seconds=3)
        return JVLinkExecutionResult({}, process_returncode=0)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _race_day_raw(raw: dict[str, object], database: Path) -> None:
    tables = cast(dict[str, list[Row]], raw["tables"])
    stamp = (str(END.year), END.strftime("%m%d"))
    keys = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
    races = {
        _race_id(row): row
        for row in tables["history_ra"] + tables["label_ra"]
        if (row["idYear"], row["idMonthDay"]) == stamp
    }
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        declared = ", ".join(_quote(c) + " TEXT" for c in (*keys, "headDataKubun", "HassoTime"))
        connection.execute(f"CREATE TABLE NL_RA_RACE ({declared})")
        for row in races.values():
            connection.execute(
                "INSERT INTO NL_RA_RACE VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*(row[k] for k in keys), "2", row["HassoTime"]),
            )
        for table, columns in (
            ("RT_O1_ODDS_TANFUKUWAKU", MARKET_O1_COLUMNS),
            ("RT_O2_ODDS_UMAREN", MARKET_O2_COLUMNS),
        ):
            declared = ", ".join(_quote(c) + " TEXT" for c in columns)
            connection.execute(f'CREATE TABLE "{table}" ({declared})')


def _race_day_seed(path: Path) -> None:
    key = (
        "<JVRaceKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate><JyoCD>01</JyoCD>"
        "<Kaiji>01</Kaiji><Nichiji>01</Nichiji><RaceNum>01</RaceNum></JVRaceKey>"
    )
    specs = "".join(
        f"<JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>{spec}</DataSpec>{key}"
        "</JVDataSpecSetting>"
        for spec in sorted(LIVE_SPECS)
    )
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><JVLinkToSQLiteSetting><Details>'
        "<JVNormalUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>"
        "</DataSpecSettings></JVNormalUpdateSetting>"
        "<JVSetupDataUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>"
        "</DataSpecSettings></JVSetupDataUpdateSetting>"
        "<JVRealTimeDataUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>"
        f"{specs}</DataSpecSettings></JVRealTimeDataUpdateSetting>"
        "</Details></JVLinkToSQLiteSetting>",
        encoding="utf-8",
    )


def _run_race_day_odds(tmp_path: Path, raw: dict[str, object], processed: Path) -> None:
    """Run the real race-day-odds loop on END; each prediction fetch publishes its race."""
    paths = DataPaths(tmp_path / "raw" / "race.db", processed, tmp_path / "runtime")
    _race_day_raw(raw, paths.raw_db)
    _race_day_seed(tmp_path / "seed.xml")
    # 14:00 JST, before the first freeze at 14:55 JST.
    clock = _RaceDayClock(datetime(2027, 1, 3, 5, 0, tzinfo=UTC))
    common: dict[str, object] = {
        "normal_update": False,
        "setup_update": False,
        "realtime_update": True,
        "normal_data_specs": frozenset(),
        "setup_data_specs": frozenset(),
    }
    retriever = RaceDayOddsRetriever(
        _SeriesRunner(raw, paths.raw_db, clock),  # type: ignore[arg-type]
        JVLinkSettingBuilder(tmp_path / "seed.xml"),
        OddsArchive(paths.raw_db),
        RaceDayOddsProfile(
            **common,  # type: ignore[arg-type]
            realtime_data_specs=LIVE_SPECS - {"0B41", "0B42"},
            offsets_minutes=(2,),
            prediction_offset_minutes=5,
        ),
        paths.raw_db,
        paths.jvlink_runtime_dir / "historical-odds-progress.db",
        paths.jvlink_runtime_dir,
        clock=clock,
        sleeper=clock.sleep,
        prediction_profile=JVLinkProfile(
            **common,  # type: ignore[arg-type]
            realtime_data_specs=frozenset({"0B41", "0B42"}),
        ),
    )
    retriever.retrieve(END, publisher=SnapshotBuilder(paths).update_race)


def _live_cli(datamart: Path, digest: str, processed: Path, output: Path, *extra: str) -> list[str]:
    command = _predict_cli(datamart, digest, processed, output, END, *extra)
    command[1] = "build-reference-prediction-live"
    return command


def test_live_cli_publishes_each_race_from_its_race_day_fetch_like_the_one_shot_build(
    tmp_path: Path,
) -> None:
    raw, late = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    _run_race_day_odds(tmp_path, raw, processed)
    one_shot = tmp_path / "one-shot"
    first = CliRunner().invoke(app, _predict_cli(datamart, digest, processed, one_shot))
    assert first.exit_code == 0, first.output
    live = tmp_path / "live"
    clock = _RaceDayClock(datetime(2027, 1, 3, 5, 50, tzinfo=UTC))
    with (
        patch("cli.reference_datamart._clock", clock),
        patch("cli.reference_datamart._sleep", clock.sleep),
    ):
        result = CliRunner().invoke(app, _live_cli(datamart, digest, processed, live))

    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [line["race_id"] for line in lines] == [
        "2027010301010109",
        "2027010301010110",
        late,
    ]
    keys = {"race_id", "status", "stage", "reason", "output", "manifest_sha256", "rows"}
    assert all(set(line) == keys for line in lines)
    builder, _ = _label_free(raw, END)
    expected = read_reference_prediction_features(one_shot, expected_columns=builder.columns)
    expected_rows = {(r["race_id"], r["horse_id"]): r for r in expected.rows.to_pylist()}
    held_file = json.loads((one_shot / "held_races.json").read_text(encoding="utf-8"))
    expected_holds = {
        item["race_id"]: item for item in held_file["held_races"] if item["role"] == "target"
    }
    compared = 0
    for line in lines:
        assert line["status"] == "published"
        loaded = read_reference_prediction_features(
            Path(line["output"]),
            expected_columns=builder.columns,
            expected_manifest_sha256=line["manifest_sha256"],
        )
        source = cast(dict[str, object], loaded.manifest["market_source"])
        assert (source["kind"], source["race_id"]) == ("race_day_prediction_fetch", line["race_id"])
        version = (
            processed / "realtime" / line["race_id"] / "versions" / cast(str, source["snapshot_id"])
        )
        assert source["tables"] == {
            name: file_sha256(version / f"{name}.parquet") for name in LIVE_TABLES
        }
        assert datetime.fromisoformat(cast(str, source["started_at"])) == datetime.fromisoformat(
            cast(str, source["freeze_at"])
        )
        assert loaded.rows.num_rows == line["rows"]
        for row in loaded.rows.to_pylist():
            assert _comparable(row, builder) == _comparable(
                expected_rows[(row["race_id"], row["horse_id"])], builder
            )
            compared += 1
        if line["stage"] is not None:
            hold = expected_holds[line["race_id"]]
            assert (line["stage"], line["reason"]) == (hold["stage"], hold["reason"])
    assert compared == expected.rows.num_rows
    assert "race_day_features date=2027-01-03 targets=3 published=3 held=0" in result.stderr
    progress = [line for line in result.stderr.splitlines() if line.startswith("phase=race ")]
    assert [line.split()[1] for line in progress] == [f"race={line['race_id']}" for line in lines]
    assert all(
        all(
            f" {name}=" in line for name in ("read_seconds", "calculate_seconds", "publish_seconds")
        )
        for line in progress
    )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("--poll-interval-seconds", "0"), "--poll-interval-seconds must be a positive integer"),
        (("--deadline-seconds", "181"), "--deadline-seconds must be from 1 through 180"),
        (("--deadline-seconds", "0"), "--deadline-seconds must be from 1 through 180"),
    ],
)
def test_live_cli_rejects_its_timing_before_reading_anything(
    tmp_path: Path, extra: tuple[str, ...], message: str
) -> None:
    output = tmp_path / "live"
    with (
        patch(
            "cli.reference_datamart.read_reference_datamart_manifest",
            side_effect=AssertionError("unexpected datamart read"),
        ),
        patch(
            "cli.reference_datamart.FixedSnapshot",
            side_effect=AssertionError("unexpected snapshot read"),
        ),
    ):
        result = CliRunner().invoke(
            app, _live_cli(tmp_path / "d", "0" * 64, tmp_path / "p", output, *extra)
        )
    assert result.exit_code == 1
    assert result.stderr == f"datamart build-reference-prediction-live failed: {message}\n"
    assert not output.exists()


def test_live_cli_failures_keep_only_finished_race_outputs(tmp_path: Path) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    _run_race_day_odds(tmp_path, raw, processed)
    original = PreparedTargets.calculate
    calls: list[str] = []

    def second_breaks(
        self: PreparedTargets, race_id: str, *args: object, **kwargs: object
    ) -> object:
        calls.append(race_id)
        if len(calls) == 2:
            raise ChronologicalInvariantError("history prefix crosses its date boundary")
        return original(self, race_id, *args, **kwargs)  # type: ignore[arg-type]

    clock = _RaceDayClock(datetime(2027, 1, 3, 5, 50, tzinfo=UTC))
    output = tmp_path / "live"
    with (
        patch("cli.reference_datamart._clock", clock),
        patch("cli.reference_datamart._sleep", clock.sleep),
        patch.object(PreparedTargets, "calculate", second_breaks),
    ):
        result = CliRunner().invoke(app, _live_cli(datamart, digest, processed, output))
    assert result.exit_code == 1
    assert "datamart build-reference-prediction-live failed: history prefix" in result.stderr
    assert [path.name for path in output.iterdir()] == ["2027010301010109"]

    def interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    output = tmp_path / "interrupted"
    clock = _RaceDayClock(datetime(2027, 1, 3, 5, 50, tzinfo=UTC))
    with (
        patch("cli.reference_datamart._clock", clock),
        patch("cli.reference_datamart._sleep", interrupt),
    ):
        result = CliRunner().invoke(app, _live_cli(datamart, digest, processed, output))
    assert result.exit_code == 130
    assert "datamart build-reference-prediction-live failed: interrupted" in result.stderr
    assert list(output.iterdir()) == []
    assert [p.name for p in tmp_path.iterdir() if ".staging-" in p.name] == []


@pytest.mark.parametrize(
    ("error", "exit_code", "message"),
    [(OSError("disk full"), 1, "disk full"), (KeyboardInterrupt(), 130, "interrupted")],
)
def test_live_cli_writer_failure_on_a_race_leaves_no_staging(
    tmp_path: Path, error: BaseException, exit_code: int, message: str
) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    _run_race_day_odds(tmp_path, raw, processed)
    original = ReferenceDatamartWriter.finish
    calls: list[int] = []

    def second_fails(
        self: ReferenceDatamartWriter, manifest: dict[str, object], held: list[Row]
    ) -> str:
        calls.append(1)
        if len(calls) == 2:
            raise error
        return original(self, manifest, held)

    clock = _RaceDayClock(datetime(2027, 1, 3, 5, 50, tzinfo=UTC))
    output = tmp_path / "live"
    with (
        patch("cli.reference_datamart._clock", clock),
        patch("cli.reference_datamart._sleep", clock.sleep),
        patch.object(ReferenceDatamartWriter, "finish", second_fails),
    ):
        result = CliRunner().invoke(app, _live_cli(datamart, digest, processed, output))
    assert result.exit_code == exit_code
    assert f"datamart build-reference-prediction-live failed: {message}" in result.stderr
    # The second race was being written; only the first race is published.
    assert [path.name for path in output.iterdir()] == ["2027010301010109"]
    assert len(result.stdout.splitlines()) == 1


def test_live_cli_preparation_failure_creates_no_output(tmp_path: Path) -> None:
    raw, _ = _rich_with_late_markets()
    processed, datamart, digest = _train(tmp_path, raw)
    output = tmp_path / "live"
    with patch.object(FixedSnapshot, "pin", side_effect=ValueError("pin failed")):
        result = CliRunner().invoke(app, _live_cli(datamart, digest, processed, output))
    assert result.exit_code == 1
    assert result.stderr.endswith("datamart build-reference-prediction-live failed: pin failed\n")
    assert result.stdout == ""
    assert not output.exists()


def _target_day_rows(raw: dict[str, object], day: date) -> tuple[list[Row], list[Row]]:
    """Return one date's stored RA and SE rows once each, as the snapshot holds them."""
    tables = cast(dict[str, list[Row]], raw["tables"])
    stamp = (str(day.year), day.strftime("%m%d"))
    result: list[list[Row]] = []
    for names in (("history_ra", "label_ra"), ("history_se", "label_se")):
        seen: dict[int, Row] = {}
        for name in names:
            for row in tables[name]:
                if (row["idYear"], row["idMonthDay"]) == stamp:
                    seen[id(row)] = row
        result.append(list(seen.values()))
    return result[0], result[1]


@pytest.mark.parametrize("day", RICH_TARGET_DAYS)
def test_shared_card_normalization_reproduces_the_feature_build(day: date) -> None:
    raw, _ = _rich_with_late_markets()
    _, races, holds = _one_shot(raw, day)
    _, prepared = prepared_from_raw(raw, registry=_registry(), day=day)
    ra_rows, se_rows = _target_day_rows(raw, day)
    cards, card_holds = label_free_target_cards(
        ra_rows, se_rows, day=day, freeze_offset_seconds=300
    )
    prepared_holds = [item for item in prepared.held if item["role"] == "target"]
    assert list(card_holds) == prepared_holds
    assert [(card.race_id, card.scheduled_start_at, card.freeze_at) for card in cards] == sorted(
        (schedule.race_id, schedule.scheduled_start_at, schedule.freeze_at)
        for schedule in prepared.schedules
    )
    published = [card for card in cards if card.race_id in races]
    assert published
    for card in published:
        assert (
            canonical_hash(dict(card.horse_mapping)) == races[card.race_id]["horse_mapping_sha256"]
        )
        assert list(card.horse_mapping) == sorted(card.horse_mapping)
    # Every race the build published or held after preparation has a card.
    assert set(races) | (set(holds) - {cast(str, h["race_id"]) for h in card_holds}) <= {
        card.race_id for card in cards
    }


def _first_runner(rows: list[Row], race_id: str) -> int:
    return next(i for i, row in enumerate(rows) if _race_id(row) == race_id)


def _duplicate_ra(ra: list[Row], se: list[Row], race_id: str) -> None:
    ra.append(dict(ra[_first_runner(ra, race_id)]))


def _conflicting_ra(column: str, value: str) -> Callable[[list[Row], list[Row], str], None]:
    def edit(ra: list[Row], se: list[Row], race_id: str) -> None:
        ra.append({**ra[_first_runner(ra, race_id)], column: value})

    return edit


def _duplicate_se(ra: list[Row], se: list[Row], race_id: str) -> None:
    se.append(dict(se[_first_runner(se, race_id)]))


def _repeat_se(column: str) -> Callable[[list[Row], list[Row], str], None]:
    def edit(ra: list[Row], se: list[Row], race_id: str) -> None:
        first = _first_runner(se, race_id)
        se[first + 1] = {**se[first + 1], column: se[first][column]}

    return edit


def _missing_horse(ra: list[Row], se: list[Row], race_id: str) -> None:
    first = _first_runner(se, race_id)
    se[first] = {**se[first], "KettoNum": None}


@pytest.mark.parametrize(
    ("edit", "stage", "reason"),
    [
        (_duplicate_ra, None, None),
        (_conflicting_ra("Kyori", "2000"), "prepare", "ambiguous_or_missing_race_row"),
        (_conflicting_ra("HassoTime", "1505"), "prepare", "ambiguous_or_missing_race_row"),
        (_conflicting_ra("GradeCD", "A"), None, None),
        (_duplicate_se, "calculate", CARD_MAPPING_MISMATCH),
        (_repeat_se("Umaban"), "calculate", CARD_MAPPING_MISMATCH),
        (_repeat_se("KettoNum"), "calculate", CARD_MAPPING_MISMATCH),
        (_missing_horse, "calculate", "card requires permanent KettoNum and Umaban mapping"),
    ],
)
def test_shared_card_normalization_holds_a_race_as_the_feature_build_does(
    edit: Callable[[list[Row], list[Row], str], None], stage: str | None, reason: str | None
) -> None:
    raw, _ = _rich_with_late_markets()
    day = RICH_TARGET_DAYS[0]
    _, races, _ = _one_shot(raw, day)
    race_id = sorted(races)[0]
    seen: list[tuple[list[Row], list[Row]]] = []

    def capture(ra: list[Row], se: list[Row]) -> None:
        edit(ra, se, race_id)
        seen.append((ra, se))

    _, prepared = prepared_from_raw(raw, registry=_registry(), day=day, edit=capture)
    ((ra_rows, se_rows),) = seen
    cards, card_holds = label_free_target_cards(
        ra_rows, se_rows, day=day, freeze_offset_seconds=300
    )
    if stage is None:
        # Identical rows count once; columns outside the card never reach the card.
        (card,) = (card for card in cards if card.race_id == race_id)
        assert canonical_hash(dict(card.horse_mapping)) == races[race_id]["horse_mapping_sha256"]
        assert race_id in {schedule.race_id for schedule in prepared.schedules}
        return
    expected = {
        "race_id": race_id,
        "role": "target",
        "stage": "target_pre_freeze",
        "reason": reason,
        "whole_race": True,
    }
    assert race_id not in {card.race_id for card in cards}
    assert [item for item in card_holds if item["race_id"] == race_id] == [expected]
    if stage == "prepare":
        assert expected in prepared.held
        assert race_id not in {schedule.race_id for schedule in prepared.schedules}
        return
    result = prepared.calculate(race_id, *_race_markets(raw, day, race_id), observed_through=None)
    assert result.hold == expected


def test_readers_return_the_validated_held_races(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
    datamart, _, builder = _write(tmp_path / "a")
    prediction, _, _ = _write_prediction(tmp_path / "b")
    one_race, _, source = _write_one_race(tmp_path / "c", held=True)
    for path, read in (
        (datamart, read_reference_datamart),
        (prediction, read_reference_prediction_features),
        (one_race, read_reference_prediction_features),
    ):
        stored = json.loads((path / "held_races.json").read_text(encoding="utf-8"))
        loaded = read(path, expected_columns=builder.columns)
        assert [dict(item) for item in loaded.held] == stored["held_races"]
        assert loaded.held
    loaded = read_reference_prediction_features(one_race, expected_columns=builder.columns)
    assert [item["race_id"] for item in loaded.held if item["role"] == "target"] == [
        source["race_id"]
    ]
