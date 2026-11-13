"""Assemble one graded race's PL prediction from published features (ADR-039)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from make_features.real_market import canonical_hash
from models.artifacts.pl_model import PLModel, read_pl_model, write_pl_model
from models.experiments.pl_evaluation import PLVariant
from models.experiments.pl_prediction import (
    PredictionHold,
    RaceFeatures,
    RacePrediction,
    RaceTarget,
    build_race_prediction,
    prediction_json,
)
from models.experiments.pl_training import PLTrainingSettings, pl_model_record, train_final_pl
from models.probability.plackett_luce import top3_order_probabilities
from tests.pl_fixtures import FEATURE_NAMES, pl_parameters, synthetic_race_arrays

JST = timezone(timedelta(hours=9))
START = datetime(2025, 12, 28, 15, 25, tzinfo=JST)
RACE_ID = "2025122806050811"
SNAPSHOT = {"snapshot_id": "s" * 32, "tables": {"NL_RA_RACE": "1" * 64, "NL_SE_RACE_UMA": "2" * 64}}
PROVENANCE = {"source_sha256": "p" * 64}
Row = dict[str, object]


def _columns() -> list[dict[str, str]]:
    return [
        {"name": name, "group": "g", "column": name, "meaning": "m", "unit": "u"}
        for name in FEATURE_NAMES
    ]


def _source() -> dict[str, object]:
    return {
        "manifest_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "target_period": {"start": "2020-01-01", "end": "2022-12-31"},
        "label_usable_through": datetime(2024, 1, 10, 15, tzinfo=UTC).isoformat(),
        "provenance_source_sha256": "c" * 64,
        "columns": _columns(),
    }


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> PLModel:
    arrays = synthetic_race_arrays((2020, 2021, 2022, 2023), races_per_year=60, seed=11)
    settings = PLTrainingSettings(
        train_start_year=2020,
        valid_year=2022,
        variant=PLVariant("all_columns"),
        lightgbm=pl_parameters(),
        num_boost_round=80,
        early_stopping_rounds=10,
        temperature_bounds=(0.05, 20.0),
    )
    final = train_final_pl(arrays, settings)
    record = pl_model_record(final, source_datamart=_source(), provenance={}, config={})
    directory = Path(tmp_path_factory.mktemp("pl")) / "model"
    directory.mkdir()
    digest = write_pl_model(directory, record, final.fit.booster)
    return read_pl_model(directory, expected_manifest_sha256=digest)


def _target(size: int = 18) -> RaceTarget:
    # Insertion order is not number order; the payload sorts by horse number.
    mapping = {f"{n:02d}": f"20210{n:05d}" for n in reversed(range(1, size + 1))}
    return RaceTarget(RACE_ID, START, START - timedelta(minutes=5), mapping, "A")


def _features(target: RaceTarget) -> RaceFeatures:
    manifest: dict[str, object] = {
        "source_datamart": {k: v for k, v in _source().items() if k != "columns"},
        "columns": _columns(),
        "market_source": {"kind": "race_day_prediction_fetch", "race_id": RACE_ID},
        "freshness": {"history_usable_through": "2025-12-28T00:00:00+09:00"},
    }
    rng = np.random.default_rng(3)
    rows: list[Row] = [
        {
            "race_id": RACE_ID,
            "horse_id": horse,
            "signal": float(rng.normal()),
            "noise": float(rng.normal()),
            "market_feature": None if number == "02" else float(rng.normal()),
        }
        for number, horse in sorted(target.horse_mapping.items(), key=lambda item: item[1])
    ]
    race: Row = {
        "race_id": RACE_ID,
        "scheduled_start_at": target.scheduled_start_at.astimezone(UTC),
        "freeze_at": target.freeze_at.astimezone(UTC),
        "field_size": len(target.horse_mapping),
        "horse_mapping_sha256": canonical_hash(dict(target.horse_mapping)),
    }
    return RaceFeatures("f" * 64, manifest, rows, [race])


def _predict(
    model: PLModel, target: RaceTarget, features: RaceFeatures, at: datetime | None = None
) -> RacePrediction | PredictionHold:
    return build_race_prediction(
        model,
        target,
        features,
        computed_at=START - timedelta(minutes=4) if at is None else at,
        snapshot=SNAPSHOT,
        provenance=PROVENANCE,
    )


def test_a_prediction_holds_every_horse_and_combination_in_number_order(model: PLModel) -> None:
    target = _target()
    features = _features(target)
    result = _predict(model, target, features)
    assert isinstance(result, RacePrediction)
    payload = result.payload
    assert set(payload) == {
        "format",
        "format_version",
        "computed_at",
        "after_sales_close",
        "race",
        "model",
        "features",
        "snapshot",
        "horses",
        "combinations",
        "provenance",
    }
    assert (payload["format"], payload["format_version"]) == ("pl_race_prediction", 1)
    assert payload["computed_at"] == "2025-12-28T06:21:00+00:00"
    assert payload["after_sales_close"] is False
    assert payload["race"] == {
        "race_id": RACE_ID,
        "scheduled_start_at": "2025-12-28T06:25:00+00:00",
        "freeze_at": "2025-12-28T06:20:00+00:00",
        "field_size": 18,
        "race_subset": "jra_flat_graded_stakes_v1",
        "grade_code": "A",
    }
    assert payload["model"] == {
        "manifest_sha256": model.manifest_sha256,
        "label_usable_through": model.label_usable_through.astimezone(UTC).isoformat(),
        "temperature": model.temperature,
    }
    assert payload["features"] == {
        "manifest_sha256": "f" * 64,
        "market_source": features.manifest["market_source"],
        "freshness": features.manifest["freshness"],
    }
    assert (payload["snapshot"], payload["provenance"]) == (SNAPSHOT, PROVENANCE)
    horses = payload["horses"]
    assert isinstance(horses, list)
    numbers = [horse["horse_number"] for horse in horses]
    assert numbers == [f"{n:02d}" for n in range(1, 19)]
    assert [horse["horse_id"] for horse in horses] == [
        target.horse_mapping[number] for number in numbers
    ]
    # The probabilities equal the model called directly on rows in horse-number order.
    by_horse = {row["horse_id"]: row for row in features.rows}
    matrix = [
        [
            np.nan if (value := by_horse[horse["horse_id"]][name]) is None else value
            for name in FEATURE_NAMES
        ]
        for horse in horses
    ]
    scores = model.predict_scores(np.asarray(matrix, dtype=np.float64), FEATURE_NAMES)
    marginal = model.probabilities(scores, [18])
    for index, horse in enumerate(horses):
        assert set(horse) == {"horse_number", "horse_id", "score", "win", "top2", "top3"}
        assert horse["score"] == scores[index]
        assert (horse["win"], horse["top2"], horse["top3"]) == (
            marginal.win[index],
            marginal.top2[index],
            marginal.top3[index],
        )
    assert result.win == {horse["horse_number"]: horse["win"] for horse in horses}
    orders = top3_order_probabilities(scores, temperature=model.temperature)
    combos = payload["combinations"]
    assert isinstance(combos, dict)
    counts = {name: len(entries) for name, entries in combos.items()}
    assert counts == {"exacta": 306, "quinella": 153, "wide": 153, "trio": 816, "trifecta": 4896}
    for name, ordered in (("exacta", True), ("quinella", False), ("wide", False)):
        keys = [tuple(entry["horses"]) for entry in combos[name]]
        assert keys == sorted(keys)
        assert all(ordered or list(key) == sorted(key) for key in keys)
        assert len(set(keys)) == len(keys)
    position = {number: index for index, number in enumerate(numbers)}
    for name in ("exacta", "quinella", "wide", "trio", "trifecta"):
        values = getattr(orders, name)
        for entry in combos[name]:
            key = tuple(position[number] for number in entry["horses"])
            assert entry["probability"] == values[key], (name, key)
    trifecta = combos["trifecta"][0]
    assert trifecta == {"horses": ["01", "02", "03"], "probability": orders.trifecta[0, 1, 2]}
    assert [tuple(entry["horses"]) for entry in combos["trio"]] == sorted(
        tuple(entry["horses"]) for entry in combos["trio"]
    )
    assert sum(entry["probability"] for entry in combos["trifecta"]) == pytest.approx(1.0)
    assert sum(entry["probability"] for entry in combos["wide"]) == pytest.approx(3.0)


def test_the_json_is_strict_sorted_and_reproducible(model: PLModel) -> None:
    target = _target()
    first = _predict(model, target, _features(target))
    second = _predict(model, target, _features(target))
    assert isinstance(first, RacePrediction)
    assert isinstance(second, RacePrediction)
    data = prediction_json(first.payload)
    assert data == prediction_json(second.payload)
    assert data.endswith(b"}\n")
    assert b"NaN" not in data
    assert b"Infinity" not in data
    data.decode("ascii")
    assert json.loads(data) == json.loads(json.dumps(first.payload))
    with pytest.raises(ValueError, match="not strict JSON"):
        prediction_json({"value": float("nan")})


@pytest.mark.parametrize(
    ("offset", "after"),
    [
        (timedelta(minutes=-2, seconds=-1), False),
        (timedelta(minutes=-2), False),
        (timedelta(), True),
    ],
)
def test_after_sales_close_is_strictly_after_two_minutes_before_the_start(
    model: PLModel, offset: timedelta, after: bool
) -> None:
    target = _target(4)
    result = _predict(model, target, _features(target), START + offset)
    assert isinstance(result, RacePrediction)
    assert result.after_sales_close is after
    assert result.payload["after_sales_close"] is after


def test_computed_at_must_be_timezone_aware(model: PLModel) -> None:
    target = _target(4)
    with pytest.raises(ValueError, match="timezone-aware"):
        _predict(model, target, _features(target), datetime(2025, 12, 28, 15, 21))


Edit = Callable[[PLModel, RaceTarget, RaceFeatures], tuple[RaceTarget, RaceFeatures]]


def _other_binding(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    manifest = dict(features.manifest)
    manifest["source_datamart"] = {**_source(), "manifest_sha256": "e" * 64}
    return target, replace(features, manifest=manifest)


def _no_race(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    return target, replace(features, races=[])


def _moved_start(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    later = target.scheduled_start_at + timedelta(minutes=10)
    return replace(target, scheduled_start_at=later, freeze_at=later - timedelta(minutes=5)), (
        features
    )


def _at_boundary(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    freeze = model.label_usable_through
    moved = replace(target, scheduled_start_at=freeze + timedelta(minutes=5), freeze_at=freeze)
    return moved, _features(moved)


def _bad_number(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    mapping = {
        ("1" if number == "01" else number): horse for number, horse in target.horse_mapping.items()
    }
    moved = replace(target, horse_mapping=mapping)
    return moved, _features(moved)


def _two_horses(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    small = _target(2)
    return small, _features(small)


def _swapped_numbers(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    mapping = dict(target.horse_mapping)
    mapping["01"], mapping["02"] = mapping["02"], mapping["01"]
    return replace(target, horse_mapping=mapping), features


def _other_horse(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    rows = [dict(row) for row in features.rows]
    rows[0]["horse_id"] = "2099999999"
    return target, replace(features, rows=rows)


def _repeated_row(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    return target, replace(features, rows=[*features.rows, features.rows[0]])


def _value(name: str, value: object) -> Edit:
    def edit(
        model: PLModel, target: RaceTarget, features: RaceFeatures
    ) -> tuple[RaceTarget, RaceFeatures]:
        rows = [dict(row) for row in features.rows]
        rows[1][name] = value
        return target, replace(features, rows=rows)

    return edit


def _missing_column(
    model: PLModel, target: RaceTarget, features: RaceFeatures
) -> tuple[RaceTarget, RaceFeatures]:
    rows = [{k: v for k, v in row.items() if k != "noise"} for row in features.rows]
    return target, replace(features, rows=rows)


@pytest.mark.parametrize(
    ("edit", "reason", "detail"),
    [
        (_other_binding, "model_features_mismatch", "manifest_sha256"),
        (_no_race, "features_missing_race", "no single row"),
        (_moved_start, "schedule_mismatch", "schedule"),
        (_at_boundary, "freeze_before_model_boundary", "label boundary"),
        (_bad_number, "horse_number_invalid", "two-digit"),
        (_two_horses, "unsupported_field_size", "at least 3 horses; got 2"),
        (_swapped_numbers, "horse_mapping_mismatch", "horse_mapping_sha256"),
        (_other_horse, "horse_set_mismatch", "entrants"),
        (_repeated_row, "horse_set_mismatch", "entrants"),
        (_value("signal", None), "features_rejected", "training never missed: ['signal']"),
        (_value("market_feature", float("inf")), "features_rejected", "infinite"),
        (_value("noise", "1.5"), "features_rejected", "numbers or null"),
        (_missing_column, "features_rejected", "'noise'"),
    ],
)
def test_each_failed_check_holds_the_race_with_its_reason(
    model: PLModel, edit: Edit, reason: str, detail: str
) -> None:
    target, features = edit(model, _target(), _features(_target()))
    result = _predict(model, target, features)
    assert isinstance(result, PredictionHold)
    assert (result.race_id, result.reason) == (RACE_ID, reason)
    assert detail in result.detail
