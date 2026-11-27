"""Check the operational PL variants against the closed numeric columns they name (ADR-051).

The config loaders check only the shape of a variant; the column names are checked against
a datamart at run time. These tests resolve the columns from the datamart profile's
calculation settings so a wrong name fails here, not during the yearly rebuild.
"""

from pathlib import Path
from typing import cast

from omegaconf import OmegaConf

from models.dataset.calculated import closed_numeric_columns
from models.experiments.pl_evaluation import PLVariant
from models.experiments.pl_training import variant_columns
from tests.closed_column_fixtures import ADDED_CLOSED_COLUMNS, ORIGINAL_CLOSED_COLUMNS

ROOT = Path(__file__).resolve().parents[3]
CONFIGS = ROOT / "configs"
_GATE = "basic_conditions_and_weight__gate_number"
_FIELD = "basic_conditions_and_weight__frozen_field_size"
_AGE = "basic_conditions_and_weight__horse_age_years"
_TOP3 = "recent_performance__past_top3_rate"
_GAPS = tuple(f"past_racing_ability__past_signed_gap_sec_lag{lag}" for lag in range(1, 5))


def _load(path: Path) -> dict[str, object]:
    loaded = OmegaConf.to_container(OmegaConf.load(path))
    assert isinstance(loaded, dict)
    return cast(dict[str, object], loaded)


def _columns() -> tuple[str, ...]:
    profile = _load(CONFIGS / "reference_datamart/measure.yaml")
    settings = cast(dict[str, object], profile["calculation_settings"])
    return tuple(column.name for column in closed_numeric_columns(settings))


def _variants() -> dict[str, tuple[str, ...]]:
    measured = _load(CONFIGS / "pl_evaluation/measure.yaml")
    variants = cast(list[dict[str, object]], measured["variants"])
    return {
        cast(str, variant["name"]): tuple(cast(list[str], variant["excluded_columns"]))
        for variant in variants
    }


def test_the_datamart_profile_appends_the_added_columns_to_the_original_36() -> None:
    assert _columns() == (*ORIGINAL_CLOSED_COLUMNS, *ADDED_CLOSED_COLUMNS)


def test_every_measured_variant_excludes_existing_columns_and_keeps_their_order() -> None:
    columns = _columns()
    variants = _variants()
    assert variants == {
        "all_columns": (),
        "without_market": ("market_characteristics__market_win_odds",),
        "without_added_columns": ADDED_CLOSED_COLUMNS,
        "without_post_position": (_GATE, _FIELD),
        "without_horse_age": (_AGE,),
        "without_signed_gap": _GAPS,
        "without_top3_rate": (_TOP3,),
    }
    kept = {
        name: variant_columns(columns, PLVariant(name, excluded))
        for name, excluded in variants.items()
    }
    for name, excluded in variants.items():
        # Exclusion never reorders: the kept columns are the others in contract order.
        assert kept[name] == tuple(c for c in columns if c not in excluded), name
        assert len(kept[name]) == len(columns) - len(excluded), name
    assert kept["without_added_columns"] == ORIGINAL_CLOSED_COLUMNS


def test_the_backtest_and_the_final_model_use_the_same_measured_36_column_variant() -> None:
    variants = _variants()
    final = cast(dict[str, object], _load(CONFIGS / "pl_training/final.yaml")["variant"])
    backtest = _load(CONFIGS / "betting_backtest/measure.yaml")
    assert final["name"] == backtest["pl_variant"] == "without_added_columns"
    assert tuple(cast(list[str], final["excluded_columns"])) == variants["without_added_columns"]
