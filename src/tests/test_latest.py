"""Tests for latest-data retrieval orchestration."""

from pathlib import Path
from unittest.mock import Mock

from data.retriever.latest import LatestRetriever
from data.retriever.setting import JVLinkProfile


def test_latest_reuses_persistent_runtime_setting(tmp_path: Path) -> None:
    runner = Mock()
    builder = Mock()
    profile = JVLinkProfile(True, False, True, frozenset(), frozenset(), frozenset())
    runtime_setting = tmp_path / "runtime" / "latest.xml"
    builder.build.return_value = runtime_setting
    retriever = LatestRetriever(runner, builder, profile, runtime_setting)

    retriever.retrieve()
    builder.build.assert_called_once_with(profile, runtime_setting.resolve(), source=None)
    runner.execute.assert_called_once_with(runtime_setting)

    builder.reset_mock()
    runner.reset_mock()
    runtime_setting.parent.mkdir(parents=True)
    runtime_setting.write_text("<setting />", encoding="utf-8")
    retriever.retrieve()
    builder.build.assert_called_once_with(
        profile,
        runtime_setting.resolve(),
        source=runtime_setting.resolve(),
    )
