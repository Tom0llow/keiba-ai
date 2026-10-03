"""Tests for latest race-data retrieval orchestration."""

from pathlib import Path
from unittest.mock import Mock

from data.retriever.latest import LatestRetriever


def test_retrieve_runs_incremental_setting_without_skipping_position_update(tmp_path: Path) -> None:
    setting = tmp_path / "latest.xml"
    setting.write_text("<setting />", encoding="utf-8")
    runner = Mock()

    LatestRetriever(runner).retrieve(setting)

    runner.execute.assert_called_once_with(setting)
