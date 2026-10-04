"""Retrieve prediction-time odds for one target race through JVLinkToSQLite."""

from __future__ import annotations

import tempfile
from pathlib import Path

from data.retriever.historical import RaceKey
from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.odds_archive import OddsArchive
from data.retriever.setting import JVLinkProfile, JVLinkSettingBuilder


class RealtimeRetriever:
    """Retrieve historical-to-now and current odds for one prediction race."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        history_profile: JVLinkProfile,
        current_profile: JVLinkProfile,
    ) -> None:
        self._runner = runner
        self._setting_builder = setting_builder
        self._archive = archive
        self._history_profile = history_profile
        self._current_profile = current_profile

    def retrieve(self, race_key: RaceKey) -> int:
        """Retrieve and archive O1/O2 odds for the target race.

        The history profile (0B41/0B42) is executed first and archived before the
        current profile (0B31/0B32) runs, because JVLinkToSQLite recreates its
        realtime O1/O2 tables on each execution.
        """
        inserted = 0
        with tempfile.TemporaryDirectory(prefix="keiba-ai-realtime-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            for name, profile in (
                ("history", self._history_profile),
                ("current", self._current_profile),
            ):
                setting = self._setting_builder.build(
                    profile,
                    temporary_path / f"realtime-{name}.xml",
                    race_key=race_key,
                )
                self._runner.execute(setting, skip_last_modified_update=True)
                inserted += self._archive.archive()
        return inserted
