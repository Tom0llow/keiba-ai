"""Acquire historical odds for the existing combined Python retrieval API."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path

from domain.race_key import RaceKey
from jra_van_retriever.acquisition.jvlink_runner import JVLinkToSQLiteError, JVLinkToSQLiteRunner
from jra_van_retriever.acquisition.odds_archive import OddsArchive
from jra_van_retriever.acquisition.setting_xml import JVLinkSettingBuilder
from jra_van_retriever.config.profiles import JVLinkProfile
from jra_van_retriever.progress.raw_observation import (
    iter_historical_race_keys,
    read_archived_race_keys,
)


class LegacyHistoricalOddsRetriever:
    """Own race-scoped archive resume checks and sequential odds acquisition."""

    def __init__(
        self,
        runner: JVLinkToSQLiteRunner,
        database: Path,
        setting_builder: JVLinkSettingBuilder,
        archive: OddsArchive,
        odds_profile: JVLinkProfile,
    ) -> None:
        self._runner = runner
        self._database = database.expanduser().resolve()
        self._setting_builder = setting_builder
        self._archive = archive
        self._odds_profile = odds_profile
        self._odds_start_date = odds_profile.race_start_date

    def retrieve_into(self, temporary_path: Path) -> int:
        """Retrieve missing odds after the combined caller has populated base data."""
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

    def iter_race_keys(self, *, start_date: date) -> Iterator[RaceKey]:
        """Yield race keys after closing the raw SQLite reader connection."""
        yield from iter_historical_race_keys(self._database, start_date=start_date)

    def _archived_race_keys(self) -> dict[str, set[RaceKey]]:
        return read_archived_race_keys(self._database, self._odds_profile.realtime_data_specs)
