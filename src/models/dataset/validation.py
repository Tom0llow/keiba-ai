"""Validate and normalize model rows, labels and race groups."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite, isnan
from types import MappingProxyType

from models.dataset.rows import FeatureRow, FeatureValue, RankingRow
from models.dataset.schema import (
    _APPROVED_FEATURE_SPECS,
    _is_reserved_result_feature_name,
    validate_feature_names,
)
from models.ranking.rules import (
    race_group_sizes,
    race_ranges,
)


def validate_feature_rows(
    rows: Sequence[FeatureRow],
    feature_names: Sequence[str],
) -> tuple[FeatureRow, ...]:
    """Validate and freeze feature rows against a trained feature schema."""
    normalized_rows = tuple(_normalize_feature_row(row) for row in rows)
    if not normalized_rows:
        raise ValueError("prediction requires at least one row")
    names = tuple(feature_names)
    validate_feature_names(names)
    allowed = set(names)
    unexpected = sorted(
        {name for row in normalized_rows for name in row.features if name not in allowed}
    )
    if unexpected:
        raise ValueError(f"feature names are outside the schema: {unexpected!r}")
    _validate_feature_row_races(normalized_rows)
    return normalized_rows


def label_for_finish_position(finish_position: int) -> int:
    """Return the MVP label for a positive confirmed finish position."""
    _validate_finish_position(finish_position)
    if finish_position == 1:
        return 3
    if finish_position == 2:
        return 2
    if finish_position == 3:
        return 1
    return 0


def _normalize_ranking_row(row: RankingRow) -> RankingRow:
    if not isinstance(row, RankingRow):
        raise TypeError("rows must contain RankingRow values")
    _validate_identity(row.race_id, row.horse_id)
    _validate_features(row.features, None)
    return RankingRow(
        race_id=row.race_id,
        horse_id=row.horse_id,
        features=MappingProxyType(dict(row.features)),
        finish_position=row.finish_position,
        freeze_at=row.freeze_at,
    )


def _normalize_feature_row(row: FeatureRow) -> FeatureRow:
    if not isinstance(row, FeatureRow):
        raise TypeError("rows must contain FeatureRow values")
    _validate_identity(row.race_id, row.horse_id)
    _validate_features(row.features, None)
    return FeatureRow(
        race_id=row.race_id,
        horse_id=row.horse_id,
        features=MappingProxyType(dict(row.features)),
        freeze_at=row.freeze_at,
        available_at=MappingProxyType(dict(row.available_at)),
    )


def _validate_identity(race_id: str, horse_id: str) -> None:
    if not isinstance(race_id, str) or not race_id:
        raise ValueError("race_id must be a non-empty string")
    if not isinstance(horse_id, str) or not horse_id:
        raise ValueError("horse_id must be a non-empty string")


def _validate_features(
    features: Mapping[str, FeatureValue],
    feature_names: Sequence[str] | None,
) -> None:
    if not isinstance(features, Mapping):
        raise TypeError("features must be a mapping")
    if feature_names is not None:
        allowed = set(feature_names)
        if any(name not in allowed for name in features):
            raise ValueError("features contain a name outside the schema")
    for name, value in features.items():
        if not isinstance(name, str) or not name:
            raise ValueError("feature names must be non-empty strings")
        if _is_reserved_result_feature_name(name):
            raise ValueError(f"result-derived feature name is reserved: {name!r}")
        if name not in _APPROVED_FEATURE_SPECS:
            raise ValueError(f"feature name is outside the approved allow-list: {name!r}")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise TypeError(f"feature {name!r} must be numeric or None")
        if isinstance(value, float) and not isnan(value) and not isfinite(value):
            raise ValueError(f"feature {name!r} must be finite or NaN")


def _validate_race_rows(rows: Sequence[RankingRow]) -> None:
    seen_races: set[str] = set()
    seen_horses: set[str] = set()
    current_race: str | None = None
    for row in rows:
        _validate_identity(row.race_id, row.horse_id)
        if row.race_id != current_race:
            if row.race_id in seen_races:
                raise ValueError("rows for each race must be contiguous")
            if current_race is not None:
                seen_horses.clear()
            current_race = row.race_id
            seen_races.add(row.race_id)
        if row.horse_id in seen_horses:
            raise ValueError("horse_id must be unique within a race")
        seen_horses.add(row.horse_id)


def _validate_finish_positions(rows: Sequence[RankingRow]) -> None:
    groups = race_group_sizes(row.race_id for row in rows)
    for start, stop in race_ranges(groups):
        race_rows = rows[start:stop]
        group_size = stop - start
        for row in race_rows:
            _validate_finish_position(row.finish_position)
            if row.finish_position > group_size:
                raise ValueError("finish_position must not exceed its race group size")
        positions = [row.finish_position for row in race_rows]
        if set(positions) != set(range(1, group_size + 1)):
            raise ValueError("finish_position values must be unique and contiguous within a race")


def _validate_finish_position(finish_position: int) -> None:
    if isinstance(finish_position, bool) or not isinstance(finish_position, int):
        raise ValueError("finish_position must be an integer")
    if finish_position < 1:
        raise ValueError("finish_position must be positive")


def _validate_feature_row_races(rows: Sequence[FeatureRow]) -> None:
    seen_races: set[str] = set()
    seen_horses: set[str] = set()
    current_race: str | None = None
    current_group_size = 0
    for row in rows:
        if row.race_id != current_race:
            if current_race is not None and current_group_size < 3:
                raise ValueError("prediction race groups must contain at least 3 rows")
            if row.race_id in seen_races:
                raise ValueError("rows for each race must be contiguous")
            if current_race is not None:
                seen_horses.clear()
            current_race = row.race_id
            seen_races.add(row.race_id)
            current_group_size = 0
        if row.horse_id in seen_horses:
            raise ValueError("horse_id must be unique within a race")
        seen_horses.add(row.horse_id)
        current_group_size += 1
    if current_group_size < 3:
        raise ValueError("prediction race groups must contain at least 3 rows")
