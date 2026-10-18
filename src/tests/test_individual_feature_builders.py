"""Verify individual builders share middle rows, source audits and table storage."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pyarrow as pa
import pytest

from make_datamart.builder import join_feature_tables
from make_datamart.tables.parquet import read_datamart, write_datamart
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import FeatureBuildError, FeatureValuesInput
from make_features.generation.normalization import normalize_feature_inputs
from make_features.odds_ratio import OddsRatioInput, build_odds_ratio
from make_features.past_racing_ability import PastRacingAbilityBuilder
from make_features.tables.build import build_feature_table
from make_features.tables.parquet import read_feature_table, write_feature_table
from make_features.validation.table import validate_feature_table

REGISTRY = create_feature_registry(
    load_feature_definitions(Path(__file__).resolve().parents[2] / "config/features.toml")
)
FEATURE_GROUP_IDS = REGISTRY.feature_ids
FEATURE_GROUP_SPECS = REGISTRY.definitions
FEATURE_BUILDERS = {
    entry.definition.feature_id: entry.builder_type(entry.definition) for entry in REGISTRY.features
}
FEATURE_INPUT_TYPES = {entry.definition.feature_id: entry.input_type for entry in REGISTRY.features}

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = FREEZE_AT - timedelta(hours=1)
RESULT_FIELD_ALIASES = (
    "arrival",
    "arrival_rank",
    "confirmed_finish",
    "confirmed_result",
    "confirmed_time",
    "dead_heat",
    "earnings",
    "final_odds",
    "finish_position",
    "finish_result",
    "HaronTimeL3",
    "last_3f",
    "last3f",
    "last_odds",
    "margin",
    "ninki",
    "odds_final",
    "outcome",
    "passing_position",
    "payout",
    "payout_amount",
    "placing",
    "popularity",
    "position",
    "prize",
    "prize_money",
    "refund",
    "result_rank",
    "race_result",
    "result",
    "target_finish",
    "target_result",
    "target",
    "time",
    "time_diff",
    "win_flag",
    "winner",
)
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
            "passing_position",
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
    *(
        f"{prefix}{alias}_{suffix}"
        for prefix in ("target_", "target_race_", "TARGET-", "Target.Race.")
        for alias in RESULT_FIELD_ALIASES
        for suffix in ("mean", "delta", "zscore")
    ),
    "target_race_prize_money_mean",
    "target_race_popularity_mean",
    "target_race_last_odds_mean",
    "target_race_passing_position_mean",
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
    write_feature_table(table, path, registered_names=REGISTRY.names)
    assert read_feature_table(path, registered_names=REGISTRY.names).equals(
        table, check_metadata=True
    )


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
@pytest.mark.parametrize("value", [100.0, None])
def test_past_racing_ability_rejects_result_aliases_with_valid_source_evidence(
    field_name: str, build_table: bool, value: float | None
) -> None:
    record = replace(
        _input("F02"),
        values={field_name: value},
        status="missing" if value is None else "confirmed",
        available_at=None if value is None else AVAILABLE_AT,
    )
    builder = PastRacingAbilityBuilder(REGISTRY.by_name("past_racing_ability").definition)
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
        *[
            f"{alias}_{suffix}"
            for alias in (
                "confirmed_finish",
                "last_odds",
                "ninki",
                "popularity",
                "odds_final",
                "passing_position",
            )
            for suffix in ("mean", "delta", "zscore")
        ],
        *[
            f"{prefix}_{target_prefix}{alias}_mean"
            for prefix in ("past", "previous", "historical", "history")
            for target_prefix in ("", "target_", "target_race_")
            for alias in RESULT_FIELD_ALIASES
        ],
        *[
            f"{prefix}_passing_position_{suffix}"
            for prefix in ("past", "previous", "historical", "history")
            for suffix in ("delta", "zscore")
        ],
    ],
)
def test_non_target_result_alias_derivatives_are_preserved_by_builders_and_tables(
    field_name: str,
) -> None:
    record = replace(_input("F02"), values={field_name: 35.0})
    builder = PastRacingAbilityBuilder(REGISTRY.by_name("past_racing_ability").definition)
    rows = builder.build_rows([record])
    table = builder.build([record], column_types={field_name: pa.float64()})
    direct_table = build_feature_table(
        "past_racing_ability",
        rows,
        column_types={field_name: pa.float64()},
        registered_names=REGISTRY.names,
    )

    assert rows[0].values == {field_name: 35.0}
    assert table[field_name].to_pylist() == [35.0]
    assert direct_table.equals(table, check_metadata=True)


@pytest.mark.parametrize("prefix", ["target_", "target_race_"])
@pytest.mark.parametrize("alias", ["distance", "weight"])
def test_pre_race_target_metadata_is_preserved_by_builders_and_tables(
    prefix: str, alias: str
) -> None:
    field_name = f"{prefix}{alias}"
    record = replace(
        _input("F10"), values={field_name: 100.0}, source_scope="pre_race", source_race_ids=()
    )
    builder = FEATURE_BUILDERS["F10"]
    rows = builder.build_rows([record])
    table = builder.build([record], column_types={field_name: pa.float64()})
    direct_table = build_feature_table(
        builder.feature_name,
        rows,
        column_types={field_name: pa.float64()},
        registered_names=REGISTRY.names,
    )

    assert rows[0].values == {field_name: 100.0}
    assert table[field_name].to_pylist() == [100.0]
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
    table = join_feature_tables([odds, graph], registered_names=REGISTRY.names)
    assert table["horse_id"].to_pylist() == ["horse-1", "horse-2"]
    assert table["opponent_graph_known"].to_pylist() == [True, None]
    assert table["odds_ratio"].to_pylist() == [0.5, 1.0]
    path = tmp_path / "datamart.parquet"
    write_datamart(table, path, registered_names=REGISTRY.names)
    assert read_datamart(path, registered_names=REGISTRY.names).equals(table, check_metadata=True)


def test_feature_type_manifest_tampering_is_rejected() -> None:
    table = FEATURE_BUILDERS["F01"].build(
        [_input("F01")], column_types={"pre_race_value": pa.float64()}
    )
    metadata = dict(table.schema.metadata or {})
    metadata[b"keiba_ai.feature_column_types"] = json.dumps([["pre_race_value", "string"]]).encode()
    with pytest.raises(ValueError, match="must have type"):
        validate_feature_table(
            table.replace_schema_metadata(metadata), registered_names=REGISTRY.names
        )


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
            "recent_performance",
            [row],
            column_types={"pre_race_value": value_type},
            registered_names=REGISTRY.names,
        )


@pytest.mark.parametrize("field_name", ["KakuteiJyuni", *RESULT_ALIAS_FIELDS])
def test_result_columns_are_rejected_even_when_every_value_is_null(field_name: str) -> None:
    row = FeatureTableRow("race-1", "horse-1", FREEZE_AT, None, {field_name: None})
    with pytest.raises(ValueError, match="result-derived"):
        build_feature_table(
            "recent_performance",
            [row],
            column_types={field_name: pa.int64()},
            registered_names=REGISTRY.names,
        )


@pytest.mark.parametrize("field_name", RESULT_ALIAS_FIELDS)
@pytest.mark.parametrize("value", [100.0, None])
def test_intermediate_table_rejects_result_aliases_with_valid_available_at(
    field_name: str, value: float | None
) -> None:
    row = FeatureTableRow("race-1", "horse-1", FREEZE_AT, AVAILABLE_AT, {field_name: value})
    with pytest.raises(ValueError, match="result-derived"):
        build_feature_table(
            "past_racing_ability",
            [row],
            column_types={field_name: pa.float64()},
            registered_names=REGISTRY.names,
        )


@pytest.mark.parametrize("feature_id", FEATURE_GROUP_IDS)
def test_individual_builder_rejects_another_features_input_type(feature_id: str) -> None:
    other_id = "F02" if feature_id == "F01" else "F01"
    with pytest.raises(TypeError, match=FEATURE_INPUT_TYPES[feature_id].__name__):
        FEATURE_BUILDERS[feature_id].build_rows([_input(other_id)])


@pytest.mark.parametrize("feature_id", FEATURE_GROUP_IDS)
def test_individual_builder_preserves_empty_rows_and_explicit_table_schema(feature_id: str) -> None:
    field_name = next(iter(_input(feature_id).values))
    builder = FEATURE_BUILDERS[feature_id]

    assert builder.build_rows([]) == []
    table = builder.build([], column_types={field_name: pa.float64()})

    assert table.num_rows == 0
    assert table.schema.field(field_name).type == pa.float64()
    assert table.schema.field("freeze_at").type == pa.timestamp("us", tz="UTC")


def test_shared_public_normalization_still_audits_explicit_inputs() -> None:
    record = _input("F01")
    rows = normalize_feature_inputs([record], "F01", FEATURE_INPUT_TYPES["F01"])

    assert len(rows) == 1
    assert rows[0].race_id == record.race_id
    assert rows[0].horse_id == record.horse_id
    assert rows[0].freeze_at == FREEZE_AT
    assert rows[0].available_at == AVAILABLE_AT
    assert rows[0].values == record.values
    with pytest.raises(FeatureBuildError):
        normalize_feature_inputs(
            [replace(record, contains_future_data=True)], "F01", FEATURE_INPUT_TYPES["F01"]
        )


def test_individual_market_builder_stops_at_shared_audit_failure() -> None:
    record = replace(_input("F19"), contains_future_data=True, values={"market_unknown": 1.0})

    with pytest.raises(FeatureBuildError) as error:
        FEATURE_BUILDERS["F19"].build_rows([record])

    assert error.value.audit.records_checked == 1
    assert error.value.audit.groups_checked == 1
    assert error.value.audit.non_missing_values == 1
    assert [violation.reason for violation in error.value.audit.violations] == [
        "future data is not allowed"
    ]


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
    assert join_feature_tables([odds], registered_names=REGISTRY.names).schema.metadata == {
        b"keiba_ai.table_kind": b"datamart",
        b"keiba_ai.feature_names": b'["odds_ratio"]',
    }


def test_new_datamart_validation_rejects_non_finite_values(tmp_path: Path) -> None:
    feature = FEATURE_BUILDERS["F01"].build(
        [_input("F01")], column_types={"pre_race_value": pa.float64()}
    )
    table = join_feature_tables([feature], registered_names=REGISTRY.names)
    index = table.column_names.index("pre_race_value")
    invalid = table.set_column(index, table.schema.field(index), pa.array([float("inf")]))
    with pytest.raises(ValueError, match="pre_race_value must be finite"):
        write_datamart(invalid, tmp_path / "datamart.parquet", registered_names=REGISTRY.names)
    assert not (tmp_path / "datamart.parquet").exists()
