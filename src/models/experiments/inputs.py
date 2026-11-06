"""Read explicit model inputs and describe their audited time boundaries."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from math import isnan
from pathlib import Path
from zoneinfo import ZoneInfo

from data.loader.read_json import read_json
from make_features.contracts.observations import HistoricalRace
from models.dataset.builder import FeatureGenerationResult, build_features
from models.dataset.rows import FeatureRow, RankingRow
from models.dataset.schema import FeatureSchema
from models.serialization.inputs import parse_feature_inputs
from models.serialization.projection import parse_label_sources
from models.serialization.real_market import SnapshotResultLabel


def file_sha256(path: Path) -> str:
    """Hash a file without loading a large artifact into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_experiment_input(
    path: Path,
) -> tuple[
    FeatureSchema, FeatureGenerationResult, str, tuple[HistoricalRace | SnapshotResultLabel, ...]
]:
    """Read and audit the existing JSON contract without changing source data."""
    digest = file_sha256(path)
    payload = read_json(path)
    schema, records = parse_feature_inputs(payload)
    results = parse_label_sources(
        payload,
        required=schema.calculation_contract is not None
        and any(r.finish_position is not None for r in records),
    )
    if file_sha256(path) != digest:
        raise ValueError("input changed while it was being read")
    return schema, build_features(records, feature_schema=schema), digest, results


def chronological_times(rows: Sequence[FeatureRow | RankingRow]) -> tuple[datetime, ...]:
    """Require one aware freeze time per race and strictly increasing race times."""
    times: list[datetime] = []
    previous_race: str | None = None
    seen: set[str] = set()
    for row in rows:
        value = row.freeze_at
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("every race requires timezone-aware freeze_at")
        if row.race_id == previous_race:
            if value != times[-1]:
                raise ValueError("every row in a race must have the same freeze_at")
            continue
        if row.race_id in seen or (times and value <= times[-1]):
            raise ValueError("race chronology must be strictly increasing by freeze_at")
        seen.add(row.race_id)
        previous_race = row.race_id
        times.append(value)
    if not times:
        raise ValueError("at least one race is required")
    return tuple(times)


def select_prediction_rows(
    rows: Sequence[FeatureRow], *, selection: str, date_timezone: str
) -> tuple[FeatureRow, ...]:
    """Select all rows or the maximum input freeze date in the configured timezone."""
    times = chronological_times(rows)
    if selection == "all":
        return tuple(rows)
    if selection != "latest_date":
        raise ValueError("unknown prediction selection")
    timezone = ZoneInfo(date_timezone)
    latest = max(value.astimezone(timezone).date() for value in times)
    return tuple(
        row
        for row in rows
        if row.freeze_at is not None and row.freeze_at.astimezone(timezone).date() == latest
    )


def dataset_summary(rows: Sequence[FeatureRow | RankingRow]) -> dict[str, object]:
    """Describe race identities, periods and per-feature missingness without filtering."""
    times = chronological_times(rows)
    missing_counts: dict[str, int] = {}
    for row in rows:
        for name, value in row.features.items():
            missing = value is None or (isinstance(value, float) and isnan(value))
            missing_counts[name] = missing_counts.get(name, 0) + int(missing)
    return {
        "rows": len(rows),
        "races": len(times),
        "race_ids": list(dict.fromkeys(row.race_id for row in rows)),
        "freeze_at_start": times[0].isoformat(),
        "freeze_at_end": times[-1].isoformat(),
        "missing_values_by_feature": missing_counts,
    }
