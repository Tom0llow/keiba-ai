"""Define fixed ranking contracts and pure race grouping and ordering rules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Literal

type TieBreakRule = Literal["score_desc_then_horse_id"]

OBJECTIVE = "lambdarank"
TIE_BREAK_RULE: TieBreakRule = "score_desc_then_horse_id"
LABEL_GAIN = (0, 1, 3, 7)
DEFAULT_LABEL_GAIN: Mapping[int, int] = MappingProxyType(dict(enumerate(LABEL_GAIN)))


def race_group_sizes(race_ids: Iterable[str]) -> tuple[int, ...]:
    """Return group sizes for already validated contiguous race identities."""
    groups: list[int] = []
    current_race: str | None = None
    for race_id in race_ids:
        if race_id != current_race:
            groups.append(1)
            current_race = race_id
        else:
            groups[-1] += 1
    return tuple(groups)


def race_ranges(groups: Sequence[int]) -> tuple[tuple[int, int], ...]:
    """Return row ranges for already validated contiguous race group sizes."""
    ranges: list[tuple[int, int]] = []
    start = 0
    for group in groups:
        stop = start + group
        ranges.append((start, stop))
        start = stop
    return tuple(ranges)


def score_order(
    scores: Sequence[float], horse_ids: Sequence[str], start: int, stop: int
) -> list[int]:
    """Order one validated race by descending score then ascending horse ID."""
    return sorted(range(start, stop), key=lambda index: (-scores[index], horse_ids[index]))
