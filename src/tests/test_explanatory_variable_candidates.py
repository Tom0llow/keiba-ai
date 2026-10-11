"""Tests for the explicit F01-F21 candidate feature boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from features.explanatory_variable_candidates import (
    CANDIDATE_GROUP_IDS,
    CANDIDATE_GROUP_SPECS,
    CandidateGenerationError,
    CandidateGroupInput,
    CandidateRecord,
    build_explanatory_variable_candidates,
)
from models.ranking_dataset import FeatureSchema

FREEZE_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
AVAILABLE_AT = datetime(2025, 12, 31, 12, tzinfo=UTC)


def _record(
    *,
    race_id: str = "race-1",
    horse_id: str = "horse-1",
    freeze_at: datetime = FREEZE_AT,
) -> CandidateRecord:
    groups = {
        group_id: CandidateGroupInput(
            group_id=group_id,
            values=({"market_win_odds": 1.0} if group_id == "F19" else {"candidate_value": 1.0}),
            available_at=AVAILABLE_AT,
            source_event_at=AVAILABLE_AT,
            source_scope="historical",
            status="confirmed",
            source_race_ids=("past-race-1",),
            contains_target_result=False,
            contains_future_data=False,
        )
        for group_id in CANDIDATE_GROUP_IDS
    }
    return CandidateRecord(race_id, horse_id, freeze_at, groups)


def test_build_candidates_keeps_all_21_groups_outside_model_schema() -> None:
    result = build_explanatory_variable_candidates([_record()])

    assert tuple(result.records[0].groups) == CANDIDATE_GROUP_IDS
    assert tuple(spec.group_id for spec in CANDIDATE_GROUP_SPECS) == CANDIDATE_GROUP_IDS
    assert result.records[0].groups["F01"].available_at == AVAILABLE_AT
    assert result.records[0].groups["F21"].values["candidate_value"] == 1.0
    assert result.audit.valid


def test_candidate_groups_are_not_added_to_feature_schema_allow_list() -> None:
    with pytest.raises(ValueError, match="approved allow-list"):
        FeatureSchema.from_names(("F01",), schema_id="candidate-not-model-v1")


def test_missing_candidate_is_retained_without_available_at() -> None:
    record = _record()
    missing_group = CandidateGroupInput(
        group_id="F19",
        values={"market_win_odds": None},
        available_at=None,
        source_event_at=None,
        source_scope="pre_race",
        status="missing",
        contains_target_result=False,
        contains_future_data=False,
    )
    record = replace(record, groups={**record.groups, "F19": missing_group})

    result = build_explanatory_variable_candidates([record])

    assert result.records[0].groups["F19"].values["market_win_odds"] is None
    assert result.records[0].groups["F19"].available_at is None
    assert result.audit.missing_values == 1


def test_future_candidate_is_rejected() -> None:
    record = _record()
    future_group = replace(
        record.groups["F01"],
        available_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )
    record = replace(record, groups={**record.groups, "F01": future_group})

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([record])

    violation = error.value.audit.violations[0]
    assert violation.group_id == "F01"
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

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([record])

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


def test_candidate_boundary_flags_are_required_in_dataclass_api() -> None:
    group = _record().groups["F01"]
    constructor = cast(Callable[..., CandidateGroupInput], CandidateGroupInput)

    with pytest.raises(TypeError, match="contains_target_result"):
        constructor(
            group_id=group.group_id,
            values=group.values,
            available_at=group.available_at,
            source_event_at=group.source_event_at,
            source_scope=group.source_scope,
            status=group.status,
            source_race_ids=group.source_race_ids,
        )


def test_freeze_at_is_required_by_python_api() -> None:
    record = replace(_record(), freeze_at=cast(datetime, None))

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([record])

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
    ],
)
def test_result_derived_candidate_field_names_are_rejected(field_name: str) -> None:
    record = _record()
    result_group = replace(record.groups["F01"], values={field_name: 1.0})
    record = replace(record, groups={**record.groups, "F01": result_group})

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([record])

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
    ],
)
def test_market_and_historical_fields_are_not_treated_as_result_fields(
    field_name: str,
) -> None:
    record = _record()
    group_id = "F19" if field_name.startswith("market") else "F01"
    group = replace(record.groups[group_id], values={field_name: 1})
    record = replace(record, groups={**record.groups, group_id: group})

    result = build_explanatory_variable_candidates([record])

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

    result = build_explanatory_variable_candidates([record])

    assert result.audit.valid


@pytest.mark.parametrize(
    "field_name",
    ["market_unknown", "market_pair_support", "ticket_total_final_odds"],
)
def test_f19_rejects_undocumented_market_fields(field_name: str) -> None:
    record = _record()
    market_group = replace(record.groups["F19"], values={field_name: 1})
    record = replace(record, groups={**record.groups, "F19": market_group})

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([record])

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

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([first, second])

    assert any(
        violation.reason == "F19 ticket total must be identical within a race"
        for violation in error.value.audit.violations
    )


def test_non_candidate_group_value_is_reported_as_generation_error() -> None:
    record = _record()
    groups: dict[str, CandidateGroupInput | None] = dict(record.groups)
    groups["F01"] = None
    malformed_record = replace(
        record,
        groups=cast(Mapping[str, CandidateGroupInput], groups),
    )

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([malformed_record])

    assert any(
        violation.reason == "groups must contain CandidateGroupInput values"
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
def test_invalid_candidate_group_metadata_is_rejected(
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

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates(
            [replace(record, groups={**record.groups, "F01": group})]
        )

    assert any(violation.reason == reason for violation in error.value.audit.violations)


def test_candidate_group_set_must_be_exactly_f01_through_f21() -> None:
    record = _record()
    missing_groups = dict(record.groups)
    del missing_groups["F21"]
    with pytest.raises(CandidateGenerationError) as missing_error:
        build_explanatory_variable_candidates([replace(record, groups=missing_groups)])
    assert any(
        violation.reason == "candidate group is missing" and violation.group_id == "F21"
        for violation in missing_error.value.audit.violations
    )

    extra_groups = dict(record.groups)
    extra_groups["F22"] = replace(record.groups["F21"], group_id="F22")
    with pytest.raises(CandidateGenerationError) as extra_error:
        build_explanatory_variable_candidates([replace(record, groups=extra_groups)])
    assert any(
        violation.reason == "candidate group is not F01-F21" and violation.group_id == "F22"
        for violation in extra_error.value.audit.violations
    )


def test_candidate_boundary_violations_are_rejected() -> None:
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
        with pytest.raises(CandidateGenerationError):
            build_explanatory_variable_candidates([replace(record, groups=updated_groups)])


def test_same_race_requires_one_freeze_time_and_stable_candidate_columns() -> None:
    first = _record(horse_id="horse-1")
    second = _record(horse_id="horse-2", freeze_at=FREEZE_AT.replace(minute=13))
    second_group = replace(second.groups["F01"], values={"other_value": 1.0})
    second = replace(second, groups={**second.groups, "F01": second_group})

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates([first, second])

    reasons = {violation.reason for violation in error.value.audit.violations}
    assert "freeze_at must be identical for all rows in a race" in reasons
    assert "candidate field names must be identical within a race" in reasons


def test_duplicate_horse_and_non_contiguous_race_rows_are_rejected() -> None:
    records = [_record(race_id="race-1", horse_id="horse-1"), _record(race_id="race-2")]
    records.append(_record(race_id="race-1", horse_id="horse-2"))

    with pytest.raises(CandidateGenerationError) as error:
        build_explanatory_variable_candidates(records)

    reasons = {violation.reason for violation in error.value.audit.violations}
    assert "rows for each race must be contiguous" in reasons

    duplicate_records = [_record(), _record(horse_id="horse-1")]
    with pytest.raises(CandidateGenerationError) as duplicate_error:
        build_explanatory_variable_candidates(duplicate_records)
    assert any(
        violation.reason == "horse_id must be unique within a race"
        for violation in duplicate_error.value.audit.violations
    )
