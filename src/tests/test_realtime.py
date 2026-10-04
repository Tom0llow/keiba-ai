"""Tests for prediction-time realtime odds retrieval."""

from datetime import date
from pathlib import Path
from unittest.mock import Mock

from data.retriever.historical import RaceKey
from data.retriever.realtime import RealtimeRetriever
from data.retriever.setting import JVLinkProfile


def _profile(data_specs: set[str]) -> JVLinkProfile:
    return JVLinkProfile(
        normal_update=False,
        setup_update=False,
        realtime_update=True,
        normal_data_specs=frozenset(),
        setup_data_specs=frozenset(),
        realtime_data_specs=frozenset(data_specs),
    )


def test_retrieve_archives_history_before_current_snapshot(tmp_path: Path) -> None:
    runner = Mock()
    builder = Mock()
    archive = Mock()
    archive.archive.side_effect = [11, 2]
    builder.build.side_effect = lambda profile, destination, **kwargs: destination
    history_profile = _profile({"0B41", "0B42"})
    current_profile = _profile({"0B31", "0B32"})
    retriever = RealtimeRetriever(
        runner,
        builder,
        archive,
        history_profile,
        current_profile,
    )
    race_key = RaceKey(date(2026, 10, 4), "05", "04", "08", "11")

    inserted = retriever.retrieve(race_key)

    assert inserted == 13
    assert builder.build.call_count == 2
    history_call, current_call = builder.build.call_args_list
    assert history_call.args[0] is history_profile
    assert history_call.args[1].name == "realtime-history.xml"
    assert history_call.kwargs["race_key"] == race_key
    assert current_call.args[0] is current_profile
    assert current_call.args[1].name == "realtime-current.xml"
    assert current_call.kwargs["race_key"] == race_key
    assert runner.execute.call_count == 2
    for call in runner.execute.call_args_list:
        assert call.kwargs == {"skip_last_modified_update": True}
    assert archive.archive.call_count == 2
