"""Every missing-adjustment reason follows from the as-of baseline summary."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import cast

import pytest

from make_features.condition_adjusted_ability import _latest_adjustment_reason
from make_features.generation.observations import JST, BaselineStatistics, CalculationContext


def _summary(**values: object) -> BaselineStatistics:
    fields: dict[str, object] = {
        "matched_count": 3,
        "unknown": False,
        "clock_mean": 95.0,
        "clock_std": 1.0,
        "velocity_mean": 16.8,
        "velocity_std": 0.2,
        "unmeasured_clock": False,
        "zero_clock": False,
        "dependencies": (),
    }
    fields.update(values)
    return BaselineStatistics(**fields)  # type: ignore[arg-type]


class _Context:
    def __init__(self, starts: tuple[object, ...], summary: BaselineStatistics) -> None:
        self._starts = starts
        self._summary = summary

    def history(self, horse_id: str, *, count: bool = True) -> tuple[object, ...]:
        return self._starts

    def baseline_statistics(self, started_at: datetime, conditions: object) -> BaselineStatistics:
        return self._summary


def _reason(
    summary: BaselineStatistics, *, velocity: bool = False, elapsed: float | None = 95.0
) -> str:
    race = SimpleNamespace(started_at=datetime(2026, 12, 13, 15, tzinfo=JST), conditions=object())
    runner = SimpleNamespace(elapsed_sec=elapsed, missing_reasons={"elapsed_sec": "source_null"})
    context = cast(CalculationContext, _Context(((race, runner),), summary))
    return _latest_adjustment_reason(context, "horse", velocity=velocity)


@pytest.mark.parametrize(
    ("summary", "velocity", "expected"),
    [
        (_summary(unknown=True), False, "unknown_reference_condition"),
        (_summary(matched_count=0), False, "no_prior_condition_reference"),
        (_summary(matched_count=1), False, "insufficient_reference_count"),
        (_summary(unmeasured_clock=True), False, "unmeasured_reference_clock"),
        (_summary(clock_std=0.0), False, "zero_variance_reference"),
        (_summary(velocity_std=0.0), True, "zero_variance_reference"),
        (_summary(velocity_std=0.0), False, "undefined_adjustment"),
        (_summary(), True, "undefined_adjustment"),
    ],
)
def test_each_baseline_state_maps_to_its_documented_reason(
    summary: BaselineStatistics, velocity: bool, expected: str
) -> None:
    assert _reason(summary, velocity=velocity) == expected


def test_missing_history_and_unmeasured_own_clock_take_precedence() -> None:
    context = cast(CalculationContext, _Context((), _summary(unknown=True)))
    assert _latest_adjustment_reason(context, "horse", velocity=False) == "no_history"
    assert _reason(_summary(unknown=True), elapsed=None) == "source_null"


def test_a_zero_winner_clock_still_fails_velocity_reasons_like_the_per_race_division() -> None:
    with pytest.raises(ZeroDivisionError):
        _reason(_summary(zero_clock=True), velocity=True)
    assert _reason(_summary(zero_clock=True), velocity=False) == "undefined_adjustment"
