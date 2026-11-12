"""Tests for declarative JVLinkToSQLite setting generation."""

import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.setting_xml import (
    JVLinkSettingBuilder,
    verify_realtime_race_key,
)
from jra_van_retriever.config.profiles import (
    JVLinkConfig,
    JVLinkProfile,
)
from jra_van_retriever.config.validation import validate_historical_odds_batch


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
"""
        + "".join(
            f"      <JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>{spec}</DataSpec>"
            "<JVRaceKey><KaisaiDate>2026-01-01T00:00:00</KaisaiDate><JyoCD>01</JyoCD>"
            "<Kaiji>01</Kaiji><Nichiji>01</Nichiji><RaceNum>01</RaceNum></JVRaceKey>"
            "</JVDataSpecSetting>\n"
            for spec in ("0B31", "0B32", "0B33", "0B34", "0B35", "0B36")
        )
        + """    </DataSpecSettings></JVRealTimeDataUpdateSetting>
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


RACE_DAY_SPECS = frozenset({"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"})
RACE_DAY_KEY = RaceKey(date(2026, 11, 15), "05", "05", "04", "11")


def _race_day_setting(tmp_path: Path) -> Path:
    seed = tmp_path / "setting.xml"
    _write_seed(seed)
    profile = JVLinkProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=RACE_DAY_SPECS,
    )
    return JVLinkSettingBuilder(seed).build(
        profile, tmp_path / "race-day-odds.xml", race_key=RACE_DAY_KEY
    )


def test_verify_realtime_race_key_accepts_a_generated_race_day_setting(tmp_path: Path) -> None:
    verify_realtime_race_key(_race_day_setting(tmp_path), RACE_DAY_SPECS, RACE_DAY_KEY)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("spec_disabled", "does not enable 0B33"),
        ("realtime_disabled", "does not enable realtime updates"),
        ("race_mismatch", "JVRaceKey.RaceNum does not match"),
        ("no_race_key", "0B31 setting must contain a JVRaceKey"),
        ("spec_missing", "missing data specs: 0B36"),
    ],
)
def test_verify_realtime_race_key_rejects_settings_that_differ_from_the_race(
    tmp_path: Path, case: str, message: str
) -> None:
    setting = _race_day_setting(tmp_path)
    tree = ET.parse(setting)
    root = tree.getroot()
    realtime = _child(root, "Details/JVRealTimeDataUpdateSetting")
    if case == "spec_disabled":
        _child(_spec(root, "0B33"), "IsEnabled").text = "false"
    elif case == "realtime_disabled":
        _child(realtime, "IsEnabled").text = "false"
    elif case == "race_mismatch":
        _child(_spec(root, "0B35"), "JVRaceKey/RaceNum").text = "12"
    elif case == "no_race_key":
        _spec(root, "0B31").remove(_child(_spec(root, "0B31"), "JVRaceKey"))
    else:
        _child(realtime, "DataSpecSettings").remove(_spec(root, "0B36"))
    tree.write(setting, encoding="utf-8", xml_declaration=True)

    with pytest.raises(ValueError, match=message):
        verify_realtime_race_key(setting, RACE_DAY_SPECS, RACE_DAY_KEY)


def _child(parent: ET.Element, path: str) -> ET.Element:
    node = parent.find(path)
    assert node is not None, path
    return node


def _spec(root: ET.Element, data_spec: str) -> ET.Element:
    for node in root.iter("JVDataSpecSetting"):
        if node.findtext("DataSpec") == data_spec:
            return node
    raise AssertionError(data_spec)


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
    config_path = Path(__file__).parents[3] / "configs" / "jvlink.toml"

    config = JVLinkConfig.from_toml(config_path)

    assert config.historical.start_datetime is None
    assert config.historical.start_datetimes is not None
    assert config.historical.start_datetimes["RACE"].isoformat() == "1986-01-01T00:00:00"
    assert config.historical.start_datetimes["WOOD"].isoformat() == "2021-07-27T00:00:00"


def test_config_loads_realtime_race(tmp_path: Path) -> None:
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
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
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
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
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
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
    config_path = Path(__file__).parents[3] / "configs" / "jvlink.toml"

    config = JVLinkConfig.from_toml(config_path)

    assert not config.historical.normal_update
    assert config.historical.setup_update
    assert not config.historical.realtime_update
    assert config.historical_odds.skip_existing
    assert config.historical_odds.race_start_date == date(2003, 10, 4)
    assert config.historical_odds.realtime_data_specs == frozenset({"0B41", "0B42"})
    assert config.historical_odds_batch is not None
    assert config.historical_odds_batch.first_year == 2003
    assert config.historical_odds_batch.last_year == 2026
    assert config.historical_odds_batch.years_per_run == 1


def test_config_rejects_removed_initial_gap_policy(tmp_path: Path) -> None:
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(
        source.read_text(encoding="utf-8").replace(
            "years_per_run = 1\n",
            'years_per_run = 1\naccept_existing_gaps_through = "2008-01-26/06/01/07/06"\n',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"historical_odds\.batch contains unsupported settings"):
        JVLinkConfig.from_toml(config_path)


def test_historical_odds_rejects_refetch_policy() -> None:
    config_path = Path(__file__).parents[3] / "configs" / "jvlink.toml"
    config = JVLinkConfig.from_toml(config_path)
    assert config.historical_odds_batch is not None

    with pytest.raises(ValueError, match="skip_existing=true"):
        validate_historical_odds_batch(
            replace(config.historical_odds, skip_existing=False), config.historical_odds_batch
        )


def test_builder_sets_the_race_key_for_every_race_day_odds_spec(tmp_path: Path) -> None:
    seed = tmp_path / "setting.xml"
    _write_seed(seed)
    config = JVLinkConfig.from_toml(Path(__file__).parents[3] / "configs" / "jvlink.toml")
    assert config.race_day_odds is not None

    destination = tmp_path / "race-day-odds.xml"
    JVLinkSettingBuilder(seed).build(
        config.race_day_odds,
        destination,
        race_key=RaceKey(date(2026, 11, 15), "05", "05", "04", "11"),
    )

    root = ET.parse(destination).getroot()
    settings = {node.findtext("DataSpec"): node for node in root.iter("JVDataSpecSetting")}
    assert settings["0B41"].findtext("IsEnabled") == "false"
    assert settings["0B11"].findtext("IsEnabled") == "false"
    for data_spec in ("0B31", "0B32", "0B33", "0B34", "0B35", "0B36"):
        setting = settings[data_spec]
        assert setting.findtext("IsEnabled") == "true"
        assert setting.findtext("JVRaceKey/KaisaiDate") == "2026-11-15T00:00:00"
        assert setting.findtext("JVRaceKey/JyoCD") == "05"
        assert setting.findtext("JVRaceKey/Kaiji") == "05"
        assert setting.findtext("JVRaceKey/Nichiji") == "04"
        assert setting.findtext("JVRaceKey/RaceNum") == "11"


def test_repository_config_loads_race_day_odds_profile() -> None:
    config = JVLinkConfig.from_toml(Path(__file__).parents[3] / "configs" / "jvlink.toml")

    assert config.race_day_odds is not None
    assert config.race_day_odds.realtime_data_specs == frozenset(
        {"0B31", "0B32", "0B33", "0B34", "0B35", "0B36"}
    )
    assert config.race_day_odds.offsets_minutes == (30, 10, 5, 2)
    assert config.race_day_odds.late_tolerance_seconds == 60
    assert config.race_day_odds.execution_timeout_seconds == 120
    assert config.race_day_odds.prediction_offset_minutes == 5


def test_config_without_race_day_odds_section_still_loads(tmp_path: Path) -> None:
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
    content = source.read_text(encoding="utf-8")
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(content.split("\n[race_day_odds]\n")[0] + "\n", encoding="utf-8")

    config = JVLinkConfig.from_toml(config_path)

    assert config.race_day_odds is None
    assert config.realtime_current.realtime_data_specs == frozenset({"0B31", "0B32"})


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'realtime_data_specs = ["0B31", "0B32", "0B33", "0B34", "0B35", "0B36"]',
            'realtime_data_specs = ["0B31"]',
            "exactly 0B31 through 0B36",
        ),
        ("offsets_minutes = [30, 10, 5, 2]", "offsets_minutes = []", "non-empty array"),
        ("offsets_minutes = [30, 10, 5, 2]", "offsets_minutes = [5, 5]", "duplicates"),
        ("offsets_minutes = [30, 10, 5, 2]", 'offsets_minutes = ["5"]', "positive integers"),
        ("late_tolerance_seconds = 60", "late_tolerance_seconds = 0", "positive integer"),
        ("late_tolerance_seconds = 60", "", "positive integer"),
        ("execution_timeout_seconds = 120", "execution_timeout_seconds = 0", "positive integer"),
        ("execution_timeout_seconds = 120", "execution_timeout_seconds = -1", "positive integer"),
        ("execution_timeout_seconds = 120", "execution_timeout_seconds = 1.5", "positive integer"),
        ("execution_timeout_seconds = 120", "execution_timeout_seconds = true", "positive integer"),
        ("execution_timeout_seconds = 120", "", "positive integer"),
        ("prediction_offset_minutes = 5", "prediction_offset_minutes = 2", "3 through 5"),
        ("prediction_offset_minutes = 5", "prediction_offset_minutes = 6", "3 through 5"),
        ("prediction_offset_minutes = 5", 'prediction_offset_minutes = "5"', "positive integer"),
    ],
)
def test_config_rejects_invalid_race_day_odds_section(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
    head, section = source.read_text(encoding="utf-8").split("\n[race_day_odds]\n")
    assert old in section
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(
        head + "\n[race_day_odds]\n" + section.replace(old, new), encoding="utf-8"
    )

    with pytest.raises(ValueError, match=message):
        JVLinkConfig.from_toml(config_path)


def test_config_without_prediction_offset_keeps_the_capture_only_plan(tmp_path: Path) -> None:
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
    content = source.read_text(encoding="utf-8")
    line = "prediction_offset_minutes = 5\n"
    assert line in content
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(content.replace(line, ""), encoding="utf-8")

    config = JVLinkConfig.from_toml(config_path)

    assert config.race_day_odds is not None
    assert config.race_day_odds.prediction_offset_minutes is None


def test_prediction_offset_requires_a_0b41_0b42_realtime_history_profile(tmp_path: Path) -> None:
    source = Path(__file__).parents[3] / "configs" / "jvlink.toml"
    head, section = source.read_text(encoding="utf-8").split("\n[realtime_history]\n")
    old = 'realtime_data_specs = ["0B41", "0B42"]'
    assert old in section.split("\n[", 1)[0]
    config_path = tmp_path / "jvlink.toml"
    config_path.write_text(
        head + "\n[realtime_history]\n" + section.replace(old, 'realtime_data_specs = ["0B41"]', 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly 0B41 and 0B42"):
        JVLinkConfig.from_toml(config_path)
