"""Assemble one graded race's PL probabilities from published race-day features (ADR-039).

Nothing here reads files or clocks. The caller supplies the validated model, the
race's stored schedule and horse-number mapping, the features it read, and the
clock at which the calculation started. A check that one race fails returns a
``PredictionHold`` with a reason code, so the other races of the day continue.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import combinations, permutations

import numpy as np
import numpy.typing as npt

from make_features.real_market import canonical_hash
from models.artifacts.pl_model import PLModel
from models.probability.plackett_luce import OrderProbabilities, top3_order_probabilities
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1

PREDICTION_FORMAT = "pl_race_prediction"
PREDICTION_FORMAT_VERSION = 1
PREDICTION_STAGE = "prediction"
# JRA sales close two minutes before the scheduled start.
SALES_CLOSE_BEFORE_START = timedelta(minutes=2)
MINIMUM_FIELD_SIZE = 3
_HORSE_NUMBER = re.compile(r"[0-9]{2}")


@dataclass(frozen=True)
class RaceTarget:
    """One graded race's stored schedule and horse-number mapping from the fixed snapshot."""

    race_id: str
    scheduled_start_at: datetime
    freeze_at: datetime
    horse_mapping: Mapping[str, str]
    grade_code: str

    @property
    def sales_close_at(self) -> datetime:
        """Return the instant when sales close for this race."""
        return self.scheduled_start_at - SALES_CLOSE_BEFORE_START


@dataclass(frozen=True)
class RaceFeatures:
    """The published features read for one race (``read_reference_prediction_features``)."""

    manifest_sha256: str
    manifest: Mapping[str, object]
    rows: Sequence[Mapping[str, object]]
    races: Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class PredictionHold:
    """One race that is not predicted, with a reason code and a readable detail."""

    race_id: str
    reason: str
    detail: str


@dataclass(frozen=True)
class RacePrediction:
    """One race's prediction payload in the ``pl_race_prediction`` format."""

    race_id: str
    after_sales_close: bool
    win: Mapping[str, float]
    payload: Mapping[str, object]


def is_after_sales_close(target: RaceTarget, at: datetime) -> bool:
    """Return whether ``at`` lies strictly after the race's sales close."""
    return at > target.sales_close_at


def build_race_prediction(
    model: PLModel,
    target: RaceTarget,
    features: RaceFeatures,
    *,
    computed_at: datetime,
    snapshot: Mapping[str, object],
    provenance: Mapping[str, object],
) -> RacePrediction | PredictionHold:
    """Check one race's features against the model and its card, then compute its probabilities.

    ``computed_at`` is the one clock reading taken just before this calculation; it
    decides ``after_sales_close``. ``snapshot`` and ``provenance`` are copied into the
    payload unchanged.

    Raises:
        ValueError: If ``computed_at`` is not timezone-aware. Every check on the race
            itself returns a ``PredictionHold`` instead.
    """
    if computed_at.utcoffset() is None:
        raise ValueError("computed_at must be timezone-aware")

    def hold(reason: str, detail: str) -> PredictionHold:
        return PredictionHold(target.race_id, reason, detail)

    try:
        model.require_compatible_features(features.manifest)
    except ValueError as exc:
        return hold("model_features_mismatch", str(exc))
    races = [race for race in features.races if race.get("race_id") == target.race_id]
    if len(races) != 1:
        return hold("features_missing_race", "the features hold no single row for this race")
    (race,) = races
    if (
        race.get("scheduled_start_at") != target.scheduled_start_at
        or race.get("freeze_at") != target.freeze_at
    ):
        return hold(
            "schedule_mismatch", "feature schedule differs from the stored snapshot schedule"
        )
    try:
        model.require_prediction_after(target.freeze_at)
    except ValueError as exc:
        return hold("freeze_before_model_boundary", str(exc))
    mapping = dict(target.horse_mapping)
    if any(_HORSE_NUMBER.fullmatch(number) is None for number in mapping):
        return hold("horse_number_invalid", "horse numbers must be two-digit strings")
    if len(mapping) < MINIMUM_FIELD_SIZE:
        return hold(
            "unsupported_field_size",
            f"PL probabilities need at least {MINIMUM_FIELD_SIZE} horses; got {len(mapping)}",
        )
    if canonical_hash(mapping) != race.get("horse_mapping_sha256"):
        return hold(
            "horse_mapping_mismatch",
            "stored horse-number mapping differs from the features' horse_mapping_sha256",
        )
    rows = [row for row in features.rows if row.get("race_id") == target.race_id]
    by_horse = {row.get("horse_id"): row for row in rows}
    if len(by_horse) != len(rows) or set(by_horse) != set(mapping.values()):
        return hold("horse_set_mismatch", "feature rows differ from the stored entrants")
    numbers = sorted(mapping)
    try:
        matrix = _matrix([by_horse[mapping[number]] for number in numbers], model.feature_names)
        scores = model.predict_scores(matrix, model.feature_names)
    except ValueError as exc:
        return hold("features_rejected", str(exc))
    marginal = model.probabilities(scores, [len(numbers)])
    orders = top3_order_probabilities(scores, temperature=model.temperature)
    after = is_after_sales_close(target, computed_at)
    win = {number: float(value) for number, value in zip(numbers, marginal.win, strict=True)}
    payload: dict[str, object] = {
        "format": PREDICTION_FORMAT,
        "format_version": PREDICTION_FORMAT_VERSION,
        "computed_at": _iso(computed_at),
        "after_sales_close": after,
        "race": {
            "race_id": target.race_id,
            "scheduled_start_at": _iso(target.scheduled_start_at),
            "freeze_at": _iso(target.freeze_at),
            "field_size": len(numbers),
            "race_subset": JRA_FLAT_GRADED_STAKES_V1,
            "grade_code": target.grade_code,
        },
        "model": {
            "manifest_sha256": model.manifest_sha256,
            "label_usable_through": _iso(model.label_usable_through),
            "temperature": model.temperature,
        },
        "features": {
            "manifest_sha256": features.manifest_sha256,
            "market_source": features.manifest.get("market_source"),
            "freshness": features.manifest.get("freshness"),
        },
        "snapshot": dict(snapshot),
        "horses": [
            {
                "horse_number": number,
                "horse_id": mapping[number],
                "score": float(scores[index]),
                "win": float(marginal.win[index]),
                "top2": float(marginal.top2[index]),
                "top3": float(marginal.top3[index]),
            }
            for index, number in enumerate(numbers)
        ],
        "combinations": _combinations(numbers, orders),
        "provenance": dict(provenance),
    }
    return RacePrediction(target.race_id, after, win, payload)


def prediction_json(payload: Mapping[str, object]) -> bytes:
    """Serialize a payload as sorted-key ASCII JSON without NaN, ending with a newline.

    Raises:
        ValueError: If the payload holds NaN, an infinity or a value JSON cannot encode.
    """
    try:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"PL race prediction is not strict JSON: {exc}") from exc
    return (text + "\n").encode("ascii")


def _matrix(rows: Sequence[Mapping[str, object]], names: Sequence[str]) -> npt.NDArray[np.float64]:
    values: list[list[float]] = []
    for row in rows:
        line: list[float] = []
        for name in names:
            if name not in row:
                raise ValueError(f"feature rows miss the model column {name!r}")
            value = row[name]
            if value is None:
                line.append(float("nan"))
            elif isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"feature column {name!r} must hold numbers or null")
            else:
                line.append(float(value))
        values.append(line)
    return np.asarray(values, dtype=np.float64).reshape(len(rows), len(names))


def _combinations(numbers: Sequence[str], orders: OrderProbabilities) -> dict[str, object]:
    indices = range(len(numbers))

    def entries(
        keys: Sequence[tuple[int, ...]], values: npt.NDArray[np.float64]
    ) -> list[dict[str, object]]:
        return [
            {"horses": [numbers[i] for i in key], "probability": float(values[key])} for key in keys
        ]

    pairs = list(combinations(indices, 2))
    triples = list(combinations(indices, 3))
    return {
        "exacta": entries(list(permutations(indices, 2)), orders.exacta),
        "quinella": entries(pairs, orders.quinella),
        "wide": entries(pairs, orders.wide),
        "trio": entries(triples, orders.trio),
        "trifecta": entries(list(permutations(indices, 3)), orders.trifecta),
    }


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
