"""Retrieve the latest race-data changes through JVLinkToSQLite."""

from __future__ import annotations

from pathlib import Path

from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner


class LatestRetriever:
    """Run the configured incremental JVLinkToSQLite acquisition once."""

    def __init__(self, runner: JVLinkToSQLiteRunner) -> None:
        """Configure the process runner used for incremental retrieval."""
        self._runner = runner

    def retrieve(self, setting: Path) -> None:
        """Retrieve the latest data and persist JVLinkToSQLite's read position.

        The setting file is intentionally passed without
        ``skip_last_modified_update`` so JVLinkToSQLite can advance its own
        incremental read-start position after a successful execution.

        Args:
            setting: JVLinkToSQLite XML setting for the latest-data update.
        """
        self._runner.execute(setting)
