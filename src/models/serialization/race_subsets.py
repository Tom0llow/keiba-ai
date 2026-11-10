"""Classify fixed-snapshot races into named evaluation subsets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from make_features.real_market import KEY_COLUMNS
from make_features.reference_raw import race_identity

JRA_FLAT_GRADED_STAKES_V1 = "jra_flat_graded_stakes_v1"
JRA_FLAT_GRADED_STAKES_V1_DEFINITION = "GradeCD A, B, or C and TrackCD 10 through 24"

# The same key columns and identity rule that build the datamart's race_id values.
RACE_KEY_COLUMNS = KEY_COLUMNS
_GRADED_CODES = frozenset({"A", "B", "C"})
_FLAT_TRACK_CODES = frozenset(f"{code:02d}" for code in range(10, 25))


@dataclass(frozen=True)
class RaceClassification:
    """Hold every validated race identity of the rows and the named evaluation subsets."""

    race_ids: frozenset[str]
    subsets: dict[str, frozenset[str]]


def classify_nl_ra_race_rows(rows: Sequence[Mapping[str, object]]) -> RaceClassification:
    """Validate ``NL_RA_RACE`` rows once and classify them into the supported subsets.

    Every row must carry one unique complete repository race key. Grade and
    track codes outside the subset definition, including null codes, are valid
    rows but are not selected.

    Raises:
        ValueError: If a row is not a mapping, lacks a required field, or has
            a duplicate or invalid race key.
    """
    selected: set[str] = set()
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("NL_RA_RACE rows must be mappings")
        race_id = _race_id(row)
        if race_id in seen:
            raise ValueError("NL_RA_RACE contains duplicate race_id")
        seen.add(race_id)
        # Snapshot code columns are nullable strings; a null code is simply not selected.
        grade = _nullable_code(row, "GradeCD")
        track = _nullable_code(row, "TrackCD")
        if grade in _GRADED_CODES and track in _FLAT_TRACK_CODES:
            selected.add(race_id)
    return RaceClassification(
        race_ids=frozenset(seen), subsets={JRA_FLAT_GRADED_STAKES_V1: frozenset(selected)}
    )


def _race_id(row: Mapping[str, object]) -> str:
    """Return the validated datamart race identity of one source row."""
    try:
        return race_identity(row)
    except ValueError as exc:
        raise ValueError(f"NL_RA_RACE requires complete 16-digit race keys: {exc}") from exc


def _nullable_code(row: Mapping[str, object], name: str) -> str | None:
    """Return one nullable source code, which must be present as a column."""
    if name not in row:
        raise ValueError(f"NL_RA_RACE row is missing required column {name!r}")
    value = row[name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"NL_RA_RACE column {name!r} must contain strings or null")
    return value


__all__ = [
    "JRA_FLAT_GRADED_STAKES_V1",
    "JRA_FLAT_GRADED_STAKES_V1_DEFINITION",
    "RACE_KEY_COLUMNS",
    "RaceClassification",
    "classify_nl_ra_race_rows",
]
