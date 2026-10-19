"""Tests for shared physical TOML loading and path resolution."""

from pathlib import Path

import pytest

from configuration.path_resolver import resolve_path


def test_common_paths_resolve_relative_absolute_and_home(tmp_path: Path) -> None:
    config = tmp_path / "config" / "data.toml"
    assert resolve_path(config, "../raw/race.db", field="raw") == tmp_path / "raw" / "race.db"
    assert resolve_path(config, str(tmp_path), field="raw") == tmp_path
    assert resolve_path(config, "~/race.db", field="raw") == Path.home() / "race.db"


@pytest.mark.parametrize("value", [None, "", "  ", 7, False])
def test_common_paths_preserve_field_specific_errors(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValueError, match=r"\[paths\].raw_db must be a non-empty string"):
        resolve_path(tmp_path / "data.toml", value, field="[paths].raw_db")
