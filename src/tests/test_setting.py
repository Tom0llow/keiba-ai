"""Tests for declarative JVLinkToSQLite setting generation."""

import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import pytest

from data.race_key import RaceKey
from data.retriever.setting import JVLinkConfig, JVLinkProfile, JVLinkSettingBuilder


def _write_seed(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<JVLinkToSQLiteSetting>
  <Details>
    <JVNormalUpdateSetting><IsEnabled>true</IsEnabled><DataSpecSettings>
      <JVDataSpecSetting><IsEnabled>true</IsEnabled><DataSpec>RACE</DataSpec>
        <JVKaisaiDateTimeKey><KaisaiDateTime>2026-01-01T00:00:00</KaisaiDateTime></JVKaisaiDateTimeKey>
      </JVDataSpecSetting>
    </DataSpecSettings></JVNormalUpdateSetting>
    <JVSetupDataUpdateSetting><IsEnabled>false</IsEnabled><DataSpecSettings>
      <JVDataSpecSetting><IsEnabled>true</IsEnabled><DataSpec>RACE</DataSpec>
        <JVKaisaiDateTimeKey><KaisaiDateTime>2015-01-01T00:00:00</KaisaiDateTime></JVKaisaiDateTimeKey>
      </JVDataSpecSetting>
      <JVDataSpecSetting><IsEnabled>true</IsEnabled><DataSpec>WOOD</DataSpec>
        <JVKaisaiDateTimeKey><KaisaiDateTime>2015-01-01T00:00:00</KaisaiDateTime></JVKaisaiDateTimeKey>
      </JVDataSpecSetting>
    </DataSpecSettings></JVSetupDataUpdateSetting>
    <JVRealTimeDataUpdateSetting><IsEnabled>true</IsEnabled><DataSpecSettings>
      <JVDataSpecSetting><IsEnabled>true</IsEnabled><DataSpec>0B11</DataSpec><JVKaisaiDateKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate></JVKaisaiDateKey></JVDataSpecSetting>
      <JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>0B41</DataSpec><JVRaceKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate><JyoCD>01</JyoCD><Kaiji>01</Kaiji><Nichiji>01</Nichiji><RaceNum>01</RaceNum></JVRaceKey></JVDataSpecSetting>
      <JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>0B42</DataSpec><JVRaceKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate><JyoCD>01</JyoCD><Kaiji>01</Kaiji><Nichiji>01</Nichiji><RaceNum>01</RaceNum></JVRaceKey></JVDataSpecSetting>
    </DataSpecSettings></JVRealTimeDataUpdateSetting>
  </Details>
</JVLinkToSQLiteSetting>
""",
        encoding="utf-8",
    )


def test_builder_applies_exclusive_odds_profile_and_race_key(tmp_path: Path) -> None:
    seed = tmp_path / "setting.xml"
    _write_seed(seed)
    profile = JVLinkProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=frozenset({"0B41", "0B42"}),
        race_start_date=date(2003, 10, 4),
    )

    destination = tmp_path / "odds.xml"
    JVLinkSettingBuilder(seed).build(
        profile,
        destination,
        race_key=RaceKey(date(2026, 10, 3), "06", "04", "07", "12"),
    )

    root = ET.parse(destination).getroot()
    settings = {node.findtext("DataSpec"): node for node in root.iter("JVDataSpecSetting")}
    assert settings["0B11"].findtext("IsEnabled") == "false"
    for data_spec in ("0B41", "0B42"):
        setting = settings[data_spec]
        assert setting.findtext("IsEnabled") == "true"
        assert setting.findtext("JVRaceKey/KaisaiDate") == "2026-10-03T00:00:00"
        assert setting.findtext("JVRaceKey/JyoCD") == "06"
        assert setting.findtext("JVRaceKey/Kaiji") == "04"
        assert setting.findtext("JVRaceKey/Nichiji") == "07"
        assert setting.findtext("JVRaceKey/RaceNum") == "12"


def test_builder_applies_data_spec_specific_setup_start_datetimes(tmp_path: Path) -> None:
    seed = tmp_path / "setting.xml"
    _write_seed(seed)
    profile = JVLinkProfile(
        normal_update=False,
        setup_update=True,
        realtime_update=False,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset({"RACE", "WOOD"}),
        realtime_data_specs=frozenset(),
        start_datetimes={
            "RACE": datetime(1986, 1, 1),
            "WOOD": datetime(2021, 7, 27),
        },
    )

    destination = tmp_path / "historical.xml"
    JVLinkSettingBuilder(seed).build(profile, destination)

    root = ET.parse(destination).getroot()
    settings = {node.findtext("DataSpec"): node for node in root.iter("JVDataSpecSetting")}
    assert settings["RACE"].findtext("JVKaisaiDateTimeKey/KaisaiDateTime") == (
        "1986-01-01T00:00:00"
    )
    assert settings["WOOD"].findtext("JVKaisaiDateTimeKey/KaisaiDateTime") == (
        "2021-07-27T00:00:00"
    )


def test_config_loads_data_spec_specific_historical_start_datetimes() -> None:
    config_path = Path(__file__).parents[2] / "config" / "jvlink.toml"

    config = JVLinkConfig.from_toml(config_path)

    assert config.historical.start_datetime is None
    assert config.historical.start_datetimes is not None
    assert config.historical.start_datetimes["RACE"].isoformat() == "1986-01-01T00:00:00"
    assert config.historical.start_datetimes["WOOD"].isoformat() == "2021-07-27T00:00:00"


def test_config_loads_realtime_race(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "config" / "jvlink.toml"
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(
        source.read_text(encoding="utf-8")
        + "\n[realtime]\n"
        + "date = 2026-10-04\n"
        + 'jyo = "05"\n'
        + 'kaiji = "04"\n'
        + 'nichiji = "08"\n'
        + 'race = "11"\n',
        encoding="utf-8",
    )

    config = JVLinkConfig.from_toml(config_path)

    assert config.realtime_race == RaceKey(date(2026, 10, 4), "05", "04", "08", "11")


@pytest.mark.parametrize("value", [None, "true", "false"])
def test_config_loads_optional_skip_existing(tmp_path: Path, value: str | None) -> None:
    source = Path(__file__).parents[2] / "config" / "jvlink.toml"
    config_path = tmp_path / "jvlink.toml"
    content = source.read_text(encoding="utf-8").replace("skip_existing = true\n", "")
    if value is not None:
        content = content.replace(
            "[historical_odds]\n", f"[historical_odds]\nskip_existing = {value}\n"
        )
    config_path.write_text(content, encoding="utf-8")

    config = JVLinkConfig.from_toml(config_path)

    assert config.historical_odds.skip_existing is (value == "true")
    assert config.realtime_history.skip_existing is False


@pytest.mark.parametrize("value", ['"true"', "1", "[]"])
def test_config_rejects_non_boolean_skip_existing(tmp_path: Path, value: str) -> None:
    source = Path(__file__).parents[2] / "config" / "jvlink.toml"
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(
        source.read_text(encoding="utf-8").replace(
            "skip_existing = true", f"skip_existing = {value}"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"\[historical_odds\]\.skip_existing must be a boolean"):
        JVLinkConfig.from_toml(config_path)


def test_repository_config_retrieves_only_missing_historical_odds() -> None:
    config_path = Path(__file__).parents[2] / "config" / "jvlink.toml"

    config = JVLinkConfig.from_toml(config_path)

    assert not config.historical.normal_update
    assert not config.historical.setup_update
    assert not config.historical.realtime_update
    assert config.historical_odds.skip_existing
    assert config.historical_odds.race_start_date == date(2003, 10, 4)
    assert config.historical_odds.realtime_data_specs == frozenset({"0B41", "0B42"})
