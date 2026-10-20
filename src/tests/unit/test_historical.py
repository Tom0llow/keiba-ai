"""Tests for historical race and odds retrieval orchestration."""

from datetime import date

import pytest

from domain.race_key import RaceKey


def test_manual_race_key_requires_two_digit_components() -> None:
    with pytest.raises(ValueError, match="jyo_code must be a two-digit string"):
        RaceKey(date(2026, 10, 4), "5", "04", "08", "11")
