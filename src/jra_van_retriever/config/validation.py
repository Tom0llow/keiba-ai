"""Validate JVLink-specific TOML values without reading files."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

from jra_van_retriever.contracts.odds import PREDICTION_SPECS

if TYPE_CHECKING:
    from jra_van_retriever.config.profiles import (
        HistoricalOddsBatch,
        JVLinkProfile,
        RaceDayOddsProfile,
    )


def _require_table(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"config must contain a [{key}] section")
    return cast(dict[str, Any], value)


def _require_bool(section: dict[str, Any], key: str, section_name: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"[{section_name}].{key} must be a boolean")
    return value


def _require_string(section: dict[str, Any], key: str, section_name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"[{section_name}].{key} must be a non-empty string")
    return value


def _require_date(section: dict[str, Any], key: str, section_name: str) -> date:
    value = section.get(key)
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"[{section_name}].{key} must be a TOML local date")
    return value


def _require_string_set(section: dict[str, Any], key: str, section_name: str) -> frozenset[str]:
    value = section.get(key)
    if not isinstance(value, list):
        raise ValueError(f"[{section_name}].{key} must be an array of non-empty strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"[{section_name}].{key} must be an array of non-empty strings")
        items.append(item)
    if len(items) != len(set(items)):
        raise ValueError(f"[{section_name}].{key} must not contain duplicates")
    return frozenset(items)


def _require_positive_int(section: dict[str, Any], key: str, section_name: str) -> int:
    value = section.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError(f"[{section_name}].{key} must be a positive integer")
    return value


def _require_positive_int_tuple(
    section: dict[str, Any], key: str, section_name: str
) -> tuple[int, ...]:
    value = section.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"[{section_name}].{key} must be a non-empty array")
    if any(type(item) is not int or item <= 0 for item in value):
        raise ValueError(f"[{section_name}].{key} must contain positive integers")
    if len(value) != len(set(value)):
        raise ValueError(f"[{section_name}].{key} must not contain duplicates")
    return tuple(value)


def _optional_datetime(section: dict[str, Any], key: str, section_name: str) -> datetime | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"[{section_name}].{key} must be a TOML local datetime")
    return value


def _optional_datetimes(
    section: dict[str, Any], key: str, section_name: str
) -> dict[str, datetime]:
    value = section.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"[{section_name}].{key} must be a table of local datetimes")

    result: dict[str, datetime] = {}
    for data_spec, start_datetime in value.items():
        if not isinstance(data_spec, str) or not data_spec:
            raise ValueError(f"[{section_name}].{key} must use non-empty data spec IDs")
        if not isinstance(start_datetime, datetime):
            raise ValueError(f"[{section_name}].{key}.{data_spec} must be a TOML local datetime")
        result[data_spec] = start_datetime
    return result


def _optional_date(section: dict[str, Any], key: str, section_name: str) -> date | None:
    value = section.get(key)
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"[{section_name}].{key} must be a TOML local date")
    return cast(date, value)


def validate_historical_odds_batch(odds: JVLinkProfile, batch: HistoricalOddsBatch) -> None:
    """Validate the profile used by the historical-odds workflow."""
    if odds.normal_update or odds.setup_update or not odds.realtime_update:
        raise ValueError("historical-odds requires only realtime odds updates")
    if not odds.skip_existing:
        raise ValueError("historical-odds requires skip_existing=true")
    if not odds.realtime_data_specs or not odds.realtime_data_specs <= {"0B41", "0B42"}:
        raise ValueError("historical-odds supports only 0B41 and 0B42")
    if odds.race_start_date is None or odds.race_start_date.year != batch.first_year:
        raise ValueError("historical_odds.race_start_date must lie in batch.first_year")


def validate_race_day_odds_profile(profile: RaceDayOddsProfile) -> None:
    """Validate the exclusive realtime profile used by race-day odds capture."""
    expected_specs = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"})
    if profile.normal_update or profile.setup_update or not profile.realtime_update:
        raise ValueError("race-day-odds requires only realtime odds updates")
    if profile.normal_data_specs or profile.setup_data_specs:
        raise ValueError("race-day-odds normal/setup data specs must be empty")
    if profile.realtime_data_specs != expected_specs:
        raise ValueError("race-day-odds requires exactly 0B31 through 0B36")
    if not profile.offsets_minutes:
        raise ValueError("race-day-odds offsets_minutes must not be empty")
    if any(type(value) is not int or value <= 0 for value in profile.offsets_minutes):
        raise ValueError("race-day-odds offsets_minutes must contain positive integers")
    if len(profile.offsets_minutes) != len(set(profile.offsets_minutes)):
        raise ValueError("race-day-odds offsets_minutes must not contain duplicates")
    if type(profile.late_tolerance_seconds) is not int or profile.late_tolerance_seconds <= 0:
        raise ValueError("race-day-odds late_tolerance_seconds must be a positive integer")
    if type(profile.execution_timeout_seconds) is not int or profile.execution_timeout_seconds <= 0:
        raise ValueError("race-day-odds execution_timeout_seconds must be a positive integer")
    offset = profile.prediction_offset_minutes
    if offset is not None and (
        type(offset) is not int or not MIN_PREDICTION_OFFSET <= offset <= MAX_PREDICTION_OFFSET
    ):
        raise ValueError(
            "race-day-odds prediction_offset_minutes must be an integer from "
            f"{MIN_PREDICTION_OFFSET} through {MAX_PREDICTION_OFFSET}"
        )


# The prediction fetch must start at or after the reference freeze (five minutes before
# the start, ADR-037) and leave time to calculate before sales close two minutes before.
MIN_PREDICTION_OFFSET = 3
MAX_PREDICTION_OFFSET = 5


def validate_race_day_prediction_profile(profile: JVLinkProfile) -> None:
    """Validate the 0B41/0B42 time-series profile of the race-day prediction fetch."""
    if profile.normal_update or profile.setup_update or not profile.realtime_update:
        raise ValueError("race-day prediction fetch requires only realtime odds updates")
    if profile.normal_data_specs or profile.setup_data_specs:
        raise ValueError("race-day prediction fetch normal/setup data specs must be empty")
    if profile.realtime_data_specs != PREDICTION_SPECS:
        raise ValueError("race-day prediction fetch requires exactly 0B41 and 0B42")
