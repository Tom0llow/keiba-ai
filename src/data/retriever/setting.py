"""Build JVLinkToSQLite execution settings from declarative TOML profiles."""

from __future__ import annotations

import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, cast


class RaceKeyLike(Protocol):
    """Minimum race-key contract required to configure realtime odds."""

    race_date: date
    jyo_code: str
    kaiji: str
    nichiji: str
    race_number: str


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


@dataclass(frozen=True)
class JVLinkConfig:
    """Local JVLinkToSQLite paths and retrieval profiles."""

    executable: Path
    seed_setting: Path
    historical: JVLinkProfile
    historical_odds: JVLinkProfile
    latest: JVLinkProfile

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
        )


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

        if profile.start_datetime is not None:
            _set_start_datetime(setup, profile.setup_data_specs, profile.start_datetime)
        if race_key is not None:
            _set_race_key(realtime, profile.realtime_data_specs, race_key)

        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        tree.write(destination, encoding="utf-8", xml_declaration=True)
        return destination


def _load_profile(config: dict[str, Any], name: str) -> JVLinkProfile:
    section = _require_table(config, name)
    return JVLinkProfile(
        normal_update=_require_bool(section, "normal_update", name),
        setup_update=_require_bool(section, "setup_update", name),
        realtime_update=_require_bool(section, "realtime_update", name),
        normal_data_specs=_require_string_set(section, "normal_data_specs", name),
        setup_data_specs=_require_string_set(section, "setup_data_specs", name),
        realtime_data_specs=_require_string_set(section, "realtime_data_specs", name),
        start_datetime=_optional_datetime(section, "start_datetime", name),
        race_start_date=_optional_date(section, "race_start_date", name),
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
        _set_required_text(data_spec_setting, "IsEnabled", str(data_spec in enabled_specs).lower())
    missing = enabled_specs - available
    if missing:
        raise ValueError(f"setting is missing data specs: {', '.join(sorted(missing))}")


def _set_start_datetime(
    setup: ET.Element, enabled_specs: frozenset[str], start_datetime: datetime
) -> None:
    settings = _required_child(setup, "DataSpecSettings")
    for data_spec_setting in settings.findall("JVDataSpecSetting"):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec not in enabled_specs:
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


def _require_string_set(
    section: dict[str, Any], key: str, section_name: str
) -> frozenset[str]:
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


def _optional_datetime(
    section: dict[str, Any], key: str, section_name: str
) -> datetime | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"[{section_name}].{key} must be a TOML local datetime")
    return value


def _optional_date(section: dict[str, Any], key: str, section_name: str) -> date | None:
    value = section.get(key)
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"[{section_name}].{key} must be a TOML local date")
    return value


def _resolve_path(config_path: Path, section: dict[str, Any], key: str) -> Path:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"[jvlink].{key} must be a non-empty string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()
