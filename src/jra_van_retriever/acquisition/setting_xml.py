"""Generate execution XML from typed JVLink profiles."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from jra_van_retriever.config.profiles import JVLinkProfile


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
        if profile.normal_start_floors:
            _raise_normal_start_floors(
                normal,
                profile.normal_data_specs,
                profile.normal_start_floors,
            )
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


def _raise_normal_start_floors(
    normal: ET.Element,
    enabled_specs: frozenset[str],
    floors: dict[str, datetime],
) -> None:
    settings = _required_child(normal, "DataSpecSettings")
    for data_spec_setting in settings.findall("JVDataSpecSetting"):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec not in enabled_specs:
            continue
        floor = floors.get(data_spec)
        if floor is None:
            continue
        if floor.tzinfo is not None:
            raise ValueError(f"normal start floor for {data_spec} must be a local datetime")
        key = _required_child(data_spec_setting, "JVKaisaiDateTimeKey")
        current = _local_datetime(_required_child(key, "KaisaiDateTime").text, data_spec)
        if current < floor:
            _set_required_text(key, "KaisaiDateTime", floor.isoformat())


def _local_datetime(value: str | None, data_spec: str) -> datetime:
    if value is None:
        raise ValueError(f"{data_spec} normal setting is missing KaisaiDateTime")
    if "T" not in value:
        raise ValueError(f"{data_spec} normal setting must contain a local ISO 8601 datetime")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{data_spec} normal setting must contain a local ISO 8601 datetime"
        ) from exc
    if result.tzinfo is not None:
        raise ValueError(f"{data_spec} normal setting must contain a local ISO 8601 datetime")
    return result


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


def verify_realtime_race_key(
    setting: Path, data_specs: frozenset[str], race_key: RaceKeyLike
) -> None:
    """Check that a generated setting enables the requested DataSpecs for the target race.

    Only realtime updates and the requested DataSpecs are checked; other sections are left
    to the builder.

    Raises:
        ValueError: If realtime updates, a requested DataSpec, or its race key
            differ from the requested values.
        xml.etree.ElementTree.ParseError: If the setting is not well-formed XML.
        OSError: If the setting cannot be read.
    """
    details = _required_child(ET.parse(setting).getroot(), "Details")
    realtime = _required_child(details, "JVRealTimeDataUpdateSetting")
    if realtime.findtext("IsEnabled") != "true":
        raise ValueError("generated setting does not enable realtime updates")
    expected = {
        "KaisaiDate": race_key.race_date.isoformat() + "T00:00:00",
        "JyoCD": race_key.jyo_code,
        "Kaiji": race_key.kaiji,
        "Nichiji": race_key.nichiji,
        "RaceNum": race_key.race_number,
    }
    found: set[str] = set()
    for data_spec_setting in _required_child(realtime, "DataSpecSettings").findall(
        "JVDataSpecSetting"
    ):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec not in data_specs:
            continue
        found.add(data_spec)
        if data_spec_setting.findtext("IsEnabled") != "true":
            raise ValueError(f"generated setting does not enable {data_spec}")
        key = data_spec_setting.find("JVRaceKey")
        if key is None:
            raise ValueError(f"{data_spec} setting must contain a JVRaceKey")
        for tag, value in expected.items():
            if key.findtext(tag) != value:
                raise ValueError(f"generated {data_spec} JVRaceKey.{tag} does not match the race")
    missing = data_specs - found
    if missing:
        raise ValueError(f"setting is missing data specs: {', '.join(sorted(missing))}")


def _required_child(parent: ET.Element, tag: str) -> ET.Element:
    element = parent.find(tag)
    if element is None:
        raise ValueError(f"JVLinkToSQLite setting is missing required element: {tag}")
    return element


def _set_required_text(parent: ET.Element, tag: str, value: str) -> None:
    element = _required_child(parent, tag)
    element.text = value
