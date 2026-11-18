"""Name ADR-044's four estimation methods and select one for a year (ADR-044 Decision 4).

Pure and standard library only; the backtest and the race-day estimator share it.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Literal

Method = Literal["pl_mid", "blend_mid", "pl_width", "blend_width"]
# The fixed order also breaks ties: the current ADR-043 method first, the most changed last.
METHODS: tuple[Method, ...] = ("pl_mid", "blend_mid", "pl_width", "blend_width")
BASELINE_METHOD: Method = "pl_mid"


def select_method(
    flat: Mapping[Method, Mapping[int, tuple[int, int]]],
    years: Sequence[int],
    year: int,
    *,
    available: Collection[Method],
) -> tuple[Method, tuple[int, ...]]:
    """Return the method for ``year`` and its comparison years (ADR-044 Decision 4).

    ``flat`` maps each method to its flat ``(receipt_yen, stake_yen)`` of every year in
    which it ran; ``available`` holds the methods that can run in ``year`` itself. The
    comparison years are the ``years`` before ``year`` that every method covers. The
    method with the highest pooled flat recovery rate wins, compared exactly in
    integers with ties to the earlier method; an unbought method is skipped. Without
    comparison years or a bought method, or when the winner cannot run in ``year``, the
    baseline ``pl_mid`` is chosen.
    """
    comparison = tuple(y for y in years if y < year and all(y in flat.get(m, {}) for m in METHODS))
    best: Method = BASELINE_METHOD
    best_totals: tuple[int, int] | None = None
    for method in METHODS if comparison else ():
        receipt = sum(flat[method][y][0] for y in comparison)
        stake = sum(flat[method][y][1] for y in comparison)
        if stake == 0:
            continue
        # receipt/stake > best_receipt/best_stake, compared exactly in integers.
        if best_totals is None or receipt * best_totals[1] > best_totals[0] * stake:
            best, best_totals = method, (receipt, stake)
    if best not in available:
        best = BASELINE_METHOD
    return best, comparison


__all__ = ["BASELINE_METHOD", "METHODS", "Method", "select_method"]
