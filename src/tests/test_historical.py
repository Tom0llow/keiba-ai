"""Tests for historical race and odds retrieval orchestration."""

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from data.retriever.historical import HistoricalRetriever, RaceKey
from data.retriever.setting import JVLinkProfile


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


def _profile(*, race_start_date: date | None = None) -> JVLinkProfile:
    return JVLinkProfile(
        normal_update=False,
        setup_update=True,
        realtime_update=False,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset({"RACE"}),
        realtime_data_specs=frozenset(),
        race_start_date=race_start_date,
    )


def test_iter_race_keys_starts_at_configured_odds_date(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    retriever = HistoricalRetriever(
        Mock(),
        database,
        Mock(),
        _profile(),
        _profile(race_start_date=date(2003, 10, 4)),
    )

    assert list(retriever.iter_race_keys(start_date=date(2003, 10, 4))) == [
        RaceKey(date(2003, 10, 4), "05", "04", "09", "01"),
        RaceKey(date(2026, 10, 3), "06", "04", "07", "12"),
    ]


def test_retrieve_builds_temporary_base_and_odds_settings(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    runner = Mock()
    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    historical_profile = _profile()
    odds_profile = _profile(race_start_date=date(2003, 10, 4))
    retriever = HistoricalRetriever(
        runner,
        database,
        builder,
        historical_profile,
        odds_profile,
    )

    count = retriever.retrieve()

    assert count == 2
    assert runner.execute.call_count == 3
    assert runner.execute.call_args_list[0].kwargs == {"skip_last_modified_update": True}
    assert runner.execute.call_args_list[0].args[0].name == "historical.xml"
    for call in runner.execute.call_args_list[1:]:
        assert call.kwargs == {"skip_last_modified_update": True}
        assert call.args[0].name == "historical-odds.xml"
    assert builder.build.call_count == 3


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

    retriever = HistoricalRetriever(
        Mock(),
        database,
        Mock(),
        _profile(),
        _profile(race_start_date=date(2003, 10, 4)),
    )
    with pytest.raises(ValueError, match="invalid idJyoCD"):
        list(retriever.iter_race_keys(start_date=date(2003, 10, 4)))
