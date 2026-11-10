"""Convert reference datamart tables into validated race arrays."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from numpy.typing import NDArray

from models.dataset.race_arrays import RaceArrays

_JST = ZoneInfo("Asia/Tokyo")


def race_arrays_from_reference_tables(
    rows: pa.Table,
    races: pa.Table,
    *,
    feature_columns: Sequence[str],
    market_column: str,
) -> RaceArrays:
    """Return model arrays from validated reference datamart tables.

    Rows are stably ordered by ``(freeze_at, race_id, horse_id)``. Numeric
    nulls become NaN, and race years are derived from scheduled time in JST.
    Columns are converted with Arrow and NumPy, so a full-period datamart is
    not materialized as Python row dictionaries.

    Raises:
        ValueError: If required columns, Arrow types, race correspondence, or
            race-level labels differ from the reference datamart contract.
    """
    names = tuple(feature_columns)
    _validate_feature_columns(names, market_column)
    _validate_rows_schema(rows, names, market_column)
    _validate_races_schema(races)
    _require_no_nulls(rows, ("race_id", "horse_id", "scheduled_start_at", "freeze_at"), "rows")
    _require_no_nulls(rows, ("finish_position",), "rows")
    _require_no_nulls(
        races,
        ("race_id", "scheduled_start_at", "freeze_at", "field_size", "label_usable_after"),
        "races",
    )

    race_ids = cast(list[str], races.column("race_id").to_pylist())
    if any(not race_id for race_id in race_ids):
        raise ValueError("race_id must be a nonempty string")
    if len(set(race_ids)) != len(race_ids):
        raise ValueError("reference race identifiers must be unique")
    field_sizes = _int64_values(races, "field_size")
    if np.any(field_sizes < 3):
        raise ValueError("reference race field_size must be at least 3")
    race_index = {race_id: index for index, race_id in enumerate(race_ids)}

    ordered = rows.sort_by(
        [("freeze_at", "ascending"), ("race_id", "ascending"), ("horse_id", "ascending")]
    )
    row_race_ids = cast(list[str], ordered.column("race_id").to_pylist())
    horse_ids = cast(list[str], ordered.column("horse_id").to_pylist())
    if any(not horse_id for horse_id in horse_ids):
        raise ValueError("horse_id must be a nonempty string")
    try:
        row_races = np.fromiter(
            (race_index[race_id] for race_id in row_race_ids),
            dtype=np.int64,
            count=len(row_race_ids),
        )
    except KeyError as exc:
        raise ValueError("reference horse row has no matching race") from exc

    for name in ("scheduled_start_at", "freeze_at"):
        if not np.array_equal(
            _timestamp_values(ordered, name), _timestamp_values(races, name)[row_races]
        ):
            raise ValueError("reference horse row timestamps differ from its race")

    starts = np.flatnonzero(np.concatenate(([True], row_races[1:] != row_races[:-1])))
    if len(starts) == 0:
        raise ValueError("reference rows must contain at least one race")
    group_races = row_races[starts]
    if len(np.unique(group_races)) != len(group_races):
        raise ValueError("reference rows for each race must be contiguous after ordering")
    if set(group_races.tolist()) != set(range(len(race_ids))):
        raise ValueError("reference race and horse-row identifiers differ")
    group_sizes = np.diff(np.concatenate((starts, [len(row_races)]))).astype(np.int64)
    if not np.array_equal(group_sizes, field_sizes[group_races]):
        raise ValueError("reference race rows differ from field_size")

    race_rows = cast(list[dict[str, object]], races.to_pylist())
    ordered_races = [race_rows[int(index)] for index in group_races]
    scheduled = [_utc_datetime(race["scheduled_start_at"]) for race in ordered_races]
    return RaceArrays(
        race_ids=tuple(race_ids[int(index)] for index in group_races),
        freeze_at=tuple(_utc_datetime(race["freeze_at"]) for race in ordered_races),
        label_usable_after=tuple(
            _utc_datetime(race["label_usable_after"]) for race in ordered_races
        ),
        years=np.asarray([value.astimezone(_JST).year for value in scheduled], dtype=np.int64),
        group_sizes=group_sizes,
        horse_ids=tuple(horse_ids),
        features=_feature_matrix(ordered, names),
        feature_names=names,
        finish_positions=_int64_values(ordered, "finish_position"),
        market_odds=_float_values(ordered, market_column),
    )


def _validate_feature_columns(feature_columns: tuple[str, ...], market_column: str) -> None:
    if len(set(feature_columns)) != len(feature_columns):
        raise ValueError("feature_columns must not contain duplicates")
    if any(not isinstance(name, str) or not name for name in feature_columns):
        raise ValueError("feature_columns must contain nonempty strings")
    if not isinstance(market_column, str) or not market_column:
        raise ValueError("market_column must be a nonempty string")


def _validate_rows_schema(
    rows: pa.Table, feature_columns: tuple[str, ...], market_column: str
) -> None:
    _require_table(rows, "rows")
    requirements: tuple[tuple[str, Callable[[pa.DataType], bool]], ...] = (
        ("race_id", pa.types.is_string),
        ("horse_id", pa.types.is_string),
        ("scheduled_start_at", _is_utc_timestamp),
        ("freeze_at", _is_utc_timestamp),
        ("finish_position", pa.types.is_int64),
        *((name, pa.types.is_float64) for name in feature_columns),
        (market_column, pa.types.is_float64),
    )
    _validate_columns(rows, requirements, "rows")


def _validate_races_schema(races: pa.Table) -> None:
    _require_table(races, "races")
    requirements: tuple[tuple[str, Callable[[pa.DataType], bool]], ...] = (
        ("race_id", pa.types.is_string),
        ("scheduled_start_at", _is_utc_timestamp),
        ("freeze_at", _is_utc_timestamp),
        ("field_size", pa.types.is_int64),
        ("label_usable_after", _is_utc_timestamp),
    )
    _validate_columns(races, requirements, "races")


def _require_table(value: object, name: str) -> None:
    if not isinstance(value, pa.Table):
        raise ValueError(f"{name} must be a pyarrow Table")


def _validate_columns(
    table: pa.Table,
    requirements: tuple[tuple[str, Callable[[pa.DataType], bool]], ...],
    table_name: str,
) -> None:
    for name, expected_type in requirements:
        index = table.schema.get_field_index(name)
        if index < 0:
            raise ValueError(f"{table_name} is missing required column {name!r}")
        if not expected_type(table.schema.field(index).type):
            raise ValueError(f"{table_name} column {name!r} has an invalid type")


def _require_no_nulls(table: pa.Table, names: Sequence[str], table_name: str) -> None:
    for name in names:
        if table.column(name).null_count:
            raise ValueError(f"{table_name} column {name!r} must not contain nulls")


def _is_utc_timestamp(data_type: pa.DataType) -> bool:
    if not pa.types.is_timestamp(data_type):
        return False
    timestamp = cast(pa.TimestampType, data_type)
    return bool(timestamp.tz == "UTC" and timestamp.unit == "us")


def _timestamp_values(table: pa.Table, name: str) -> NDArray[np.int64]:
    return np.asarray(table.column(name).cast(pa.int64()).to_numpy(), dtype=np.int64)


def _int64_values(table: pa.Table, name: str) -> NDArray[np.int64]:
    return np.asarray(table.column(name).to_numpy(), dtype=np.int64)


def _float_values(table: pa.Table, name: str) -> NDArray[np.float64]:
    column = pc.fill_null(table.column(name), float("nan"))
    values = np.asarray(column.to_numpy(), dtype=np.float64)
    if np.any(np.isinf(values)):
        raise ValueError(f"{name} must be finite or null")
    return values


def _feature_matrix(table: pa.Table, names: Sequence[str]) -> NDArray[np.float64]:
    matrix = np.empty((table.num_rows, len(names)), dtype=np.float64)
    for index, name in enumerate(names):
        matrix[:, index] = _float_values(table, name)
    return matrix


def _utc_datetime(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("reference timestamps must be UTC-aware datetimes")
    return value


__all__ = ["race_arrays_from_reference_tables"]
