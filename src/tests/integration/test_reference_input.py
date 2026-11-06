"""All 21 groups use bounded raw fixtures and explicit, non-certifying assumptions."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from configuration.experiments import load_experiment_config
from configuration.reference_input import load_reference_input_config
from data.loader.read_json import read_json
from data.saver.write_json import write_json
from main import app
from make_features.catalog.loader import load_feature_definitions
from make_features.catalog.registry import create_feature_registry
from make_features.contracts.observations import ReferenceEvidence
from make_features.generation.calculate import calculate_features, calculate_reference_features
from make_features.generation.observations import prepare_context
from make_features.real_market import canonical_hash
from make_features.reference_raw import conditions, historical_race
from make_features.reference_snapshot import normalize_reference_input
from make_features.serialization.observations import (
    normalized_payload,
    parse_calculation_dependencies,
    parse_calculation_parameters,
    parse_historical_results,
    parse_observation_inputs,
)
from models.dataset.builder import build_features
from models.dataset.calculated import CalculationContract
from models.dataset.schema import FeatureSchema
from models.evaluation.walk_forward import WalkForwardConfig, make_walk_forward_folds
from models.experiments.runner import run_experiment
from models.serialization.inputs import parse_feature_inputs
from models.serialization.projection import parse_label_sources, prepare_model_payload
from models.serialization.reference import prepare_reference_payload
from tests.reference_fixtures import ROOT, markets, parquet_snapshot, race_rows, raw_input


def _prepare(raw: dict[str, object]) -> dict[str, object]:
    config = load_reference_input_config(
        ROOT / "configs/reference_input", config_name="trial", overrides=["processed_root=unused"]
    )
    registry = create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml"))
    return prepare_reference_payload(
        raw, registry=registry, selected_columns=cast(list[str], config["selected_columns"])
    )


def _tables(raw: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    return cast(dict[str, list[dict[str, object]]], raw["tables"])


def _shared_result_input(*, labels: bool = True) -> dict[str, object]:
    raw = raw_input((date(2026, 9, 6), date(2026, 9, 27)), labels=labels)
    ra, se = race_rows(date(2026, 9, 6))
    _tables(raw)["history_ra"].append(ra)
    _tables(raw)["history_se"].extend(se)
    return raw


def test_consistent_shared_rows_accept_different_projection_columns() -> None:
    payload = _prepare(_shared_result_input())
    _, records = parse_feature_inputs(payload)
    assert len(records) == 8
    assert len(parse_label_sources(payload, required=True)) == 2
    earlier, later = records[0], records[4]
    assert earlier.finish_position == 1
    assert later.features["recent_performance__past_finish_lag1"] == 1


@pytest.mark.parametrize(
    "roles", [("history", "target"), ("history", "label"), ("target", "label")]
)
@pytest.mark.parametrize("kind", ["ra", "se"])
def test_conflicting_shared_physical_rows_reject_the_entire_input(
    roles: tuple[str, str], kind: str
) -> None:
    raw = _shared_result_input(labels="label" in roles)
    tables = _tables(raw)
    changed = tables[f"{roles[1]}_{kind}"]
    if roles == ("history", "label"):
        if kind == "ra":
            changed[0]["HaronTimeL3"] = "361"
        else:
            changed[0]["KakuteiJyuni"], changed[1]["KakuteiJyuni"] = "02", "01"
            changed[0]["NyusenJyuni"], changed[1]["NyusenJyuni"] = "02", "01"
    else:
        changed[0]["HassoTime" if kind == "ra" else "Futan"] = "1501" if kind == "ra" else "580"
    with pytest.raises(ValueError, match="conflicting shared raw"):
        _prepare(raw)


@pytest.mark.parametrize(("original", "changed"), [(None, ""), ("", " "), ("A ", "A")])
def test_shared_columns_compare_unmodified_raw_values(original: str | None, changed: str) -> None:
    raw = raw_input(labels=True)
    tables = _tables(raw)
    tables["target_ra"][0]["CourseKubunCD"] = original
    tables["label_ra"][0]["CourseKubunCD"] = changed
    with pytest.raises(ValueError, match="conflicting shared raw"):
        normalize_reference_input(raw)


@pytest.mark.parametrize("field", ["idYear", "KettoNum"])
@pytest.mark.parametrize("value", [None, "", " "])
def test_shared_physical_rows_require_complete_keys(field: str, value: str | None) -> None:
    raw = _shared_result_input()
    _tables(raw)["history_se"][-4][field] = value
    with pytest.raises(ValueError, match="key"):
        normalize_reference_input(raw)


@pytest.mark.parametrize("kind", ["ra", "se", "input_history"])
def test_standalone_label_parser_checks_original_shared_rows(kind: str) -> None:
    payload = _prepare(_shared_result_input())
    payload["label_sources"] = copy.deepcopy(payload["label_sources"])
    sources = cast(list[dict[str, object]], payload["label_sources"])
    result = cast(dict[str, object], sources[0]["raw"])
    if kind == "input_history":
        raw = cast(dict[str, object], payload["reference_input"])
        runners = _tables(raw)["history_se"][-4:]
        runners[0]["KakuteiJyuni"], runners[1]["KakuteiJyuni"] = "02", "01"
        payload["reference_input_sha256"] = canonical_hash(raw)
    elif kind == "ra":
        cast(dict[str, object], result["ra"])["HassoTime"] = "1501"
        sources[0]["raw_sha256"] = canonical_hash(result)
    else:
        runners = cast(list[dict[str, object]], result["se"])
        runners[0]["KakuteiJyuni"], runners[1]["KakuteiJyuni"] = "02", "01"
        sources[0]["raw_sha256"] = canonical_hash(result)
        records = cast(list[dict[str, object]], payload["records"])
        records[0]["finish_position"], records[1]["finish_position"] = 2, 1
    with pytest.raises(ValueError, match="conflicting shared raw"):
        parse_label_sources(payload, required=True)


def test_model_input_replay_rejects_conflicting_history_and_labels() -> None:
    labeled = _prepare(_shared_result_input())
    raw = _shared_result_input(labels=False)
    runners = _tables(raw)["history_se"][-4:]
    runners[0]["KakuteiJyuni"], runners[1]["KakuteiJyuni"] = "02", "01"
    payload = _prepare(raw)
    original = cast(dict[str, object], labeled["reference_input"])
    for name in ("label_ra", "label_se"):
        _tables(raw)[name] = copy.deepcopy(_tables(original)[name])
    raw["include_labels"] = True
    payload["reference_input"] = raw
    payload["reference_input_sha256"] = canonical_hash(raw)
    payload["label_sources"] = labeled["label_sources"]
    for record, label in zip(
        cast(list[dict[str, object]], payload["records"]),
        cast(list[dict[str, object]], labeled["records"]),
        strict=True,
    ):
        record["finish_position"] = label["finish_position"]
    with pytest.raises(ValueError, match="conflicting shared raw"):
        parse_feature_inputs(payload)


def test_all_groups_replay_raw_units_population_and_shared_sources() -> None:
    raw = raw_input()
    normalized = normalize_reference_input(raw)
    source = normalized.observations[0]
    assert source.card.conditions.going is None
    assert source.card.conditions.class_code is None
    assert len(source.history) == 6
    assert len(source.coverage[0].horse_ids) == 8
    assert all(
        isinstance(r.evidence, ReferenceEvidence) and r.evidence.received_at is None
        for r in source.history
    )
    assert source.history[0].runners[0].elapsed_sec == pytest.approx(105.6)
    assert source.history[0].runners[0].signed_gap_sec == -0.1
    assert sum(s.distance_m for s in source.history[0].sections) == 1600
    assert source.pedigrees[0].sire == "SIRE1"
    assert source.pedigrees[0].broodmare_sire == "DAM1"
    assert len(source.workouts) == 10
    assert source.workouts[0].course is None
    assert source.workouts[0].turn is None
    assert source.markets[0].pairs[0].odds == 12.0
    assert source.markets[0].horses[0].place_low == 1.1
    payload = _prepare(raw)
    schema, rows = parse_feature_inputs(payload)
    assert len(schema.feature_names) == 21
    assert rows[0].features["past_body_weight__past_weight_lag1_kg"] == 482
    calculation = cast(dict[str, object], payload["calculation"])
    dependencies = cast(list[dict[str, object]], calculation["dependencies"])
    assert all(len(cast(dict[str, object], row["groups"])) == 21 for row in dependencies)
    assert len(cast(dict[str, object], calculation["source_catalog"])) < 100
    assert "sources" not in str(dependencies)
    registry = create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml"))
    calculated = calculate_reference_features(
        normalized.observations, normalized.parameters, registry=registry
    )
    group = calculated.manifests[0][
        registry.by_name("hill_and_wood_workouts").definition.feature_id
    ]
    assert group.values["hc_same_day_reference_count"] == 4
    assert group.values["hc_same_day_course_diff_sec"] == -2
    assert FeatureSchema.from_metadata(schema.as_metadata()) == schema


@pytest.mark.parametrize(
    "entry",
    [
        "calculate",
        "context",
        "observations",
        "parameters",
        "dependencies",
        "results",
        "contract",
        "projection",
    ],
)
def test_reference_evidence_cannot_enter_existing_strict_contracts(entry: str) -> None:
    normalized = normalize_reference_input(raw_input())
    registry = create_feature_registry(load_feature_definitions(ROOT / "configs/features.toml"))

    def invoke() -> None:
        if entry == "calculate":
            calculate_features(normalized.observations, normalized.parameters, registry=registry)
        elif entry == "context":
            prepare_context(normalized.observations[0], normalized.parameters)
        elif entry == "observations":
            parse_observation_inputs(
                {"schema_version": 1, "observations": normalized_payload(normalized.observations)}
            )
        elif entry == "parameters":
            parse_calculation_parameters(
                cast(dict[str, object], normalized_payload(normalized.parameters))
            )
        elif entry == "dependencies":
            source = normalized.observations[0].card.evidence
            parse_calculation_dependencies(
                [
                    {
                        "race_id": "r",
                        "horse_id": "h",
                        "groups": {
                            "g": {
                                "rule_id": "r",
                                "sources": [normalized_payload(source)],
                                "historical_race_ids": [],
                                "missing_reasons": {},
                                "diagnostics": {},
                            }
                        },
                    }
                ]
            )
        elif entry == "results":
            parse_historical_results(
                {
                    "schema_version": 1,
                    "results": normalized_payload(normalized.observations[0].history),
                }
            )
        elif entry == "contract":
            CalculationContract.create(
                normalized.parameters, ["market_characteristics__market_win_odds"]
            )
        else:
            calculated = calculate_reference_features(
                normalized.observations, normalized.parameters, registry=registry
            )
            prepare_model_payload(
                calculated,
                registry=registry,
                selected_columns=["market_characteristics__market_win_odds"],
            )

    with pytest.raises(ValueError, match="reference evidence"):
        invoke()


def test_target_outcomes_future_versions_and_current_cumulative_fields_do_not_change_features() -> (
    None
):
    raw = raw_input(labels=True)
    baseline = _prepare(raw)
    changed = copy.deepcopy(raw)
    tables = _tables(changed)
    for row in tables["label_se"]:
        row["KakuteiJyuni"] = f"{5 - int(cast(str, row['KakuteiJyuni'])):02d}"
        row["Time"] = "9599"
        row["BaTaijyu"] = "999"
        row["Odds"] = "9999"
    tables["label_ra"][0]["TenkoBabaSibaBabaCD"] = "4"
    for row in tables["um"]:
        row["future_cumulative_earnings"] = "99999999"
    for clock, phase in (("1456", "1"), ("1454", "4")):
        o1, o2 = markets(date(2026, 9, 6), clock=clock, total=99999)
        o1["headDataKubun"] = phase
        o2["headDataKubun"] = phase
        tables["o1"].append(o1)
        tables["o2"].append(o2)
    modified = _prepare(changed)
    before = cast(list[dict[str, object]], baseline["records"])
    after = cast(list[dict[str, object]], modified["records"])
    assert [r["features"] for r in before] == [r["features"] for r in after]
    prediction = copy.deepcopy(changed)
    prediction["include_labels"] = False
    _tables(prediction)["label_ra"] = []
    _tables(prediction)["label_se"] = []
    assert [
        r["features"] for r in cast(list[dict[str, object]], _prepare(prediction)["records"])
    ] == [r["features"] for r in before]


def test_whole_race_hold_retains_reason_and_never_removes_a_single_horse() -> None:
    raw = raw_input((date(2026, 9, 6), date(2026, 9, 13)), labels=True)
    tables = _tables(raw)
    tables["history_se"][0]["IJyoCD"] = "1"
    tables["label_se"][0]["DochakuKubun"] = "1"
    payload = _prepare(raw)
    holds = cast(list[dict[str, object]], payload["held_races"])
    assert {(h["role"], h["reason"]) for h in holds} == {
        ("history", "non_normal_or_tied_result"),
        ("target", "non_normal_or_tied_result"),
    }
    rows = cast(list[dict[str, object]], payload["records"])
    assert len(rows) == 4
    assert {r["race_id"] for r in rows} == {"2026091301010109"}


def test_special_measurements_and_market_quotes_remain_missing_without_imputation() -> None:
    ra, se = race_rows(date(2026, 8, 1))
    se[0].update(Time="0000", HaronTimeL3="000", BaTaijyu="999", Jyuni4c="00")
    ra["LapTime0"] = "000"
    history = historical_race(ra, se, days=7)
    own = history.runners[0]
    assert own.elapsed_sec is own.last3f_sec is own.body_weight_kg is own.corner4 is None
    assert history.sections[0].seconds is None
    assert own.missing_reasons["elapsed_sec"]
    raw = raw_input()
    for row in _tables(raw)["o1"]:
        row["OddsTansyoInfo0Odds"] = "9999"
    payload = _prepare(raw)
    assert (
        cast(dict[str, object], cast(list[dict[str, object]], payload["records"])[0]["features"])[
            "market_characteristics__market_win_odds"
        ]
        is None
    )


@pytest.mark.parametrize(
    "part",
    ["raw", "value", "availability", "source_catalog", "label", "missing_label", "delay", "rules"],
)
def test_source_values_and_label_tampering_are_rejected(part: str) -> None:
    payload = _prepare(raw_input(labels=True))
    rows = cast(list[dict[str, object]], payload["records"])
    raw = cast(dict[str, object], payload["reference_input"])
    if part == "raw":
        _tables(raw)["o1"][0]["OddsTansyoInfo0Odds"] = "0123"
    elif part == "value":
        cast(dict[str, object], rows[0]["features"])["market_characteristics__market_win_odds"] = (
            999
        )
    elif part == "availability":
        cast(dict[str, object], rows[0]["available_at"])[
            "market_characteristics__market_win_odds"
        ] = "2026-09-06T14:56:00+09:00"
    elif part == "source_catalog":
        calculated = cast(dict[str, object], payload["calculation"])
        catalog = cast(dict[str, object], calculated["source_catalog"])
        cast(dict[str, object], next(iter(catalog.values())))["received_at"] = (
            "2026-01-01T00:00:00+09:00"
        )
    elif part == "label":
        rows[0]["finish_position"] = 4
    elif part == "missing_label":
        payload.pop("label_sources")
    elif part == "delay":
        cast(list[dict[str, object]], payload["label_sources"])[0]["usable_after"] = (
            "2026-09-07T00:00:00+09:00"
        )
    else:
        cast(dict[str, object], raw["rules"])["result_delay_days"] = 8
        payload["reference_input_sha256"] = canonical_hash(raw)
    with pytest.raises(ValueError, match=r"hash|differ"):
        parse_feature_inputs(payload)


def test_schema_semantic_settings_and_exact_cutoff_are_enforced() -> None:
    raw = raw_input()
    first = _prepare(raw)
    altered = copy.deepcopy(raw)
    cast(dict[str, object], altered["rules"])["result_delay_days"] = 8
    second = _prepare(altered)
    assert first["schema_id"] != second["schema_id"]
    race = cast(list[dict[str, object]], raw["races"])[0]
    race["freeze_at"] = "2026-09-06T14:55:01+09:00"
    with pytest.raises(ValueError, match="300 seconds"):
        _prepare(raw)
    ra, _ = race_rows(date(2026, 8, 1))
    ra["TrackCD"] = "29"
    with pytest.raises(ValueError, match="unsupported TrackCD"):
        conditions(ra, target=False)


def test_parquet_cli_train_register_and_future_predict_with_reference_assurance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = raw_input((date(2026, 9, 6), date(2026, 9, 13), date(2026, 9, 27)), labels=True)
    processed = tmp_path / "processed"
    version = parquet_snapshot(processed, raw)
    originals = {p.name: p.read_bytes() for p in version.glob("*.parquet")}
    manifest, output = tmp_path / "manifest.json", tmp_path / "prepared.json"
    write_json(manifest, {"races": raw["races"]})
    args = [
        "model",
        "prepare-reference-input",
        "--manifest",
        str(manifest),
        "--output",
        str(output),
        "--config-dir",
        str(ROOT / "configs/reference_input"),
        "--config-name",
        "trial",
        "--features-config",
        str(ROOT / "configs/features.toml"),
        "--override",
        f"processed_root='{processed.as_posix()}'",
    ]
    runner = CliRunner()
    prepared = runner.invoke(app, args)
    assert prepared.exit_code == 0, prepared.output
    payload = read_json(output)
    schema, records = parse_feature_inputs(payload)
    dataset = build_features(records, feature_schema=schema).dataset
    assert dataset is not None
    with pytest.raises(ValueError, match="label-use audit"):
        make_walk_forward_folds(dataset, WalkForwardConfig(1, 1, 1, 1))
    before = output.read_bytes()
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_bytes() == before
    assert {p.name: p.read_bytes() for p in version.glob("*.parquet")} == originals
    monkeypatch.chdir(tmp_path)
    config = load_experiment_config(
        ROOT / "configs/experiments",
        action="train",
        overrides=[
            f"data.input='{output.as_posix()}'",
            "model.parameters.n_estimators=2",
            "model.parameters.min_child_samples=1",
        ],
    )
    trained = run_experiment(config)
    context = read_json(Path(str(trained["output_dir"])) / "native/training.json")
    assert trained["model_version"] == "1"
    assert context["label_boundary_meaning"] == "declared_usable_after"
    assert context["label_known_through"] == "2026-09-21T00:00:00+09:00"
    assert cast(dict[str, object], context["input_assurance"])["received_at"] is None
    future = tmp_path / "future.json"
    write_json(future, _prepare(raw_input((date(2026, 10, 4),))))
    prediction = load_experiment_config(
        ROOT / "configs/experiments",
        action="predict",
        overrides=[f"data.input='{future.as_posix()}'", "model.version=1"],
    )
    result = run_experiment(prediction)
    saved = read_json(Path(str(result["output_dir"])) / "predictions.json")
    assert len(cast(list[object], saved["predictions"])) == 4
    assert saved["input_assurance"] == context["input_assurance"]
