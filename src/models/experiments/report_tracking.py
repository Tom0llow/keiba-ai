"""Turn a published evaluation or backtest report into MLflow run records (ADR-050).

The output directory stays the source of truth; the records are a derived index. This
module does no I/O: it parses the report bytes and returns what the caller logs.
"""

from __future__ import annotations

import hashlib
import json
import math
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

PL_EVALUATION_FORMAT = "pl_probability_evaluation"
BETTING_BACKTEST_FORMAT = "ev_betting_backtest"
SUPPORTED_FORMATS = {PL_EVALUATION_FORMAT: 1, BETTING_BACKTEST_FORMAT: 2}
EXPERIMENT_NAMES = {
    PL_EVALUATION_FORMAT: "pl-evaluation",
    BETTING_BACKTEST_FORMAT: "betting-backtest",
}
REPORT_FILE = "report.json"
MAX_PARAM_LENGTH = 6000
MAX_TAG_LENGTH = 8000
MAX_KEY_LENGTH = 250
# MLflow accepts only these characters in tag, param and metric keys (no ":" on Windows).
_KEY_PATTERN = re.compile(r"[/\w.\- ]+")
PARENT_ROLE = "report"
VARIANT_ROLE = "variant"

COMPARED_METRICS = (
    "winner_log_loss",
    "multiclass_brier",
    "exacta_log_loss",
    "quinella_log_loss",
    "trifecta_log_loss",
    "trio_log_loss",
)
_COMPARISON_FIELDS = {
    "model_mean": "model_mean",
    "market_mean": "market_mean",
    "mean_difference": "mean_difference",
    "ci_lower": "confidence_interval_lower",
    "ci_upper": "confidence_interval_upper",
}
_PROBABILITY_KINDS = ("raw", "calibrated")
_GRADED_SUBSET = "jra_flat_graded_stakes_v1"
_BETTING_FIELDS = (
    "stake_yen",
    "payout_yen",
    "refund_yen",
    "receipt_yen",
    "recovery_rate",
    "net_yen",
    "purchased_races",
    "hit_races",
    "hit_rate",
    "maximum_drawdown_yen",
    "maximum_consecutive_losses",
)


@dataclass(frozen=True)
class MetricValue:
    """Hold one metric value; ``step`` is a test year or 0 for a pooled value."""

    key: str
    value: float
    step: int = 0


@dataclass(frozen=True)
class RunRecord:
    """Hold everything logged to one MLflow run."""

    name: str
    tags: dict[str, str]
    params: dict[str, str]
    metrics: tuple[MetricValue, ...]
    artifacts: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportRecord:
    """Hold the experiment name, the parent run and its child runs for one report."""

    experiment_name: str
    report_sha256: str
    parent: RunRecord
    children: tuple[RunRecord, ...]


def report_record(
    report_bytes: bytes, *, report_dir: str, file_sha256: Mapping[str, str]
) -> ReportRecord:
    """Validate a published report and build its run records.

    ``file_sha256`` maps every file name directly in the output directory to its
    SHA-256; it must contain ``report.json`` with the digest of ``report_bytes``.
    """
    digest = hashlib.sha256(report_bytes).hexdigest()
    if file_sha256.get(REPORT_FILE) != digest:
        raise ValueError("report.json SHA-256 differs from the listed output files")
    try:
        report = json.loads(report_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("report.json is not valid JSON") from exc
    report = _mapping(report, "report")
    report_format = report.get("format")
    version = report.get("format_version")
    if (
        not isinstance(report_format, str)
        or report_format not in SUPPORTED_FORMATS
        or isinstance(version, bool)
        or version != SUPPORTED_FORMATS[report_format]
    ):
        supported = ", ".join(f"{name} v{number}" for name, number in SUPPORTED_FORMATS.items())
        raise ValueError(
            f"unsupported report format {report_format!r} v{version!r}; supported: {supported}"
        )
    config = _mapping(report.get("config"), "config")
    tags = {
        "run_role": PARENT_ROLE,
        "report_format": report_format,
        "report_format_version": str(version),
        "report_dir": report_dir,
        "report_sha256": digest,
        "source_sha256": _string(_get(report, "provenance", "source_sha256"), "source_sha256"),
        **{f"file_sha256.{name}": value for name, value in sorted(file_sha256.items())},
    }
    params, omitted = flatten_params(config)
    config_json = _json_bytes(config)
    artifacts = {REPORT_FILE: report_bytes, "config.json": config_json}
    if report_format == PL_EVALUATION_FORMAT:
        tags.update(_pl_tags(report))
        metrics: tuple[MetricValue, ...] = ()
        children = _pl_children(report)
    else:
        tags.update(_backtest_tags(report, config))
        selection = _selection_params(report)
        clashes = sorted(set(selection) & {*params, *omitted})
        if clashes:
            raise ValueError(f"config already has the selection param keys {clashes!r}")
        params.update(selection)
        metrics = _backtest_metrics(report)
        children = ()
    if omitted:
        tags["params_omitted"] = json.dumps(omitted, ensure_ascii=False)
    name = report_dir.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or report_format
    parent = RunRecord(name, tags, params, metrics, artifacts)
    for run in (parent, *children):
        _validate_run(run)
    return ReportRecord(
        experiment_name=EXPERIMENT_NAMES[report_format],
        report_sha256=digest,
        parent=parent,
        children=children,
    )


def flatten_params(config: Mapping[str, object]) -> tuple[dict[str, str], list[str]]:
    """Flatten nested mappings to dotted keys; drop values longer than MLflow allows.

    Strings stay as they are; every other value, including lists and nulls, becomes
    compact JSON. Returns the parameters and the sorted keys that were too long.
    """
    params: dict[str, str] = {}
    omitted: list[str] = []

    def visit(prefix: str, value: object) -> None:
        if isinstance(value, Mapping) and value:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"config key under {prefix or 'config'!r} must be a string")
                visit(f"{prefix}.{key}" if prefix else key, item)
            return
        if prefix in params or prefix in omitted:
            raise ValueError(f"config flattens to the param key {prefix!r} more than once")
        text = value if isinstance(value, str) else _json_text(value)
        if len(text) > MAX_PARAM_LENGTH:
            omitted.append(prefix)
        else:
            params[prefix] = text

    visit("", config)
    return params, sorted(omitted)


def _pl_tags(report: Mapping[str, object]) -> dict[str, str]:
    return {
        "datamart_manifest_sha256": _string(
            _get(report, "datamart", "manifest_sha256"), "datamart.manifest_sha256"
        ),
        "datamart_contract_sha256": _string(
            _get(report, "datamart", "contract_sha256"), "datamart.contract_sha256"
        ),
        "snapshot_id": _string(
            _get(report, "race_subsets", _GRADED_SUBSET, "source", "snapshot_id"),
            "race_subsets snapshot_id",
        ),
    }


def _pl_children(report: Mapping[str, object]) -> tuple[RunRecord, ...]:
    pooled = _mapping(report.get("pooled"), "pooled")
    folds = _sequence(report.get("folds"), "folds")
    children: list[RunRecord] = []
    for item in _sequence(report.get("variants"), "variants"):
        variant = _mapping(item, "variant")
        name = _string(variant.get("name"), "variant name")
        excluded = _sequence(variant.get("excluded_columns"), f"{name} excluded_columns")
        features = _sequence(variant.get("feature_names"), f"{name} feature_names")
        features_json = _json_bytes(list(features))
        metrics: list[MetricValue] = []
        tags = {"run_role": VARIANT_ROLE, "variant": name}
        variant_pooled = _mapping(pooled.get(name), f"pooled.{name}")
        for kind in _PROBABILITY_KINDS:
            stage_nll = _sequence(
                _get(variant_pooled, "all_test_races", kind, "stage_nll"), f"{name} stage_nll"
            )
            for index, value in enumerate(stage_nll, start=1):
                _append(metrics, f"pooled/{kind}/stage_nll/{index}", value)
        _comparison_values(
            metrics, tags, "pooled", _nullable(variant_pooled, "market_complete_races")
        )
        subsets = _mapping(variant_pooled.get("subsets"), f"pooled.{name}.subsets")
        graded = _nullable(subsets, _GRADED_SUBSET)
        if graded is not None:
            _comparison_values(metrics, tags, "graded", _nullable(graded, "market_complete_races"))
        for fold_item in folds:
            fold = _mapping(fold_item, "fold")
            year = _integer(fold.get("test_year"), "fold test_year")
            fold_variant = _mapping(_get(fold, "variants", name), f"fold {year} {name}")
            _append(metrics, "fold/best_iteration", _get(fold_variant, "best_iteration"), year)
            _append(metrics, "fold/best_valid_nll", _get(fold_variant, "best_valid_nll"), year)
            _append(
                metrics,
                "fold/temperature",
                _get(fold_variant, "temperature", "temperature"),
                year,
            )
            complete = _nullable(fold_variant, "market_complete_races")
            if complete is None:
                continue
            for kind in _PROBABILITY_KINDS:
                for metric in COMPARED_METRICS:
                    _append(
                        metrics,
                        f"fold/{kind}/{metric}/mean_difference",
                        _get(complete, "comparison", kind, metric, "mean_difference"),
                        year,
                    )
        children.append(
            RunRecord(
                name=name,
                tags=tags,
                params={
                    "variant": name,
                    "excluded_columns": _json_text(list(excluded)),
                    "feature_count": str(len(features)),
                    "feature_names_sha256": hashlib.sha256(features_json).hexdigest(),
                },
                metrics=tuple(metrics),
                artifacts={"feature_names.json": features_json},
            )
        )
    if not children:
        raise ValueError("variants must not be empty")
    return tuple(children)


def _comparison_values(
    metrics: list[MetricValue],
    tags: dict[str, str],
    prefix: str,
    complete: Mapping[str, object] | None,
) -> None:
    if complete is None:
        return
    for kind in _PROBABILITY_KINDS:
        for metric in COMPARED_METRICS:
            comparison = _mapping(
                _get(complete, "comparison", kind, metric), f"{prefix} {kind} {metric}"
            )
            for name, source in _COMPARISON_FIELDS.items():
                _append(metrics, f"{prefix}/{kind}/{metric}/{name}", _get(comparison, source))
            tags[f"{prefix}/{kind}/{metric}/conclusion"] = _string(
                comparison.get("conclusion"), f"{prefix} {kind} {metric} conclusion"
            )


def _backtest_tags(report: Mapping[str, object], config: Mapping[str, object]) -> dict[str, str]:
    return {
        "pl_report_sha256": _string(config.get("pl_report_sha256"), "config.pl_report_sha256"),
        "pl_predictions_sha256": _string(
            config.get("pl_predictions_sha256"), "config.pl_predictions_sha256"
        ),
        "pl_variant": _string(config.get("pl_variant"), "config.pl_variant"),
        "snapshot_id": _string(
            _get(report, "inputs", "snapshot", "snapshot_id"), "inputs.snapshot.snapshot_id"
        ),
    }


def _selection_params(report: Mapping[str, object]) -> dict[str, str]:
    selection = _mapping(report.get("selection"), "selection")
    return {
        f"selection.{year}": _string(
            _mapping(item, f"selection {year}").get("method"), f"selection {year} method"
        )
        for year, item in selection.items()
    }


def _backtest_metrics(report: Mapping[str, object]) -> tuple[MetricValue, ...]:
    metrics: list[MetricValue] = []
    _betting_values(metrics, "all", _mapping(report.get("all_test_years"), "all_test_years"))
    common = _mapping(report.get("common_years"), "common_years")
    selected = _nullable(common, "selected")
    if selected is not None:
        _betting_values(metrics, "common", selected)
    for year_text, item in _mapping(report.get("years"), "years").items():
        _betting_values(metrics, "year", _mapping(item, f"year {year_text}"), _year(year_text))
    for method, item in _mapping(report.get("methods"), "methods").items():
        method_years = _mapping(_get(item, "years"), f"method {method} years")
        for year_text, entry in method_years.items():
            year = _year(year_text)
            entry_map = _mapping(entry, f"method {method} {year_text}")
            flat = _nullable(entry_map, "flat")
            if flat is not None:
                _append(
                    metrics,
                    f"method/{method}/flat_recovery_rate",
                    _get(flat, "recovery_rate"),
                    year,
                )
            policy = _nullable(entry_map, "policy")
            if policy is not None:
                _append(
                    metrics,
                    f"method/{method}/policy_recovery_rate",
                    _get(policy, "recovery_rate"),
                    year,
                )
    return tuple(metrics)


def _betting_values(
    metrics: list[MetricValue], prefix: str, values: Mapping[str, object], step: int = 0
) -> None:
    for name in _BETTING_FIELDS:
        if name not in values:
            raise ValueError(f"{prefix} betting metrics lack {name}")
        _append(metrics, f"{prefix}/{name}", values[name], step)
    interval = _mapping(values.get("recovery_rate_interval"), f"{prefix} recovery_rate_interval")
    _append(metrics, f"{prefix}/recovery_rate_lower", _get(interval, "lower"), step)
    _append(metrics, f"{prefix}/recovery_rate_upper", _get(interval, "upper"), step)
    for bet_type, item in _mapping(values.get("bet_types"), f"{prefix} bet_types").items():
        _append(
            metrics,
            f"{prefix}/{bet_type}/recovery_rate",
            _get(item, "recovery_rate"),
            step,
        )


def _validate_run(run: RunRecord) -> None:
    """Reject keys and tag values MLflow would refuse, before any run is created."""
    keys = [*run.tags, *run.params, *(item.key for item in run.metrics)]
    for key in keys:
        normalized = posixpath.normpath(key)
        if (
            not key
            or len(key) > MAX_KEY_LENGTH
            or _KEY_PATTERN.fullmatch(key) is None
            # MLflow may store keys as paths, so they must not change when normalized.
            or normalized != key
            or normalized == "."
            or normalized.startswith(("..", "/"))
        ):
            raise ValueError(
                f"run {run.name!r} key {key!r} must be 1-{MAX_KEY_LENGTH} characters of "
                "letters, digits, '_', '-', '.', ' ' or '/' and a normalized relative path"
            )
    for key, value in run.tags.items():
        if len(value) > MAX_TAG_LENGTH:
            raise ValueError(f"run {run.name!r} tag {key!r} is longer than {MAX_TAG_LENGTH}")
    # MLflow truncates an over-long param with only a warning; config params are omitted earlier.
    for key, value in run.params.items():
        if len(value) > MAX_PARAM_LENGTH:
            raise ValueError(f"run {run.name!r} param {key!r} is longer than {MAX_PARAM_LENGTH}")


def _append(metrics: list[MetricValue], key: str, value: object, step: int = 0) -> None:
    """Add a numeric value; a null is skipped, anything else non-numeric is rejected."""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metric {key} must be a number or null")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"metric {key} must be finite")
    metrics.append(MetricValue(key, number, step))


def _get(value: object, *keys: str) -> object:
    """Follow required keys; a missing key or a non-mapping on the way is rejected."""
    current = value
    path: list[str] = []
    for key in keys:
        path.append(key)
        if not isinstance(current, Mapping) or key not in current:
            raise ValueError(f"report lacks {'.'.join(path)}")
        current = current[key]
    return current


def _nullable(value: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    if key not in value:
        raise ValueError(f"report lacks {key}")
    item = value[key]
    return None if item is None else _mapping(item, key)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return cast(list[object], value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _year(text: str) -> int:
    if not (len(text) == 4 and text.isdigit()):
        raise ValueError(f"year key {text!r} must be four digits")
    return int(text)


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _json_bytes(value: object) -> bytes:
    return _json_text(value).encode("utf-8")
