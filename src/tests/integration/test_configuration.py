"""Tests for shared physical TOML loading and path resolution."""

import tomllib
from pathlib import Path

import pytest

from configuration.data_paths import DataPaths
from configuration.loader import load_toml


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
