"""Validated, race-contiguous inputs for the ranking model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, isnan
from types import MappingProxyType
from typing import Literal

type FeatureValue = int | float | None
type TieBreakRule = Literal["score_desc_then_horse_id"]
type FeatureValueType = Literal["numeric"]
type MissingValuePolicy = Literal["preserve_native_missing"]

TIE_BREAK_RULE: TieBreakRule = "score_desc_then_horse_id"
DEFAULT_LABEL_GAIN: Mapping[int, int] = MappingProxyType({0: 0, 1: 1, 2: 3, 3: 7})
_RESERVED_RESULT_FEATURE_NAME_ALIASES = frozenset(
    {
        "confirmed_time",
        "earnings",
        "final_odds",
        "finish_position",
        "finish_time",
        "harontimel3",
        "arrival",
        "arrival_rank",
        "dead_heat",
        "history_result",
        "kakuteijyuni",
        "last_3f",
        "last3f",
        "last_odds",
        "margin",
        "ninki",
        "odds_final",
        "passing_position",
        "payout",
        "payout_amount",
        "payouts",
        "popularity",
        "prize",
        "prize_money",
        "placing",
        "position",
        "refund",
        "refund_amount",
        "rank",
        "result",
        "result_rank",
        "race_result",
        "time",
        "timediff",
    }
)
_RESERVED_RESULT_FEATURE_NAME_TOKENS = frozenset(
    {
        "arrival",
        "earnings",
        "finish",
        "last3f",
        "margin",
        "passing",
        "payout",
        "placing",
        "popularity",
        "position",
        "prize",
        "rank",
        "result",
        "speed",
        "time",
        "outcome",
        "winner",
    }
)


@dataclass(frozen=True)
class FeatureSpec:
    """Describe one numeric feature at the model boundary."""

    name: str
    generation_rule: str
    result_derived: bool
    value_type: FeatureValueType = "numeric"
    unit: str | None = None
    missing_value_policy: MissingValuePolicy = "preserve_native_missing"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("feature spec names must be non-empty strings")
        if not isinstance(self.generation_rule, str) or not self.generation_rule:
            raise ValueError("feature spec generation_rule must be a non-empty string")
        if not isinstance(self.result_derived, bool):
            raise ValueError("feature spec result_derived must be a boolean")
        if self.result_derived:
            raise ValueError("result-derived features are not allowed in the model schema")
        if self.value_type != "numeric":
            raise ValueError("feature spec value_type must be 'numeric'")
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit):
            raise ValueError("feature spec unit must be a non-empty string or None")
        if self.missing_value_policy != "preserve_native_missing":
            raise ValueError("feature spec missing_value_policy must be 'preserve_native_missing'")


_APPROVED_FEATURE_SPECS: Mapping[str, FeatureSpec] = MappingProxyType(
    {
        "ability": FeatureSpec(
            name="ability",
            generation_rule="pre_race_ability_v1",
            result_derived=False,
            unit="score",
        ),
        "historical_odds": FeatureSpec(
            name="historical_odds",
            generation_rule="historical_odds_v1",
            result_derived=False,
            unit="decimal",
        ),
    }
)


@dataclass(frozen=True)
class FeatureSchema:
    """Describe the ordered feature contract used by training and prediction."""

    schema_id: str
    features: tuple[FeatureSpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.schema_id, str) or not self.schema_id:
            raise ValueError("feature schema schema_id must be a non-empty string")
        if not self.features:
            raise ValueError("feature schema must contain at least one feature")
        names = tuple(feature.name for feature in self.features)
        _validate_feature_names(names)
        for feature in self.features:
            if _APPROVED_FEATURE_SPECS.get(feature.name) != feature:
                raise ValueError(
                    f"feature {feature.name!r} does not match the approved feature specification"
                )

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Return the ordered names represented by this schema."""
        return tuple(feature.name for feature in self.features)

    @classmethod
    def from_names(
        cls,
        feature_names: Sequence[str],
        *,
        schema_id: str,
        generation_rule: str | None = None,
    ) -> FeatureSchema:
        """Create a schema from the approved feature allow-list."""
        names = tuple(feature_names)
        _validate_feature_names(names)
        specs = tuple(_APPROVED_FEATURE_SPECS[name] for name in names)
        if generation_rule is not None and any(
            spec.generation_rule != generation_rule for spec in specs
        ):
            raise ValueError("generation_rule does not match the approved feature specification")
        return cls(
            schema_id=schema_id,
            features=specs,
        )

    def as_metadata(self) -> dict[str, object]:
        """Return a JSON-compatible schema description."""
        return {
            "schema_id": self.schema_id,
            "features": [
                {
                    "generation_rule": feature.generation_rule,
                    "missing_value_policy": feature.missing_value_policy,
                    "name": feature.name,
                    "result_derived": feature.result_derived,
                    "unit": feature.unit,
                    "value_type": feature.value_type,
                }
                for feature in self.features
            ],
        }


@dataclass(frozen=True)
class FeatureRow:
    """Represent one horse's feature values for prediction."""

    race_id: str
    horse_id: str
    features: Mapping[str, FeatureValue]
    freeze_at: datetime | None = None


@dataclass(frozen=True)
class RankingRow:
    """Represent one labeled horse row for ranking training."""

    race_id: str
    horse_id: str
    features: Mapping[str, FeatureValue]
    finish_position: int
    freeze_at: datetime | None = None


@dataclass(frozen=True)
class RankingDataset:
    """Hold contiguous race rows, labels, and LightGBM group sizes.

    The dataset does not fill missing values.  A missing feature key becomes
    ``None`` and an existing ``float('nan')`` remains NaN in the feature
    matrix.  In particular, no final-odds value is used as a fallback.
    """

    rows: tuple[RankingRow, ...]
    feature_names: tuple[str, ...]
    feature_schema: FeatureSchema
    labels: tuple[int, ...]
    groups: tuple[int, ...]

    def __post_init__(self) -> None:
        """Validate all row, label, feature, and group invariants."""
        if not self.rows:
            raise ValueError("ranking dataset must contain at least one row")
        _validate_feature_names(self.feature_names)
        if self.feature_schema.feature_names != self.feature_names:
            raise ValueError("feature_schema names must match feature_names")
        _validate_race_rows(self.rows)
        _validate_finish_positions(self.rows)
        expected_labels = tuple(label_for_finish_position(row.finish_position) for row in self.rows)
        if self.labels != expected_labels:
            raise ValueError("labels must match finish_position values")
        expected_groups = _race_groups(self.rows)
        self.validate_groups(self.groups, len(self.rows))
        if self.groups != expected_groups:
            raise ValueError("groups must match the contiguous race rows")
        for row in self.rows:
            _validate_features(row.features, self.feature_names)

    @classmethod
    def from_rows(
        cls,
        rows: Sequence[RankingRow],
        *,
        feature_names: Sequence[str],
        feature_schema: FeatureSchema,
    ) -> RankingDataset:
        """Build and validate a dataset from rows already read from Parquet.

        Args:
            rows: Race rows in the order in which they will be passed to the
                ranker. Rows for one race must be contiguous.
            feature_names: Required ordered feature schema. Missing keys in a
                row are represented by ``None``.
            feature_schema: Semantic schema for the ordered feature names.

        Returns:
            A validated immutable dataset with labels and group sizes.

        Raises:
            ValueError: If rows, features, or race boundaries are invalid.
        """
        normalized_rows = tuple(_normalize_ranking_row(row) for row in rows)
        if not normalized_rows:
            raise ValueError("ranking dataset must contain at least one row")
        names = tuple(feature_names)
        _validate_feature_names(names)
        if feature_schema.feature_names != names:
            raise ValueError("feature_schema names must match feature_names")
        allowed = set(names)
        unexpected = sorted(
            {name for row in normalized_rows for name in row.features if name not in allowed}
        )
        if unexpected:
            raise ValueError(f"feature names are outside the schema: {unexpected!r}")
        _validate_race_rows(normalized_rows)
        _validate_finish_positions(normalized_rows)
        labels = tuple(label_for_finish_position(row.finish_position) for row in normalized_rows)
        return cls(
            rows=normalized_rows,
            feature_names=names,
            feature_schema=feature_schema,
            labels=labels,
            groups=_race_groups(normalized_rows),
        )

    def feature_matrix(self) -> list[list[FeatureValue]]:
        """Return feature values without imputing missing values."""
        return [[row.features.get(name) for name in self.feature_names] for row in self.rows]

    @staticmethod
    def validate_groups(groups: Sequence[int], row_count: int) -> None:
        """Validate LightGBM group sizes against the number of rows.

        ``groups`` contains one row count of at least three per race, not race IDs.
        """
        if row_count < 0:
            raise ValueError("row_count must not be negative")
        if any(isinstance(group, bool) or not isinstance(group, int) for group in groups):
            raise ValueError("group sizes must be integers")
        if any(group < 3 for group in groups):
            raise ValueError("group sizes must be at least 3")
        if sum(groups) != row_count:
            raise ValueError("sum(groups) must equal the number of rows")


def validate_feature_rows(
    rows: Sequence[FeatureRow],
    feature_names: Sequence[str],
) -> tuple[FeatureRow, ...]:
    """Validate and freeze feature rows against a trained feature schema."""
    normalized_rows = tuple(_normalize_feature_row(row) for row in rows)
    if not normalized_rows:
        raise ValueError("prediction requires at least one row")
    names = tuple(feature_names)
    _validate_feature_names(names)
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
    )


def _validate_feature_names(feature_names: Sequence[str]) -> None:
    if not feature_names:
        raise ValueError("at least one feature is required")
    if any(not isinstance(name, str) or not name for name in feature_names):
        raise ValueError("feature names must be non-empty strings")
    if len(set(feature_names)) != len(feature_names):
        raise ValueError("feature names must be unique")
    reserved = sorted(name for name in feature_names if _is_reserved_result_feature_name(name))
    if reserved:
        raise ValueError(f"result-derived feature names are reserved: {reserved!r}")
    unapproved = sorted(name for name in feature_names if name not in _APPROVED_FEATURE_SPECS)
    if unapproved:
        raise ValueError(f"feature names are outside the approved allow-list: {unapproved!r}")


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
    start = 0
    for group_size in _race_groups(rows):
        race_rows = rows[start : start + group_size]
        for row in race_rows:
            _validate_finish_position(row.finish_position)
            if row.finish_position > group_size:
                raise ValueError("finish_position must not exceed its race group size")
        positions = [row.finish_position for row in race_rows]
        if set(positions) != set(range(1, group_size + 1)):
            raise ValueError("finish_position values must be unique and contiguous within a race")
        start += group_size


def _validate_finish_position(finish_position: int) -> None:
    if isinstance(finish_position, bool) or not isinstance(finish_position, int):
        raise ValueError("finish_position must be an integer")
    if finish_position < 1:
        raise ValueError("finish_position must be positive")


def _is_reserved_result_feature_name(name: str) -> bool:
    normalized = "".join(character for character in name.casefold() if character.isalnum())
    if normalized == "odds":
        return True
    reserved = {
        "".join(character for character in alias.casefold() if character.isalnum())
        for alias in _RESERVED_RESULT_FEATURE_NAME_ALIASES
    }
    return (
        normalized in reserved
        or normalized.startswith("pay")
        or any(
            normalized == token or normalized.startswith(token) or normalized.endswith(token)
            for token in _RESERVED_RESULT_FEATURE_NAME_TOKENS
        )
    )


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


def _race_groups(rows: Sequence[RankingRow]) -> tuple[int, ...]:
    groups: list[int] = []
    current_race: str | None = None
    for row in rows:
        if row.race_id != current_race:
            groups.append(1)
            current_race = row.race_id
        else:
            groups[-1] += 1
    return tuple(groups)
