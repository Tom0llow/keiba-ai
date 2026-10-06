"""Focused tests for the LambdaRank ranking MVP."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from math import isclose, isfinite, isnan
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

import models.train_model as train_model_module
from models.evaluate_model import evaluate_ranking
from models.predict_model import RankingModel
from models.ranking_dataset import (
    TIE_BREAK_RULE,
    FeatureRow,
    RankingDataset,
    RankingRow,
)
from models.train_model import train_lambdarank


def _training_rows() -> list[RankingRow]:
    return [
        RankingRow("race-1", "horse-1", {"ability": 4.0, "odds": None}, 1),
        RankingRow("race-1", "horse-2", {"ability": 3.0, "odds": 2.0}, 2),
        RankingRow("race-1", "horse-3", {"ability": 2.0, "odds": 4.0}, 3),
        RankingRow("race-1", "horse-4", {"ability": 1.0, "odds": 8.0}, 4),
        RankingRow("race-2", "horse-5", {"ability": 4.5, "odds": float("nan")}, 1),
        RankingRow("race-2", "horse-6", {"ability": 3.5, "odds": 2.5}, 2),
        RankingRow("race-2", "horse-7", {"ability": 2.5, "odds": 5.0}, 3),
        RankingRow("race-2", "horse-8", {"ability": 1.5}, 4),
    ]


def test_dataset_maps_labels_and_validates_race_groups() -> None:
    dataset = RankingDataset.from_rows(_training_rows(), feature_names=("ability", "odds"))

    assert dataset.labels == (3, 2, 1, 0, 3, 2, 1, 0)
    assert dataset.groups == (4, 4)
    assert dataset.feature_matrix()[0] == [4.0, None]
    missing_odds = dataset.feature_matrix()[4][1]
    assert isinstance(missing_odds, float)
    assert isnan(missing_odds)
    assert dataset.feature_matrix()[7] == [1.5, None]

    with pytest.raises(ValueError, match=r"sum\(groups\)"):
        RankingDataset.validate_groups((4, 3), 8)
    with pytest.raises(ValueError, match="at least 3"):
        RankingDataset.validate_groups((2,), 2)


def test_dataset_requires_explicit_schema_and_does_not_select_renamed_results() -> None:
    from_rows_without_schema = cast(Callable[..., object], RankingDataset.from_rows)
    with pytest.raises(TypeError):
        from_rows_without_schema(_training_rows())

    renamed_result = [
        RankingRow(
            "race-1",
            f"horse-{position}",
            {"ability": float(position), "result_rank": position},
            position,
        )
        for position in range(1, 4)
    ]
    with pytest.raises(ValueError, match=r"reserved|outside the schema"):
        RankingDataset.from_rows(renamed_result, feature_names=("ability",))


@pytest.mark.parametrize(
    "reserved_name",
    [
        "finish_position",
        "KakuteiJyuni",
        "Kakutei_Jyuni",
        "Time",
        "TimeDiff",
        "Odds",
        "Ninki",
        "final_odds",
        "popularity",
        "payouts",
    ],
)
def test_dataset_rejects_result_derived_feature_names(reserved_name: str) -> None:
    rows = [
        RankingRow("race-1", f"horse-{position}", {reserved_name: float(position)}, position)
        for position in range(1, 4)
    ]

    with pytest.raises(ValueError, match="reserved"):
        RankingDataset.from_rows(rows, feature_names=(reserved_name,))


def test_dataset_rejects_non_contiguous_races_and_invalid_positions() -> None:
    non_contiguous = [
        RankingRow("race-1", "horse-1", {"ability": 1.0}, 1),
        RankingRow("race-2", "horse-2", {"ability": 1.0}, 1),
        RankingRow("race-1", "horse-3", {"ability": 1.0}, 2),
    ]
    with pytest.raises(ValueError, match="contiguous"):
        RankingDataset.from_rows(non_contiguous, feature_names=("ability",))

    with pytest.raises(ValueError, match="positive"):
        RankingDataset.from_rows(
            [RankingRow("race-1", "horse-1", {"ability": 1.0}, 0)],
            feature_names=("ability",),
        )

    accepted = RankingDataset.from_rows(_training_rows()[:4], feature_names=("ability", "odds"))
    assert accepted.labels[-1] == 0

    invalid_position = _training_rows()[:4]
    invalid_position[-1] = RankingRow("race-1", "horse-4", {"ability": 1.0}, 999)
    with pytest.raises(ValueError, match="race group size"):
        RankingDataset.from_rows(invalid_position, feature_names=("ability", "odds"))


def test_dataset_rejects_duplicate_or_non_contiguous_finish_positions() -> None:
    invalid_rows = [
        RankingRow("race-1", f"horse-{position}", {"ability": 1.0}, finish_position)
        for position, finish_position in enumerate((1, 2, 2, 4), start=1)
    ]

    with pytest.raises(ValueError, match="unique and contiguous"):
        RankingDataset.from_rows(invalid_rows, feature_names=("ability",))

    valid_rows = [
        RankingRow("race-1", f"horse-{position}", {"ability": 1.0}, position)
        for position in range(1, 6)
    ]
    dataset = RankingDataset.from_rows(valid_rows, feature_names=("ability",))
    assert dataset.labels == (3, 2, 1, 0, 0)


def test_metrics_are_race_equal_and_top3_uses_overlap() -> None:
    dataset = RankingDataset.from_rows(_training_rows(), feature_names=("ability", "odds"))
    scores = (4.0, 3.0, 2.0, 1.0, 1.0, 4.0, 3.0, 2.0)

    metrics = evaluate_ranking(dataset, scores)

    ideal_dcg = 7.0 + 3.0 / 1.584962500721156 + 1.0 / 2.0
    second_dcg = 3.0 + 1.0 / 1.584962500721156
    expected_ndcg = (1.0 + second_dcg / ideal_dcg) / 2.0
    assert isclose(metrics.ndcg_at_3, expected_ndcg)
    assert metrics.top1_accuracy == 0.5
    assert metrics.top3_overlap == (1.0 + 2.0 / 3.0) / 2.0

    with pytest.raises(ValueError, match="real numbers"):
        evaluate_ranking(dataset, cast(Sequence[float], ("0.1",) * len(scores)))
    with pytest.raises(ValueError, match="real numbers"):
        evaluate_ranking(dataset, cast(Sequence[float], (True,) * len(scores)))


class _TieBooster:
    def __init__(self, feature_names: Sequence[str] = ("ability",)) -> None:
        self._feature_names = tuple(feature_names)
        self.params: Mapping[str, object] = {
            "objective": "lambdarank",
            "label_gain": (0, 1, 3, 7),
        }

    def predict(self, data: object) -> object:
        return [1.0 for _ in cast(Sequence[object], data)]

    def feature_name(self) -> object:
        return list(self._feature_names)

    def save_model(self, filename: str) -> object:
        raise AssertionError(f"save_model is not used in this test: {filename}")


class _SavingBooster:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.params: Mapping[str, object] = {
            "objective": "lambdarank",
            "label_gain": (0, 1, 3, 7),
        }

    def predict(self, data: object) -> object:
        return [0.0 for _ in cast(Sequence[object], data)]

    def feature_name(self) -> object:
        return ["ability"]

    def save_model(self, filename: str) -> object:
        Path(filename).write_bytes(self.payload)
        return None


def test_prediction_ties_keep_input_row_order_and_scores_only() -> None:
    model = RankingModel.from_native_booster(_TieBooster(), ("ability",))
    rows = [
        FeatureRow("race-1", "horse-2", {"ability": 1.0}),
        FeatureRow("race-1", "horse-1", {"ability": 1.0}),
        FeatureRow("race-1", "horse-3", {"ability": 1.0}),
    ]

    predictions = model.predict(rows)

    assert model.tie_break_rule == TIE_BREAK_RULE
    assert [(prediction.horse_id, prediction.rank) for prediction in predictions] == [
        ("horse-2", 1),
        ("horse-1", 2),
        ("horse-3", 3),
    ]
    assert all(isfinite(prediction.score) for prediction in predictions)
    assert not hasattr(predictions[0], "probability")


def test_prediction_rejects_race_with_fewer_than_three_rows() -> None:
    model = RankingModel.from_native_booster(_TieBooster(), ("ability",))
    rows = [
        FeatureRow("race-1", "horse-1", {"ability": 1.0}),
        FeatureRow("race-1", "horse-2", {"ability": 1.0}),
    ]

    with pytest.raises(ValueError, match="at least 3"):
        model.predict(rows)


def test_model_save_rejects_existing_artifact_without_replacing_it(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    first_model = RankingModel.from_native_booster(_SavingBooster(b"native-model-1"), ("ability",))
    second_model = RankingModel.from_native_booster(_SavingBooster(b"native-model-2"), ("ability",))

    first_model.save(model_path)
    first_native = model_path.read_bytes()
    metadata_path = model_path.with_name("ranking.model.metadata.json")
    first_metadata = metadata_path.read_bytes()

    with pytest.raises(FileExistsError):
        second_model.save(model_path)
    assert model_path.read_bytes() == first_native
    assert metadata_path.read_bytes() == first_metadata

    model_path.unlink()
    with pytest.raises(FileExistsError):
        second_model.save(model_path)
    assert metadata_path.read_bytes() == first_metadata


def test_model_save_recovers_interrupted_publication(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    model_path.write_bytes(b"incomplete-native")
    model_path.with_name("ranking.model.metadata.json").write_text(
        "incomplete-metadata", encoding="utf-8"
    )
    model_path.with_name("ranking.model.publishing").write_text("publishing\n", encoding="ascii")

    RankingModel.from_native_booster(_SavingBooster(b"native-model"), ("ability",)).save(model_path)

    assert model_path.read_bytes() == b"native-model"
    assert not model_path.with_name("ranking.model.publishing").exists()


def test_model_load_rejects_metadata_change_with_unchanged_native(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    RankingModel.from_native_booster(_SavingBooster(b"native-model"), ("ability",)).save(model_path)
    metadata_path = model_path.with_name("ranking.model.metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["feature_names"] = ["renamed_ability"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata does not match its digest"):
        RankingModel.load(model_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("objective", "regression", "objective"),
        ("tie_break_rule", "other_rule", "tie_break_rule"),
    ],
)
def test_model_load_rejects_metadata_contract_override(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    model_path = tmp_path / "ranking.model"
    RankingModel.from_native_booster(_SavingBooster(b"native-model"), ("ability",)).save(model_path)
    metadata_path = model_path.with_name("ranking.model.metadata.json")
    metadata = cast(dict[str, object], json.loads(metadata_path.read_text(encoding="utf-8")))
    metadata[field] = value
    payload = {key: item for key, item in metadata.items() if key != "metadata_sha256"}
    metadata["metadata_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        RankingModel.load(model_path)


def test_training_forces_fixed_label_gain(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_parameters: dict[str, object] = {}

    class _CapturingRanker:
        booster_ = _TieBooster(("ability", "odds"))

        def __init__(self, **parameters: object) -> None:
            captured_parameters.update(parameters)

        def fit(
            self,
            features: object,
            labels: object,
            *,
            group: Sequence[int],
            feature_name: Sequence[str],
        ) -> object:
            return None

    lightgbm_module = ModuleType("lightgbm")
    lightgbm_module.__dict__["LGBMRanker"] = _CapturingRanker
    monkeypatch.setattr(train_model_module, "_load_lightgbm", lambda: lightgbm_module)

    dataset = RankingDataset.from_rows(_training_rows()[:4], feature_names=("ability", "odds"))
    train_lambdarank(
        dataset,
        parameters={"label_gain": [99, 100], "objective": "regression"},
    )

    assert captured_parameters["label_gain"] == [0, 1, 3, 7]
    assert captured_parameters["objective"] == "lambdarank"


@pytest.mark.integration
def test_lightgbm_train_predict_and_native_save_load(tmp_path: Path) -> None:
    dataset = RankingDataset.from_rows(_training_rows(), feature_names=("ability", "odds"))
    model = train_lambdarank(
        dataset,
        parameters={"n_estimators": 10, "min_child_samples": 1, "num_leaves": 4},
    )
    feature_rows = [FeatureRow(row.race_id, row.horse_id, row.features) for row in dataset.rows]

    predictions = model.predict(feature_rows)
    model_path = tmp_path / "ranking.model"
    model.save(model_path)
    loaded_predictions = RankingModel.load(model_path).predict(feature_rows)

    assert model.objective == "lambdarank"
    assert model.tie_break_rule == TIE_BREAK_RULE
    assert [prediction.rank for prediction in predictions[:4]] == [1, 2, 3, 4]
    assert all(isfinite(prediction.score) for prediction in predictions)
    assert loaded_predictions == predictions
    assert model_path.is_file()
    assert model_path.with_name("ranking.model.metadata.json").is_file()
    assert model_path.with_name("ranking.model.ready").is_file()
