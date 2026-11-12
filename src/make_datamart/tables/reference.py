"""Persist and fully validate the reference-feature datamart and prediction formats.

The labeled datamart (ADR-034) and the label-free prediction features (ADR-036) share
one directory layout and one validator; ``_Layout`` holds every difference so that no
check is switched on or off piecemeal. Prediction features record where their market
came from (``market_source``, format_version 2, ADR-037).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa

from data.loader.file_hash import file_sha256
from data.loader.read_parquet import read_parquet
from data.saver.write_json import write_json
from data.saver.write_parquet import write_parquet
from make_features.real_market import JST
from make_features.reference_raw import result_boundary


class ReferenceColumn(Protocol):
    """Expose the persisted numeric-column description without importing models."""

    @property
    def group(self) -> str: ...

    @property
    def column(self) -> str: ...

    @property
    def meaning(self) -> str: ...

    @property
    def unit(self) -> str: ...

    @property
    def name(self) -> str: ...


_TIMESTAMP = pa.timestamp("us", tz="UTC")
_MANIFEST_KEYS = {
    "format",
    "format_version",
    "implementation",
    "verification",
    "contract",
    "columns",
    "available_at_groups",
    "feature_definitions",
    "target_period",
    "snapshot",
    "assurance",
    "label",
    "held_races",
    "partitions",
    "provenance",
    "preparation_config",
}
_SOURCE_DATAMART_KEYS = frozenset(
    {
        "manifest_sha256",
        "contract_sha256",
        "target_period",
        "label_usable_through",
        "provenance_source_sha256",
    }
)
_FRESHNESS_KEYS = frozenset(
    {
        "latest_workout_date",
        "card_horses",
        "card_horses_without_pedigree_row",
        "history_held_recent",
        "history_held_recent_window_days",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX32 = re.compile(r"[0-9a-f]{32}")
_FETCH_KEYS = frozenset(
    {
        "kind",
        "race_id",
        "scheduled_start_at",
        "freeze_at",
        "capture_id",
        "data_specs",
        "started_at",
        "snapshot_id",
        "tables",
    }
)
_FETCH_DATA_SPECS = ["0B41", "0B42"]
_FETCH_TABLES = frozenset(
    {"ARCHIVE_O1_ODDS_TANFUKUWAKU", "ARCHIVE_O2_ODDS_UMAREN", "ARCHIVE_CAPTURE_LOG"}
)


@dataclass(frozen=True)
class _Layout:
    """Every persisted difference between the labeled and label-free formats."""

    labeled: bool
    format: str
    format_version: int
    held_format: str
    manifest_keys: frozenset[str]
    stages: frozenset[str]
    rows_kind: bytes
    races_kind: bytes
    # The labeled datamart's metadata bytes predate the prediction format and never change.
    metadata_format: str | None


_DATAMART = _Layout(
    labeled=True,
    format="reference_feature_datamart",
    format_version=1,
    held_format="reference_feature_datamart_held_races",
    manifest_keys=frozenset(_MANIFEST_KEYS),
    stages=frozenset({"history_result", "target_pre_freeze", "target_outcome", "calculation"}),
    rows_kind=b"reference_datamart_rows",
    races_kind=b"reference_datamart_races",
    metadata_format=None,
)
_PREDICTION = _Layout(
    labeled=False,
    format="reference_prediction_features",
    format_version=2,
    held_format="reference_prediction_features_held_races",
    manifest_keys=frozenset(
        (_MANIFEST_KEYS - {"label"}) | {"source_datamart", "freshness", "market_source"}
    ),
    stages=frozenset({"history_result", "target_pre_freeze", "calculation"}),
    rows_kind=b"reference_prediction_rows",
    races_kind=b"reference_prediction_races",
    metadata_format="reference_prediction_features",
)


@dataclass(frozen=True)
class ReferenceDatamartRead:
    """Return the validated identifier and tables without recalculating features."""

    manifest_sha256: str
    manifest: Mapping[str, object]
    rows: pa.Table
    races: pa.Table


class ReferenceDatamartWriter:
    """Write yearly partitions into empty staging, then the held races and manifest."""

    def __init__(
        self,
        path: Path,
        *,
        columns: Sequence[ReferenceColumn],
        available_at_groups: Sequence[str],
        contract: Mapping[str, object],
        labeled: bool = True,
    ) -> None:
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError("reference datamart staging must be an existing empty directory")
        self._layout = _DATAMART if labeled else _PREDICTION
        self._path = path
        self._columns = tuple(columns)
        self._groups = tuple(available_at_groups)
        self._contract = dict(contract)
        self._contract_sha256 = _validate_contract(
            self._contract, [column.name for column in self._columns]
        )
        self._partitions: list[dict[str, object]] = []

    def write_year(
        self,
        year: int,
        rows: Sequence[Mapping[str, object]],
        races: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        """Write one calendar year's horse and race rows; empty years are written too."""
        if self._partitions and cast(int, self._partitions[-1]["year"]) >= year:
            raise ValueError("reference datamart partitions must be written in year order")
        directory = self._path / f"year={year}"
        directory.mkdir()
        layout = self._layout
        metadata = _metadata(year, self._contract_sha256, layout)
        row_table = pa.Table.from_pylist(
            list(rows), schema=_rows_schema(self._columns, self._groups, metadata, layout)
        )
        race_table = pa.Table.from_pylist(list(races), schema=_races_schema(metadata, layout))
        rows_path = directory / "part-0.parquet"
        races_path = directory / "races.parquet"
        write_parquet(row_table, rows_path)
        write_parquet(race_table, races_path)
        freezes = cast(list[datetime], race_table.column("freeze_at").to_pylist())
        entry: dict[str, object] = {
            "year": year,
            "rows_file": f"year={year}/part-0.parquet",
            "rows_sha256": file_sha256(rows_path),
            "row_count": row_table.num_rows,
            "races_file": f"year={year}/races.parquet",
            "races_sha256": file_sha256(races_path),
            "race_count": race_table.num_rows,
            "first_freeze_at": min(freezes).isoformat() if freezes else None,
            "last_freeze_at": max(freezes).isoformat() if freezes else None,
        }
        self._partitions.append(entry)
        return entry

    def finish(
        self, manifest: Mapping[str, object], held_races: Sequence[Mapping[str, object]]
    ) -> str:
        """Write held races and the manifest, re-read everything and return its identity."""
        if manifest.get("contract") != self._contract:
            raise ValueError("reference datamart manifest contract differs from the partitions")
        held = sorted(held_races, key=lambda item: (str(item["race_id"]), str(item["role"])))
        held_path = self._path / "held_races.json"
        write_json(
            held_path,
            {
                "format": self._layout.held_format,
                "format_version": self._layout.format_version,
                "held_races": [dict(item) for item in held],
            },
            overwrite=False,
        )
        role_counts = Counter(str(item["role"]) for item in held)
        stage_counts = Counter(str(item["stage"]) for item in held)
        complete = {
            **manifest,
            "held_races": {
                "file": "held_races.json",
                "sha256": file_sha256(held_path),
                "count": len(held),
                "by_role": dict(sorted(role_counts.items())),
                "by_stage": dict(sorted(stage_counts.items())),
            },
            "partitions": list(self._partitions),
        }
        if set(complete) != self._layout.manifest_keys:
            raise ValueError("reference datamart manifest fields differ from the format contract")
        write_json(self._path / "manifest.json", complete, overwrite=False)
        return _read(self._path, self._layout, expected_columns=self._columns).manifest_sha256


def read_reference_datamart(
    path: Path,
    *,
    expected_columns: Sequence[ReferenceColumn],
    expected_manifest_sha256: str | None = None,
) -> ReferenceDatamartRead:
    """Validate hashes, schemas, time boundaries and complete labels without recomputation."""
    return _read(
        path,
        _DATAMART,
        expected_columns=expected_columns,
        expected_manifest_sha256=expected_manifest_sha256,
    )


def read_reference_prediction_features(
    path: Path,
    *,
    expected_columns: Sequence[ReferenceColumn],
    expected_manifest_sha256: str | None = None,
) -> ReferenceDatamartRead:
    """Validate label-free prediction features (ADR-036) without recomputation.

    Every label-independent datamart check applies. In addition, every race lies on the
    single target date, the history ends by that date's start, no label column exists,
    the training-datamart binding is well formed, and the market source (ADR-037) is
    either the pinned snapshot or one race-day fetch that started at or after freeze.
    format_version 1 outputs carry no market source and are rejected.
    """
    return _read(
        path,
        _PREDICTION,
        expected_columns=expected_columns,
        expected_manifest_sha256=expected_manifest_sha256,
    )


def read_reference_datamart_manifest(
    path: Path, *, expected_manifest_sha256: str
) -> dict[str, object]:
    """Read only a labeled datamart's manifest, pinned by its SHA-256.

    The format, the manifest keys, the column list and the calculation contract are
    checked; the partitions are not read (``finish`` read them when it was published).
    """
    manifest = _pinned_manifest(path.resolve(), expected_manifest_sha256)
    if set(manifest) != _MANIFEST_KEYS:
        raise ValueError("reference datamart manifest fields differ from the format contract")
    _check_format(manifest, _DATAMART)
    columns = manifest["columns"]
    if (
        not isinstance(columns, list)
        or not columns
        or any(
            not isinstance(column, dict) or not isinstance(column.get("name"), str)
            for column in columns
        )
    ):
        raise ValueError("reference datamart columns are invalid")
    _validate_contract(manifest["contract"], [cast(str, column["name"]) for column in columns])
    return manifest


def read_reference_datamart_label_usable_through(
    path: Path, *, expected_manifest_sha256: str
) -> datetime:
    """Return the latest label-use boundary of a labeled datamart's races.

    The pinned manifest is checked like ``read_reference_datamart_manifest``; then only the
    ``label_usable_after`` column of each hash-checked ``races.parquet`` is read. The value
    is the maximum over the whole datamart, an upper bound of any training fold's boundary.
    A model trained on this datamart may predict only races whose freeze lies at or after
    this instant (ADR-036).
    """
    read_reference_datamart_manifest(path, expected_manifest_sha256=expected_manifest_sha256)
    values = _pinned_races_column(path, expected_manifest_sha256, None, "label_usable_after")
    if not values:
        raise ValueError("reference datamart has no labeled races")
    return max(cast(datetime, value) for value in values)


def read_reference_datamart_race_ids(
    path: Path, *, years: Sequence[int], expected_manifest_sha256: str
) -> frozenset[str]:
    """Read only the race IDs of the given years' race tables, without the full validation.

    The manifest bytes and each selected ``races.parquet`` are checked against the
    pinned SHA-256 values with the same path rule as the full reader, so callers can
    check race coverage before ``read_reference_datamart`` (which still verifies everything).
    """
    values = _pinned_races_column(path, expected_manifest_sha256, set(years), "race_id")
    return frozenset(_race_identity({"race_id": value}) for value in values)


def _read(
    path: Path,
    layout: _Layout,
    *,
    expected_columns: Sequence[ReferenceColumn],
    expected_manifest_sha256: str | None = None,
) -> ReferenceDatamartRead:
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("reference datamart path must be a directory")
    manifest_bytes = (root / "manifest.json").read_bytes()
    # Parse exactly the bytes that were hashed.
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if expected_manifest_sha256 is not None and manifest_sha256 != expected_manifest_sha256:
        raise ValueError("reference datamart manifest SHA-256 differs from the expected identity")
    manifest = _parse_manifest(manifest_bytes)
    _check_format(manifest, layout)
    if set(manifest) != layout.manifest_keys:
        raise ValueError("reference datamart manifest fields differ from the format contract")
    columns = tuple(expected_columns)
    if not columns or len({column.name for column in columns}) != len(columns):
        raise ValueError("expected reference datamart columns must be nonempty and unique")
    column_payload = [
        {
            "name": column.name,
            "group": column.group,
            "column": column.column,
            "meaning": column.meaning,
            "unit": column.unit,
        }
        for column in columns
    ]
    if manifest["columns"] != column_payload:
        raise ValueError("reference datamart columns differ from the expected closed contract")
    contract_sha256 = _validate_contract(manifest["contract"], [column.name for column in columns])
    groups = manifest["available_at_groups"]
    if (
        not isinstance(groups, list)
        or not groups
        or any(not isinstance(group, str) or not group for group in groups)
        or len(set(groups)) != len(groups)
    ):
        raise ValueError("reference datamart available_at groups are invalid")
    # Every closed numeric column needs its group's availability clock in the rows.
    if {column.group for column in columns} - set(cast(list[str], groups)):
        raise ValueError("reference datamart available_at groups miss a closed column group")
    start, end = _target_period(manifest["target_period"])
    held = _validate_held(root, manifest["held_races"], layout, None if layout.labeled else start)
    delay: int | None = None
    if layout.labeled:
        delay = _declared_delay(manifest)
    else:
        if start != end:
            raise ValueError("reference prediction features cover exactly one target date")
        _validate_source_datamart(manifest["source_datamart"], contract_sha256)
        _validate_freshness(manifest["freshness"])
    expected_years = list(range(start.year, end.year + 1))
    partitions = manifest["partitions"]
    if (
        not isinstance(partitions, list)
        or [entry.get("year") for entry in partitions if isinstance(entry, dict)] != expected_years
    ):
        raise ValueError("reference datamart partitions do not cover every target year")
    row_tables = []
    race_tables = []
    seen_races: set[str] = set()
    for entry in cast(list[dict[str, object]], partitions):
        rows, races = _read_partition(
            root, entry, columns, cast(list[str], groups), contract_sha256, layout
        )
        _validate_partition_rows(
            rows, races, cast(int, entry["year"]), seen_races, delay=delay, period=(start, end)
        )
        row_tables.append(rows)
        race_tables.append(races)
    rows = pa.concat_tables(row_tables) if row_tables else pa.Table.from_pylist([])
    races = pa.concat_tables(race_tables) if race_tables else pa.Table.from_pylist([])
    if not layout.labeled:
        _validate_market_source(
            manifest["market_source"],
            day=f"{start:%Y%m%d}",
            races=cast(list[dict[str, object]], races.to_pylist()),
            target_holds={cast(str, item["race_id"]) for item in held if item["role"] == "target"},
        )
    return ReferenceDatamartRead(manifest_sha256, manifest, rows, races)


def _parse_manifest(manifest_bytes: bytes) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("reference datamart manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("reference datamart manifest fields differ from the format contract")
    return manifest


def _pinned_manifest(root: Path, expected_manifest_sha256: str) -> dict[str, object]:
    manifest_bytes = (root / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
        raise ValueError("reference datamart manifest SHA-256 differs from the expected identity")
    return _parse_manifest(manifest_bytes)


def _check_format(manifest: Mapping[str, object], layout: _Layout) -> None:
    if (
        not layout.labeled
        and manifest.get("format") == layout.format
        and manifest.get("format_version") == 1
    ):
        raise ValueError(
            "reference prediction features format_version 1 has no market source; "
            "regenerate them (ADR-037)"
        )
    if (
        manifest.get("format") != layout.format
        or manifest.get("format_version") != layout.format_version
        or manifest.get("implementation") != "snapshot_reference_21_groups_v1"
        or manifest.get("verification") != "build_time_audit_no_read_recomputation_v1"
    ):
        raise ValueError("unsupported reference datamart format or implementation")


def _pinned_races_column(
    path: Path, expected_manifest_sha256: str, years: set[int] | None, column: str
) -> list[object]:
    """Read one column of hash-checked race tables of a pinned labeled datamart."""
    root = path.resolve()
    manifest = _pinned_manifest(root, expected_manifest_sha256)
    partitions = manifest.get("partitions")
    if not isinstance(partitions, list):
        raise ValueError("reference datamart partitions do not cover every target year")
    values: list[object] = []
    for entry in partitions:
        if not isinstance(entry, dict) or type(entry.get("year")) is not int:
            raise ValueError("reference datamart partition entry is invalid")
        year = cast(int, entry["year"])
        if years is not None and year not in years:
            continue
        expected_races = f"year={year}/races.parquet"
        if entry.get("races_file") != expected_races:
            raise ValueError("reference datamart partition paths are invalid")
        races_path = root / expected_races
        if file_sha256(races_path) != entry.get("races_sha256"):
            raise ValueError("reference datamart partition file hash mismatch")
        selected = read_parquet(races_path, columns=[column]).column(column).to_pylist()
        if len(selected) != entry.get("race_count"):
            raise ValueError("reference datamart partition row count mismatch")
        values.extend(selected)
    return values


def _validate_source_datamart(value: object, contract_sha256: str) -> None:
    if not isinstance(value, dict) or set(value) != _SOURCE_DATAMART_KEYS:
        raise ValueError("reference prediction source datamart binding is invalid")
    for name in ("manifest_sha256", "contract_sha256", "provenance_source_sha256"):
        if not isinstance(value[name], str) or _HEX64.fullmatch(value[name]) is None:
            raise ValueError("reference prediction source datamart binding is invalid")
    if value["contract_sha256"] != contract_sha256:
        raise ValueError("reference prediction contract differs from its source datamart")
    _target_period(value["target_period"])
    through = value["label_usable_through"]
    try:
        parsed = datetime.fromisoformat(cast(str, through))
    except (TypeError, ValueError) as exc:
        raise ValueError("reference prediction source label boundary is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("reference prediction source label boundary is invalid")


def _validate_freshness(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _FRESHNESS_KEYS:
        raise ValueError("reference prediction freshness is invalid")
    workouts = value["latest_workout_date"]
    if not isinstance(workouts, dict) or set(workouts) != {"hc", "wc"}:
        raise ValueError("reference prediction freshness is invalid")
    for day in workouts.values():
        if day is not None:
            try:
                datetime.strptime(cast(str, day), "%Y-%m-%d")
            except (TypeError, ValueError) as exc:
                raise ValueError("reference prediction freshness is invalid") from exc
    for name in _FRESHNESS_KEYS - {"latest_workout_date"}:
        if type(value[name]) is not int or value[name] < 0:
            raise ValueError("reference prediction freshness is invalid")


def _metadata(year: int, contract_sha256: str, layout: _Layout) -> dict[bytes, bytes]:
    identity: dict[str, object] = {
        "format_version": layout.format_version,
        "year": year,
        "contract_sha256": contract_sha256,
    }
    if layout.metadata_format is not None:
        identity["format"] = layout.metadata_format
    common = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        b"keiba_ai.timestamp_timezone": b"UTC",
        b"keiba_ai.reference_datamart": common,
    }


def _validate_contract(value: object, expected_names: Sequence[str]) -> str:
    if not isinstance(value, dict) or set(value) != {"settings", "sha256"}:
        raise ValueError("reference datamart calculation contract metadata is invalid")
    settings, digest = value["settings"], value["sha256"]
    if (
        not isinstance(settings, dict)
        or set(settings) != {"implementation", "parameters", "selected_columns"}
        or settings["implementation"] != "snapshot_reference_21_groups_v1"
        or settings["selected_columns"] != list(expected_names)
        or not isinstance(settings["parameters"], dict)
        or set(cast(dict[str, object], settings["parameters"]))
        != {"calculation", "reference_rules"}
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise ValueError("reference datamart calculation contract differs")
    canonical = json.dumps(
        settings, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != digest:
        raise ValueError("reference datamart calculation contract hash mismatch")
    return digest


def _rows_schema(
    columns: Sequence[ReferenceColumn],
    groups: Sequence[str],
    metadata: Mapping[bytes, bytes],
    layout: _Layout,
) -> pa.Schema:
    names = [column.name for column in columns]
    available = [f"{group}__available_at" for group in groups]
    fixed = {"race_id", "horse_id", "scheduled_start_at", "freeze_at", "finish_position"}
    if fixed & set(names) or fixed & set(available) or set(names) & set(available):
        raise ValueError("reference datamart column names collide")
    schema = pa.schema(
        [
            pa.field("race_id", pa.string(), nullable=False),
            pa.field("horse_id", pa.string(), nullable=False),
            pa.field("scheduled_start_at", _TIMESTAMP, nullable=False),
            pa.field("freeze_at", _TIMESTAMP, nullable=False),
            *(pa.field(name, pa.float64(), nullable=True) for name in names),
            *(pa.field(name, _TIMESTAMP, nullable=False) for name in available),
            *([pa.field("finish_position", pa.int64(), nullable=False)] if layout.labeled else []),
        ],
        metadata={
            **metadata,
            b"keiba_ai.table_kind": layout.rows_kind,
        },
    )
    return schema


def _races_schema(metadata: Mapping[bytes, bytes], layout: _Layout) -> pa.Schema:
    labels = [
        pa.field("label_usable_after", _TIMESTAMP, nullable=False),
        pa.field("result_delay_days", pa.int64(), nullable=False),
        pa.field("label_raw_sha256", pa.string(), nullable=False),
    ]
    return pa.schema(
        [
            pa.field("race_id", pa.string(), nullable=False),
            pa.field("scheduled_start_at", _TIMESTAMP, nullable=False),
            pa.field("freeze_at", _TIMESTAMP, nullable=False),
            pa.field("field_size", pa.int64(), nullable=False),
            *(labels if layout.labeled else []),
            pa.field("horse_mapping_sha256", pa.string(), nullable=False),
            pa.field("history_usable_through", _TIMESTAMP, nullable=True),
        ],
        metadata={
            **metadata,
            b"keiba_ai.table_kind": layout.races_kind,
        },
    )


def _validate_held(
    root: Path, value: object, layout: _Layout, target_day: datetime | None
) -> list[dict[str, object]]:
    """Check and return held races; ``target_day`` is the single label-free target date."""
    if not isinstance(value, dict) or set(value) != {
        "file",
        "sha256",
        "count",
        "by_role",
        "by_stage",
    }:
        raise ValueError("reference datamart held-race manifest is invalid")
    held_path = root / "held_races.json"
    if value["file"] != "held_races.json" or file_sha256(held_path) != value["sha256"]:
        raise ValueError("reference datamart held-race file hash mismatch")
    try:
        payload = json.loads(held_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("reference datamart held-race file is invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"format", "format_version", "held_races"}
        or payload["format"] != layout.held_format
        or payload["format_version"] != layout.format_version
        or not isinstance(payload["held_races"], list)
    ):
        raise ValueError("reference datamart held-race format is invalid")
    held = cast(list[object], payload["held_races"])
    if len(held) != value["count"]:
        raise ValueError("reference datamart held-race count mismatch")
    previous: tuple[str, str] | None = None
    roles: Counter[str] = Counter()
    stages: Counter[str] = Counter()
    for item in held:
        if (
            not isinstance(item, dict)
            or set(item) != {"race_id", "role", "stage", "reason", "whole_race"}
            or re.fullmatch(r"[0-9]{16}", str(item["race_id"])) is None
            or item["role"] not in {"history", "target"}
            or item["stage"] not in layout.stages
            or not isinstance(item["reason"], str)
            or not item["reason"]
            or item["whole_race"] is not True
        ):
            raise ValueError("reference datamart held-race entry is invalid")
        if target_day is not None and not _label_free_hold(item, f"{target_day:%Y%m%d}"):
            raise ValueError("reference prediction held race role, stage or date is invalid")
        key = (cast(str, item["race_id"]), cast(str, item["role"]))
        if previous is not None and key < previous:
            raise ValueError("reference datamart held races are not deterministically ordered")
        previous = key
        roles[cast(str, item["role"])] += 1
        stages[cast(str, item["stage"])] += 1
    if (
        dict(sorted(roles.items())) != value["by_role"]
        or dict(sorted(stages.items())) != value["by_stage"]
    ):
        raise ValueError("reference datamart held-race role or stage counts differ")
    return cast(list[dict[str, object]], held)


def _validate_market_source(
    value: object, *, day: str, races: Sequence[Mapping[str, object]], target_holds: set[str]
) -> None:
    """Check where the market came from; a fetch must start at or after freeze (ADR-037).

    The start clock is completeness evidence: 0B41 fetched after freeze holds every
    publication up to it. Leakage is prevented separately when the features are built.
    """
    if not isinstance(value, dict):
        raise ValueError("reference prediction market source is invalid")
    if value.get("kind") == "complete_snapshot":
        if set(value) != {"kind"}:
            raise ValueError("reference prediction market source is invalid")
        return
    if value.get("kind") != "race_day_prediction_fetch" or set(value) != _FETCH_KEYS:
        raise ValueError("reference prediction market source is invalid")
    race_id = value["race_id"]
    tables = value["tables"]
    if (
        not isinstance(race_id, str)
        or re.fullmatch(r"[0-9]{16}", race_id) is None
        or race_id[:8] != day
        or not isinstance(value["capture_id"], str)
        or _HEX32.fullmatch(value["capture_id"]) is None
        or not isinstance(value["snapshot_id"], str)
        or _HEX32.fullmatch(value["snapshot_id"]) is None
        or value["data_specs"] != _FETCH_DATA_SPECS
        or not isinstance(tables, dict)
        or set(tables) != _FETCH_TABLES
        or any(
            not isinstance(digest, str) or _HEX64.fullmatch(digest) is None
            for digest in tables.values()
        )
    ):
        raise ValueError("reference prediction market source is invalid")
    scheduled, freeze, started = (
        _aware(value[name]) for name in ("scheduled_start_at", "freeze_at", "started_at")
    )
    if scheduled - freeze != timedelta(seconds=300):
        raise ValueError("reference prediction market source freeze boundary differs")
    if started < freeze:
        raise ValueError("reference prediction market fetch started before freeze_at")
    if {_race_identity(race) for race in races} | target_holds != {race_id}:
        raise ValueError("reference prediction races differ from their market source")
    for race in races:
        if race["scheduled_start_at"] != scheduled or race["freeze_at"] != freeze:
            raise ValueError("reference prediction race clocks differ from their market source")


def _aware(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(cast(str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError("reference prediction market source clock is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("reference prediction market source clock is invalid")
    return parsed


def _label_free_hold(item: Mapping[str, object], day: str) -> bool:
    """History holds precede the target date; target holds lie on it, before any label."""
    race_day = str(item["race_id"])[:8]
    if item["stage"] == "history_result":
        return item["role"] == "history" and race_day < day
    return item["role"] == "target" and race_day == day


def _target_period(value: object) -> tuple[datetime, datetime]:
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise ValueError("reference datamart target period is invalid")
    try:
        start = datetime.fromisoformat(cast(str, value["start"]))
        end = datetime.fromisoformat(cast(str, value["end"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("reference datamart target period is invalid") from exc
    if start.time() != datetime.min.time() or end.time() != datetime.min.time() or start > end:
        raise ValueError("reference datamart target period is invalid")
    return start, end


def _read_partition(
    root: Path,
    entry: Mapping[str, object],
    columns: Sequence[ReferenceColumn],
    groups: Sequence[str],
    contract_sha256: str,
    layout: _Layout,
) -> tuple[pa.Table, pa.Table]:
    required = {
        "year",
        "rows_file",
        "rows_sha256",
        "row_count",
        "races_file",
        "races_sha256",
        "race_count",
        "first_freeze_at",
        "last_freeze_at",
    }
    if set(entry) != required or type(entry["year"]) is not int:
        raise ValueError("reference datamart partition entry is invalid")
    year = entry["year"]
    expected_rows = f"year={year}/part-0.parquet"
    expected_races = f"year={year}/races.parquet"
    if entry["rows_file"] != expected_rows or entry["races_file"] != expected_races:
        raise ValueError("reference datamart partition paths are invalid")
    rows_path, races_path = root / expected_rows, root / expected_races
    if (
        file_sha256(rows_path) != entry["rows_sha256"]
        or file_sha256(races_path) != entry["races_sha256"]
    ):
        raise ValueError("reference datamart partition file hash mismatch")
    metadata = _metadata(year, contract_sha256, layout)
    rows, races = read_parquet(rows_path), read_parquet(races_path)
    if not rows.schema.equals(_rows_schema(columns, groups, metadata, layout), check_metadata=True):
        raise ValueError("reference datamart row schema or metadata differs")
    if not races.schema.equals(_races_schema(metadata, layout), check_metadata=True):
        raise ValueError("reference datamart race schema or metadata differs")
    if rows.num_rows != entry["row_count"] or races.num_rows != entry["race_count"]:
        raise ValueError("reference datamart partition row count mismatch")
    freezes = cast(list[datetime], races.column("freeze_at").to_pylist())
    first = min(freezes).isoformat() if freezes else None
    last = max(freezes).isoformat() if freezes else None
    if entry["first_freeze_at"] != first or entry["last_freeze_at"] != last:
        raise ValueError("reference datamart partition freeze range mismatch")
    return rows, races


def _declared_delay(manifest: Mapping[str, object]) -> int:
    label = manifest["label"]
    contract = cast(dict[str, dict[str, dict[str, object]]], manifest["contract"])
    rules = contract["settings"]["parameters"]["reference_rules"]
    if not isinstance(label, dict) or not isinstance(rules, dict):
        raise ValueError("reference datamart label declaration is invalid")
    delay = label.get("result_delay_days")
    if type(delay) is not int or delay != rules.get("result_delay_days"):
        raise ValueError("reference datamart label delay differs from its reference rules")
    return delay


def _validate_partition_rows(
    rows: pa.Table,
    races: pa.Table,
    year: int,
    seen_races: set[str],
    *,
    delay: int | None,
    period: tuple[datetime, datetime],
) -> None:
    """Check rows; ``delay`` is the label delay, or None for label-free prediction rows."""
    row_values = cast(list[dict[str, object]], rows.to_pylist())
    race_values = cast(list[dict[str, object]], races.to_pylist())
    row_order = [(row["freeze_at"], row["race_id"]) for row in row_values]
    race_order = [(race["freeze_at"], race["race_id"]) for race in race_values]
    if row_order != sorted(row_order) or race_order != sorted(race_order):
        raise ValueError("reference datamart rows are not in chronological order")
    race_map: dict[str, dict[str, object]] = {}
    for race in race_values:
        identity = _race_identity(race)
        if identity in race_map or identity in seen_races:
            raise ValueError("reference datamart race keys are duplicated")
        seen_races.add(identity)
        race_map[identity] = race
        scheduled = cast(datetime, race["scheduled_start_at"])
        freeze = cast(datetime, race["freeze_at"])
        local = scheduled.astimezone(JST)
        if local.year != year or scheduled - freeze != timedelta(seconds=300):
            raise ValueError("reference datamart race year or freeze boundary differs")
        if not period[0].date() <= local.date() <= period[1].date():
            raise ValueError("reference datamart race lies outside its target period")
        history = race["history_usable_through"]
        if history is not None and cast(datetime, history) > freeze:
            raise ValueError("reference datamart history crosses freeze_at")
        hashes = ["horse_mapping_sha256"]
        if delay is not None:
            label = cast(datetime, race["label_usable_after"])
            if (
                race["result_delay_days"] != delay
                or label != result_boundary(scheduled, delay)
                or label <= freeze
            ):
                raise ValueError("reference datamart label-use boundary differs")
            hashes.append("label_raw_sha256")
        elif history is not None and cast(datetime, history) > datetime.combine(
            local.date(), datetime.min.time(), JST
        ):
            # A label-free target date sees only history usable before the date begins.
            raise ValueError("reference prediction history crosses the target date")
        if type(race["field_size"]) is not int or race["field_size"] < 1:
            raise ValueError("reference datamart race field_size is invalid")
        for name in hashes:
            if re.fullmatch(r"[0-9a-f]{64}", str(race[name])) is None:
                raise ValueError("reference datamart label hashes are invalid")
    by_race: dict[str, list[dict[str, object]]] = defaultdict(list)
    keys: set[tuple[str, str]] = set()
    available_names = [name for name in rows.column_names if name.endswith("__available_at")]
    value_names = [field.name for field in rows.schema if pa.types.is_float64(field.type)]
    for row in row_values:
        identity = _race_identity(row)
        horse = row["horse_id"]
        if not isinstance(horse, str) or not horse or (identity, horse) in keys:
            raise ValueError("reference datamart row keys are invalid or duplicated")
        keys.add((identity, horse))
        matching_race = race_map.get(identity)
        if matching_race is None:
            raise ValueError("reference datamart row has no race record")
        if (
            row["scheduled_start_at"] != matching_race["scheduled_start_at"]
            or row["freeze_at"] != matching_race["freeze_at"]
            or any(
                cast(datetime, row[name]) > cast(datetime, row["freeze_at"])
                for name in available_names
            )
        ):
            raise ValueError("reference datamart row time boundary differs")
        for name in value_names:
            value = row[name]
            if value is not None and not isfinite(cast(float, value)):
                raise ValueError("reference datamart numeric value must be finite or null")
        if delay is not None and type(row["finish_position"]) is not int:
            raise ValueError("reference datamart finish_position is invalid")
        by_race[identity].append(row)
    if set(by_race) != set(race_map):
        raise ValueError("reference datamart races and horse rows differ")
    for identity, race in race_map.items():
        selected = by_race[identity]
        field_size = cast(int, race["field_size"])
        if len(selected) != field_size:
            raise ValueError("reference datamart race rows differ from its field size")
        if delay is None:
            continue
        finishes = sorted(cast(int, row["finish_position"]) for row in selected)
        if finishes != list(range(1, field_size + 1)):
            raise ValueError("reference datamart finishing positions are noncontiguous")


def _race_identity(value: Mapping[str, object]) -> str:
    identity = value.get("race_id")
    if not isinstance(identity, str) or re.fullmatch(r"[0-9]{16}", identity) is None:
        raise ValueError("reference datamart requires a complete 16-digit race_id")
    return identity
