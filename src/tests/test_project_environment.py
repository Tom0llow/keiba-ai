"""Smoke tests for the non-package bootstrap environment."""

from importlib.metadata import PackageNotFoundError, distribution

import pytest


def test_project_is_not_installed_as_a_distribution() -> None:
    """Verify the synced environment has no installable project artifact."""
    with pytest.raises(PackageNotFoundError):
        distribution("keiba-ai")
