"""Tests for reading one pinned race-scoped processed version (ADR-037)."""

from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data.loader.file_hash import file_sha256
from data.loader.race_version import read_race_version
from domain.race_key import RaceKey

KEY = RaceKey(date(2026, 11, 15), "05", "05", "04", "11")
KEYS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
VALUES = ("2026", "1115", "05", "05", "04", "11")
COLUMNS = {"ARCHIVE_O1_ODDS_TANFUKUWAKU": (*KEYS, "HappyoTime")}


def _publish(root: Path, version: str, tables: dict[str, list[dict[str, object]]]) -> Path:
    directory = root / "realtime" / KEY.race_id / "versions" / version
    directory.mkdir(parents=True)
    for name, rows in tables.items():
        schema = pa.schema([(column, pa.string()) for column in rows[0]])
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), directory / f"{name}.parquet")
    (root / "realtime" / KEY.race_id / "CURRENT").write_text(version, encoding="utf-8")
    return directory


def _row(happyo: str, race: str = "11", extra: str = "x") -> dict[str, object]:
    return {**dict(zip(KEYS, (*VALUES[:-1], race), strict=True)), "HappyoTime": happyo, "X": extra}


def test_reads_only_the_current_version_with_projected_columns_and_hashes(tmp_path: Path) -> None:
    _publish(tmp_path, "a" * 32, {"ARCHIVE_O1_ODDS_TANFUKUWAKU": [_row("11151449")]})
    current = _publish(
        tmp_path,
        "b" * 32,
        {"ARCHIVE_O1_ODDS_TANFUKUWAKU": [_row("11151449"), _row("11151454")]},
    )

    version = read_race_version(tmp_path, KEY, columns=COLUMNS)

    assert version is not None
    assert version.snapshot_id == "b" * 32
    assert [row["HappyoTime"] for row in version.rows["ARCHIVE_O1_ODDS_TANFUKUWAKU"]] == [
        "11151449",
        "11151454",
    ]
    assert "X" not in version.rows["ARCHIVE_O1_ODDS_TANFUKUWAKU"][0]
    assert version.sha256 == {
        "ARCHIVE_O1_ODDS_TANFUKUWAKU": file_sha256(current / "ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet")
    }


def test_returns_none_before_the_race_is_published(tmp_path: Path) -> None:
    assert read_race_version(tmp_path, KEY, columns=COLUMNS) is None


def test_an_optional_table_may_be_absent_but_a_required_one_may_not(tmp_path: Path) -> None:
    _publish(tmp_path, "c" * 32, {"ARCHIVE_O1_ODDS_TANFUKUWAKU": [_row("11151454")]})
    columns = {**COLUMNS, "ARCHIVE_CAPTURE_LOG": (*KEYS, "data_spec")}

    version = read_race_version(
        tmp_path, KEY, columns=columns, optional=frozenset({"ARCHIVE_CAPTURE_LOG"})
    )

    assert version is not None
    assert set(version.rows) == set(version.sha256) == {"ARCHIVE_O1_ODDS_TANFUKUWAKU"}
    with pytest.raises(ValueError, match="missing: ARCHIVE_CAPTURE_LOG"):
        read_race_version(tmp_path, KEY, columns=columns)


@pytest.mark.parametrize(
    ("rows", "columns", "message"),
    [
        ([_row("11151454", race="12")], COLUMNS, "another race"),
        ([_row("11151454")], {"ARCHIVE_O1_ODDS_TANFUKUWAKU": ("HappyoTime",)}, "race key"),
        (
            [_row("11151454")],
            {"ARCHIVE_O1_ODDS_TANFUKUWAKU": (*KEYS, "Missing")},
            "columns are missing",
        ),
    ],
)
def test_rejects_foreign_rows_and_incomplete_projections(
    tmp_path: Path,
    rows: list[dict[str, object]],
    columns: dict[str, tuple[str, ...]],
    message: str,
) -> None:
    _publish(tmp_path, "d" * 32, {"ARCHIVE_O1_ODDS_TANFUKUWAKU": rows})

    with pytest.raises(ValueError, match=message):
        read_race_version(tmp_path, KEY, columns=columns)


def test_rejects_columns_that_are_not_strings(tmp_path: Path) -> None:
    directory = _publish(tmp_path, "e" * 32, {"ARCHIVE_O1_ODDS_TANFUKUWAKU": [_row("1")]})
    table = pa.table({**{key: [value] for key, value in zip(KEYS, VALUES, strict=True)}})
    table = table.append_column("HappyoTime", pa.array([11151454], pa.int64()))
    pq.write_table(table, directory / "ARCHIVE_O1_ODDS_TANFUKUWAKU.parquet")

    with pytest.raises(ValueError, match="nullable strings"):
        read_race_version(tmp_path, KEY, columns=COLUMNS)
