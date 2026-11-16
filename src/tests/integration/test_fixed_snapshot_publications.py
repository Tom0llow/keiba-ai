"""Read intermediate publications from a fixed snapshot in two passes (plan AC-14)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from data.loader.fixed_snapshot import FixedSnapshot

KEYS = ("idYear", "idMonthDay", "idJyoCD", "idKaiji", "idNichiji", "idRaceNum")
VALUES = (*KEYS, "headDataKubun", "HappyoTime", "Value")
TABLE = "ARCHIVE_TEST_ODDS"
RACE_A = "2024061505030111"
RACE_B = "2024061505030112"
RACE_2025 = "2025061505030111"
OTHER_VENUE = "2024061512030111"


def _row(race_id: str, kubun: str, clock: str | None, value: str) -> dict[str, object]:
    return {
        "idYear": race_id[:4],
        "idMonthDay": race_id[4:8],
        "idJyoCD": race_id[8:10],
        "idKaiji": race_id[10:12],
        "idNichiji": race_id[12:14],
        "idRaceNum": race_id[14:16],
        "headDataKubun": kubun,
        "HappyoTime": clock,
        "Value": value,
    }


ROWS = [
    _row(RACE_2025, "1", "06151520", "other-year"),
    _row(RACE_A, "1", "06151520", "a-1520"),
    _row(RACE_B, "1", "06151520", "b-1520"),
    _row(RACE_A, "1", "06151524", "a-1524-first"),
    _row(RACE_A, "1", "06151524", "a-1524-second"),
    _row(RACE_B, "1", "06151524", "b-1524"),
    _row(RACE_A, "2", "06151524", "a-final-kind"),
    _row(RACE_A, "1", None, "a-null"),
    _row(RACE_B, "1", None, "b-null"),
    _row(OTHER_VENUE, "1", "06151524", "other-venue"),
    _row(RACE_A, "3", "06151526", "a-kind-3"),
]


def _snapshot(tmp_path: Path, *, columns: tuple[str, ...] = VALUES) -> FixedSnapshot:
    path = tmp_path / "processed" / "snapshots" / "fixture"
    path.mkdir(parents=True)
    schema = pa.schema([(name, pa.string()) for name in columns])
    rows = [{name: row[name] for name in columns} for row in ROWS]
    # Small row groups with years mixed across them, as in the archive tables.
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema), path / f"{TABLE}.parquet", row_group_size=2
    )
    return FixedSnapshot(tmp_path / "processed", snapshot_id="fixture")


def test_scan_returns_only_intermediate_publication_keys_of_the_year_and_venues(
    tmp_path: Path,
) -> None:
    reader = _snapshot(tmp_path).publication_reader(
        TABLE, key_columns=KEYS, value_columns=VALUES, venues=("05",)
    )

    rows = reader.scan(2024)

    assert all(set(row) == {*KEYS, "headDataKubun", "HappyoTime"} for row in rows)
    assert sorted(
        ("".join(str(row[name]) for name in KEYS), row["HappyoTime"] or "") for row in rows
    ) == sorted(
        [
            (RACE_A, "06151520"),
            (RACE_B, "06151520"),
            (RACE_A, "06151524"),
            (RACE_A, "06151524"),
            (RACE_B, "06151524"),
            (RACE_A, ""),
            (RACE_B, ""),
        ]
    )
    assert {row["headDataKubun"] for row in rows} == {"1"}


def test_read_pairs_returns_every_row_of_the_selected_pairs_and_nothing_else(
    tmp_path: Path,
) -> None:
    reader = _snapshot(tmp_path).publication_reader(
        TABLE, key_columns=KEYS, value_columns=VALUES, venues=("05", "12")
    )

    rows = reader.read_pairs(2024, [(RACE_A, "06151524"), (RACE_B, None)])

    assert sorted(str(row["Value"]) for row in rows) == ["a-1524-first", "a-1524-second", "b-null"]
    assert all(set(row) == set(VALUES) for row in rows)
    assert reader.read_pairs(2024, []) == []


def test_read_pairs_rejects_pairs_of_another_year(tmp_path: Path) -> None:
    reader = _snapshot(tmp_path).publication_reader(
        TABLE, key_columns=KEYS, value_columns=VALUES, venues=("05",)
    )

    with pytest.raises(ValueError, match="requested year"):
        reader.read_pairs(2024, [(RACE_2025, "06151520")])


def test_publication_reader_opens_the_dataset_once_and_hashes_the_table(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    with patch("data.loader.fixed_snapshot.ds.dataset", wraps=ds.dataset) as opened:
        reader = snapshot.publication_reader(
            TABLE, key_columns=KEYS, value_columns=VALUES, venues=("05",)
        )
        reader.scan(2024)
        reader.read_pairs(2024, [(RACE_A, "06151520")])
        reader.scan(2025)

    assert opened.call_count == 1
    assert TABLE in snapshot.manifest()["tables"]  # type: ignore[operator]


@pytest.mark.parametrize(
    ("columns", "key_columns", "value_columns", "message"),
    [
        (tuple(name for name in VALUES if name != "HappyoTime"), KEYS, VALUES, "missing"),
        (VALUES, KEYS[:-1], VALUES, "complete fixed-snapshot race key"),
        (VALUES, KEYS, ("Value",), "must include keys"),
    ],
)
def test_publication_reader_rejects_missing_or_incomplete_columns(
    tmp_path: Path,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
    value_columns: tuple[str, ...],
    message: str,
) -> None:
    snapshot = _snapshot(tmp_path, columns=columns)

    with pytest.raises(ValueError, match=message):
        snapshot.publication_reader(
            TABLE, key_columns=key_columns, value_columns=value_columns, venues=("05",)
        )
