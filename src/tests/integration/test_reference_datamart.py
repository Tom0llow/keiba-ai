"""Reference datamart: equivalence with the per-race path, leakage, persistence and CLI."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
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
from make_datamart.tables.reference import (
    ReferenceDatamartWriter,
    read_reference_datamart,
    read_reference_datamart_label_usable_through,
    read_reference_datamart_manifest,
    read_reference_prediction_features,
)
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import FeatureRegistry, create_feature_registry
from make_features.contracts.observations import ObservationInput, ReferenceEvidence
from make_features.generation.chronological import (
    ChronologicalHistory,
    ChronologicalInvariantError,
    SharedCalculationContext,
    shared_context,
)
from make_features.real_market import JST
from make_features.reference_raw import (
    CARD_RA_COLUMNS,
    CARD_SE_COLUMNS,
    HC_COLUMNS,
    HISTORY_RA_COLUMNS,
    HISTORY_SE_COLUMNS,
    WC_COLUMNS,
    result_boundary,
)
from models.dataset.calculated import closed_numeric_columns
from models.serialization.reference import prepare_reference_payload
from models.serialization.reference_datamart import (
    ReferenceDatamartBuilder,
    ReferenceYearOutput,
)
from tests.reference_fixtures import (
    RICH_TARGET_DAYS,
    ROOT,
    add_post_freeze_markets,
    datamart_from_raw,
    markets,
    parquet_snapshot,
    pre_race,
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
    # A session on the day before each target date is the workout window's last day.
    for day in RICH_TARGET_DAYS:
        for kind in ("hc", "wc"):
            tables[kind].append(_workout(kind, "2020100002", day - timedelta(days=1)))
    return raw, late


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
            snapshot=snapshot, provenance={}, preparation_config={}, source_datamart={}
        )
    manifest = free.prediction_manifest(
        snapshot=snapshot, provenance={}, preparation_config={}, source_datamart={"a": 1}
    )
    assert manifest["format"] == "reference_prediction_features"
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
    assert "label" not in manifest
    held = json.loads((path / "held_races.json").read_text(encoding="utf-8"))
    assert held["format"] == "reference_prediction_features_held_races"
    assert {item["stage"] for item in held["held_races"]} <= {
        "history_result",
        "target_pre_freeze",
        "calculation",
    }
    schema = pq.read_schema(path / "year=2027" / "part-0.parquet")
    identity = json.loads(schema.metadata[b"keiba_ai.reference_datamart"])
    assert identity["format"] == "reference_prediction_features"
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
