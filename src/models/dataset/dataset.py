"""Hold a validated race-contiguous ranking dataset."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from models.dataset.rows import FeatureValue, RankingRow
from models.dataset.schema import FeatureSchema, validate_feature_names
from models.dataset.validation import (
    _normalize_ranking_row,
    _validate_features,
    _validate_finish_positions,
    _validate_race_rows,
    label_for_finish_position,
)
from models.ranking.rules import (
    race_group_sizes,
)


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
        validate_feature_names(self.feature_names)
        if self.feature_schema.feature_names != self.feature_names:
            raise ValueError("feature_schema names must match feature_names")
        _validate_race_rows(self.rows)
        _validate_finish_positions(self.rows)
        expected_labels = tuple(label_for_finish_position(row.finish_position) for row in self.rows)
        if self.labels != expected_labels:
            raise ValueError("labels must match finish_position values")
        expected_groups = race_group_sizes(row.race_id for row in self.rows)
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
        validate_feature_names(names)
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
            groups=race_group_sizes(row.race_id for row in normalized_rows),
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
