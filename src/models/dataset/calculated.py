"""Own the closed numeric projection and evidence-independent calculation identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date
from math import isfinite
from types import UnionType
from typing import cast, get_args, get_origin, get_type_hints

from make_features.contracts.observations import CalculationParameters
from make_features.real_market import MARKET_COLUMN, MARKET_IMPLEMENTATION, validate_market_settings
from make_features.reference_rules import REFERENCE_IMPLEMENTATION, validate_reference_rules
from make_features.serialization.observations import normalized_payload
from make_features.validation.observations import reject_reference, validate_parameters

CALCULATION_IMPLEMENTATION = "normalized_21_groups_v1"


@dataclass(frozen=True)
class NumericColumn:
    """Describe one exact approved calculation output and its meaning."""

    group: str
    column: str
    meaning: str
    unit: str

    @property
    def name(self) -> str:
        """Return an unambiguous native LightGBM column name."""
        return f"{self.group}__{self.column}"


# These are deliberate numeric projections, never a scan of arbitrary scalar outputs.
_COLUMNS = (
    NumericColumn(
        "recent_performance", "past_win_rate", "selected prior starts win fraction", "fraction"
    ),
    NumericColumn(
        "condition_adjusted_ability",
        "past_ability_time_mean",
        "prior standardized condition-adjusted time advantage mean",
        "dimensionless",
    ),
    NumericColumn(
        "condition_suitability",
        "horse_condition_smoothed_win_rate",
        "condition-matched horse win fraction with explicit smoothing",
        "fraction",
    ),
    NumericColumn(
        "rest_and_condition_change",
        "days_since_previous_start",
        "calendar days since previous start",
        "days",
    ),
    NumericColumn(
        "jockey_performance",
        "jockey_smoothed_win_rate",
        "rolling jockey win fraction with explicit smoothing",
        "fraction",
    ),
    NumericColumn(
        "trainer_performance",
        "trainer_smoothed_win_rate",
        "rolling trainer win fraction with explicit smoothing",
        "fraction",
    ),
    NumericColumn(
        "basic_conditions_and_weight", "race_distance_m", "frozen race distance", "metres"
    ),
    NumericColumn(
        "basic_conditions_and_weight", "carried_weight_kg", "frozen carried weight", "kilograms"
    ),
    NumericColumn(
        "jockey_combination",
        "horse_jockey_win_rate",
        "prior horse and jockey win fraction",
        "fraction",
    ),
    NumericColumn(
        "expected_race_development",
        "opponent_front_share",
        "known opponents classified as front-running fraction",
        "fraction",
    ),
    NumericColumn(
        "pedigree_suitability",
        "sire_condition_win_rate",
        "condition-matched sire offspring win fraction",
        "fraction",
    ),
    NumericColumn(
        "history_volume_and_missingness",
        "past_observed_start_count",
        "all observed prior starts count",
        "count",
    ),
    NumericColumn(
        "past_body_weight", "past_weight_lag1_kg", "previous measured body weight", "kilograms"
    ),
    NumericColumn(
        "hill_and_wood_workouts",
        "hc_last_clock_sec",
        "latest hill workout measured clock",
        "seconds",
    ),
    NumericColumn(
        "hill_and_wood_workouts",
        "wc_last_clock_sec",
        "latest wood workout measured clock",
        "seconds",
    ),
    NumericColumn(
        "market_characteristics", "market_win_odds", "frozen pre-race decimal win quote", "decimal"
    ),
    NumericColumn(
        "same_gate_and_trainer_relative",
        "same_gate_ability_diff",
        "difference in mean standardized time ability from same-gate peers",
        "dimensionless",
    ),
    NumericColumn(
        "opponent_pagerank",
        "opponent_graph_score",
        "prior opponent graph normalized PageRank",
        "score",
    ),
)
_LAGS = {
    ("recent_performance", "past_finish"): ("prior confirmed finish", "rank"),
    ("past_racing_ability", "past_velocity_mps"): (
        "prior measured race velocity",
        "metres_per_second",
    ),
    ("running_style_and_position", "past_corner4_relative"): (
        "prior fourth-corner relative position",
        "fraction",
    ),
    ("past_lap_and_running_style", "past_pace_velocity_gap_mps"): (
        "prior early minus late race velocity",
        "metres_per_second",
    ),
}
_METRIC_UNITS = {
    "elapsed_sec": "seconds",
    "velocity_mps": "metres_per_second",
    "last3f_sec": "seconds",
    "finish_relative": "fraction",
    "condition_time_advantage": "dimensionless",
}


def closed_numeric_columns(parameters: Mapping[str, object]) -> tuple[NumericColumn, ...]:
    """Return every approved numeric output in its deterministic contract order."""
    metric = str(parameters["metric"])
    lag_count = parameters["lag_count"]
    if metric not in _METRIC_UNITS or type(lag_count) is not int or lag_count < 1:
        raise ValueError("closed numeric columns require a supported metric and positive lag_count")
    dynamic = (
        NumericColumn(
            "recent_stability",
            f"past_{metric}_mean",
            "prior metric complete-window mean",
            _METRIC_UNITS[metric],
        ),
        NumericColumn(
            "within_race_relative",
            f"relative_{metric}_rank",
            "frozen field competition rank of prior metric",
            "rank",
        ),
    )
    lags = tuple(
        NumericColumn(group, f"{prefix}_lag{lag}", f"{meaning}, lag {lag}", unit)
        for (group, prefix), (meaning, unit) in _LAGS.items()
        for lag in range(1, lag_count + 1)
    )
    columns = (*_COLUMNS, *dynamic, *lags)
    if len({column.name for column in columns}) != len(columns):
        raise ValueError("closed numeric column names must be unique")
    for column in columns:
        if resolve_numeric_column(column.name, parameters) != column:
            raise ValueError(f"closed numeric column cannot be resolved: {column.name!r}")
    return columns


def resolve_numeric_column(name: str, parameters: Mapping[str, object]) -> NumericColumn:
    """Resolve exact names or strictly bounded, explicitly enumerated lag families."""
    for column in _COLUMNS:
        if name == column.name:
            return column
    metric = str(parameters["metric"])
    for group, prefix, suffix, meaning, unit in (
        (
            "recent_stability",
            "past",
            "mean",
            "prior metric complete-window mean",
            _METRIC_UNITS[metric],
        ),
        (
            "within_race_relative",
            "relative",
            "rank",
            "frozen field competition rank of prior metric",
            "rank",
        ),
    ):
        column = NumericColumn(group, f"{prefix}_{metric}_{suffix}", meaning, unit)
        if name == column.name:
            return column
    for (group, prefix), (meaning, unit) in _LAGS.items():
        match = re.fullmatch(re.escape(f"{group}__{prefix}_lag") + r"([1-9][0-9]*)", name)
        if match and int(match[1]) <= cast(int, parameters["lag_count"]):
            return NumericColumn(
                group, f"{prefix}_lag{match[1]}", f"{meaning}, lag {match[1]}", unit
            )
    raise ValueError(f"calculated column is outside the closed numeric allow-list: {name!r}")


@dataclass(frozen=True)
class CalculationContract:
    """Keep canonical semantic settings, ordered columns and an implementation version."""

    canonical_json: str

    def __post_init__(self) -> None:
        payload = json.loads(self.canonical_json)
        if not isinstance(payload, dict) or set(payload) != {
            "implementation",
            "parameters",
            "selected_columns",
        }:
            raise ValueError("invalid calculation contract")
        market = payload["implementation"] == MARKET_IMPLEMENTATION
        reference = payload["implementation"] == REFERENCE_IMPLEMENTATION
        if not market and not reference and payload["implementation"] != CALCULATION_IMPLEMENTATION:
            raise ValueError("unsupported calculation implementation")
        settings: dict[str, object]
        if reference:
            raw = payload["parameters"]
            if not isinstance(raw, dict) or set(raw) != {"calculation", "reference_rules"}:
                raise ValueError(
                    "reference contract requires calculation settings and explicit reference rules"
                )
            settings = {
                "calculation": _semantic_parameters(raw["calculation"]),
                "reference_rules": validate_reference_rules(raw["reference_rules"]),
            }
        else:
            settings = (
                validate_market_settings(payload["parameters"])
                if market
                else _semantic_parameters(payload["parameters"])
            )
        if _canonical(settings) != _canonical(payload["parameters"]):
            raise ValueError("semantic calculation parameters must use normalized types")
        names = payload["selected_columns"]
        if (
            not isinstance(names, list)
            or not names
            or any(not isinstance(n, str) for n in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("selected_columns must be a nonempty unique ordered string list")
        if market and names != [MARKET_COLUMN]:
            raise ValueError("published win market requires its single approved column")
        for name in names:
            resolve_numeric_column(
                name, cast(Mapping[str, object], settings["calculation"]) if reference else settings
            )
        if self.canonical_json != _canonical(payload):
            raise ValueError("calculation contract must use canonical JSON")

    @classmethod
    def reference(
        cls, parameters: CalculationParameters, rules: Mapping[str, object], names: Sequence[str]
    ) -> CalculationContract:
        """Bind all 21 formulas to a separately versioned explicit reference policy."""
        validate_parameters(parameters)
        semantic = cast(dict[str, object], normalized_payload(parameters))
        semantic.pop("evidence")
        return cls(
            _canonical(
                {
                    "implementation": REFERENCE_IMPLEMENTATION,
                    "parameters": {
                        "calculation": _semantic_parameters(semantic),
                        "reference_rules": validate_reference_rules(rules),
                    },
                    "selected_columns": list(names),
                }
            )
        )

    @classmethod
    def published_market(cls, parameters: Mapping[str, object]) -> CalculationContract:
        """Create the separate one-column published market contract."""
        return cls(
            _canonical(
                {
                    "implementation": MARKET_IMPLEMENTATION,
                    "parameters": validate_market_settings(parameters),
                    "selected_columns": [MARKET_COLUMN],
                }
            )
        )

    @classmethod
    def create(cls, parameters: CalculationParameters, names: Sequence[str]) -> CalculationContract:
        """Validate original parameters and exclude their source evidence from identity."""
        reject_reference(parameters)
        validate_parameters(parameters)
        settings = cast(dict[str, object], normalized_payload(parameters))
        settings.pop("evidence")
        settings = _semantic_parameters(settings)
        return cls(
            _canonical(
                {
                    "implementation": CALCULATION_IMPLEMENTATION,
                    "parameters": settings,
                    "selected_columns": list(names),
                }
            )
        )

    @classmethod
    def from_metadata(cls, value: object) -> CalculationContract:
        """Revalidate semantic parameters, digest and implementation on every read."""
        if not isinstance(value, dict) or set(value) != {"settings", "sha256"}:
            raise ValueError("invalid calculation_contract metadata")
        contract = cls(_canonical(value["settings"]))
        if value["sha256"] != contract.sha256:
            raise ValueError("calculation contract hash mismatch")
        return contract

    @property
    def settings(self) -> dict[str, object]:
        """Return a fresh decoded semantic mapping."""
        return cast(dict[str, object], json.loads(self.canonical_json))

    @property
    def names(self) -> tuple[str, ...]:
        """Return the exact ordered projection."""
        return tuple(cast(list[str], self.settings["selected_columns"]))

    @property
    def sha256(self) -> str:
        """Return the semantic identity independent of input freeze and evidence."""
        return hashlib.sha256(self.canonical_json.encode()).hexdigest()

    def columns(self) -> tuple[NumericColumn, ...]:
        """Return the closed column definitions for these settings."""
        settings = cast(dict[str, object], self.settings["parameters"])
        if self.settings["implementation"] == REFERENCE_IMPLEMENTATION:
            settings = cast(dict[str, object], settings["calculation"])
        return tuple(resolve_numeric_column(name, settings) for name in self.names)

    def as_metadata(self) -> dict[str, object]:
        """Return a JSON-compatible verified contract."""
        return {"settings": self.settings, "sha256": self.sha256}


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _typed(value: object, expected: object) -> object:
    origin, args = get_origin(expected), get_args(expected)
    if origin is UnionType:
        for choice in args:
            try:
                return _typed(value, choice)
            except ValueError:
                pass
        raise ValueError("invalid nullable calculation setting")
    if expected is type(None) and value is None:
        return None
    if origin is tuple and isinstance(value, list) and len(args) == 2:
        return [_typed(v, args[0]) for v in value]
    if (
        expected is date
        and isinstance(value, str)
        and date.fromisoformat(value).isoformat() == value
    ):
        return value
    if expected is float and type(value) in (int, float) and isfinite(cast(float, value)):
        return float(cast(float, value))
    if expected in (str, int, bool) and type(value) is expected:
        return value
    raise ValueError("calculation setting has an invalid normalized type")


def _semantic_parameters(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("semantic calculation parameters must be an object")
    annotations = get_type_hints(CalculationParameters)
    names = {f.name for f in fields(CalculationParameters)} - {"evidence"}
    if set(value) != names:
        raise ValueError("semantic calculation parameters have missing or unsupported fields")
    p = {name: _typed(value[name], annotations[name]) for name in names}
    positive = [
        "lag_count",
        "count_window",
        "days_window",
        "minimum_count",
        "style_window",
        "style_minimum_count",
        "workout_distance_m",
        "workout_section_distance_m",
        "market_anchor_seconds",
        "market_max_age_seconds",
        "graph_days",
        "graph_max_iterations",
    ]
    if (
        any(cast(int, p[k]) < 1 for k in positive)
        or cast(int, p["market_version_tolerance_seconds"]) < 0
    ):
        raise ValueError("calculation integer windows must be positive")
    if (
        any(cast(float, p[k]) <= 0 for k in ("half_life_days", "graph_tolerance"))
        or cast(float, p["smoothing_alpha"]) < 0
    ):
        raise ValueError("invalid calculation weights")
    if p["graph_half_life_days"] is not None and cast(float, p["graph_half_life_days"]) <= 0:
        raise ValueError("graph half life must be positive")
    if not 0 < cast(float, p["graph_damping"]) < 1 or any(
        not 0 <= cast(float, p[k]) <= 1 for k in ("leader_threshold", "front_threshold")
    ):
        raise ValueError("invalid calculation probability/threshold")
    if cast(int, p["style_minimum_count"]) > cast(int, p["style_window"]):
        raise ValueError("style minimum count exceeds window")
    keys = cast(list[str], p["condition_keys"])
    classes = cast(list[str], p["class_order"])
    if (
        not keys
        or len(set(keys)) != len(keys)
        or set(keys) - {"distance_m", "surface", "venue", "course", "going", "class_code"}
    ):
        raise ValueError("invalid condition keys")
    if (
        not classes
        or len(set(classes)) != len(classes)
        or any(not c for c in classes)
        or not p["rule_id"]
    ):
        raise ValueError("explicit rule and unique class order are required")
    choices = {
        "condition_window_order": {"filter_then_window", "window_then_filter"},
        "tie_policy": {"competition"},
        "metric": set(_METRIC_UNITS),
        "metric_direction": {"higher", "lower"},
        "graph_edge_rule": {"all_pairs", "winner_only"},
        "graph_base_weight": {"inverse_field_minus_one", "unit"},
    }
    if any(p[key] not in allowed for key, allowed in choices.items()):
        raise ValueError("unsupported semantic calculation option")
    return p
