"""Tests for declarative JVLinkToSQLite setting generation."""

import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from data.race_key import RaceKey
from data.retriever.setting import JVLinkProfile, JVLinkSettingBuilder


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
