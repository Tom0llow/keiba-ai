"""Tests for the explicit F01-F21 explanatory-variable boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from features.catalog.loader import load_feature_definitions
from features.catalog.registry import create_feature_registry
from features.contracts.rows import FeatureTableRow
from features.explanatory_variables import (
    FeatureBatchInput,
    FeatureBuildError,
    FeatureGroupInput,
    audit_feature_inputs,
    build_explanatory_variables,
)
from models.ranking_dataset import FeatureSchema

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
AVAILABLE_AT = datetime(2025, 12, 31, 12, tzinfo=UTC)
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


def _record(
    *,
    race_id: str = "race-1",
    horse_id: str = "horse-1",
    freeze_at: datetime = FREEZE_AT,
) -> FeatureBatchInput:
    groups = {
        feature_id: FeatureGroupInput(
            feature_id=feature_id,
            values=({"market_win_odds": 1.0} if feature_id == "F19" else {"feature_value": 1.0}),
            available_at=AVAILABLE_AT,
            source_event_at=AVAILABLE_AT,
            source_scope="historical",
            status="confirmed",
            source_race_ids=("past-race-1",),
            contains_target_result=False,
            contains_future_data=False,
        )
        for feature_id in FEATURE_GROUP_IDS
    }
    return FeatureBatchInput(race_id, horse_id, freeze_at, groups)


def test_build_variables_keeps_all_21_groups_outside_model_schema() -> None:
    result = build_explanatory_variables([_record()], registry=REGISTRY)

    assert tuple(result.inputs[0].groups) == FEATURE_GROUP_IDS
    assert tuple(spec.feature_id for spec in FEATURE_GROUP_SPECS) == FEATURE_GROUP_IDS
    assert result.inputs[0].groups["F01"].available_at == AVAILABLE_AT
    assert result.inputs[0].groups["F21"].values["feature_value"] == 1.0
    assert tuple(result.rows) == FEATURE_GROUP_IDS
    assert all(isinstance(rows[0], FeatureTableRow) for rows in result.rows.values())
    assert result.rows["F01"][0].values == {"feature_value": 1.0}
    assert result.rows["F01"][0].freeze_at == FREEZE_AT
    assert result.audit.valid


def test_batch_rows_match_individual_builders_with_utc_and_missing_values() -> None:
    first = _record(horse_id="horse-1")
    second = _record(horse_id="horse-2")
    records = [
        replace(
            first,
            freeze_at="2026-01-01T21:00:00+09:00",
            groups={
                feature_id: replace(
                    group,
                    available_at="2025-12-31T21:00:00+09:00",
                    source_event_at="2025-12-31T21:00:00+09:00",
                )
                for feature_id, group in first.groups.items()
            },
        ),
        replace(
            second,
            groups={
                feature_id: replace(
                    group,
                    values=dict.fromkeys(group.values, float("nan")),
                    available_at=None,
                    source_event_at=None,
                    status="missing",
                )
                for feature_id, group in second.groups.items()
            },
        ),
    ]

    result = build_explanatory_variables(records, registry=REGISTRY)

    for registration in REGISTRY.features:
        feature_id = registration.definition.feature_id
        individual_inputs = [
            registration.input_type(
                feature_id=feature_id,
                race_id=record.race_id,
                horse_id=record.horse_id,
                freeze_at=record.freeze_at,
                values=record.groups[feature_id].values,
                available_at=record.groups[feature_id].available_at,
                source_event_at=record.groups[feature_id].source_event_at,
                source_scope=record.groups[feature_id].source_scope,
                status=record.groups[feature_id].status,
                source_race_ids=record.groups[feature_id].source_race_ids,
                contains_target_result=False,
                contains_future_data=False,
            )
            for record in records
        ]
        builder = registration.builder_type(registration.definition)
        individual_rows = builder.build_rows(individual_inputs)
        for batch_row, individual_row in zip(result.rows[feature_id], individual_rows, strict=True):
            assert batch_row.race_id == individual_row.race_id
            assert batch_row.horse_id == individual_row.horse_id
            assert batch_row.freeze_at == individual_row.freeze_at
            assert batch_row.available_at == individual_row.available_at
            assert batch_row.values == individual_row.values
        assert result.rows[feature_id][0].freeze_at == FREEZE_AT
        assert result.rows[feature_id][0].available_at == AVAILABLE_AT
        assert result.rows[feature_id][1].available_at is None
        assert set(result.rows[feature_id][1].values.values()) == {None}
    assert result.audit.records_checked == 2
    assert result.audit.groups_checked == 42
    assert result.audit.non_missing_values == 21
    assert result.audit.missing_values == 21


def test_batch_generation_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError, match="requires at least one record"):
        build_explanatory_variables([], registry=REGISTRY)


def test_feature_groups_are_not_added_to_feature_schema_allow_list() -> None:
    with pytest.raises(ValueError, match="approved allow-list"):
        FeatureSchema.from_names(("F01",), schema_id="feature-not-model-v1")


def test_missing_feature_is_retained_without_available_at() -> None:
    record = _record()
    missing_group = FeatureGroupInput(
        feature_id="F19",
        values={"market_win_odds": None},
        available_at=None,
        source_event_at=None,
        source_scope="pre_race",
        status="missing",
        contains_target_result=False,
        contains_future_data=False,
    )
    record = replace(record, groups={**record.groups, "F19": missing_group})

    result = build_explanatory_variables([record], registry=REGISTRY)

    assert result.inputs[0].groups["F19"].values["market_win_odds"] is None
    assert result.inputs[0].groups["F19"].available_at is None
    assert result.audit.missing_values == 1


def test_future_feature_is_rejected() -> None:
    record = _record()
    future_group = replace(
        record.groups["F01"],
        available_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )
    record = replace(record, groups={**record.groups, "F01": future_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record], registry=REGISTRY)

    violation = error.value.audit.violations[0]
    assert violation.feature_id == "F01"
    assert "after freeze_at" in violation.reason


@pytest.mark.parametrize("source_scope", ["historical", "pre_race"])
def test_source_event_after_freeze_is_rejected_for_any_source_scope(
    source_scope: str,
) -> None:
    record = _record()
    future_source_group = replace(
        record.groups["F01"],
        available_at=AVAILABLE_AT,
        source_event_at=FREEZE_AT.replace(minute=1),
        source_scope=source_scope,
    )
    record = replace(record, groups={**record.groups, "F01": future_source_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record], registry=REGISTRY)

    assert any(
        violation.reason == "source_event_at is after freeze_at"
        for violation in error.value.audit.violations
    )
    violation = next(
        violation
        for violation in error.value.audit.violations
        if violation.reason == "source_event_at is after freeze_at"
    )
    assert violation.source_event_at == FREEZE_AT.replace(minute=1)
    assert violation.available_at is None


def test_feature_boundary_flags_are_required_in_dataclass_api() -> None:
    group = _record().groups["F01"]
    constructor = cast(Callable[..., FeatureGroupInput], FeatureGroupInput)

    with pytest.raises(TypeError, match="contains_target_result"):
        constructor(
            feature_id=group.feature_id,
            values=group.values,
            available_at=group.available_at,
            source_event_at=group.source_event_at,
            source_scope=group.source_scope,
            status=group.status,
            source_race_ids=group.source_race_ids,
        )


def test_freeze_at_is_required_by_python_api() -> None:
    record = replace(_record(), freeze_at=cast(datetime, None))

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record], registry=REGISTRY)

    assert any(
        violation.reason == "freeze_at is required" for violation in error.value.audit.violations
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "target_race_result",
        "target_arrival",
        "market_final_odds",
        "target_race_speed",
        "target_kakutei_jyuni",
        "target_nyusen_jyuni",
        "KakuteiJyuni",
        "NyusenJyuni",
        "Time",
        "TimeDiff",
        "target_race_payout",
        "target_race_final_odds",
        "target_win_flag",
        "target_race_win_flag",
        "target_finish",
        "target_placing",
        "target_rank",
        "target_winner",
        "target_outcome",
        "target_score",
        "target_finish_position",
        "finish_time",
        "arrival_time",
        "winner_flag",
        "target",
        "win_flag",
        "result_score",
        "result_time",
        "race_result",
        "race_result_score",
        "finish_position",
        *[
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
                "last_odds",
                "ninki",
                "popularity",
                "odds_final",
                "passing_position",
            )
        ],
        "LAST-3F",
        "haron.time.l3",
        "TARGET-LAST.3F",
        "Target.Race.HARON-TIME-L3",
        "TARGET-RACE-CONFIRMED.TIME",
        "Target.Race.Dead-Heat",
        "target-race-EARNINGS",
        "TARGET.RACE.Margin",
        "target_race_last_3f_mean",
        "target_race_HaronTimeL3_delta",
        "target_confirmed_time_zscore",
        "target_dead_heat_count",
        "target_race_earnings_mean",
        "target_margin_delta",
        *[
            f"{prefix}{alias}_{suffix}"
            for prefix in ("target_", "target_race_", "TARGET-", "Target.Race.")
            for alias in RESULT_FIELD_ALIASES
            for suffix in ("mean", "delta", "zscore")
        ],
        "target_race_prize_money_mean",
        "target_race_popularity_mean",
        "target_race_last_odds_mean",
        "target_race_passing_position_mean",
    ],
)
@pytest.mark.parametrize("value", [100.0, None])
def test_result_derived_feature_field_names_are_rejected(
    field_name: str, value: float | None
) -> None:
    record = _record()
    result_group = replace(
        record.groups["F01"],
        values={field_name: value},
        status="missing" if value is None else "confirmed",
        available_at=None if value is None else AVAILABLE_AT,
    )
    record = replace(record, groups={**record.groups, "F01": result_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record], registry=REGISTRY)

    assert any(
        violation.field_name == field_name
        and violation.reason == "result-derived field is not allowed"
        for violation in error.value.audit.violations
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "market_win_odds",
        "market_win_rank",
        "market_rank_change",
        "previous_race_result",
        "previous_race_finish_position",
        *[
            f"{prefix}_{alias}"
            for prefix in ("past", "previous", "historical", "history")
            for alias in (
                "last_3f",
                "last3f",
                "HaronTimeL3",
                "confirmed_time",
                "dead_heat",
                "earnings",
                "margin",
            )
        ],
        "history_result",
        "PAST-LAST.3F",
        "Historical.HARON-TIME-L3",
        "last_3f_mean",
        "HaronTimeL3_delta",
        "confirmed_time_zscore",
        "dead_heat_count",
        "earnings_mean",
        "margin_delta",
        "past_last_3f_mean",
        "previous_HaronTimeL3_delta",
        "historical_confirmed_time_zscore",
        "history_earnings_mean",
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
def test_market_and_historical_fields_are_not_treated_as_result_fields(
    field_name: str,
) -> None:
    record = _record()
    feature_id = "F19" if field_name.startswith("market") else "F01"
    group = replace(record.groups[feature_id], values={field_name: 1})
    record = replace(record, groups={**record.groups, feature_id: group})

    result = build_explanatory_variables([record], registry=REGISTRY)

    assert result.audit.valid


@pytest.mark.parametrize("prefix", ["target_", "target_race_"])
@pytest.mark.parametrize("alias", ["distance", "weight"])
def test_pre_race_target_metadata_is_not_treated_as_result_fields(prefix: str, alias: str) -> None:
    record = _record()
    field_name = f"{prefix}{alias}"
    group = replace(
        record.groups["F10"],
        values={field_name: 100.0},
        source_scope="pre_race",
        source_race_ids=(),
    )
    record = replace(record, groups={**record.groups, "F10": group})

    result = build_explanatory_variables([record], registry=REGISTRY)

    assert result.audit.valid
    assert result.rows["F10"][0].values == {field_name: 100.0}


@pytest.mark.parametrize(
    ("feature_id", "field_name"),
    [
        ("F09", "relative_metric_rank"),
        ("F09", "relative_metric_zscore"),
        ("F20", "same_gate_ability_rank"),
        ("F20", "same_gate_ability_zscore"),
        ("F20", "same_trainer_ability_rank"),
        ("F20", "same_trainer_ability_zscore"),
        ("F21", "opponent_graph_score"),
    ],
)
def test_relative_rank_and_score_variables_are_not_result_fields(
    feature_id: str,
    field_name: str,
) -> None:
    record = _record()
    group = replace(record.groups[feature_id], values={field_name: 1.0})
    record = replace(record, groups={**record.groups, feature_id: group})

    result = build_explanatory_variables([record], registry=REGISTRY)

    assert result.audit.valid


@pytest.mark.parametrize(
    "field_name",
    [
        "ticket_total_tansyo",
        "ticket_total_fukusyo",
        "ticket_total_wakuren",
        "ticket_total_umaren",
        "ticket_total_growth_tansyo",
        "ticket_total_growth_fukusyo",
        "ticket_total_growth_wakuren",
        "ticket_total_growth_umaren",
        "ticket_total_growth_rate_tansyo",
        "ticket_total_growth_rate_fukusyo",
        "ticket_total_growth_rate_wakuren",
        "ticket_total_growth_rate_umaren",
        "market_pair_support_i",
    ],
)
def test_f19_documented_market_fields_are_allowed(field_name: str) -> None:
    record = _record()
    market_group = replace(record.groups["F19"], values={field_name: 1})
    record = replace(record, groups={**record.groups, "F19": market_group})

    result = build_explanatory_variables([record], registry=REGISTRY)

    assert result.audit.valid


@pytest.mark.parametrize(
    "field_name",
    ["market_unknown", "market_pair_support", "ticket_total_final_odds"],
)
def test_f19_rejects_undocumented_market_fields(field_name: str) -> None:
    record = _record()
    market_group = replace(record.groups["F19"], values={field_name: 1})
    record = replace(record, groups={**record.groups, "F19": market_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record], registry=REGISTRY)

    assert any(
        violation.field_name == field_name and violation.reason == "F19 market field is not allowed"
        for violation in error.value.audit.violations
    )


def test_batch_audit_appends_market_violations_after_shared_failures() -> None:
    record = _record()
    record = replace(
        record,
        groups={
            **record.groups,
            "F19": replace(
                record.groups["F19"],
                contains_future_data=True,
                values={"market_unknown": 1.0},
            ),
        },
    )

    audit = audit_feature_inputs([record], registry=REGISTRY)
    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record], registry=REGISTRY)

    assert error.value.audit == audit
    assert audit.records_checked == 1
    assert audit.groups_checked == 21
    assert audit.non_missing_values == 21
    assert [violation.reason for violation in audit.violations] == [
        "future data is not allowed",
        "F19 market field is not allowed",
    ]
    assert [violation.feature_id for violation in audit.violations] == ["F19", "F19"]


def test_f19_ticket_totals_must_be_shared_within_a_race() -> None:
    first = _record(horse_id="horse-1")
    second = _record(horse_id="horse-2")
    first_group = replace(first.groups["F19"], values={"ticket_total_tansyo": 100})
    second_group = replace(second.groups["F19"], values={"ticket_total_tansyo": 200})
    first = replace(first, groups={**first.groups, "F19": first_group})
    second = replace(second, groups={**second.groups, "F19": second_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([first, second], registry=REGISTRY)

    assert any(
        violation.reason == "F19 ticket total must be identical within a race"
        for violation in error.value.audit.violations
    )


def test_non_feature_group_value_is_reported_as_generation_error() -> None:
    record = _record()
    groups: dict[str, FeatureGroupInput | None] = dict(record.groups)
    groups["F01"] = None
    malformed_record = replace(
        record,
        groups=cast(Mapping[str, FeatureGroupInput], groups),
    )

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([malformed_record], registry=REGISTRY)

    assert any(
        violation.reason == "groups must contain FeatureGroupInput values"
        for violation in error.value.audit.violations
    )


@pytest.mark.parametrize(
    ("attribute", "value", "reason"),
    [
        ("source_scope", "unknown", "source_scope must be pre_race or historical"),
        ("status", "unknown", "status must be confirmed, missing, or unconfirmed"),
        (
            "source_race_ids",
            ("past-race-1", 1),
            "source_race_ids must contain non-empty strings",
        ),
    ],
)
def test_invalid_feature_group_metadata_is_rejected(
    attribute: str,
    value: object,
    reason: str,
) -> None:
    record = _record()
    if attribute == "source_scope":
        group = replace(record.groups["F01"], source_scope=cast(str, value))
    elif attribute == "status":
        group = replace(record.groups["F01"], status=cast(str, value))
    else:
        group = replace(
            record.groups["F01"],
            source_race_ids=cast(tuple[str, ...], value),
        )

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables(
            [replace(record, groups={**record.groups, "F01": group})], registry=REGISTRY
        )

    assert any(violation.reason == reason for violation in error.value.audit.violations)


def test_feature_group_set_must_be_exactly_f01_through_f21() -> None:
    record = _record()
    missing_groups = dict(record.groups)
    del missing_groups["F21"]
    with pytest.raises(FeatureBuildError) as missing_error:
        build_explanatory_variables([replace(record, groups=missing_groups)], registry=REGISTRY)
    assert any(
        violation.reason == "feature group is missing" and violation.feature_id == "F21"
        for violation in missing_error.value.audit.violations
    )

    extra_groups = dict(record.groups)
    extra_groups["F22"] = replace(record.groups["F21"], feature_id="F22")
    with pytest.raises(FeatureBuildError) as extra_error:
        build_explanatory_variables([replace(record, groups=extra_groups)], registry=REGISTRY)
    assert any(
        violation.reason == "feature group is not registered" and violation.feature_id == "F22"
        for violation in extra_error.value.audit.violations
    )


def test_feature_boundary_violations_are_rejected() -> None:
    record = _record()
    base_group = record.groups["F01"]
    updates = (
        replace(base_group, contains_target_result=True),
        replace(base_group, contains_future_data=True),
        replace(base_group, status="unconfirmed"),
        replace(base_group, source_race_ids=("race-1",)),
        replace(base_group, values={"finish_position": 1}),
    )
    for update in updates:
        updated_groups = {
            **record.groups,
            "F01": update,
        }
        with pytest.raises(FeatureBuildError):
            build_explanatory_variables([replace(record, groups=updated_groups)], registry=REGISTRY)


def test_same_race_requires_one_freeze_time_and_stable_feature_columns() -> None:
    first = _record(horse_id="horse-1")
    second = _record(horse_id="horse-2", freeze_at=FREEZE_AT.replace(minute=13))
    second_group = replace(second.groups["F01"], values={"other_value": 1.0})
    second = replace(second, groups={**second.groups, "F01": second_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([first, second], registry=REGISTRY)

    reasons = {violation.reason for violation in error.value.audit.violations}
    assert "freeze_at must be identical for all rows in a race" in reasons
    assert "feature field names must be identical within a race" in reasons


def test_duplicate_horse_and_non_contiguous_race_rows_are_rejected() -> None:
    records = [_record(race_id="race-1", horse_id="horse-1"), _record(race_id="race-2")]
    records.append(_record(race_id="race-1", horse_id="horse-2"))

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables(records, registry=REGISTRY)

    reasons = {violation.reason for violation in error.value.audit.violations}
    assert "rows for each race must be contiguous" in reasons

    duplicate_records = [_record(), _record(horse_id="horse-1")]
    with pytest.raises(FeatureBuildError) as duplicate_error:
        build_explanatory_variables(duplicate_records, registry=REGISTRY)
    assert any(
        violation.reason == "horse_id must be unique within a race"
        for violation in duplicate_error.value.audit.violations
    )
