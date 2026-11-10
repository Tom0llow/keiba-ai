"""Calculate stable top-three Plackett--Luce probabilities and derivatives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise, permutations

import numpy as np
import numpy.typing as npt

type BoolArray = npt.NDArray[np.bool_]
type FloatArray = npt.NDArray[np.float64]
type IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class RaceLayout:
    """Describe contiguous races as a padded row matrix.

    ``row_indices`` maps valid padded cells to the original row order. Padding
    cells contain ``-1`` and are false in ``mask``.
    """

    group_sizes: tuple[int, ...]
    offsets: IntArray = field(init=False, repr=False)
    row_indices: IntArray = field(init=False, repr=False)
    mask: BoolArray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate group sizes and build the padded race layout."""
        if not self.group_sizes:
            raise ValueError("group_sizes must contain at least one race")
        if any(
            isinstance(group_size, bool) or not isinstance(group_size, int)
            for group_size in self.group_sizes
        ):
            raise ValueError("group sizes must be integers")
        if any(group_size < 3 for group_size in self.group_sizes):
            raise ValueError("group sizes must be at least 3")

        normalized_sizes = tuple(self.group_sizes)
        offsets = np.empty(len(normalized_sizes) + 1, dtype=np.int64)
        offsets[0] = 0
        offsets[1:] = np.cumsum(np.asarray(normalized_sizes, dtype=np.int64))
        row_indices = np.full((len(normalized_sizes), max(normalized_sizes)), -1, dtype=np.int64)
        for race_index, (start, stop) in enumerate(pairwise(offsets)):
            row_indices[race_index, : stop - start] = np.arange(start, stop, dtype=np.int64)

        object.__setattr__(self, "group_sizes", normalized_sizes)
        object.__setattr__(self, "offsets", offsets)
        object.__setattr__(self, "row_indices", row_indices)
        object.__setattr__(self, "mask", row_indices >= 0)

    @classmethod
    def from_group_sizes(cls, group_sizes: Sequence[int]) -> RaceLayout:
        """Build a layout from contiguous race group sizes."""
        return cls(tuple(group_sizes))

    @property
    def race_count(self) -> int:
        """Return the number of races."""
        return len(self.group_sizes)

    @property
    def row_count(self) -> int:
        """Return the number of unpadded rows."""
        return int(self.offsets[-1])


@dataclass(frozen=True)
class Top3PlackettLuce:
    """Hold top-three NLL values and derivatives in original row order."""

    total_nll: float
    race_nll: FloatArray
    stage_nll: FloatArray
    gradient: FloatArray
    hessian_diagonal: FloatArray


@dataclass(frozen=True)
class MarginalProbabilities:
    """Hold each horse's probability of winning, top-two, and top-three finishes."""

    win: FloatArray
    top2: FloatArray
    top3: FloatArray


@dataclass(frozen=True)
class CombinationLogProbabilities:
    """Hold race-level log probabilities for the actual top-three combinations."""

    win: FloatArray
    exacta: FloatArray
    quinella: FloatArray
    trifecta: FloatArray
    trio: FloatArray


def top3_plackett_luce(
    scores: npt.ArrayLike,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    *,
    temperature: float = 1.0,
) -> Top3PlackettLuce:
    """Return top-three PL NLL values and score derivatives.

    The returned gradient and Hessian diagonal differentiate the total NLL
    with respect to the supplied, unscaled scores.
    """
    scaled_scores, temperature_value = _scaled_scores(scores, layout, temperature)
    positions = padded_finish_positions(finish_positions, layout)
    ordered_slots = np.argsort(positions, axis=1)[:, :3]
    padded_scores = _pad_scores(scaled_scores, layout)
    probabilities, stage_nll = _stage_probabilities(padded_scores, ordered_slots, layout.mask)

    padded_gradient = probabilities.sum(axis=0)
    race_indices = np.arange(layout.race_count)
    for stage_index in range(3):
        padded_gradient[race_indices, ordered_slots[:, stage_index]] -= 1.0
    padded_hessian = (probabilities * (1.0 - probabilities)).sum(axis=0)

    return Top3PlackettLuce(
        total_nll=float(stage_nll.sum()),
        race_nll=stage_nll.sum(axis=1),
        stage_nll=stage_nll,
        gradient=_rows_from_padded(padded_gradient, layout) / temperature_value,
        hessian_diagonal=_rows_from_padded(padded_hessian, layout)
        / (temperature_value * temperature_value),
    )


def top3_marginal_probabilities(
    scores: npt.ArrayLike,
    layout: RaceLayout,
    *,
    temperature: float = 1.0,
    chunk_races: int = 256,
) -> MarginalProbabilities:
    """Return PL win, top-two, and top-three marginal probabilities.

    Races are calculated in chunks so the temporary conditional-probability
    matrix is bounded by ``chunk_races * max_group_size ** 2``.
    """
    scaled_scores, _ = _scaled_scores(scores, layout, temperature)
    if isinstance(chunk_races, bool) or not isinstance(chunk_races, int) or chunk_races < 1:
        raise ValueError("chunk_races must be a positive integer")

    padded_scores = _pad_scores(scaled_scores, layout)
    padded_win = np.zeros_like(padded_scores)
    padded_top2 = np.zeros_like(padded_scores)
    padded_top3 = np.zeros_like(padded_scores)
    for start in range(0, layout.race_count, chunk_races):
        stop = min(start + chunk_races, layout.race_count)
        win, top2, top3 = _chunk_marginal_probabilities(
            padded_scores[start:stop], layout.mask[start:stop]
        )
        padded_win[start:stop] = win
        padded_top2[start:stop] = top2
        padded_top3[start:stop] = top3

    return MarginalProbabilities(
        win=_rows_from_padded(padded_win, layout),
        top2=_rows_from_padded(padded_top2, layout),
        top3=_rows_from_padded(padded_top3, layout),
    )


def top3_combination_log_probabilities(
    scores: npt.ArrayLike,
    finish_positions: npt.ArrayLike,
    layout: RaceLayout,
    *,
    temperature: float = 1.0,
) -> CombinationLogProbabilities:
    """Return log probabilities of the actual win and top-three combinations."""
    scaled_scores, _ = _scaled_scores(scores, layout, temperature)
    positions = padded_finish_positions(finish_positions, layout)
    ordered_slots = np.argsort(positions, axis=1)[:, :3]
    padded_scores = _pad_scores(scaled_scores, layout)

    winning_order = ordered_slots[:, :1]
    exacta_order = ordered_slots[:, :2]
    trifecta_order = ordered_slots
    reverse_exacta_order = exacta_order[:, ::-1]
    quinella = np.logaddexp(
        _log_order_probability(padded_scores, exacta_order, layout.mask),
        _log_order_probability(padded_scores, reverse_exacta_order, layout.mask),
    )
    trio_orders = np.stack(
        [ordered_slots[:, permutation] for permutation in permutations(range(3))],
        axis=0,
    )
    trio_log_probabilities = np.stack(
        [_log_order_probability(padded_scores, order, layout.mask) for order in trio_orders],
        axis=0,
    )

    return CombinationLogProbabilities(
        win=_log_order_probability(padded_scores, winning_order, layout.mask),
        exacta=_log_order_probability(padded_scores, exacta_order, layout.mask),
        quinella=quinella,
        trifecta=_log_order_probability(padded_scores, trifecta_order, layout.mask),
        trio=np.logaddexp.reduce(trio_log_probabilities, axis=0),
    )


def _scaled_scores(
    scores: npt.ArrayLike,
    layout: RaceLayout,
    temperature: float,
) -> tuple[FloatArray, float]:
    temperature_value = _temperature_value(temperature)
    values = np.asarray(scores, dtype=np.float64)
    if values.ndim != 1 or len(values) != layout.row_count:
        raise ValueError("scores must be a one-dimensional array matching the layout rows")
    if not np.all(np.isfinite(values)):
        raise ValueError("scores must be finite")
    scaled_scores = values / temperature_value
    if not np.all(np.isfinite(scaled_scores)):
        raise ValueError("scores divided by temperature must be finite")
    return scaled_scores, temperature_value


def _temperature_value(temperature: float) -> float:
    if isinstance(temperature, bool):
        raise ValueError("temperature must be a positive finite number")
    try:
        value = float(temperature)
    except (TypeError, ValueError) as exc:
        raise ValueError("temperature must be a positive finite number") from exc
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("temperature must be a positive finite number")
    return value


def padded_finish_positions(finish_positions: npt.ArrayLike, layout: RaceLayout) -> IntArray:
    """Validate 1..n finishing positions per race and return them in the padded layout."""
    values = np.asarray(finish_positions)
    if values.ndim != 1 or len(values) != layout.row_count:
        raise ValueError(
            "finish_positions must be a one-dimensional array matching the layout rows"
        )
    if np.issubdtype(values.dtype, np.bool_) or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("finish_positions must contain integers")

    padded_positions = np.full(layout.mask.shape, layout.mask.shape[1] + 1, dtype=np.int64)
    padded_positions[layout.mask] = values.astype(np.int64, copy=False)
    expected_positions = np.where(
        layout.mask,
        np.arange(1, layout.mask.shape[1] + 1, dtype=np.int64),
        layout.mask.shape[1] + 1,
    )
    if not np.array_equal(np.sort(padded_positions, axis=1), expected_positions):
        raise ValueError("finish_positions must be a 1..n permutation within every race")
    return padded_positions


def _pad_scores(scores: FloatArray, layout: RaceLayout) -> FloatArray:
    padded_scores = np.full(layout.mask.shape, -np.inf, dtype=np.float64)
    padded_scores[layout.mask] = scores
    return padded_scores


def _rows_from_padded(values: FloatArray, layout: RaceLayout) -> FloatArray:
    rows = np.empty(layout.row_count, dtype=np.float64)
    rows[layout.row_indices[layout.mask]] = values[layout.mask]
    return rows


def _stage_probabilities(
    padded_scores: FloatArray,
    ordered_slots: IntArray,
    mask: BoolArray,
) -> tuple[FloatArray, FloatArray]:
    active = mask.copy()
    race_indices = np.arange(padded_scores.shape[0])
    probabilities = np.empty((3, *padded_scores.shape), dtype=np.float64)
    stage_nll = np.empty((padded_scores.shape[0], 3), dtype=np.float64)
    for stage_index in range(3):
        stage_scores = np.where(active, padded_scores, -np.inf)
        maxima = stage_scores.max(axis=1)
        weights = np.exp(stage_scores - maxima[:, np.newaxis])
        normalizers = weights.sum(axis=1)
        probabilities[stage_index] = weights / normalizers[:, np.newaxis]
        selected_slots = ordered_slots[:, stage_index]
        stage_nll[:, stage_index] = (
            maxima + np.log(normalizers) - stage_scores[race_indices, selected_slots]
        )
        active[race_indices, selected_slots] = False
    return probabilities, stage_nll


def _chunk_marginal_probabilities(
    padded_scores: FloatArray,
    mask: BoolArray,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    win = _softmax(padded_scores, axis=1)
    second_total = np.zeros_like(padded_scores)
    third_total = np.zeros_like(padded_scores)
    chunk_size, max_group_size = padded_scores.shape

    for first_slot in range(max_group_size):
        after_first = padded_scores.copy()
        after_first[:, first_slot] = -np.inf
        second = _softmax(after_first, axis=1)
        second_path = win[:, first_slot, np.newaxis] * second
        second_total += second_path

        after_second = np.broadcast_to(
            after_first[:, np.newaxis, :], (chunk_size, max_group_size, max_group_size)
        ).copy()
        after_second[:, np.arange(max_group_size), np.arange(max_group_size)] = -np.inf
        third = _softmax(after_second, axis=2)
        third_total += (second_path[:, :, np.newaxis] * third).sum(axis=1)

    top2 = win + second_total
    top3 = top2 + third_total
    return win * mask, top2 * mask, top3 * mask


def _softmax(values: FloatArray, *, axis: int) -> FloatArray:
    maxima = values.max(axis=axis, keepdims=True)
    weights = np.exp(values - maxima)
    return weights / weights.sum(axis=axis, keepdims=True)


def _log_order_probability(
    padded_scores: FloatArray,
    ordered_slots: IntArray,
    mask: BoolArray,
) -> FloatArray:
    active = mask.copy()
    race_indices = np.arange(padded_scores.shape[0])
    log_probability = np.zeros(padded_scores.shape[0], dtype=np.float64)
    for stage_index in range(ordered_slots.shape[1]):
        stage_scores = np.where(active, padded_scores, -np.inf)
        maxima = stage_scores.max(axis=1)
        normalizers = np.exp(stage_scores - maxima[:, np.newaxis]).sum(axis=1)
        selected_slots = ordered_slots[:, stage_index]
        log_probability += stage_scores[race_indices, selected_slots] - maxima - np.log(normalizers)
        active[race_indices, selected_slots] = False
    return log_probability


__all__ = [
    "CombinationLogProbabilities",
    "MarginalProbabilities",
    "RaceLayout",
    "Top3PlackettLuce",
    "padded_finish_positions",
    "top3_combination_log_probabilities",
    "top3_marginal_probabilities",
    "top3_plackett_luce",
]
