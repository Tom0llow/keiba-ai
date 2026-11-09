"""Tests for shared physical TOML loading and path resolution."""

import tomllib
from pathlib import Path
from typing import cast

import pytest
from omegaconf.errors import OmegaConfBaseException

from configuration.data_paths import DataPaths
from configuration.loader import load_toml
from configuration.reference_datamart import load_reference_datamart_config
from configuration.reference_input import load_reference_input_config

ROOT = Path(__file__).resolve().parents[3]


def test_shared_loader_preserves_unrecognized_feature_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[other]\nvalue = ["custom", "values"]\n', encoding="utf-8")
    assert load_toml(path) == {"other": {"value": ["custom", "values"]}}


def test_shared_loader_preserves_parser_and_filesystem_errors(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    with pytest.raises(FileNotFoundError):
        load_toml(path)
    path.write_text("invalid = [", encoding="utf-8")
    with pytest.raises(tomllib.TOMLDecodeError):
        load_toml(path)


def test_data_path_required_fields_remain_owned_by_shared_path_settings(tmp_path: Path) -> None:
    config = tmp_path / "data.toml"
    config.write_text('[paths]\nraw_db = "race.db"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[paths\].processed_dir must be a non-empty string"):
        DataPaths.from_toml(config)


_DATAMART_CONFIGS = ROOT / "configs/reference_datamart"
_MEASURE = ["processed_root=unused", "snapshot_id=fixture-v1"]


def test_reference_datamart_build_profile_requires_every_value() -> None:
    with pytest.raises(OmegaConfBaseException):
        load_reference_datamart_config(_DATAMART_CONFIGS, config_name="build")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ("target_start=2026-01-01", "target_start must not be later"),
        ("calculation_settings.history_start=2025-02-01", "history_start must not be later"),
        ("target_end=2025-12-1", "ISO date"),
        ("+extra=1", "missing or unsupported keys"),
        ("~reference_rules.venues", "nested keys"),
    ],
)
def test_reference_datamart_profile_rejects_invalid_periods_and_keys(
    override: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_reference_datamart_config(
            _DATAMART_CONFIGS, config_name="measure", overrides=[*_MEASURE, override]
        )


def test_reference_datamart_measure_profile_matches_trial_except_history_start() -> None:
    measure = load_reference_datamart_config(
        _DATAMART_CONFIGS, config_name="measure", overrides=_MEASURE
    )
    trial = load_reference_input_config(
        ROOT / "configs/reference_input", config_name="trial", overrides=["processed_root=unused"]
    )
    settings = dict(cast(dict[str, object], measure["calculation_settings"]))
    assert settings.pop("history_start") == "2005-01-01"
    expected = dict(cast(dict[str, object], trial["calculation_settings"]))
    expected.pop("history_start")
    assert settings == expected
    assert measure["reference_rules"] == trial["reference_rules"]
    assert (measure["target_start"], measure["target_end"]) == ("2025-01-01", "2025-12-31")
