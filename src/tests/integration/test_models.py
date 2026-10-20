"""Focused tests for the LambdaRank ranking MVP."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import cast

import pytest

from models.artifacts.native_model import NativeModelArtifact
from models.dataset.dataset import RankingDataset
from models.dataset.rows import FeatureRow, RankingRow
from models.dataset.schema import FeatureSchema
from models.predict_model import RankingModel
from models.ranking.rules import TIE_BREAK_RULE
from models.training.train import train_lambdarank


def _training_rows() -> list[RankingRow]:
    return [
        RankingRow("race-1", "horse-1", {"ability": 4.0, "historical_odds": None}, 1),
        RankingRow("race-1", "horse-2", {"ability": 3.0, "historical_odds": 2.0}, 2),
        RankingRow("race-1", "horse-3", {"ability": 2.0, "historical_odds": 4.0}, 3),
        RankingRow("race-1", "horse-4", {"ability": 1.0, "historical_odds": 8.0}, 4),
        RankingRow("race-2", "horse-5", {"ability": 4.5, "historical_odds": float("nan")}, 1),
        RankingRow("race-2", "horse-6", {"ability": 3.5, "historical_odds": 2.5}, 2),
        RankingRow("race-2", "horse-7", {"ability": 2.5, "historical_odds": 5.0}, 3),
        RankingRow("race-2", "horse-8", {"ability": 1.5}, 4),
    ]


def _schema(feature_names: Sequence[str], schema_id: str = "test-v1") -> FeatureSchema:
    return FeatureSchema.from_names(feature_names, schema_id=schema_id)


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


def test_model_save_rejects_existing_artifact_without_replacing_it(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    first_model = RankingModel.from_native_booster(
        _SavingBooster(b"native-model-1"), ("ability",), _schema(("ability",))
    )
    second_model = RankingModel.from_native_booster(
        _SavingBooster(b"native-model-2"), ("ability",), _schema(("ability",))
    )

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

    RankingModel.from_native_booster(
        _SavingBooster(b"native-model"), ("ability",), _schema(("ability",))
    ).save(model_path)

    assert model_path.read_bytes() == b"native-model"
    assert not model_path.with_name("ranking.model.publishing").exists()


def test_model_save_is_idempotent_after_ready_publication(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    model = RankingModel.from_native_booster(
        _SavingBooster(b"native-model"), ("ability",), _schema(("ability",))
    )
    model.save(model_path)
    model_path.with_name("ranking.model.publishing").write_text("publishing\n", encoding="ascii")

    model.save(model_path)

    assert model_path.with_name("ranking.model.ready").is_file()
    assert not model_path.with_name("ranking.model.publishing").exists()


def test_model_load_rejects_metadata_change_with_unchanged_native(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    RankingModel.from_native_booster(
        _SavingBooster(b"native-model"), ("ability",), _schema(("ability",))
    ).save(model_path)
    metadata_path = model_path.with_name("ranking.model.metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["feature_names"] = ["renamed_ability"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata does not match its digest"):
        RankingModel.load(model_path)


def test_native_artifact_rejects_mismatched_schema_before_publication(tmp_path: Path) -> None:
    artifact = NativeModelArtifact(tmp_path / "ranking.model")

    with pytest.raises(ValueError, match="feature names do not match"):
        artifact.save(_TieBooster(("historical_odds",)), _schema(("ability",)))

    assert not tuple(tmp_path.iterdir())


def test_native_artifact_rejects_unfinished_or_changed_native_files(tmp_path: Path) -> None:
    model_path = tmp_path / "ranking.model"
    artifact = NativeModelArtifact(model_path)
    artifact.save(_SavingBooster(b"native-model"), _schema(("ability",)))
    ready_path = model_path.with_name("ranking.model.ready")
    ready_path.unlink()

    with pytest.raises(FileNotFoundError):
        artifact.load()

    ready_path.write_text("ready\n", encoding="ascii")
    model_path.write_bytes(b"changed-native-model")
    with pytest.raises(ValueError, match="native model does not match metadata"):
        artifact.load()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("objective", "regression", "objective"),
        ("label_gain", [0, 1, 2, 7], "label_gain"),
        ("tie_break_rule", "other_rule", "tie_break_rule"),
    ],
)
def test_model_load_rejects_metadata_contract_override(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    model_path = tmp_path / "ranking.model"
    RankingModel.from_native_booster(
        _SavingBooster(b"native-model"), ("ability",), _schema(("ability",))
    ).save(model_path)
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


@pytest.mark.integration
def test_lightgbm_train_predict_and_native_save_load(tmp_path: Path) -> None:
    schema = _schema(("ability", "historical_odds"), schema_id="training-v1")
    dataset = RankingDataset.from_rows(
        _training_rows(),
        feature_names=("ability", "historical_odds"),
        feature_schema=schema,
    )
    model = train_lambdarank(
        dataset,
        parameters={"n_estimators": 10, "min_child_samples": 1, "num_leaves": 4},
    )
    feature_rows = [FeatureRow(row.race_id, row.horse_id, row.features) for row in dataset.rows]

    predictions = model.predict(feature_rows)
    model_path = tmp_path / "ranking.model"
    model.save(model_path)
    loaded_model = RankingModel.load(model_path)
    loaded_predictions = loaded_model.predict(feature_rows, feature_schema=schema)
    contents = NativeModelArtifact(model_path).load()
    copied_path = tmp_path / "copied.model"
    NativeModelArtifact(copied_path).save(contents.booster, contents.feature_schema)

    assert model.objective == "lambdarank"
    assert model.tie_break_rule == TIE_BREAK_RULE
    assert loaded_model.feature_schema == schema
    assert [prediction.rank for prediction in predictions[:4]] == [1, 2, 3, 4]
    assert all(isfinite(prediction.score) for prediction in predictions)
    assert loaded_predictions == predictions
    assert contents.feature_schema == schema
    assert RankingModel.load(copied_path).predict(feature_rows) == predictions
    assert model_path.is_file()
    metadata_path = model_path.with_name("ranking.model.metadata.json")
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["label_gain"] == [0, 1, 3, 7]
    assert model_path.with_name("ranking.model.ready").is_file()
