"""Smoke tests for the bootstrap package."""

import keiba_ai


def test_package_can_be_imported() -> None:
    assert keiba_ai.__name__ == "keiba_ai"
