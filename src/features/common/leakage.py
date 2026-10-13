"""Reject target-result columns and references to future outcomes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from features.common.types import FeatureGroupInput, FeatureViolation, _violation

_RESULT_FIELD_NAMES = frozenset(
    {
        "arrival",
        "arrivalrank",
        "confirmedfinish",
        "confirmedresult",
        "confirmedtime",
        "deadheat",
        "earnings",
        "finalodds",
        "finishposition",
        "finishresult",
        "harontimel3",
        "last3f",
        "lastodds",
        "margin",
        "ninki",
        "oddsfinal",
        "outcome",
        "passingposition",
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
        "time",
        "timediff",
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
_HISTORICAL_FIELD_PREFIXES = (
    "history",
    "historical",
    "past",
    "previous",
)
_TARGET_RESULT_FIELD_MARKERS = (
    "arrival",
    "confirmedtime",
    "deadheat",
    "earnings",
    "finish",
    "finalodds",
    "harontimel3",
    "last3f",
    "margin",
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


def is_result_field(field_name: str) -> bool:
    """Identify result-derived columns while allowing explicitly historical names."""
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    if normalized.startswith(_HISTORICAL_FIELD_PREFIXES):
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
    return target_field.startswith(tuple(_RESULT_FIELD_NAMES)) or target_field.startswith(
        _TARGET_RESULT_FIELD_MARKERS
    )


def audit_source(
    group: FeatureGroupInput,
    *,
    row_index: int,
    race_id: str,
    horse_id: str,
    freeze_at: datetime | None,
    violations: list[FeatureViolation],
) -> None:
    """Reject target outcomes, future flags and invalid historical references."""
    feature_id = group.feature_id
    if not isinstance(group.contains_target_result, bool):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "contains_target_result must be boolean",
            )
        )
    elif group.contains_target_result:
        violations.append(
            _violation(
                row_index, race_id, horse_id, feature_id, None, "target race result is not allowed"
            )
        )
    if not isinstance(group.contains_future_data, bool):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
                None,
                "contains_future_data must be boolean",
            )
        )
    elif group.contains_future_data:
        violations.append(
            _violation(row_index, race_id, horse_id, feature_id, None, "future data is not allowed")
        )

    source_race_ids = group.source_race_ids
    if isinstance(source_race_ids, str) or not isinstance(source_race_ids, Sequence):
        violations.append(
            _violation(
                row_index,
                race_id,
                horse_id,
                feature_id,
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
                    feature_id,
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
                    feature_id,
                    None,
                    "historical source cannot be the target race",
                )
            )
