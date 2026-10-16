"""Retrieve historical race data and time-series odds through JVLinkToSQLite."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path

from domain.race_key import RaceKey
from retriever.jvlinktosqlite import JVLinkToSQLiteError, JVLinkToSQLiteRunner
from retriever.odds_archive import OddsArchive
from retriever.raw_snapshot import iter_historical_race_keys, read_archived_race_keys
from retriever.setting import JVLinkProfile, JVLinkSettingBuilder


class HistoricalRetriever:
    """Populate the raw database with historical races and time-series odds."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        database: Path,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        historical_profile: JVLinkProfile,
        odds_profile: JVLinkProfile,
    ) -> None:
        self._runner = runner
        self._database = database.expanduser().resolve()
        self._setting_builder = setting_builder
        self._archive = archive
        self._historical_profile = historical_profile
        self._odds_profile = odds_profile
        self._odds_start_date = odds_profile.race_start_date

    def retrieve_basic(self) -> None:
        """Retrieve enabled base history and ensure the raw database exists."""
        with tempfile.TemporaryDirectory(
            prefix="keiba-ai-historical-basic-"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            self._retrieve_base(temporary_path)
            if not self._database.is_file():
                raise FileNotFoundError(f"raw race database does not exist: {self._database}")

    def retrieve(self) -> int:
        """Retrieve enabled base history and configured time-series odds."""
        with tempfile.TemporaryDirectory(prefix="keiba-ai-historical-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            self._retrieve_base(temporary_path)
            if not self._database.is_file():
                raise FileNotFoundError(f"raw race database does not exist: {self._database}")

            if self._odds_start_date is None:
                raise ValueError("historical_odds.race_start_date is required")
            race_keys = tuple(self.iter_race_keys(start_date=self._odds_start_date))
            archived_races = self._archived_race_keys() if self._odds_profile.skip_existing else {}
            odds_setting = temporary_path / "historical-odds.xml"
            count = 0
            for race_key in race_keys:
                profile = self._odds_profile
                if profile.skip_existing:
                    missing_specs = frozenset(
                        data_spec
                        for data_spec in profile.realtime_data_specs
                        if race_key not in archived_races.get(data_spec, set())
                    )
                    if not missing_specs:
                        continue
                    profile = replace(profile, realtime_data_specs=missing_specs)
                self._setting_builder.build(
                    profile,
                    odds_setting,
                    race_key=race_key,
                )
                try:
                    self._runner.execute(odds_setting, skip_last_modified_update=True)
                except JVLinkToSQLiteError as exc:
                    raise JVLinkToSQLiteError(
                        f"historical odds retrieval failed for race {race_key}: {exc}",
                        returncode=exc.returncode,
                    ) from exc
                self._archive.archive()
                count += 1
            return count

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

    def iter_race_keys(self, *, start_date: date) -> Iterator[RaceKey]:
        """Yield race keys after closing the raw SQLite reader connection."""
        yield from iter_historical_race_keys(self._database, start_date=start_date)

    def _archived_race_keys(self) -> dict[str, set[RaceKey]]:
        return read_archived_race_keys(self._database, self._odds_profile.realtime_data_specs)
