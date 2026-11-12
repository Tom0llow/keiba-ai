"""Write, read and use the final top-three PL model artifact (ADR-038)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from typing import cast
from unittest.mock import patch

import numpy as np
import pytest

from models.artifacts.pl_model import (
    PLModel,
    PLModelRecord,
    read_pl_model,
    write_pl_model,
)
from models.backends.lightgbm import load_pl_booster, split_missing_types
from models.dataset.race_arrays import RaceArrays
from models.experiments.pl_evaluation import PLVariant
from models.experiments.pl_training import (
    FinalPLFit,
    PLTrainingSettings,
    pl_model_record,
    train_final_pl,
)
from models.probability.plackett_luce import RaceLayout, top3_marginal_probabilities
from tests.pl_fixtures import FEATURE_NAMES, pl_parameters, synthetic_race_arrays

Manifest = dict[str, object]


def _columns() -> list[dict[str, str]]:
    return [
        {"name": name, "group": "g", "column": name, "meaning": "m", "unit": "u"}
        for name in FEATURE_NAMES
    ]


def _source(through: datetime = datetime(2024, 1, 10, 15, tzinfo=UTC)) -> dict[str, object]:
    return {
        "manifest_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "target_period": {"start": "2020-01-01", "end": "2022-12-31"},
        "label_usable_through": through.isoformat(),
        "provenance_source_sha256": "c" * 64,
        "columns": _columns(),
    }


def _fit() -> tuple[RaceArrays, FinalPLFit]:
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
    return arrays, train_final_pl(arrays, settings)


def _write(tmp_path: Path, final: FinalPLFit) -> tuple[Path, str]:
    directory = tmp_path / "model"
    directory.mkdir()
    return directory, write_pl_model(directory, _record(final), final.fit.booster)


def _record(final: FinalPLFit) -> PLModelRecord:
    return pl_model_record(
        final, source_datamart=_source(), provenance={"source_sha256": "d" * 64}, config={}
    )


@pytest.fixture(scope="module")
def trained() -> tuple[RaceArrays, FinalPLFit]:
    return _fit()


def test_a_read_model_scores_and_probabilities_equal_the_trained_booster(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    arrays, final = trained
    directory, digest = _write(tmp_path, final)

    model = read_pl_model(directory, expected_manifest_sha256=digest)

    for year in (2022, 2023):
        races = arrays.subset([i for i, value in enumerate(arrays.years) if value == year])
        features = races.columns(final.feature_names)
        expected = final.fit.predict_scores(features)
        # Label-free input: only the matrix and its column names.
        scores = model.predict_scores(features.features, final.feature_names)
        np.testing.assert_array_equal(scores, expected)
        probabilities = model.probabilities(scores, races.group_sizes.tolist())
        reference = top3_marginal_probabilities(
            expected,
            RaceLayout.from_group_sizes(races.group_sizes.tolist()),
            temperature=final.temperature.temperature,
        )
        for name in ("win", "top2", "top3"):
            np.testing.assert_array_equal(getattr(probabilities, name), getattr(reference, name))
    assert model.manifest_sha256 == digest
    assert model.temperature == final.temperature.temperature
    assert model.label_usable_through == final.audit.label_usable_through


def test_the_manifest_records_the_binding_boundaries_and_versions(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    _, final = trained
    directory, digest = _write(tmp_path, final)
    raw = (directory / "manifest.json").read_bytes()
    manifest = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == digest
    assert raw.endswith(b"\n")
    assert manifest["format"] == "pl_top3_model"
    assert manifest["source_datamart"] == _source()
    model = manifest["model"]
    assert model["objective"] == "top3_plackett_luce"
    assert model["best_iteration"] == final.fit.best_iteration
    assert model["lightgbm_version"] == version("lightgbm")
    assert model["numpy_version"] == np.__version__
    assert manifest["provenance"] == {"source_sha256": "d" * 64}
    assert manifest["config"] == {}
    assert manifest["features"]["nullable_in_training"] == [False, False, True]
    training = manifest["training"]
    assert training["label_usable_through"] == final.audit.label_usable_through.isoformat()
    assert training["label_usable_through"].endswith("+00:00")
    assert (training["train_start_year"], training["valid_year"]) == (2020, 2022)
    assert "datamart_path" not in json.dumps(manifest)
    assert sorted(path.name for path in directory.iterdir()) == ["manifest.json", "model.txt"]


def _rewrite(directory: Path, change: Callable[[Manifest], None]) -> str:
    path = directory / "manifest.json"
    manifest = json.loads(path.read_bytes())
    change(manifest)
    payload = (json.dumps(manifest, sort_keys=True) + "\n").encode("ascii")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _set(section: str, key: str, value: object) -> Callable[[Manifest], None]:
    def change(manifest: Manifest) -> None:
        cast(dict[str, object], manifest[section])[key] = value

    return change


def _top(key: str, value: object) -> Callable[[Manifest], None]:
    def change(manifest: Manifest) -> None:
        manifest[key] = value

    return change


def _drop(section: str, key: str) -> Callable[[Manifest], None]:
    def change(manifest: Manifest) -> None:
        del cast(dict[str, object], manifest[section])[key]

    return change


def _one_fewer_iteration(manifest: Manifest) -> None:
    # Inside 1..num_boost_round, so only the native iteration count can reject it.
    model = cast(dict[str, int], manifest["model"])
    assert model["best_iteration"] > 1
    model["best_iteration"] -= 1


def _reorder(manifest: Manifest) -> None:
    features = cast(dict[str, list[str]], manifest["features"])
    features["columns"] = list(reversed(features["columns"]))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_top("format_version", 2), "format"),
        (_top("extra", 1), "keys"),
        (_drop("model", "numpy_version"), "keys"),
        (_set("model", "file", "other.txt"), "file or objective"),
        (_set("model", "objective", "lambdarank"), "file or objective"),
        (_set("model", "lightgbm", {**pl_parameters(), "objective": "x"}), "reserved"),
        (_set("model", "best_iteration", 0), "positive integer"),
        (_set("model", "best_iteration", 10_000), "best_iteration must lie"),
        (_one_fewer_iteration, "iterations differ"),
        (_set("model", "sha256", "0" * 64), "native model SHA-256"),
        (_set("temperature", "value", 0.0), "temperature"),
        (_set("temperature", "value", 25.0), "within its bounds"),
        (_set("training", "label_usable_through", "2024-01-01T00:00:00"), "UTC clock"),
        (_set("training", "label_usable_through", "2024-01-01T09:00:00+09:00"), "UTC clock"),
        (_set("training", "label_usable_through", "2030-01-01T00:00:00+00:00"), "differs"),
        (_set("features", "excluded_columns", ["unknown"]), "columns differ"),
        (_set("features", "nullable_in_training", [True]), "columns differ"),
        (_reorder, "columns differ"),
        (_set("source_datamart", "manifest_sha256", "short"), "hex digits"),
        (
            _set("source_datamart", "label_usable_through", "2020-01-01T00:00:00+00:00"),
            "later than its datamart",
        ),
    ],
)
def test_the_reader_rejects_any_inconsistent_manifest(
    tmp_path: Path,
    trained: tuple[RaceArrays, FinalPLFit],
    change: Callable[[Manifest], None],
    message: str,
) -> None:
    _, final = trained
    directory, _ = _write(tmp_path, final)
    digest = _rewrite(directory, change)

    with pytest.raises(ValueError, match=message):
        read_pl_model(directory, expected_manifest_sha256=digest)


def test_the_reader_rejects_identity_files_model_bytes_and_lightgbm_version(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    _, final = trained
    directory, digest = _write(tmp_path, final)

    with pytest.raises(ValueError, match="64 lowercase hex"):
        read_pl_model(directory, expected_manifest_sha256="ABC")
    with pytest.raises(ValueError, match="expected identity"):
        read_pl_model(directory, expected_manifest_sha256="0" * 64)
    with (
        patch("models.artifacts.pl_model.version", return_value="0.0.1"),
        pytest.raises(ValueError, match="LightGBM"),
    ):
        read_pl_model(directory, expected_manifest_sha256=digest)
    (directory / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=r"exactly model\.txt"):
        read_pl_model(directory, expected_manifest_sha256=digest)
    (directory / "extra.txt").unlink()
    model_bytes = (directory / "model.txt").read_bytes()
    (directory / "model.txt").unlink()
    with pytest.raises(ValueError, match=r"exactly model\.txt"):
        read_pl_model(directory, expected_manifest_sha256=digest)
    (directory / "model.txt").write_bytes(model_bytes)
    read_pl_model(directory, expected_manifest_sha256=digest)
    (directory / "model.txt").write_bytes((directory / "model.txt").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="native model SHA-256"):
        read_pl_model(directory, expected_manifest_sha256=digest)


def _rare_missing_fit() -> FinalPLFit:
    # A tiny bin sample misses the few market NaNs, as LightGBM's 200,000-row sample
    # can on the full datamart, so the market splits get no missing-value branch.
    arrays = synthetic_race_arrays((2020, 2021, 2022), races_per_year=40, seed=13)
    return train_final_pl(
        arrays,
        PLTrainingSettings(
            train_start_year=2020,
            valid_year=2022,
            variant=PLVariant("all_columns"),
            lightgbm={**pl_parameters(), "bin_construct_sample_cnt": 20},
            num_boost_round=30,
            early_stopping_rounds=5,
            temperature_bounds=(0.05, 20.0),
        ),
    )


def test_columns_missing_in_training_must_split_with_a_missing_value_branch(
    tmp_path: Path,
) -> None:
    final = _rare_missing_fit()
    assert final.nullable_in_training[2]
    kinds = split_missing_types(
        final.fit.booster.dump_model(num_iteration=final.fit.best_iteration),
        len(final.feature_names),
    )
    assert "None" in kinds[2]
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(ValueError, match=r"without a missing-value branch: \['market_feature'\]"):
        write_pl_model(staging, _record(final), final.fit.booster)
    assert not any(staging.iterdir())

    directory = tmp_path / "model"
    directory.mkdir()
    with patch("models.artifacts.pl_model._require_missing_branches"):
        digest = write_pl_model(directory, _record(final), final.fit.booster)
    with pytest.raises(ValueError, match="without a missing-value branch"):
        read_pl_model(directory, expected_manifest_sha256=digest)


@pytest.mark.parametrize(
    ("dump", "message"),
    [
        ({}, "tree_info"),
        ({"tree_info": [{"tree_structure": None}]}, "invalid tree node"),
        (
            {"tree_info": [{"tree_structure": {"split_index": 0, "split_feature": 5}}]},
            "invalid split",
        ),
        (
            {
                "tree_info": [
                    {
                        "tree_structure": {
                            "split_index": 0,
                            "split_feature": 0,
                            "missing_type": "NaN",
                            "decision_type": "==",
                        }
                    }
                ]
            },
            "numerical",
        ),
    ],
)
def test_split_missing_types_rejects_malformed_dumps(dump: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        split_missing_types(dump, 3)


def test_the_native_loader_rejects_feature_names_other_than_the_manifest(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    _, final = trained
    directory, _ = _write(tmp_path, final)
    text = (directory / "model.txt").read_text(encoding="utf-8")

    assert load_pl_booster(text, final.feature_names).current_iteration() == (
        final.fit.best_iteration
    )
    with pytest.raises(ValueError, match="feature names differ from its manifest"):
        load_pl_booster(text, tuple(reversed(final.feature_names)))


def test_a_missing_market_value_is_rejected_when_training_never_missed_it(
    tmp_path: Path,
) -> None:
    # The operational datamart has no missing market odds, unlike the default fixture.
    arrays = synthetic_race_arrays(
        (2020, 2021, 2022), races_per_year=40, seed=13, incomplete_market_race=False
    )
    final = train_final_pl(
        arrays,
        PLTrainingSettings(
            train_start_year=2020,
            valid_year=2022,
            variant=PLVariant("all_columns"),
            lightgbm=pl_parameters(),
            num_boost_round=30,
            early_stopping_rounds=5,
            temperature_bounds=(0.05, 20.0),
        ),
    )
    assert final.nullable_in_training == (False, False, False)
    model = _model(tmp_path, final)
    matrix = arrays.columns(final.feature_names).features[:6].copy()
    matrix[2, 2] = np.nan

    with pytest.raises(ValueError, match="market_feature"):
        model.predict_scores(matrix, final.feature_names)


def _model(tmp_path: Path, final: FinalPLFit) -> PLModel:
    directory, digest = _write(tmp_path, final)
    return read_pl_model(directory, expected_manifest_sha256=digest)


def test_scores_reject_other_columns_and_missing_values_training_never_had(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    arrays, final = trained
    model = _model(tmp_path, final)
    matrix = arrays.columns(final.feature_names).features[:8].copy()

    with pytest.raises(ValueError, match="order differ"):
        model.predict_scores(matrix, tuple(reversed(final.feature_names)))
    with pytest.raises(ValueError, match="two-dimensional"):
        model.predict_scores(matrix[:, :2], final.feature_names)
    signal_missing = matrix.copy()
    signal_missing[0, 0] = np.nan
    with pytest.raises(ValueError, match="signal"):
        model.predict_scores(signal_missing, final.feature_names)
    # The market feature was missing in training, so LightGBM learned its missing branch.
    market_missing = matrix.copy()
    market_missing[0, 2] = np.nan
    assert np.all(np.isfinite(model.predict_scores(market_missing, final.feature_names)))
    with pytest.raises(ValueError, match="group sizes"):
        model.probabilities(np.zeros(8), [3, 3])


@pytest.mark.parametrize(
    ("column", "value"),
    [(0, np.inf), (0, -np.inf), (2, np.inf), (2, -np.inf)],
)
def test_scores_reject_infinite_values_by_column(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit], column: int, value: float
) -> None:
    # Training rejects infinite values; the market feature accepts NaN but not infinity.
    arrays, final = trained
    model = _model(tmp_path, final)
    matrix = arrays.columns(final.feature_names).features[:8].copy()
    matrix[1, column] = value

    with pytest.raises(ValueError, match="infinite values") as raised:
        model.predict_scores(matrix, final.feature_names)
    assert str(raised.value).endswith(f"{[final.feature_names[column]]!r}")


def test_scores_name_every_column_with_infinite_values(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    arrays, final = trained
    model = _model(tmp_path, final)
    matrix = arrays.columns(final.feature_names).features[:8].copy()
    matrix[0, 0] = np.inf
    matrix[3, 2] = -np.inf

    with pytest.raises(ValueError, match="infinite values") as raised:
        model.predict_scores(matrix, final.feature_names)
    assert str(raised.value).endswith(f"{['signal', 'market_feature']!r}")


def _prediction_manifest(**changes: object) -> dict[str, object]:
    source = {key: value for key, value in _source().items() if key != "columns"}
    source.update(changes)
    return {"source_datamart": source, "columns": _columns()}


@pytest.mark.parametrize(
    "prediction",
    [
        _prediction_manifest(manifest_sha256="e" * 64),
        _prediction_manifest(contract_sha256="e" * 64),
        _prediction_manifest(target_period={"start": "2020-01-01", "end": "2023-12-31"}),
        _prediction_manifest(provenance_source_sha256="e" * 64),
        _prediction_manifest(label_usable_through="2024-01-11T15:00:00+00:00"),
        {**_prediction_manifest(), "columns": _columns()[:2]},
        {"columns": _columns()},
    ],
)
def test_compatible_features_must_come_from_the_training_datamart(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit], prediction: dict[str, object]
) -> None:
    _, final = trained
    model = _model(tmp_path, final)
    model.require_compatible_features(_prediction_manifest())

    with pytest.raises(ValueError, match=r"differ|binding"):
        model.require_compatible_features(prediction)


def test_the_feature_label_boundary_is_compared_as_an_instant(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    _, final = trained
    model = _model(tmp_path, final)
    tokyo = timezone(timedelta(hours=9))

    model.require_compatible_features(
        _prediction_manifest(
            label_usable_through=datetime(2024, 1, 10, 15, tzinfo=UTC).astimezone(tokyo).isoformat()
        )
    )
    for value, message in (
        ("2024-01-10T15:00:00", "timezone-aware"),
        ("not a clock", "ISO 8601"),
        (None, "ISO 8601"),
    ):
        with pytest.raises(
            ValueError, match=f"prediction features label_usable_through.*{message}"
        ):
            model.require_compatible_features(_prediction_manifest(label_usable_through=value))


def test_predictions_must_follow_every_label_the_model_used(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    _, final = trained
    model = _model(tmp_path, final)
    boundary = final.audit.label_usable_through

    model.require_prediction_after(boundary + timedelta(seconds=1))
    with pytest.raises(ValueError, match="after the PL model label boundary"):
        model.require_prediction_after(boundary)
    with pytest.raises(ValueError, match="timezone-aware"):
        model.require_prediction_after(boundary.replace(tzinfo=None))


def test_the_writer_requires_an_empty_staging_directory(
    tmp_path: Path, trained: tuple[RaceArrays, FinalPLFit]
) -> None:
    _, final = trained
    directory = tmp_path / "model"
    directory.mkdir()
    (directory / "x").write_text("x", encoding="utf-8")
    record = pl_model_record(final, source_datamart=_source(), provenance={}, config={})

    with pytest.raises(ValueError, match="empty directory"):
        write_pl_model(directory, record, final.fit.booster)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda record: replace(record, temperature=100.0), "within its bounds"),
        (
            lambda record: replace(
                record, label_usable_through=record.label_usable_through.replace(tzinfo=None)
            ),
            "timezone-aware",
        ),
        (lambda record: replace(record, config={"x": float("nan")}), "not strict JSON"),
        (lambda record: replace(record, provenance={"p": Path("x")}), "not strict JSON"),
    ],
)
def test_the_writer_rejects_an_invalid_record_before_writing_any_file(
    tmp_path: Path,
    trained: tuple[RaceArrays, FinalPLFit],
    change: Callable[[PLModelRecord], PLModelRecord],
    message: str,
) -> None:
    _, final = trained
    directory = tmp_path / "model"
    directory.mkdir()
    record = change(_record(final))

    with pytest.raises(ValueError, match=message):
        write_pl_model(directory, record, final.fit.booster)
    assert list(directory.iterdir()) == []
