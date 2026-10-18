"""Retrieve historical base race data through JVLinkToSQLite."""

from __future__ import annotations

import tempfile
from pathlib import Path

from jra_van_retriever.acquisition.jvlink_runner import JVLinkToSQLiteRunner
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkProfile


class HistoricalBasicRetriever:
    """Own historical base acquisition without odds state or archive behavior."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        database: Path,
        setting_builder: JVLinkSettingBuilder,
        profile: JVLinkProfile,
    ) -> None:
        self._runner = runner
        self._database = database.expanduser().resolve()
        self._setting_builder = setting_builder
        self._historical_profile = profile

    def retrieve_basic(self) -> None:
        """Retrieve enabled base history and ensure the raw database exists."""
        with tempfile.TemporaryDirectory(
            prefix="keiba-ai-historical-basic-"
        ) as temporary_directory:
            self.retrieve_into(Path(temporary_directory))

    def retrieve_into(self, temporary_path: Path) -> None:
        """Acquire base data using the caller-owned temporary setting directory."""
        self._retrieve_base(temporary_path)
        if not self._database.is_file():
            raise FileNotFoundError(f"raw race database does not exist: {self._database}")

    def _retrieve_base(self, temporary_path: Path) -> None:
        if not (
            self._historical_profile.normal_update
            or self._historical_profile.setup_update
            or self._historical_profile.realtime_update
        ):
            return
        base_setting = self._setting_builder.build(
            self._historical_profile,
            temporary_path / "historical.xml",
        )
        self._runner.execute(base_setting, skip_last_modified_update=True)
