"""Build and audit candidate explanatory-variable groups F01 through F21.

The implementation accepts only normalized, already-computed candidate values.
It does not interpret JRA-VAN codes, choose history windows, or read a data
source.  Candidate groups remain outside the numeric ``FeatureSchema`` until
their generation rules are explicitly approved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite, isnan
from types import MappingProxyType
from typing import Literal, cast

from features.candidate_spec import CandidateGroupSpec
from features.f01_recent_performance import SPEC as F01_SPEC
from features.f02_past_racing_ability import SPEC as F02_SPEC
from features.f03_condition_adjusted_ability import SPEC as F03_SPEC
from features.f04_recent_stability import SPEC as F04_SPEC
from features.f05_condition_suitability import SPEC as F05_SPEC
from features.f06_rest_and_condition_change import SPEC as F06_SPEC
from features.f07_jockey_performance import SPEC as F07_SPEC
from features.f08_trainer_performance import SPEC as F08_SPEC
from features.f09_within_race_relative import SPEC as F09_SPEC
from features.f10_basic_conditions_and_weight import SPEC as F10_SPEC
from features.f11_jockey_combination import SPEC as F11_SPEC
from features.f12_running_style_and_position import SPEC as F12_SPEC
from features.f13_expected_race_development import SPEC as F13_SPEC
from features.f14_pedigree_suitability import SPEC as F14_SPEC
from features.f15_history_volume_and_missingness import SPEC as F15_SPEC
from features.f16_past_body_weight import SPEC as F16_SPEC
from features.f17_hill_and_wood_workouts import SPEC as F17_SPEC
from features.f18_past_lap_and_running_style import SPEC as F18_SPEC
from features.f19_market_characteristics import SPEC as F19_SPEC
from features.f20_same_gate_and_trainer_relative import SPEC as F20_SPEC
from features.f21_opponent_pagerank import SPEC as F21_SPEC

type CandidateTimestamp = datetime | str
type CandidateValue = str | int | float | bool | None
type CandidateStatus = Literal["confirmed", "missing", "unconfirmed"]
type CandidateSourceScope = Literal["pre_race", "historical"]

CANDIDATE_GROUP_SPECS = (
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
CANDIDATE_GROUP_IDS = tuple(spec.group_id for spec in CANDIDATE_GROUP_SPECS)

_ALLOWED_SOURCE_SCOPES = frozenset({"pre_race", "historical"})
_ALLOWED_STATUSES = frozenset({"confirmed", "missing", "unconfirmed"})
_RESULT_FIELD_NAMES = frozenset(
    {
        "arrival",
        "arrivalrank",
        "confirmedfinish",
        "confirmedresult",
        "finalodds",
        "finishposition",
        "finishresult",
        "lastodds",
        "ninki",
        "oddsfinal",
        "outcome",
        "payout",
        "payoutamount",
        "placing",
        "popularity",
        "position",
        "prize",
        "prizemoney",
        "refund",
        "resultrank",
        "raceresult",
        "result",
        "targetfinish",
        "targetresult",
        "target",
        "winflag",
        "winner",
    }
)
_RESULT_FIELD_PREFIXES = (
    "raceresult",
    "resultscore",
    "targetfinish",
    "targetresult",
)
_ALLOWED_MARKET_FIELD_NAMES = frozenset(
    {
        "marketlogoddschange",
        "marketoddsratio",
        "marketpairsupporti",
        "marketrankchange",
        "marketplacelow",
        "marketplacehigh",
        "marketplacewidth",
        "marketwinodds",
        "marketwinsupport",
        "marketwinrank",
    }
)
_MARKET_TICKET_TYPES = frozenset({"fukusyo", "tansyo", "umaren", "wakuren"})
_HISTORICAL_FIELD_PREFIXES = (
    "history",
    "historical",
    "past",
    "previous",
)
_TARGET_RESULT_FIELD_MARKERS = (
    "arrival",
    "finish",
    "finalodds",
    "outcome",
    "kakuteijyuni",
    "nyusenjyuni",
    "payout",
    "placing",
    "position",
    "rank",
    "refund",
    "result",
    "score",
    "speed",
    "time",
    "winflag",
    "winner",
)
_RESULT_FIELD_NAME_MARKERS = (
    "arrival",
    "finish",
    "finalodds",
    "outcome",
    "kakuteijyuni",
    "nyusenjyuni",
    "payout",
    "placing",
    "position",
    "prize",
    "result",
    "refund",
    "winner",
)


@dataclass(frozen=True, slots=True)
class CandidateGroupInput:
    """Provide one candidate group from an explicit normalized boundary.

    ``values`` must contain scalar values only.  ``source_scope`` distinguishes
    values computed from the target race's pre-race state from values derived
    from historical records.  A historical source may not reference the target
    race, and its source event must not be after ``freeze_at``.
    ``status='missing'`` preserves unavailable values as ``None`` or ``NaN``;
    ``status='unconfirmed'`` is rejected rather than treated as valid.
    """

    group_id: str
    values: Mapping[str, CandidateValue]
    available_at: CandidateTimestamp | None
    source_event_at: CandidateTimestamp | None
    source_scope: str
    status: str
    source_race_ids: Sequence[str] = ()
    contains_target_result: bool = field(kw_only=True)
    contains_future_data: bool = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """Represent one horse's F01-F21 candidate values at a freeze time."""

    race_id: str
    horse_id: str
    freeze_at: CandidateTimestamp
    groups: Mapping[str, CandidateGroupInput]


@dataclass(frozen=True, slots=True)
class CandidateViolation:
    """Describe one candidate-input contract violation."""

    row_index: int
    race_id: str
    horse_id: str
    group_id: str | None
    field_name: str | None
    reason: str
    freeze_at: datetime | None = None
    available_at: datetime | None = None
    source_event_at: datetime | None = None

    @property
    def message(self) -> str:
        """Return a concise location and reason for the violation."""
        location = f"row {self.row_index} ({self.race_id}/{self.horse_id})"
        if self.group_id is not None:
            location += f" group {self.group_id!r}"
        if self.field_name is not None:
            location += f" field {self.field_name!r}"
        return f"{location}: {self.reason}"


@dataclass(frozen=True, slots=True)
class CandidateAudit:
    """Summarize candidate validation without dropping input rows."""

    records_checked: int
    groups_checked: int
    non_missing_values: int
    missing_values: int
    violations: tuple[CandidateViolation, ...]

    @property
    def valid(self) -> bool:
        """Return whether all candidate inputs passed validation."""
        return not self.violations


class CandidateGenerationError(ValueError):
    """Indicate that candidate inputs failed their explicit boundary checks."""

    def __init__(self, audit: CandidateAudit) -> None:
        self.audit = audit
        details = "; ".join(violation.message for violation in audit.violations)
        super().__init__(f"candidate generation audit failed: {details}")


@dataclass(frozen=True, slots=True)
class CandidateGenerationResult:
    """Hold normalized candidate records and their audit."""

    records: tuple[CandidateRecord, ...]
    audit: CandidateAudit


def audit_candidate_inputs(records: Sequence[CandidateRecord]) -> CandidateAudit:
    """Audit explicit F01-F21 candidate inputs.

    The audit checks timezone-aware as-of timestamps, target-result and future
    data markers, missing/unconfirmed status, and race-contiguous row shape.
    It never imputes a missing candidate value.
    """
    violations: list[CandidateViolation] = []
    records_checked = len(records)
    groups_checked = 0
    non_missing_values = 0
    missing_values = 0
    seen_races: set[str] = set()
    current_race: str | None = None
    current_horses: set[str] = set()
    race_freeze_at: dict[str, datetime] = {}
    race_group_fields: dict[tuple[str, str], frozenset[str]] = {}
    race_group_scopes: dict[tuple[str, str], str] = {}
    race_ticket_totals: dict[tuple[str, str, str], CandidateValue] = {}

    for row_index, record in enumerate(records):
        if not isinstance(record, CandidateRecord):
            raise TypeError("records must contain CandidateRecord values")
        race_id = record.race_id if isinstance(record.race_id, str) else "<invalid>"
        horse_id = record.horse_id if isinstance(record.horse_id, str) else "<invalid>"
        if not isinstance(record.race_id, str) or not record.race_id:
            violations.append(
                _violation(row_index, race_id, horse_id, None, None, "race_id must be non-empty")
            )
        if not isinstance(record.horse_id, str) or not record.horse_id:
            violations.append(
                _violation(row_index, race_id, horse_id, None, None, "horse_id must be non-empty")
            )

        freeze_at, freeze_error = _parse_timestamp(record.freeze_at)
        if freeze_error is not None:
            violations.append(_violation(row_index, race_id, horse_id, None, None, freeze_error))
        elif freeze_at is None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    None,
                    None,
                    "freeze_at is required",
                )
            )

        if current_race != race_id:
            if race_id in seen_races:
                violations.append(
                    _violation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        None,
                        "rows for each race must be contiguous",
                    )
                )
            if current_race is not None:
                current_horses.clear()
            current_race = race_id
            seen_races.add(race_id)
        if horse_id in current_horses:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    None,
                    None,
                    "horse_id must be unique within a race",
                )
            )
        current_horses.add(horse_id)

        if freeze_at is not None:
            previous_freeze_at = race_freeze_at.setdefault(race_id, freeze_at)
            if previous_freeze_at != freeze_at:
                violations.append(
                    _violation(
                        row_index,
                        race_id,
                        horse_id,
                        None,
                        None,
                        "freeze_at must be identical for all rows in a race",
                        freeze_at=freeze_at,
                    )
                )

        if not isinstance(record.groups, Mapping):
            violations.append(
                _violation(row_index, race_id, horse_id, None, None, "groups must be a mapping")
            )
            continue

        group_ids = set(record.groups)
        for group_id in CANDIDATE_GROUP_IDS:
            if group_id not in record.groups:
                violations.append(
                    _violation(
                        row_index, race_id, horse_id, group_id, None, "candidate group is missing"
                    )
                )
        for group_id in group_ids:
            if not isinstance(group_id, str) or group_id not in CANDIDATE_GROUP_IDS:
                violations.append(
                    _violation(
                        row_index,
                        race_id,
                        horse_id,
                        str(group_id),
                        None,
                        "candidate group is not F01-F21",
                    )
                )

        for group_id in CANDIDATE_GROUP_IDS:
            if group_id not in record.groups:
                continue
            group = record.groups[group_id]
            groups_checked += 1
            _audit_group(
                group,
                expected_group_id=group_id,
                row_index=row_index,
                race_id=race_id,
                horse_id=horse_id,
                freeze_at=freeze_at,
                violations=violations,
            )
            if not isinstance(group, CandidateGroupInput):
                continue

            if isinstance(group.values, Mapping):
                values = group.values
                non_missing_values += sum(
                    _is_non_missing(value)
                    for value in values.values()
                    if _is_candidate_value(value)
                )
                missing_values += sum(
                    _is_missing(value) for value in values.values() if _is_candidate_value(value)
                )
                key = (race_id, group_id)
                field_names = frozenset(
                    field_name for field_name in values if isinstance(field_name, str)
                )
                previous_fields = race_group_fields.setdefault(key, field_names)
                if previous_fields != field_names:
                    violations.append(
                        _violation(
                            row_index,
                            race_id,
                            horse_id,
                            group_id,
                            None,
                            "candidate field names must be identical within a race",
                        )
                    )
                for field_name, value in values.items():
                    if not isinstance(field_name, str) or not _is_ticket_total_field(field_name):
                        continue
                    shared_key = (race_id, group_id, field_name)
                    if shared_key not in race_ticket_totals:
                        race_ticket_totals[shared_key] = value
                    elif not _candidate_values_equal(race_ticket_totals[shared_key], value):
                        violations.append(
                            _violation(
                                row_index,
                                race_id,
                                horse_id,
                                group_id,
                                field_name,
                                "F19 ticket total must be identical within a race",
                            )
                        )
            if isinstance(group.source_scope, str):
                key = (race_id, group_id)
                previous_scope = race_group_scopes.setdefault(key, group.source_scope)
                if previous_scope != group.source_scope:
                    violations.append(
                        _violation(
                            row_index,
                            race_id,
                            horse_id,
                            group_id,
                            None,
                            "source_scope must be identical within a race and group",
                        )
                    )

    return CandidateAudit(
        records_checked=records_checked,
        groups_checked=groups_checked,
        non_missing_values=non_missing_values,
        missing_values=missing_values,
        violations=tuple(violations),
    )


def build_explanatory_variable_candidates(
    records: Sequence[CandidateRecord],
) -> CandidateGenerationResult:
    """Validate and return candidate groups without entering ``FeatureSchema``.

    Args:
        records: Race-contiguous rows containing all F01-F21 groups.  Values
            must already be normalized by an upstream data boundary.

    Raises:
        ValueError: If no records are supplied.
        CandidateGenerationError: If any temporal, source, status, or row
            consistency check fails.
    """
    if not records:
        raise ValueError("candidate generation requires at least one record")
    audit = audit_candidate_inputs(records)
    if not audit.valid:
        raise CandidateGenerationError(audit)
    normalized_records = tuple(_normalize_record(record) for record in records)
    return CandidateGenerationResult(records=normalized_records, audit=audit)


def _audit_group(
    group: object,
    *,
    expected_group_id: str,
    row_index: int,
    race_id: str,
    horse_id: str,
    freeze_at: datetime | None,
    violations: list[CandidateViolation],
) -> None:
    if not isinstance(group, CandidateGroupInput):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                None,
                None,
                "groups must contain CandidateGroupInput values",
            )
        )
        return
    group_id = group.group_id
    if group_id != expected_group_id:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                expected_group_id,
                None,
                "group_id must match its groups mapping key",
            )
        )
    if group_id not in CANDIDATE_GROUP_IDS:
        violations.append(
            _violation(
                row_index, race_id, horse_id, group_id, None, "candidate group is not F01-F21"
            )
        )
    if group.source_scope not in _ALLOWED_SOURCE_SCOPES:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "source_scope must be pre_race or historical",
            )
        )
    if group.status not in _ALLOWED_STATUSES:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "status must be confirmed, missing, or unconfirmed",
            )
        )
    if not isinstance(group.contains_target_result, bool):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "contains_target_result must be boolean",
            )
        )
    elif group.contains_target_result:
        violations.append(
            _violation(
                row_index, race_id, horse_id, group_id, None, "target race result is not allowed"
            )
        )
    if not isinstance(group.contains_future_data, bool):
        violations.append(
            _violation(
                row_index, race_id, horse_id, group_id, None, "contains_future_data must be boolean"
            )
        )
    elif group.contains_future_data:
        violations.append(
            _violation(row_index, race_id, horse_id, group_id, None, "future data is not allowed")
        )

    source_race_ids = group.source_race_ids
    if isinstance(source_race_ids, str) or not isinstance(source_race_ids, Sequence):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "source_race_ids must be a sequence of strings",
            )
        )
        source_race_ids = ()
    for source_race_id in source_race_ids:
        if not isinstance(source_race_id, str) or not source_race_id:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    None,
                    "source_race_ids must contain non-empty strings",
                )
            )
        elif group.source_scope == "historical" and source_race_id == race_id:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    None,
                    "historical source cannot be the target race",
                )
            )

    available_at: datetime | None = None
    if group.available_at is not None:
        available_at, timestamp_error = _parse_timestamp(group.available_at)
        if timestamp_error is not None:
            violations.append(
                _violation(
                    row_index, race_id, horse_id, group_id, None, f"available_at {timestamp_error}"
                )
            )
    source_event_at: datetime | None = None
    if group.source_event_at is not None:
        source_event_at, timestamp_error = _parse_timestamp(group.source_event_at)
        if timestamp_error is not None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    None,
                    f"source_event_at {timestamp_error}",
                )
            )
    if not isinstance(group.values, Mapping):
        violations.append(
            _violation(row_index, race_id, horse_id, group_id, None, "values must be a mapping")
        )
        return

    non_missing = False
    all_missing = True
    for field_name, value in group.values.items():
        if not isinstance(field_name, str) or not field_name:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    None,
                    "candidate field names must be non-empty strings",
                )
            )
            continue
        if _is_result_field(field_name):
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    field_name,
                    "result-derived field is not allowed",
                )
            )
        if group_id == "F19" and not _is_allowed_market_field(field_name):
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    field_name,
                    "F19 market field is not allowed",
                )
            )
        if not _is_candidate_value(value):
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    field_name,
                    "candidate value must be a scalar or None",
                )
            )
            continue
        if _is_missing(value):
            continue
        non_missing = True
        all_missing = False
        if available_at is None:
            violations.append(
                _violation(
                    row_index,
                    race_id,
                    horse_id,
                    group_id,
                    field_name,
                    "non-missing candidate value requires available_at",
                    freeze_at=freeze_at,
                )
            )
    if freeze_at is not None and available_at is not None and available_at > freeze_at:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "available_at is after freeze_at",
                freeze_at=freeze_at,
                available_at=available_at,
            )
        )
    if group.status == "unconfirmed":
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "unconfirmed candidate values are not allowed",
            )
        )
    if group.status == "missing" and non_missing:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "missing status cannot contain non-missing values",
            )
        )
    if group.status == "confirmed" and all_missing:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "all-missing values must use status='missing'",
            )
        )
    if group.status == "missing" and group.available_at is not None:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "missing values must not have available_at",
            )
        )
    if group.source_scope == "historical" and non_missing and source_event_at is None:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "historical non-missing values require source_event_at",
            )
        )
    if freeze_at is not None and source_event_at is not None and source_event_at > freeze_at:
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                group_id,
                None,
                "source_event_at is after freeze_at",
                freeze_at=freeze_at,
                source_event_at=source_event_at,
            )
        )


def _normalize_record(record: CandidateRecord) -> CandidateRecord:
    freeze_at, error = _parse_timestamp(record.freeze_at)
    if error is not None or freeze_at is None:
        raise AssertionError("validated candidate audit must contain freeze_at")
    groups: dict[str, CandidateGroupInput] = {}
    for group_id in CANDIDATE_GROUP_IDS:
        group = record.groups[group_id]
        available_at, available_error = _parse_timestamp(group.available_at)
        if available_error is not None:
            raise AssertionError("validated candidate audit must contain valid available_at")
        source_event_at, source_event_error = _parse_timestamp(group.source_event_at)
        if source_event_error is not None:
            raise AssertionError("validated candidate audit must contain valid source_event_at")
        groups[group_id] = CandidateGroupInput(
            group_id=group_id,
            values=MappingProxyType(dict(group.values)),
            available_at=available_at,
            source_event_at=source_event_at,
            source_scope=cast(CandidateSourceScope, group.source_scope),
            status=cast(CandidateStatus, group.status),
            source_race_ids=tuple(group.source_race_ids),
            contains_target_result=False,
            contains_future_data=False,
        )
    return CandidateRecord(
        race_id=record.race_id,
        horse_id=record.horse_id,
        freeze_at=freeze_at,
        groups=MappingProxyType(groups),
    )


def _parse_timestamp(value: CandidateTimestamp | None) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            return None, f"must be a valid ISO-8601 timestamp ({exc})"
    else:
        return None, "must be a datetime or ISO-8601 timestamp string"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "must be timezone-aware"
    return parsed.astimezone(UTC), None


def _is_candidate_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and (isnan(value) or isfinite(value))


def _is_missing(value: CandidateValue) -> bool:
    return value is None or (isinstance(value, float) and isnan(value))


def _is_non_missing(value: CandidateValue) -> bool:
    return not _is_missing(value)


def _is_result_field(field_name: str) -> bool:
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    if normalized.startswith(_HISTORICAL_FIELD_PREFIXES):
        return False
    if _is_allowed_market_field(field_name):
        return False
    if normalized in _RESULT_FIELD_NAMES or normalized.startswith(_RESULT_FIELD_PREFIXES):
        return True
    if "result" in normalized:
        return True
    if normalized == "winflag" or any(
        normalized == marker or normalized.startswith(marker) or normalized.endswith(marker)
        for marker in _RESULT_FIELD_NAME_MARKERS
    ):
        return True
    if not normalized.startswith("target"):
        return False
    target_field = normalized[len("target") :]
    if target_field.startswith("race"):
        target_field = target_field[len("race") :]
    return target_field.startswith(_TARGET_RESULT_FIELD_MARKERS)


def _is_allowed_market_field(field_name: str) -> bool:
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    if normalized in _ALLOWED_MARKET_FIELD_NAMES:
        return True
    return _is_ticket_total_field(field_name)


def _is_ticket_total_field(field_name: str) -> bool:
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    return any(
        normalized
        in {
            f"tickettotal{ticket_type}",
            f"tickettotalgrowth{ticket_type}",
            f"tickettotalgrowthrate{ticket_type}",
        }
        for ticket_type in _MARKET_TICKET_TYPES
    )


def _candidate_values_equal(left: CandidateValue, right: CandidateValue) -> bool:
    if _is_missing(left) or _is_missing(right):
        return _is_missing(left) and _is_missing(right)
    return left == right


def _violation(
    row_index: int,
    race_id: str,
    horse_id: str,
    group_id: str | None,
    field_name: str | None,
    reason: str,
    *,
    freeze_at: datetime | None = None,
    available_at: datetime | None = None,
    source_event_at: datetime | None = None,
) -> CandidateViolation:
    return CandidateViolation(
        row_index=row_index,
        race_id=race_id,
        horse_id=horse_id,
        group_id=group_id,
        field_name=field_name,
        reason=reason,
        freeze_at=freeze_at,
        available_at=available_at,
        source_event_at=source_event_at,
    )


__all__ = [
    "CANDIDATE_GROUP_IDS",
    "CANDIDATE_GROUP_SPECS",
    "CandidateAudit",
    "CandidateGenerationError",
    "CandidateGenerationResult",
    "CandidateGroupInput",
    "CandidateGroupSpec",
    "CandidateRecord",
    "CandidateValue",
    "CandidateViolation",
    "audit_candidate_inputs",
    "build_explanatory_variable_candidates",
]
