"""Reference datamart: equivalence with the per-race path, leakage, persistence and CLI."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from data.loader.file_hash import file_sha256
from main import app
from make_datamart.tables.reference import ReferenceDatamartWriter, read_reference_datamart
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import FeatureRegistry, create_feature_registry
from make_features.contracts.observations import ObservationInput, ReferenceEvidence
from make_features.generation.chronological import (
    ChronologicalHistory,
    ChronologicalInvariantError,
    SharedCalculationContext,
    shared_context,
)
from make_features.reference_raw import result_boundary
from models.dataset.calculated import closed_numeric_columns
from models.serialization.reference import prepare_reference_payload
from models.serialization.reference_datamart import (
    ReferenceDatamartBuilder,
    ReferenceYearOutput,
)
from tests.reference_fixtures import (
    RICH_TARGET_DAYS,
    ROOT,
    datamart_from_raw,
    parquet_snapshot,
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
