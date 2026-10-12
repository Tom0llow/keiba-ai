"""Tests for the explicit F01-F21 explanatory-variable boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from features.basic_conditions_and_weight import SPEC as F10_SPEC
from features.common.rows import FeatureTableRow
from features.condition_adjusted_ability import SPEC as F03_SPEC
from features.condition_suitability import SPEC as F05_SPEC
from features.expected_race_development import SPEC as F13_SPEC
from features.explanatory_variables import (
    FEATURE_GROUP_IDS,
    FEATURE_GROUP_SPECS,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureGroupInput,
    build_explanatory_variables,
)
from features.hill_and_wood_workouts import SPEC as F17_SPEC
from features.history_volume_and_missingness import SPEC as F15_SPEC
from features.jockey_combination import SPEC as F11_SPEC
from features.jockey_performance import SPEC as F07_SPEC
from features.market_characteristics import SPEC as F19_SPEC
from features.opponent_pagerank import SPEC as F21_SPEC
from features.past_body_weight import SPEC as F16_SPEC
from features.past_lap_and_running_style import SPEC as F18_SPEC
from features.past_racing_ability import SPEC as F02_SPEC
from features.pedigree_suitability import SPEC as F14_SPEC
from features.recent_performance import SPEC as F01_SPEC
from features.recent_stability import SPEC as F04_SPEC
from features.rest_and_condition_change import SPEC as F06_SPEC
from features.running_style_and_position import SPEC as F12_SPEC
from features.same_gate_and_trainer_relative import SPEC as F20_SPEC
from features.trainer_performance import SPEC as F08_SPEC
from features.within_race_relative import SPEC as F09_SPEC
from models.ranking_dataset import FeatureSchema

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = datetime(2025, 12, 31, 12, tzinfo=UTC)


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
    result = build_explanatory_variables([_record()])

    assert tuple(result.inputs[0].groups) == FEATURE_GROUP_IDS
    assert tuple(spec.feature_id for spec in FEATURE_GROUP_SPECS) == FEATURE_GROUP_IDS
    assert result.inputs[0].groups["F01"].available_at == AVAILABLE_AT
    assert result.inputs[0].groups["F21"].values["feature_value"] == 1.0
    assert tuple(result.rows) == FEATURE_GROUP_IDS
    assert all(isinstance(rows[0], FeatureTableRow) for rows in result.rows.values())
    assert result.rows["F01"][0].values == {"feature_value": 1.0}
    assert result.rows["F01"][0].freeze_at == FREEZE_AT
    assert result.audit.valid


def test_each_feature_group_has_its_own_spec_module() -> None:
    specs = (
        F01_SPEC,
        F02_SPEC,
        F03_SPEC,
        F04_SPEC,
        F05_SPEC,
        F06_SPEC,
        F07_SPEC,
        F08_SPEC,
        F09_SPEC,
        F10_SPEC,
        F11_SPEC,
        F12_SPEC,
        F13_SPEC,
        F14_SPEC,
        F15_SPEC,
        F16_SPEC,
        F17_SPEC,
        F18_SPEC,
        F19_SPEC,
        F20_SPEC,
        F21_SPEC,
    )

    assert tuple(spec.feature_id for spec in specs) == FEATURE_GROUP_IDS
    assert specs == FEATURE_GROUP_SPECS


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

    result = build_explanatory_variables([record])

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
        build_explanatory_variables([record])

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
        build_explanatory_variables([record])

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
        build_explanatory_variables([record])

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
    ],
)
def test_result_derived_feature_field_names_are_rejected(field_name: str) -> None:
    record = _record()
    result_group = replace(record.groups["F01"], values={field_name: 1.0})
    record = replace(record, groups={**record.groups, "F01": result_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([record])

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
    ],
)
def test_market_and_historical_fields_are_not_treated_as_result_fields(
    field_name: str,
) -> None:
    record = _record()
    feature_id = "F19" if field_name.startswith("market") else "F01"
    group = replace(record.groups[feature_id], values={field_name: 1})
    record = replace(record, groups={**record.groups, feature_id: group})

    result = build_explanatory_variables([record])

    assert result.audit.valid


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

    result = build_explanatory_variables([record])

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

    result = build_explanatory_variables([record])

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
        build_explanatory_variables([record])

    assert any(
        violation.field_name == field_name and violation.reason == "F19 market field is not allowed"
        for violation in error.value.audit.violations
    )


def test_f19_ticket_totals_must_be_shared_within_a_race() -> None:
    first = _record(horse_id="horse-1")
    second = _record(horse_id="horse-2")
    first_group = replace(first.groups["F19"], values={"ticket_total_tansyo": 100})
    second_group = replace(second.groups["F19"], values={"ticket_total_tansyo": 200})
    first = replace(first, groups={**first.groups, "F19": first_group})
    second = replace(second, groups={**second.groups, "F19": second_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([first, second])

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
        build_explanatory_variables([malformed_record])

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
        build_explanatory_variables([replace(record, groups={**record.groups, "F01": group})])

    assert any(violation.reason == reason for violation in error.value.audit.violations)


def test_feature_group_set_must_be_exactly_f01_through_f21() -> None:
    record = _record()
    missing_groups = dict(record.groups)
    del missing_groups["F21"]
    with pytest.raises(FeatureBuildError) as missing_error:
        build_explanatory_variables([replace(record, groups=missing_groups)])
    assert any(
        violation.reason == "feature group is missing" and violation.feature_id == "F21"
        for violation in missing_error.value.audit.violations
    )

    extra_groups = dict(record.groups)
    extra_groups["F22"] = replace(record.groups["F21"], feature_id="F22")
    with pytest.raises(FeatureBuildError) as extra_error:
        build_explanatory_variables([replace(record, groups=extra_groups)])
    assert any(
        violation.reason == "feature group is not F01-F21" and violation.feature_id == "F22"
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
            build_explanatory_variables([replace(record, groups=updated_groups)])


def test_same_race_requires_one_freeze_time_and_stable_feature_columns() -> None:
    first = _record(horse_id="horse-1")
    second = _record(horse_id="horse-2", freeze_at=FREEZE_AT.replace(minute=13))
    second_group = replace(second.groups["F01"], values={"other_value": 1.0})
    second = replace(second, groups={**second.groups, "F01": second_group})

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables([first, second])

    reasons = {violation.reason for violation in error.value.audit.violations}
    assert "freeze_at must be identical for all rows in a race" in reasons
    assert "feature field names must be identical within a race" in reasons


def test_duplicate_horse_and_non_contiguous_race_rows_are_rejected() -> None:
    records = [_record(race_id="race-1", horse_id="horse-1"), _record(race_id="race-2")]
    records.append(_record(race_id="race-1", horse_id="horse-2"))

    with pytest.raises(FeatureBuildError) as error:
        build_explanatory_variables(records)

    reasons = {violation.reason for violation in error.value.audit.violations}
    assert "rows for each race must be contiguous" in reasons

    duplicate_records = [_record(), _record(horse_id="horse-1")]
    with pytest.raises(FeatureBuildError) as duplicate_error:
        build_explanatory_variables(duplicate_records)
    assert any(
        violation.reason == "horse_id must be unique within a race"
        for violation in duplicate_error.value.audit.violations
    )
