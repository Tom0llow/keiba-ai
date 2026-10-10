"""Build JVLinkToSQLite execution settings from declarative TOML profiles."""

from __future__ import annotations

import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from data.race_key import RaceKey


class RaceKeyLike(Protocol):
    """Minimum race-key contract required to configure realtime odds."""

    @property
    def race_date(self) -> date: ...

    @property
    def jyo_code(self) -> str: ...

    @property
    def kaiji(self) -> str: ...

    @property
    def nichiji(self) -> str: ...

    @property
    def race_number(self) -> str: ...


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
        with resolved.open("rb") as config_file:
            config = tomllib.load(config_file)

        jvlink = _require_table(config, "jvlink")
        return cls(
            executable=_resolve_path(resolved, jvlink, "executable"),
            seed_setting=_resolve_path(resolved, jvlink, "seed_setting"),
            historical=_load_profile(config, "historical"),
            historical_odds=_load_profile(config, "historical_odds"),
            latest=_load_profile(config, "latest"),
            realtime_history=_load_profile(config, "realtime_history"),
            realtime_current=_load_profile(config, "realtime_current"),
            realtime_race=_optional_race_key(config, "realtime"),
            historical_odds_batch=_load_batch(config),
        )


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


class JVLinkSettingBuilder:
    """Generate execution XML without mutating the user-owned seed setting."""

    def __init__(self, seed_setting: Path) -> None:
        self._seed_setting = seed_setting.expanduser().resolve()
        if not self._seed_setting.is_file():
            raise FileNotFoundError(
                f"JVLinkToSQLite seed setting does not exist: {self._seed_setting}"
            )

    def build(
        self,
        profile: JVLinkProfile,
        destination: Path,
        *,
        source: Path | None = None,
        race_key: RaceKeyLike | None = None,
    ) -> Path:
        """Apply one profile to the seed or a persisted runtime setting."""
        source_path = self._seed_setting if source is None else source.expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"JVLinkToSQLite setting does not exist: {source_path}")

        tree = ET.parse(source_path)
        details = _required_child(tree.getroot(), "Details")
        normal = _required_child(details, "JVNormalUpdateSetting")
        setup = _required_child(details, "JVSetupDataUpdateSetting")
        realtime = _required_child(details, "JVRealTimeDataUpdateSetting")

        _apply_section(normal, profile.normal_update, profile.normal_data_specs)
        _apply_section(setup, profile.setup_update, profile.setup_data_specs)
        _apply_section(realtime, profile.realtime_update, profile.realtime_data_specs)

        if profile.start_datetime is not None or profile.start_datetimes:
            _set_start_datetimes(
                setup,
                profile.setup_data_specs,
                profile.start_datetime,
                profile.start_datetimes,
            )
        if race_key is not None:
            _set_race_key(realtime, profile.realtime_data_specs, race_key)

        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        tree.write(destination, encoding="utf-8", xml_declaration=True)
        return destination


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


def _apply_section(section: ET.Element, enabled: bool, enabled_specs: frozenset[str]) -> None:
    _set_required_text(section, "IsEnabled", str(enabled).lower())
    settings = _required_child(section, "DataSpecSettings")
    available: set[str] = set()
    for data_spec_setting in settings.findall("JVDataSpecSetting"):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec is None:
            raise ValueError("JVDataSpecSetting is missing DataSpec")
        available.add(data_spec)
        _set_required_text(
            data_spec_setting,
            "IsEnabled",
            str(data_spec in enabled_specs).lower(),
        )
    missing = enabled_specs - available
    if missing:
        raise ValueError(f"setting is missing data specs: {', '.join(sorted(missing))}")


def _set_start_datetimes(
    setup: ET.Element,
    enabled_specs: frozenset[str],
    default_start_datetime: datetime | None,
    start_datetimes: dict[str, datetime] | None,
) -> None:
    settings = _required_child(setup, "DataSpecSettings")
    for data_spec_setting in settings.findall("JVDataSpecSetting"):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec not in enabled_specs:
            continue
        start_datetime = (start_datetimes or {}).get(data_spec, default_start_datetime)
        if start_datetime is None:
            continue
        key = _required_child(data_spec_setting, "JVKaisaiDateTimeKey")
        _set_required_text(key, "KaisaiDateTime", start_datetime.isoformat())


def _set_race_key(
    realtime: ET.Element, enabled_specs: frozenset[str], race_key: RaceKeyLike
) -> None:
    settings = _required_child(realtime, "DataSpecSettings")
    for data_spec_setting in settings.findall("JVDataSpecSetting"):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec not in enabled_specs:
            continue
        key = data_spec_setting.find("JVRaceKey")
        if key is None:
            raise ValueError(f"{data_spec} setting must contain a JVRaceKey")
        _set_required_text(key, "KaisaiDate", race_key.race_date.isoformat() + "T00:00:00")
        _set_required_text(key, "JyoCD", race_key.jyo_code)
        _set_required_text(key, "Kaiji", race_key.kaiji)
        _set_required_text(key, "Nichiji", race_key.nichiji)
        _set_required_text(key, "RaceNum", race_key.race_number)


def _required_child(parent: ET.Element, tag: str) -> ET.Element:
    element = parent.find(tag)
    if element is None:
        raise ValueError(f"JVLinkToSQLite setting is missing required element: {tag}")
    return element


def _set_required_text(parent: ET.Element, tag: str, value: str) -> None:
    element = _required_child(parent, tag)
    element.text = value


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


def _resolve_path(config_path: Path, section: dict[str, Any], key: str) -> Path:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"[jvlink].{key} must be a non-empty string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()
