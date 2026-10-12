"""Verify individual builders share middle rows, source audits and table storage."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pyarrow as pa
import pytest

from features.common.feature_table import (
    build_feature_table,
    read_feature_table,
    validate_feature_table,
    write_feature_table,
)
from features.common.registry import FEATURE_BUILDERS, FEATURE_GROUP_IDS, FEATURE_INPUT_TYPES
from features.common.rows import FeatureTableRow
from features.common.types import FeatureBuildError, FeatureValuesInput
from features.odds_ratio import OddsRatioInput, build_odds_ratio
from features.past_racing_ability import PastRacingAbilityBuilder
from make_datamart.builder import join_feature_tables, read_datamart, write_datamart

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)
RESULT_ALIAS_FIELDS = (
    *(
        f"{prefix}{alias}"
        for prefix in ("", "target_", "target_race_")
        for alias in (
            "last_3f",
            "last3f",
            "HaronTimeL3",
            "confirmed_time",
            "dead_heat",
            "earnings",
            "margin",
        )
    ),
    "TARGET-LAST.3F",
    "Target.Race.HARON-TIME-L3",
    "target_race_last_3f_mean",
    "target_race_HaronTimeL3_delta",
    "target_confirmed_time_zscore",
    "target_dead_heat_count",
    "target_race_earnings_mean",
    "target_margin_delta",
)


def _input(feature_id: str, *, horse_id: str = "horse-1") -> FeatureValuesInput:
    field_name = "market_win_odds" if feature_id == "F19" else "pre_race_value"
    return FEATURE_INPUT_TYPES[feature_id](
        feature_id=feature_id,
        race_id="race-1",
        horse_id=horse_id,
        freeze_at=FREEZE_AT,
        values={field_name: 2.0},
        available_at=AVAILABLE_AT,
        source_event_at=AVAILABLE_AT,
        source_scope="historical",
        status="confirmed",
        source_race_ids=("past-race",),
        contains_target_result=False,
        contains_future_data=False,
    )


@pytest.mark.parametrize("feature_id", FEATURE_GROUP_IDS)
def test_each_builder_returns_common_rows_and_round_trips_a_table(
    tmp_path: Path, feature_id: str
) -> None:
    record = _input(feature_id)
    builder = FEATURE_BUILDERS[feature_id]
    rows = builder.build_rows([record])
    field_name = next(iter(record.values))
    table = builder.build([record], column_types={field_name: pa.float64()})

    assert len(rows) == 1
    assert isinstance(rows[0], FeatureTableRow)
    assert rows[0].values == record.values
    assert table[field_name].to_pylist() == [2.0]
    assert table["freeze_at"].to_pylist() == [FREEZE_AT]
    path = tmp_path / "feature.parquet"
    write_feature_table(table, path)
    assert read_feature_table(path).equals(table, check_metadata=True)


@pytest.mark.parametrize("feature_id", FEATURE_GROUP_IDS)
def test_individual_builders_reject_future_source_evidence(feature_id: str) -> None:
    record = replace(_input(feature_id), source_event_at=FREEZE_AT + timedelta(seconds=1))
    with pytest.raises(FeatureBuildError) as error:
        FEATURE_BUILDERS[feature_id].build_rows([record])
    assert any(
        violation.reason == "source_event_at is after freeze_at"
        for violation in error.value.audit.violations
    )


@pytest.mark.parametrize("field_name", RESULT_ALIAS_FIELDS)
@pytest.mark.parametrize("build_table", [False, True])
def test_past_racing_ability_rejects_result_aliases_with_valid_source_evidence(
    field_name: str, build_table: bool
) -> None:
    record = replace(_input("F02"), values={field_name: 35.0})
    builder = PastRacingAbilityBuilder()
    generate = (
        partial(builder.build, column_types={field_name: pa.float64()})
        if build_table
        else builder.build_rows
    )

    with pytest.raises(FeatureBuildError) as error:
        generate([record])

    assert any(
        violation.feature_id == "F02"
        and violation.field_name == field_name
        and violation.reason == "result-derived field is not allowed"
        for violation in error.value.audit.violations
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "last_3f_mean",
        "HaronTimeL3_delta",
        *[
            f"{prefix}_{alias}"
            for prefix in ("past", "previous", "historical", "history")
            for alias in ("last_3f_mean", "HaronTimeL3_delta")
        ],
        "past_target_race_last_3f_mean",
        "historical_target_race_HaronTimeL3_delta",
    ],
)
def test_non_target_result_alias_derivatives_are_preserved_by_builders_and_tables(
    field_name: str,
) -> None:
    record = replace(_input("F02"), values={field_name: 35.0})
    builder = PastRacingAbilityBuilder()
    rows = builder.build_rows([record])
    table = builder.build([record], column_types={field_name: pa.float64()})
    direct_table = build_feature_table(
        "past_racing_ability", rows, column_types={field_name: pa.float64()}
    )

    assert rows[0].values == {field_name: 35.0}
    assert table[field_name].to_pylist() == [35.0]
    assert direct_table.equals(table, check_metadata=True)


def test_new_tables_require_explicit_types_instead_of_inferring_them() -> None:
    with pytest.raises(ValueError, match="explicit column_types"):
        FEATURE_BUILDERS["F01"].build([_input("F01")])


def test_missing_rows_keep_keys_and_nulls_without_mutating_input() -> None:
    record = replace(
        _input("F01"),
        values={"past_finish": float("nan")},
        status="missing",
        available_at=None,
        source_event_at=None,
    )
    table = FEATURE_BUILDERS["F01"].build([record], column_types={"past_finish": pa.int64()})
    assert table["past_finish"].to_pylist() == [None]
    assert table["horse_id"].to_pylist() == ["horse-1"]
    assert record.values["past_finish"] != record.values["past_finish"]


def test_old_and_new_feature_tables_join_and_round_trip_together(tmp_path: Path) -> None:
    odds = build_odds_ratio(
        [
            OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0),
            OddsRatioInput("race-1", "horse-2", FREEZE_AT, AVAILABLE_AT, 4.0, 4.0),
        ]
    )
    record = replace(_input("F21"), values={"opponent_graph_known": True})
    graph = FEATURE_BUILDERS["F21"].build(
        [record], column_types={"opponent_graph_known": pa.bool_()}
    )
    table = join_feature_tables([odds, graph])
    assert table["horse_id"].to_pylist() == ["horse-1", "horse-2"]
    assert table["opponent_graph_known"].to_pylist() == [True, None]
    assert table["odds_ratio"].to_pylist() == [0.5, 1.0]
    path = tmp_path / "datamart.parquet"
    write_datamart(table, path)
    assert read_datamart(path).equals(table, check_metadata=True)


def test_feature_type_manifest_tampering_is_rejected() -> None:
    table = FEATURE_BUILDERS["F01"].build(
        [_input("F01")], column_types={"pre_race_value": pa.float64()}
    )
    metadata = dict(table.schema.metadata or {})
    metadata[b"keiba_ai.feature_column_types"] = json.dumps([["pre_race_value", "string"]]).encode()
    with pytest.raises(ValueError, match="must have type"):
        validate_feature_table(table.replace_schema_metadata(metadata))


@pytest.mark.parametrize(
    ("value", "value_type"),
    [(True, pa.float64()), (1.5, pa.int64()), (1, pa.bool_()), (2.0, pa.string())],
)
def test_declared_types_do_not_silently_coerce_values(
    value: object, value_type: pa.DataType
) -> None:
    row = FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {"pre_race_value": value})
    with pytest.raises(ValueError, match="does not match declared type"):
        build_feature_table(
            "recent_performance", [row], column_types={"pre_race_value": value_type}
        )


@pytest.mark.parametrize("field_name", ["KakuteiJyuni", *RESULT_ALIAS_FIELDS])
def test_result_columns_are_rejected_even_when_every_value_is_null(field_name: str) -> None:
    row = FeatureTableRow("race-1", "horse-1", FREEZE_AT, None, {field_name: None})
    with pytest.raises(ValueError, match="result-derived"):
        build_feature_table("recent_performance", [row], column_types={field_name: pa.int64()})


@pytest.mark.parametrize("field_name", RESULT_ALIAS_FIELDS)
def test_intermediate_table_rejects_result_aliases_with_valid_available_at(
    field_name: str,
) -> None:
    row = FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {field_name: 35.0})
    with pytest.raises(ValueError, match="result-derived"):
        build_feature_table("past_racing_ability", [row], column_types={field_name: pa.float64()})


def test_individual_builder_rejects_another_features_input_type() -> None:
    with pytest.raises(TypeError, match="RecentPerformanceInput"):
        FEATURE_BUILDERS["F01"].build_rows([_input("F02")])


def test_individual_market_builder_enforces_shared_race_totals() -> None:
    first = replace(_input("F19"), values={"ticket_total_tansyo": 100})
    second = replace(first, horse_id="horse-2", values={"ticket_total_tansyo": 200})
    with pytest.raises(FeatureBuildError) as error:
        FEATURE_BUILDERS["F19"].build_rows([first, second])
    assert any(
        violation.reason == "F19 ticket total must be identical within a race"
        for violation in error.value.audit.violations
    )


def test_existing_datamart_metadata_is_preserved() -> None:
    odds = build_odds_ratio(
        [OddsRatioInput("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, 2.0, 4.0)]
    )
    assert join_feature_tables([odds]).schema.metadata == {
        b"keiba_ai.table_kind": b"datamart",
        b"keiba_ai.feature_names": b'["odds_ratio"]',
    }


def test_new_datamart_validation_rejects_non_finite_values(tmp_path: Path) -> None:
    feature = FEATURE_BUILDERS["F01"].build(
        [_input("F01")], column_types={"pre_race_value": pa.float64()}
    )
    table = join_feature_tables([feature])
    index = table.column_names.index("pre_race_value")
    invalid = table.set_column(index, table.schema.field(index), pa.array([float("inf")]))
    with pytest.raises(ValueError, match="pre_race_value must be finite"):
        write_datamart(invalid, tmp_path / "datamart.parquet")
    assert not (tmp_path / "datamart.parquet").exists()
