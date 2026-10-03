"""Tests for historical race and odds retrieval orchestration."""

import sqlite3
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from data.retriever.historical import HistoricalRetriever, RaceKey, _write_odds_setting


def _create_race_db(path: Path) -> None:
    with sqlite3.connect(path) as database:
        database.execute(
            """
            CREATE TABLE NL_RA_RACE (
                idYear TEXT,
                idMonthDay TEXT,
                idJyoCD TEXT,
                idKaiji TEXT,
                idNichiji TEXT,
                idRaceNum TEXT
            )
            """
        )
        database.executemany(
            "INSERT INTO NL_RA_RACE VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("2003", "1003", "05", "04", "08", "11"),
                ("2003", "1004", "05", "04", "09", "01"),
                ("2026", "1003", "06", "04", "07", "12"),
            ],
        )


def _write_template(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<JVLinkToSQLiteSetting>
  <JVDataSpecSetting>
    <IsEnabled>false</IsEnabled>
    <DataSpec>0B41</DataSpec>
    <JVRaceKey>
      <KaisaiDate>2000-01-01T00:00:00</KaisaiDate>
      <JyoCD>01</JyoCD>
      <Kaiji>01</Kaiji>
      <Nichiji>01</Nichiji>
      <RaceNum>01</RaceNum>
    </JVRaceKey>
  </JVDataSpecSetting>
  <JVDataSpecSetting>
    <IsEnabled>false</IsEnabled>
    <DataSpec>0B42</DataSpec>
    <JVRaceKey>
      <KaisaiDate>2000-01-01T00:00:00</KaisaiDate>
      <JyoCD>01</JyoCD>
      <Kaiji>01</Kaiji>
      <Nichiji>01</Nichiji>
      <RaceNum>01</RaceNum>
    </JVRaceKey>
  </JVDataSpecSetting>
</JVLinkToSQLiteSetting>
""",
        encoding="utf-8",
    )


def test_iter_race_keys_starts_at_supported_odds_date(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    retriever = HistoricalRetriever(Mock(), database)

    assert list(retriever.iter_race_keys()) == [
        RaceKey(date(2003, 10, 4), "05", "04", "09", "01"),
        RaceKey(date(2026, 10, 3), "06", "04", "07", "12"),
    ]


def test_write_odds_setting_updates_both_time_series_specs(tmp_path: Path) -> None:
    template = tmp_path / "template.xml"
    destination = tmp_path / "generated.xml"
    _write_template(template)

    _write_odds_setting(
        template,
        destination,
        RaceKey(date(2026, 10, 3), "06", "04", "07", "12"),
    )

    root = ET.parse(destination).getroot()
    settings = {node.findtext("DataSpec"): node for node in root.iter("JVDataSpecSetting")}
    for data_spec in ("0B41", "0B42"):
        setting = settings[data_spec]
        assert setting.findtext("IsEnabled") == "true"
        race_key = setting.find("JVRaceKey")
        assert race_key is not None
        assert race_key.findtext("KaisaiDate") == "2026-10-03T00:00:00"
        assert race_key.findtext("JyoCD") == "06"
        assert race_key.findtext("Kaiji") == "04"
        assert race_key.findtext("Nichiji") == "07"
        assert race_key.findtext("RaceNum") == "12"


def test_retrieve_runs_base_then_odds_for_each_eligible_race(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    base_setting = tmp_path / "base.xml"
    base_setting.write_text("<setting />", encoding="utf-8")
    odds_template = tmp_path / "odds.xml"
    _write_template(odds_template)
    runner = Mock()
    retriever = HistoricalRetriever(runner, database)

    count = retriever.retrieve(base_setting, odds_template)

    assert count == 2
    assert runner.execute.call_count == 3
    assert runner.execute.call_args_list[0].args == (base_setting,)
    for call in runner.execute.call_args_list[1:]:
        assert call.kwargs == {"skip_last_modified_update": True}
        assert call.args[0].name == "historical-odds.xml"


def test_invalid_race_key_component_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT, idMonthDay TEXT, idJyoCD TEXT, "
            "idKaiji TEXT, idNichiji TEXT, idRaceNum TEXT)"
        )
        connection.execute(
            "INSERT INTO NL_RA_RACE VALUES (?, ?, ?, ?, ?, ?)",
            ("2026", "1003", "6", "04", "07", "12"),
        )

    with pytest.raises(ValueError, match="invalid idJyoCD"):
        list(HistoricalRetriever(Mock(), database).iter_race_keys())


def test_odds_template_requires_both_data_specs(tmp_path: Path) -> None:
    template = tmp_path / "template.xml"
    template.write_text(
        "<Root><JVDataSpecSetting><IsEnabled>false</IsEnabled><DataSpec>0B41</DataSpec>"
        "<JVRaceKey><KaisaiDate/><JyoCD/><Kaiji/><Nichiji/><RaceNum/></JVRaceKey>"
        "</JVDataSpecSetting></Root>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="0B42"):
        _write_odds_setting(
            template,
            tmp_path / "out.xml",
            RaceKey(date(2026, 10, 3), "06", "04", "07", "12"),
        )
