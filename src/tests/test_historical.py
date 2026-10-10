"""Tests for historical race and odds retrieval orchestration."""

import sqlite3
from collections.abc import Iterable
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from data.race_key import RaceKey
from data.retriever.historical import HistoricalRetriever
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


def _retriever(database: Path) -> HistoricalRetriever:
    return HistoricalRetriever(
        Mock(),
        database,
        Mock(),
        Mock(),
        _profile(),
        _profile(race_start_date=date(2003, 10, 4)),
    )


_ODDS_TABLES = {
    "0B41": "ARCHIVE_O1_ODDS_TANFUKUWAKU",
    "0B42": "ARCHIVE_O2_ODDS_UMAREN",
}
_ELIGIBLE_RACE_ROWS = [
    ("2003", "1004", "05", "04", "09", "01"),
    ("2026", "1003", "06", "04", "07", "12"),
]


def _create_odds_archive(path: Path, data_spec: str, rows: Iterable[tuple[str, ...]]) -> None:
    table = _ODDS_TABLES[data_spec]
    with sqlite3.connect(path) as database:
        database.execute(
            f'CREATE TABLE "{table}" (idYear TEXT, idMonthDay TEXT, idJyoCD TEXT, '
            "idKaiji TEXT, idNichiji TEXT, idRaceNum TEXT)"
        )
        database.executemany(f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?)', rows)


def _odds_retriever(
    database: Path,
    *,
    skip_existing: bool = True,
    data_specs: frozenset[str] = frozenset({"0B41", "0B42"}),
) -> tuple[HistoricalRetriever, Mock, Mock, Mock]:
    runner = Mock()
    builder = Mock()
    archive = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    historical_profile = replace(_profile(), setup_update=False)
    odds_profile = JVLinkProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=data_specs,
        race_start_date=date(2003, 10, 4),
        skip_existing=skip_existing,
    )
    retriever = HistoricalRetriever(
        runner, database, builder, archive, historical_profile, odds_profile
    )
    return retriever, runner, builder, archive


def test_iter_race_keys_starts_at_configured_odds_date(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)

    assert list(_retriever(database).iter_race_keys(start_date=date(2003, 10, 4))) == [
        RaceKey(date(2003, 10, 4), "05", "04", "09", "01"),
        RaceKey(date(2026, 10, 3), "06", "04", "07", "12"),
    ]


def test_iter_race_keys_closes_reader_before_first_yield(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    race_keys = _retriever(database).iter_race_keys(start_date=date(2003, 10, 4))

    assert next(race_keys) == RaceKey(date(2003, 10, 4), "05", "04", "09", "01")

    with sqlite3.connect(database, timeout=0) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        writer.rollback()


def test_retrieve_builds_temporary_base_and_archives_each_odds_result(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    runner = Mock()
    builder = Mock()
    archive = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    historical_profile = _profile()
    odds_profile = _profile(race_start_date=date(2003, 10, 4))
    retriever = HistoricalRetriever(
        runner,
        database,
        builder,
        archive,
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
    assert archive.archive.call_count == 2


def test_retrieve_basic_runs_only_base_update(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    runner = Mock()
    runner.execute.side_effect = lambda *_args, **_kwargs: _create_race_db(database)
    builder = Mock()
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    archive = Mock()
    retriever = HistoricalRetriever(
        runner,
        database,
        builder,
        archive,
        _profile(),
        _profile(),
    )

    retriever.retrieve_basic()

    runner.execute.assert_called_once()
    assert runner.execute.call_args.args[0].name == "historical.xml"
    assert builder.build.call_count == 1
    archive.archive.assert_not_called()


def test_iter_race_keys_skips_non_jra_races(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE NL_RA_RACE (idYear TEXT, idMonthDay TEXT, idJyoCD TEXT, "
            "idKaiji TEXT, idNichiji TEXT, idRaceNum TEXT)"
        )
        connection.execute(
            "INSERT INTO NL_RA_RACE VALUES (?, ?, ?, ?, ?, ?)",
            ("2026", "1003", "A4", "00", "00", "07"),
        )

    assert list(_retriever(database).iter_race_keys(start_date=date(2003, 10, 4))) == []


def test_manual_race_key_requires_two_digit_components() -> None:
    with pytest.raises(ValueError, match="jyo_code must be a two-digit string"):
        RaceKey(date(2026, 10, 4), "5", "04", "08", "11")


def test_retrieve_skips_fully_archived_races_without_odds_execution(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    for data_spec in _ODDS_TABLES:
        _create_odds_archive(database, data_spec, _ELIGIBLE_RACE_ROWS)
    retriever, runner, builder, archive = _odds_retriever(database)

    assert retriever.retrieve() == 0

    runner.execute.assert_not_called()
    builder.build.assert_not_called()
    archive.archive.assert_not_called()


@pytest.mark.parametrize("archived_spec", ["0B41", "0B42"])
def test_retrieve_requests_only_the_missing_odds_spec(tmp_path: Path, archived_spec: str) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    for data_spec in _ODDS_TABLES:
        rows = _ELIGIBLE_RACE_ROWS if data_spec == archived_spec else _ELIGIBLE_RACE_ROWS[1:]
        _create_odds_archive(database, data_spec, rows)
    retriever, runner, builder, archive = _odds_retriever(database)

    assert retriever.retrieve() == 1

    runner.execute.assert_called_once()
    archive.archive.assert_called_once()
    builder.build.assert_called_once()
    call = builder.build.call_args
    assert call.args[0].realtime_data_specs == frozenset(_ODDS_TABLES) - {archived_spec}
    assert call.kwargs["race_key"] == RaceKey(date(2003, 10, 4), "05", "04", "09", "01")


@pytest.mark.parametrize("empty_tables", [False, True])
def test_retrieve_fetches_odds_when_archives_are_missing_or_empty(
    tmp_path: Path, empty_tables: bool
) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    if empty_tables:
        for data_spec in _ODDS_TABLES:
            _create_odds_archive(database, data_spec, [])
    retriever, runner, builder, archive = _odds_retriever(database)

    assert retriever.retrieve() == 2

    assert runner.execute.call_count == 2
    assert archive.archive.call_count == 2
    assert all(
        call.args[0].realtime_data_specs == frozenset(_ODDS_TABLES)
        for call in builder.build.call_args_list
    )
    assert all(call.args[1].name == "historical-odds.xml" for call in builder.build.call_args_list)


@pytest.mark.parametrize(
    ("component", "different_value"),
    [(0, "2004"), (1, "1005"), (2, "06"), (3, "05"), (4, "08"), (5, "02")],
)
def test_retrieve_does_not_skip_a_race_with_any_different_key_component(
    tmp_path: Path, component: int, different_value: str
) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    different_race = list(_ELIGIBLE_RACE_ROWS[0])
    different_race[component] = different_value
    for data_spec in _ODDS_TABLES:
        _create_odds_archive(database, data_spec, [tuple(different_race), _ELIGIBLE_RACE_ROWS[1]])
    retriever, runner, builder, archive = _odds_retriever(database)

    assert retriever.retrieve() == 1

    runner.execute.assert_called_once()
    archive.archive.assert_called_once()
    assert builder.build.call_args.args[0].realtime_data_specs == frozenset(_ODDS_TABLES)
    assert builder.build.call_args.kwargs["race_key"] == RaceKey(
        date(2003, 10, 4), "05", "04", "09", "01"
    )


def test_retrieve_preserves_unknown_odds_specs(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    for data_spec in _ODDS_TABLES:
        _create_odds_archive(database, data_spec, _ELIGIBLE_RACE_ROWS)
    retriever, runner, builder, archive = _odds_retriever(
        database, data_specs=frozenset({"0B41", "0B42", "OTHER"})
    )

    assert retriever.retrieve() == 2

    assert runner.execute.call_count == 2
    assert archive.archive.call_count == 2
    assert all(
        call.args[0].realtime_data_specs == frozenset({"OTHER"})
        for call in builder.build.call_args_list
    )


def test_retrieve_closes_readers_before_subprocess_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    for data_spec in _ODDS_TABLES:
        _create_odds_archive(database, data_spec, [])
    retriever, runner, _, _ = _odds_retriever(database)
    connect = sqlite3.connect
    readers: list[sqlite3.Connection] = []

    def open_reader(database_uri: str, *, uri: bool = False) -> sqlite3.Connection:
        connection = connect(database_uri, uri=uri)
        readers.append(connection)
        return connection

    def execute_with_writer(setting: Path, *, skip_last_modified_update: bool) -> None:
        assert readers
        for reader in readers:
            with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
                reader.execute("SELECT 1")
        with connect(database, timeout=0) as writer:
            writer.execute("BEGIN EXCLUSIVE")
            writer.rollback()

    monkeypatch.setattr("data.retriever.historical.sqlite3.connect", open_reader)
    runner.execute.side_effect = execute_with_writer

    assert retriever.retrieve() == 2


def test_retrieve_requires_existing_database_when_base_updates_are_disabled(tmp_path: Path) -> None:
    retriever, runner, builder, archive = _odds_retriever(tmp_path / "missing.db")

    with pytest.raises(FileNotFoundError, match="raw race database does not exist"):
        retriever.retrieve()

    runner.execute.assert_not_called()
    builder.build.assert_not_called()
    archive.archive.assert_not_called()


def test_retrieve_does_not_treat_staging_rows_as_archived_odds(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE RT_O1_ODDS_TANFUKUWAKU AS SELECT * FROM NL_RA_RACE")
        connection.execute("CREATE TABLE RT_O2_ODDS_UMAREN AS SELECT * FROM NL_RA_RACE")
    retriever, runner, builder, archive = _odds_retriever(database)

    assert retriever.retrieve() == 2

    assert runner.execute.call_count == 2
    assert archive.archive.call_count == 2
    assert all(
        call.args[0].realtime_data_specs == frozenset(_ODDS_TABLES)
        for call in builder.build.call_args_list
    )


def test_retrieve_refetches_archived_odds_when_skip_existing_is_false(tmp_path: Path) -> None:
    database = tmp_path / "race.db"
    _create_race_db(database)
    for data_spec in _ODDS_TABLES:
        _create_odds_archive(database, data_spec, _ELIGIBLE_RACE_ROWS)
    retriever, runner, builder, archive = _odds_retriever(database, skip_existing=False)

    assert retriever.retrieve() == 2

    assert runner.execute.call_count == 2
    assert archive.archive.call_count == 2
    assert all(
        call.args[0].realtime_data_specs == frozenset(_ODDS_TABLES)
        for call in builder.build.call_args_list
    )
