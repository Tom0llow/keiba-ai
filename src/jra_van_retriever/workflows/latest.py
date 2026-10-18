"""Retrieve the latest race-data changes through JVLinkToSQLite."""

from __future__ import annotations

from pathlib import Path

from jra_van_retriever.acquisition.jvlink_runner import JVLinkToSQLiteRunner
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkProfile


class LatestRetriever:
    """Run incremental retrieval while preserving JVLinkToSQLite read state."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        setting_builder: JVLinkSettingBuilder,
        profile: JVLinkProfile,
        runtime_setting: Path,
    ) -> None:
        self._runner = runner
        self._setting_builder = setting_builder
        self._profile = profile
        self._runtime_setting = runtime_setting.expanduser().resolve()

    def retrieve(self) -> None:
        """Apply the latest profile and let JVLinkToSQLite persist its read position."""
        source = self._runtime_setting if self._runtime_setting.is_file() else None
        setting = self._setting_builder.build(
            self._profile,
            self._runtime_setting,
            source=source,
        )
        self._runner.execute(setting)
