"""Check scalar values and missingness without changing data."""

from __future__ import annotations

from math import isfinite, isnan

from features.contracts.types import FeatureScalar


def is_feature_value(value: object) -> bool:
    """Return whether a value is a supported scalar, including missing values."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and (isnan(value) or isfinite(value))


def is_missing(value: FeatureScalar) -> bool:
    """Recognize None and NaN without imputing or coercing values."""
    return value is None or (isinstance(value, float) and isnan(value))


def is_non_missing(value: FeatureScalar) -> bool:
    """Return whether the scalar has a non-missing value."""
    return not is_missing(value)


def feature_values_equal(left: FeatureScalar, right: FeatureScalar) -> bool:
    """Compare scalars while treating missing representations as equal."""
    if is_missing(left) or is_missing(right):
        return is_missing(left) and is_missing(right)
    return left == right
