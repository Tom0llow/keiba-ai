"""Convert declarative acquisition profiles into validated settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from configuration.loader import load_toml
from configuration.path_resolver import resolve_path
from domain.race_key import RaceKey
from jra_van_retriever.config.validation import (
    _optional_date,
    _optional_datetime,
    _optional_datetimes,
    _require_bool,
    _require_date,
    _require_string,
    _require_string_set,
    _require_table,
)


@dataclass(frozen=True)
class JVLinkProfile:
    """Declarative enablement policy for one JVLinkToSQLite execution mode."""

    normal_update: bool
    setup_update: bool
    realtime_update: bool
    normal_data_specs: frozenset[str]
    setup_data_specs: frozenset[str]
    realtime_data_specs: frozenset[str]
    start_datetime: datetime | None = None
    race_start_date: date | None = None
    start_datetimes: dict[str, datetime] | None = None
    skip_existing: bool = False


@dataclass(frozen=True)
class HistoricalOddsBatch:
    """Fixed year range for weekly historical odds retrieval."""

    first_year: int
    last_year: int
    years_per_run: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int
            for value in (self.first_year, self.last_year, self.years_per_run)
        ):
            raise ValueError("historical_odds.batch years must be integers")
        if not 1000 <= self.first_year <= self.last_year <= 9998:
            raise ValueError("historical_odds.batch year range is invalid")
        if self.years_per_run != 1:
            raise ValueError("historical_odds.batch.years_per_run must be 1")


@dataclass(frozen=True)
class JVLinkConfig:
    """Local JVLinkToSQLite paths, retrieval profiles, and target race."""

    executable: Path
    seed_setting: Path
    historical: JVLinkProfile
    historical_odds: JVLinkProfile
    latest: JVLinkProfile
    realtime_history: JVLinkProfile
    realtime_current: JVLinkProfile
    realtime_race: RaceKey | None = None
    historical_odds_batch: HistoricalOddsBatch | None = None

    @classmethod
    def from_toml(cls, config_path: Path) -> JVLinkConfig:
        """Load and validate the JVLink configuration."""
        resolved = config_path.expanduser().resolve()
        config = load_toml(resolved)

        jvlink = _require_table(config, "jvlink")
        return cls(
            executable=resolve_path(
                resolved, jvlink.get("executable"), field="[jvlink].executable"
            ),
            seed_setting=resolve_path(
                resolved, jvlink.get("seed_setting"), field="[jvlink].seed_setting"
            ),
            historical=_load_profile(config, "historical"),
            historical_odds=_load_profile(config, "historical_odds"),
            latest=_load_profile(config, "latest"),
            realtime_history=_load_profile(config, "realtime_history"),
            realtime_current=_load_profile(config, "realtime_current"),
            realtime_race=_optional_race_key(config, "realtime"),
            historical_odds_batch=_load_batch(config),
        )


def _load_batch(config: dict[str, Any]) -> HistoricalOddsBatch | None:
    odds = _require_table(config, "historical_odds")
    if "batch" not in odds:
        return None
    section = _require_table(odds, "batch")
    allowed = {"first_year", "last_year", "years_per_run"}
    if section.keys() - allowed:
        raise ValueError("historical_odds.batch contains unsupported settings")
    years: list[int] = []
    for key in ("first_year", "last_year", "years_per_run"):
        value = section.get(key)
        if type(value) is not int:
            raise ValueError(f"historical_odds.batch.{key} must be an integer")
        years.append(value)
    return HistoricalOddsBatch(years[0], years[1], years[2])


def _load_profile(config: dict[str, Any], name: str) -> JVLinkProfile:
    section = _require_table(config, name)
    setup_data_specs = _require_string_set(section, "setup_data_specs", name)
    start_datetime = _optional_datetime(section, "start_datetime", name)
    start_datetimes = _optional_datetimes(section, "start_datetimes", name)
    if start_datetime is not None and start_datetimes:
        raise ValueError(f"[{name}] must define only one of start_datetime or start_datetimes")
    if start_datetimes and set(start_datetimes) != set(setup_data_specs):
        raise ValueError(f"[{name}].start_datetimes must contain exactly the setup_data_specs")
    return JVLinkProfile(
        normal_update=_require_bool(section, "normal_update", name),
        setup_update=_require_bool(section, "setup_update", name),
        realtime_update=_require_bool(section, "realtime_update", name),
        normal_data_specs=_require_string_set(section, "normal_data_specs", name),
        setup_data_specs=setup_data_specs,
        realtime_data_specs=_require_string_set(section, "realtime_data_specs", name),
        start_datetime=start_datetime,
        start_datetimes=start_datetimes or None,
        race_start_date=_optional_date(section, "race_start_date", name),
        skip_existing=(
            _require_bool(section, "skip_existing", name) if "skip_existing" in section else False
        ),
    )


def _optional_race_key(config: dict[str, Any], section_name: str) -> RaceKey | None:
    value = config.get(section_name)
    if value is None:
        return None
    section = _require_table(config, section_name)
    return RaceKey(
        _require_date(section, "date", section_name),
        _require_string(section, "jyo", section_name),
        _require_string(section, "kaiji", section_name),
        _require_string(section, "nichiji", section_name),
        _require_string(section, "race", section_name),
    )
