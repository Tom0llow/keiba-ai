"""Retrieve historical race data and time-series odds through JVLinkToSQLite."""

from __future__ import annotations

import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from data.retriever.jvlinktosqlite import JVLinkToSQLiteRunner

_HISTORICAL_ODDS_START = date(2003, 10, 4)
_ODDS_DATA_SPECS = {"0B41", "0B42"}


@dataclass(frozen=True, order=True)
class RaceKey:
    """Represent the five components required by JVLinkToSQLite's JVRaceKey."""

    race_date: date
    jyo_code: str
    kaiji: str
    nichiji: str
    race_number: str


class HistoricalRetriever:
    """Populate the raw database with historical races and time-series odds."""

    def __init__(self, runner: JVLinkToSQLiteRunner, database: Path) -> None:
        """Configure a historical retriever for one raw SQLite database."""
        self._runner = runner
        self._database = database.expanduser().resolve()

    def retrieve(self, base_setting: Path, odds_setting_template: Path) -> int:
        """Retrieve base history, then 0B41/0B42 odds for every eligible race.

        The base import runs first because the race table supplies the exact
        JVRaceKey components needed for historical odds requests. The odds
        setting is copied to a temporary file for each race so the caller-owned
        template is never mutated.

        Args:
            base_setting: JVLinkToSQLite setting for the normal historical load.
            odds_setting_template: Setting containing 0B41 and 0B42 entries with
                JVRaceKey children.

        Returns:
            Number of races for which the odds setting was executed.

        Raises:
            FileNotFoundError: If the raw SQLite database does not exist after
                the base import or the odds setting template is missing.
            ValueError: If the race table contains an invalid key or the odds
                setting does not contain usable 0B41 and 0B42 entries.
        """
        self._runner.execute(base_setting)
        if not self._database.is_file():
            raise FileNotFoundError(f"raw race database does not exist: {self._database}")

        count = 0
        with tempfile.TemporaryDirectory(prefix="keiba-ai-odds-") as temporary_directory:
            generated_setting = Path(temporary_directory) / "historical-odds.xml"
            for race_key in self.iter_race_keys():
                _write_odds_setting(odds_setting_template, generated_setting, race_key)
                self._runner.execute(generated_setting, skip_last_modified_update=True)
                count += 1
        return count

    def iter_race_keys(self, *, start_date: date = _HISTORICAL_ODDS_START) -> Iterator[RaceKey]:
        """Yield eligible race keys from ``NL_RA_RACE`` in chronological order."""
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


def _write_odds_setting(template: Path, destination: Path, race_key: RaceKey) -> None:
    template_path = template.expanduser().resolve()
    if not template_path.is_file():
        raise FileNotFoundError(f"odds setting template does not exist: {template_path}")

    tree = ET.parse(template_path)
    found_specs: set[str] = set()
    for data_spec_setting in tree.getroot().iter("JVDataSpecSetting"):
        data_spec = data_spec_setting.findtext("DataSpec")
        if data_spec not in _ODDS_DATA_SPECS:
            continue

        race_key_node = data_spec_setting.find("JVRaceKey")
        if race_key_node is None:
            raise ValueError(f"{data_spec} setting must contain a JVRaceKey")
        _set_required_text(
            race_key_node,
            "KaisaiDate",
            race_key.race_date.isoformat() + "T00:00:00",
        )
        _set_required_text(race_key_node, "JyoCD", race_key.jyo_code)
        _set_required_text(race_key_node, "Kaiji", race_key.kaiji)
        _set_required_text(race_key_node, "Nichiji", race_key.nichiji)
        _set_required_text(race_key_node, "RaceNum", race_key.race_number)
        _set_required_text(data_spec_setting, "IsEnabled", "true")
        found_specs.add(data_spec)

    missing = _ODDS_DATA_SPECS - found_specs
    if missing:
        raise ValueError(
            f"odds setting template is missing data specs: {', '.join(sorted(missing))}"
        )

    tree.write(destination, encoding="utf-8", xml_declaration=True)


def _set_required_text(parent: ET.Element, tag: str, value: str) -> None:
    element = parent.find(tag)
    if element is None:
        raise ValueError(f"odds setting is missing required element: {tag}")
    element.text = value
