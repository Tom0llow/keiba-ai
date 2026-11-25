"""Check the run records built from published PL evaluation and backtest reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import cast

import pytest

from models.experiments.report_tracking import (
    COMPARED_METRICS,
    MAX_PARAM_LENGTH,
    MetricValue,
    ReportRecord,
    flatten_params,
    report_record,
)

HEX_A = "a" * 64
HEX_B = "b" * 64


def _comparison(difference: float) -> dict[str, object]:
    return {
        "model_mean": 2.0 + difference,
        "market_mean": 2.0,
        "mean_difference": difference,
        "confidence_interval_lower": difference - 0.01,
        "confidence_interval_upper": difference + 0.01,
        "conclusion": "market_better" if difference > 0 else "model_better",
    }


def _complete(difference: float) -> dict[str, object]:
    return {
        "race_count": 10,
        "comparison": {
            kind: {metric: _comparison(difference) for metric in COMPARED_METRICS}
            for kind in ("raw", "calibrated")
        },
    }


def _summary() -> dict[str, object]:
    return {"race_count": 10, "winner_log_loss": 2.0, "stage_nll": [2.0, 2.1, 2.2]}


def pl_report() -> dict[str, object]:
    variants = [
        {"name": "all_columns", "excluded_columns": [], "feature_names": ["a", "b"]},
        {"name": "without_b", "excluded_columns": ["b"], "feature_names": ["a"]},
    ]

    def fold(year: int, difference: float) -> dict[str, object]:
        return {
            "test_year": year,
            "variants": {
                item["name"]: {
                    "best_iteration": 10 + year % 10,
                    "best_valid_nll": 6.5,
                    "temperature": {"temperature": 0.99, "at_bound": False},
                    "market_complete_races": _complete(difference) if year == 2024 else None,
                }
                for item in variants
            },
        }

    return {
        "format": "pl_probability_evaluation",
        "format_version": 1,
        "datamart": {"manifest_sha256": HEX_A, "contract_sha256": HEX_B},
        "race_subsets": {
            "jra_flat_graded_stakes_v1": {"source": {"snapshot_id": "snap-1", "sha256": HEX_A}}
        },
        "config": {
            "datamart_path": "C:/data/datamart",
            "test_years": [2024, 2025],
            "variants": [
                {k: v for k, v in item.items() if k != "feature_names"} for item in variants
            ],
            "lightgbm": {"learning_rate": 0.05, "deterministic": True},
            "temperature_bounds": [0.05, 20.0],
            "optional": None,
        },
        "provenance": {"source_sha256": HEX_B},
        "variants": variants,
        "folds": [fold(2024, 0.02), fold(2025, 0.01)],
        "pooled": {
            item["name"]: {
                "all_test_races": {"raw": _summary(), "calibrated": _summary()},
                "market_complete_races": _complete(0.009),
                "subsets": {
                    "jra_flat_graded_stakes_v1": {
                        "all_test_races": {"raw": _summary(), "calibrated": _summary()},
                        "market_complete_races": _complete(-0.003),
                    }
                },
            }
            for item in variants
        },
    }


def _betting(rate: float | None, *, stake: int = 1000) -> dict[str, object]:
    return {
        "stake_yen": stake,
        "payout_yen": 900,
        "refund_yen": 0,
        "receipt_yen": 900,
        "recovery_rate": rate,
        "net_yen": -100,
        "purchased_races": 3,
        "hit_races": 1,
        "hit_rate": 1 / 3,
        "maximum_drawdown_yen": 500,
        "maximum_consecutive_losses": 2,
        "recovery_rate_interval": {"lower": None if rate is None else rate - 0.2, "upper": None},
        "bet_types": {
            "win": {
                "bets": 2,
                "hits": 1,
                "stake_yen": 600,
                "receipt_yen": 700,
                "recovery_rate": 1.1,
            },
            "place": {
                "bets": 1,
                "hits": 0,
                "stake_yen": 400,
                "receipt_yen": 0,
                "recovery_rate": 0.0,
            },
        },
    }


def backtest_report() -> dict[str, object]:
    return {
        "format": "ev_betting_backtest",
        "format_version": 2,
        "config": {
            "pl_report_sha256": HEX_A,
            "pl_predictions_sha256": HEX_B,
            "pl_variant": "all_columns",
            "test_years": [2024, 2025],
            "policy": {"min_expected_return": 1.1, "kelly_fraction": 0.25},
        },
        "inputs": {"snapshot": {"snapshot_id": "snap-1", "tables": {}}},
        "provenance": {"source_sha256": HEX_B},
        "selection": {"2024": {"method": "pl_mid"}, "2025": {"method": "blend_width"}},
        "all_test_years": _betting(0.9),
        "common_years": {"years": [2025], "selected": _betting(0.8), "methods": {}},
        "years": {"2024": _betting(None, stake=0), "2025": _betting(0.9)},
        "methods": {
            "pl_mid": {
                "years": {
                    "2024": {"available": True, "flat": {"recovery_rate": 0.7}, "policy": None},
                    "2025": {
                        "available": True,
                        "flat": {"recovery_rate": 0.75},
                        "policy": {"recovery_rate": 0.95},
                    },
                }
            },
            "blend_width": {"years": {"2024": {"available": False, "flat": None, "policy": None}}},
        },
    }


def _record(report: dict[str, object], **extra_files: str) -> ReportRecord:
    data = json.dumps(report).encode()
    files = {"report.json": hashlib.sha256(data).hexdigest(), **extra_files}
    return report_record(data, report_dir="C:/work/output/run-1", file_sha256=files)


def _metrics(values: tuple[MetricValue, ...]) -> dict[tuple[str, int], float]:
    result = {(item.key, item.step): item.value for item in values}
    assert len(result) == len(values), "metric keys and steps must be unique"
    return result


def test_pl_report_builds_parent_tags_params_and_artifacts() -> None:
    record = _record(pl_report(), **{"predictions.parquet": HEX_A})

    assert record.experiment_name == "pl-evaluation"
    parent = record.parent
    assert parent.name == "run-1"
    assert parent.tags["run_role"] == "report"
    assert parent.tags["report_sha256"] == record.report_sha256
    assert parent.tags["file_sha256.report.json"] == record.report_sha256
    assert parent.tags["file_sha256.predictions.parquet"] == HEX_A
    assert parent.tags["datamart_manifest_sha256"] == HEX_A
    assert parent.tags["datamart_contract_sha256"] == HEX_B
    assert parent.tags["snapshot_id"] == "snap-1"
    assert parent.tags["source_sha256"] == HEX_B
    assert parent.tags["report_dir"] == "C:/work/output/run-1"
    assert parent.params["lightgbm.learning_rate"] == "0.05"
    assert parent.params["lightgbm.deterministic"] == "true"
    assert parent.params["test_years"] == "[2024,2025]"
    assert parent.params["optional"] == "null"
    assert parent.params["datamart_path"] == "C:/data/datamart"
    assert parent.metrics == ()
    assert set(parent.artifacts) == {"report.json", "config.json"}
    assert json.loads(parent.artifacts["config.json"]) == pl_report()["config"]
    assert "params_omitted" not in parent.tags


def test_pl_report_builds_one_child_per_variant_with_report_values() -> None:
    record = _record(pl_report())

    assert [child.name for child in record.children] == ["all_columns", "without_b"]
    child = record.children[1]
    assert child.tags == {
        "run_role": "variant",
        "variant": "without_b",
        **{
            f"{prefix}/{kind}/{metric}/conclusion": conclusion
            for prefix, conclusion in (("pooled", "market_better"), ("graded", "model_better"))
            for kind in ("raw", "calibrated")
            for metric in COMPARED_METRICS
        },
    }
    features = json.dumps(["a"], separators=(",", ":")).encode()
    assert child.params == {
        "variant": "without_b",
        "excluded_columns": '["b"]',
        "feature_count": "1",
        "feature_names_sha256": hashlib.sha256(features).hexdigest(),
    }
    assert child.artifacts == {"feature_names.json": features}
    metrics = _metrics(child.metrics)
    assert metrics[("pooled/raw/winner_log_loss/mean_difference", 0)] == 0.009
    assert metrics[("pooled/calibrated/trio_log_loss/ci_lower", 0)] == pytest.approx(-0.001)
    assert metrics[("pooled/raw/exacta_log_loss/market_mean", 0)] == 2.0
    assert metrics[("graded/raw/winner_log_loss/mean_difference", 0)] == -0.003
    assert metrics[("graded/calibrated/winner_log_loss/ci_upper", 0)] == pytest.approx(0.007)
    assert metrics[("pooled/raw/stage_nll/1", 0)] == 2.0
    assert metrics[("pooled/calibrated/stage_nll/3", 0)] == 2.2
    assert metrics[("fold/best_iteration", 2024)] == 14
    assert metrics[("fold/best_iteration", 2025)] == 15
    assert metrics[("fold/temperature", 2025)] == 0.99
    assert metrics[("fold/best_valid_nll", 2024)] == 6.5
    assert metrics[("fold/raw/winner_log_loss/mean_difference", 2024)] == 0.02
    # The 2025 fold has no market-complete races, so it has no comparison metrics.
    assert ("fold/raw/winner_log_loss/mean_difference", 2025) not in metrics
    assert len(metrics) == 6 + 2 * 2 * 6 * 5 + 3 * 2 + 2 * 6


def test_pl_report_without_market_complete_or_graded_sections_skips_them() -> None:
    report = pl_report()
    pooled = cast(dict[str, dict[str, object]], report["pooled"])
    pooled["all_columns"]["market_complete_races"] = None
    pooled["all_columns"]["subsets"] = {"jra_flat_graded_stakes_v1": None}

    metrics = _metrics(_record(report).children[0].metrics)

    assert not any(key.startswith(("pooled/raw/winner", "graded/")) for key, _ in metrics)
    assert ("pooled/raw/stage_nll/1", 0) in metrics


def test_backtest_report_builds_parent_metrics_tags_and_selection() -> None:
    record = _record(backtest_report(), **{"bets.parquet": HEX_A})

    assert record.experiment_name == "betting-backtest"
    assert record.children == ()
    parent = record.parent
    assert parent.tags["pl_report_sha256"] == HEX_A
    assert parent.tags["pl_predictions_sha256"] == HEX_B
    assert parent.tags["pl_variant"] == "all_columns"
    assert parent.tags["snapshot_id"] == "snap-1"
    assert parent.tags["file_sha256.bets.parquet"] == HEX_A
    assert parent.params["selection.2024"] == "pl_mid"
    assert parent.params["selection.2025"] == "blend_width"
    assert parent.params["policy.kelly_fraction"] == "0.25"
    metrics = _metrics(parent.metrics)
    assert metrics[("all/recovery_rate", 0)] == 0.9
    assert metrics[("all/recovery_rate_lower", 0)] == pytest.approx(0.7)
    assert metrics[("all/win/recovery_rate", 0)] == 1.1
    assert metrics[("all/stake_yen", 0)] == 1000
    assert metrics[("common/recovery_rate", 0)] == 0.8
    assert metrics[("year/recovery_rate", 2025)] == 0.9
    assert metrics[("year/stake_yen", 2024)] == 0
    assert metrics[("method/pl_mid/flat_recovery_rate", 2024)] == 0.7
    assert metrics[("method/pl_mid/policy_recovery_rate", 2025)] == 0.95
    # Nulls are not recorded: an unpurchased year, an open interval, an unavailable method.
    assert ("year/recovery_rate", 2024) not in metrics
    assert ("year/recovery_rate_lower", 2024) not in metrics
    assert ("all/recovery_rate_upper", 0) not in metrics
    assert ("method/pl_mid/policy_recovery_rate", 2024) not in metrics
    assert not any(key.startswith("method/blend_width/") for key, _ in metrics)


def test_backtest_report_without_common_years_skips_common_metrics() -> None:
    report = backtest_report()
    report["common_years"] = {"years": [], "selected": None, "methods": {}}

    metrics = _metrics(_record(report).parent.metrics)

    assert not any(key.startswith("common/") for key, _ in metrics)


@pytest.mark.parametrize(
    ("report_format", "version"),
    [
        ("ev_betting_backtest", 1),
        ("pl_probability_evaluation", 2),
        ("pl_probability_evaluation", True),
        ("final_odds_evaluation", 1),
        (None, 1),
    ],
)
def test_unsupported_format_or_version_is_rejected(report_format: object, version: object) -> None:
    report = pl_report()
    report["format"] = report_format
    report["format_version"] = version

    with pytest.raises(ValueError, match="unsupported report format"):
        _record(report)


@pytest.mark.parametrize(
    ("builder", "path"),
    [
        (pl_report, ("datamart", "manifest_sha256")),
        (pl_report, ("provenance", "source_sha256")),
        (pl_report, ("pooled",)),
        (pl_report, ("folds",)),
        (backtest_report, ("config", "pl_variant")),
        (backtest_report, ("inputs", "snapshot", "snapshot_id")),
        (backtest_report, ("all_test_years", "recovery_rate")),
        (backtest_report, ("methods",)),
    ],
)
def test_missing_required_items_are_rejected(
    builder: Callable[[], dict[str, object]], path: tuple[str, ...]
) -> None:
    report = builder()
    parent = report
    for key in path[:-1]:
        parent = cast(dict[str, object], parent[key])
    del parent[path[-1]]

    with pytest.raises(ValueError, match=r"lacks? |must be"):
        _record(report)


def _fold_variant(report: dict[str, object]) -> dict[str, object]:
    folds = cast(list[dict[str, dict[str, dict[str, object]]]], report["folds"])
    return folds[0]["variants"]["all_columns"]


def _pooled_comparison(report: dict[str, object]) -> dict[str, object]:
    pooled = cast(dict[str, dict[str, dict[str, dict[str, object]]]], report["pooled"])
    comparison = cast(
        dict[str, dict[str, object]], pooled["all_columns"]["market_complete_races"]["comparison"]
    )
    return comparison["raw"]


def _method_year(report: dict[str, object]) -> dict[str, object]:
    methods = cast(dict[str, dict[str, dict[str, dict[str, object]]]], report["methods"])
    return methods["pl_mid"]["years"]["2025"]


@pytest.mark.parametrize(
    ("builder", "remove", "missing"),
    [
        (pl_report, lambda r: _fold_variant(r).pop("best_valid_nll"), "best_valid_nll"),
        (pl_report, lambda r: _fold_variant(r).pop("best_iteration"), "best_iteration"),
        (
            pl_report,
            lambda r: cast(dict[str, object], _pooled_comparison(r)["winner_log_loss"]).pop(
                "model_mean"
            ),
            "model_mean",
        ),
        (
            backtest_report,
            lambda r: cast(dict[str, dict[str, object]], r["all_test_years"])[
                "recovery_rate_interval"
            ].pop("upper"),
            "upper",
        ),
        (
            backtest_report,
            lambda r: cast(dict[str, dict[str, dict[str, object]]], r["all_test_years"])[
                "bet_types"
            ]["win"].pop("recovery_rate"),
            "recovery_rate",
        ),
        (
            backtest_report,
            lambda r: cast(dict[str, object], _method_year(r)["flat"]).pop("recovery_rate"),
            "recovery_rate",
        ),
        (
            backtest_report,
            lambda r: cast(dict[str, object], _method_year(r)["policy"]).pop("recovery_rate"),
            "recovery_rate",
        ),
    ],
)
def test_missing_metric_leaves_are_rejected_not_skipped(
    builder: Callable[[], dict[str, object]],
    remove: Callable[[dict[str, object]], object],
    missing: str,
) -> None:
    report = builder()
    remove(report)

    with pytest.raises(ValueError, match=f"report lacks {missing}"):
        _record(report)


@pytest.mark.parametrize(
    ("files", "config_key"),
    [
        ({"notes(1).md": HEX_A}, None),
        ({"a:b.parquet": HEX_A}, None),
        ({}, "bad:key"),
        ({}, "/absolute"),
        ({}, "../escape"),
        ({}, "."),
        ({}, "x" * 251),
    ],
)
def test_keys_mlflow_would_refuse_are_rejected_before_tracking(
    files: dict[str, str], config_key: str | None
) -> None:
    report = pl_report()
    if config_key is not None:
        cast(dict[str, object], report["config"])[config_key] = 1

    with pytest.raises(ValueError, match="must be 1-250 characters"):
        _record(report, **files)


def test_config_keys_flattening_to_the_same_param_are_rejected() -> None:
    report = pl_report()
    config = cast(dict[str, object], report["config"])
    config["a.b"] = 1
    config["a"] = {"b": 2}

    with pytest.raises(ValueError, match=r"param key 'a.b' more than once"):
        _record(report)


def test_backtest_config_selection_keys_cannot_clash_with_selection_params() -> None:
    report = backtest_report()
    cast(dict[str, object], report["config"])["selection"] = {"2024": "manual"}

    with pytest.raises(ValueError, match=r"selection param keys \['selection.2024'\]"):
        _record(report)


def test_overlong_tag_value_is_rejected_before_tracking() -> None:
    data = json.dumps(pl_report()).encode()
    files = {"report.json": hashlib.sha256(data).hexdigest()}

    with pytest.raises(ValueError, match="tag 'report_dir' is longer than 8000"):
        report_record(data, report_dir="d" * 8001, file_sha256=files)


def test_report_hash_must_match_the_listed_report_file() -> None:
    data = json.dumps(pl_report()).encode()

    with pytest.raises(ValueError, match="SHA-256 differs"):
        report_record(data, report_dir="run", file_sha256={"report.json": HEX_A})
    with pytest.raises(ValueError, match="SHA-256 differs"):
        report_record(data, report_dir="run", file_sha256={})


def test_non_numeric_metric_is_rejected() -> None:
    report = backtest_report()
    cast(dict[str, object], report["all_test_years"])["recovery_rate"] = "0.9"

    with pytest.raises(ValueError, match="all/recovery_rate must be a number"):
        _record(report)


def test_long_params_are_omitted_and_listed() -> None:
    report = pl_report()
    long_list = ["x" * 100] * (MAX_PARAM_LENGTH // 100)
    config = cast(dict[str, object], report["config"])
    config["variants"] = long_list
    config["nested"] = {"long": "y" * (MAX_PARAM_LENGTH + 1), "short": "ok"}

    parent = _record(report).parent

    assert "variants" not in parent.params
    assert "nested.long" not in parent.params
    assert parent.params["nested.short"] == "ok"
    assert json.loads(parent.tags["params_omitted"]) == ["nested.long", "variants"]
    assert json.loads(parent.artifacts["config.json"])["variants"] == long_list


def test_flatten_params_keeps_exact_limit_and_encodes_empty_containers() -> None:
    params, omitted = flatten_params(
        {"at_limit": "z" * MAX_PARAM_LENGTH, "empty_list": [], "empty_map": {}, "flag": False}
    )

    assert params == {
        "at_limit": "z" * MAX_PARAM_LENGTH,
        "empty_list": "[]",
        "empty_map": "{}",
        "flag": "false",
    }
    assert omitted == []
