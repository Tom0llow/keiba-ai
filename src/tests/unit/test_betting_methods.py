"""Tests for ADR-044 Decision 4's method selection shared with the race-day estimator."""

from __future__ import annotations

from models.betting.methods import METHODS, Method, select_method

ALL = frozenset(METHODS)


def _flat(**rates: dict[int, tuple[int, int]]) -> dict[Method, dict[int, tuple[int, int]]]:
    return {method: rates.get(method, {}) for method in METHODS}


def _every(totals: tuple[int, int]) -> dict[Method, dict[int, tuple[int, int]]]:
    return {method: {2024: totals} for method in METHODS}


def test_without_comparison_years_the_baseline_is_chosen() -> None:
    flat = _flat(pl_mid={}, blend_mid={2024: (900, 100)})

    assert select_method(flat, (2024, 2025), 2025, available=ALL) == ("pl_mid", ())


def test_only_earlier_years_every_method_covers_are_compared() -> None:
    every = {2024: (50, 100), 2025: (60, 100)}
    flat = _flat(
        pl_mid=every,
        blend_mid={2024: (40, 100), 2025: (90, 100)},
        pl_width=every,
        blend_width={2025: (99, 100)},  # 2024 missing: only 2025 is compared
    )

    method, years = select_method(flat, (2024, 2025, 2026), 2026, available=ALL)

    assert years == (2025,)
    assert method == "blend_width"


def test_ties_go_to_the_earlier_method_and_unbought_methods_are_skipped() -> None:
    flat = _flat(
        pl_mid={2024: (0, 0)},
        blend_mid={2024: (70, 100)},
        pl_width={2024: (140, 200)},
        blend_width={2024: (35, 50)},
    )

    assert select_method(flat, (2024,), 2025, available=ALL) == ("blend_mid", (2024,))


def test_an_unavailable_winner_or_nothing_bought_falls_back_to_the_baseline() -> None:
    bought = _every((10, 100))
    bought["blend_width"] = {2024: (90, 100)}
    nothing = _every((0, 0))

    unavailable: frozenset[Method] = frozenset({"pl_mid", "pl_width"})
    assert select_method(bought, (2024,), 2025, available=unavailable) == ("pl_mid", (2024,))
    assert select_method(nothing, (2024,), 2025, available=ALL) == ("pl_mid", (2024,))
