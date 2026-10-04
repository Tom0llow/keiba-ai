"""Retrieve historical race data and time-series odds through JVLinkToSQLite."""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner
from data.retriever.odds_archive import OddsArchive
from data.retriever.setting import JVLinkProfile, JVLinkSettingBuilder


@dataclass(frozen=True, order=True)
class RaceKey:
    """Represent the five components required by JVLinkToSQLite's JVRaceKey."""

    race_date: date
    jyo_code: str
    kaiji: str
    nichiji: str
    race_number: str

    def __post_init__(self) -> None:
        for name, value in (
            ("jyo_code", self.jyo_code),
            ("kaiji", self.kaiji),
            ("nichiji", self.nichiji),
            ("race_number", self.race_number),
        ):
            if not value.isdigit() or len(value) != 2:
                raise ValueError(f"{name} must be a two-digit string: {value!r}")


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
        if odds_profile.race_start_date is None:
            raise ValueError("historical_odds.race_start_date is required")
        self._odds_start_date = odds_profile.race_start_date

    def retrieve(self) -> int:
        """Retrieve base history, then archive configured time-series odds by race."""
        with tempfile.TemporaryDirectory(prefix="keiba-ai-historical-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            base_setting = self._setting_builder.build(
                self._historical_profile,
                temporary_path / "historical.xml",
            )
            self._runner.execute(base_setting, skip_last_modified_update=True)
            if not self._database.is_file():
                raise FileNotFoundError(f"raw race database does not exist: {self._database}")

            odds_setting = temporary_path / "historical-odds.xml"
            count = 0
            for race_key in self.iter_race_keys(start_date=self._odds_start_date):
                self._setting_builder.build(
                    self._odds_profile,
                    odds_setting,
                    race_key=race_key,
                )
                self._runner.execute(odds_setting, skip_last_modified_update=True)
                self._archive.archive()
                count += 1
            return count

    def iter_race_keys(self, *, start_date: date) -> Iterator[RaceKey]:
        """Yield race keys from ``NL_RA_RACE`` in chronological order."""
        if not self._database.is_file():
            raise FileNotFoundError(f"raw race database does not exist: {self._database}")

        query = """
            SELECT idYear, idMonthDay, idJyoCD, idKaiji, idNichiji, idRaceNum
            FROM NL_RA_RACE
            WHERE idYear || idMonthDay >= ?
            ORDER BY idYear, idMonthDay, idJyoCD, idKaiji, idNichiji, idRaceNum
        """
        with sqlite3.connect(f"{self._database.as_uri()}?mode=ro", uri=True) as database:
            for row in database.execute(query, (start_date.strftime("%Y%m%d"),)):
                yield _race_key_from_row(row)


def _race_key_from_row(row: tuple[str, str, str, str, str, str]) -> RaceKey:
    year, month_day, jyo_code, kaiji, nichiji, race_number = row
    if not (year.isdigit() and len(year) == 4 and month_day.isdigit() and len(month_day) == 4):
        raise ValueError(f"invalid race date components: {year!r}, {month_day!r}")

    try:
        race_date = date(int(year), int(month_day[:2]), int(month_day[2:]))
    except ValueError as exc:
        raise ValueError(f"invalid race date components: {year!r}, {month_day!r}") from exc

    components = {
        "idJyoCD": jyo_code,
        "idKaiji": kaiji,
        "idNichiji": nichiji,
        "idRaceNum": race_number,
    }
    for name, value in components.items():
        if not isinstance(value, str) or not value.isdigit() or len(value) != 2:
            raise ValueError(f"invalid {name}: {value!r}")

    return RaceKey(race_date, jyo_code, kaiji, nichiji, race_number)
