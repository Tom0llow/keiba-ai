"""Build deterministic synthetic races for Plackett--Luce training tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy as np

from models.dataset.race_arrays import RaceArrays

FEATURE_NAMES = ("signal", "noise", "market_feature")


def synthetic_race_arrays(
    years: Sequence[int],
    *,
    races_per_year: int,
    seed: int,
    signal_scale: float = 1.5,
    field_sizes: Sequence[int] = (6, 8, 10, 12),
    incomplete_market_race: bool = True,
    random_finishes: bool = False,
) -> RaceArrays:
    """Return races whose orders are sampled from PL strengths ``signal_scale * signal``.

    Finishing orders use the Gumbel-max form of Plackett--Luce sampling.
    Market odds are a noisy view of the true win probabilities with a 20%
    takeout; ``market_feature`` repeats those odds as a model feature. When
    requested, the first race of every year lacks one horse's odds, so it is
    not market-complete.
    """
    generator = np.random.default_rng(seed)
    race_ids: list[str] = []
    freeze_at: list[datetime] = []
    labels: list[datetime] = []
    race_years: list[int] = []
    group_sizes: list[int] = []
    horse_ids: list[str] = []
    features: list[list[float]] = []
    finishes: list[int] = []
    odds: list[float] = []
    for year in years:
        for race in range(races_per_year):
            size = int(field_sizes[race % len(field_sizes)])
            start = datetime(year, 1, 5, 6, 0, tzinfo=UTC) + timedelta(
                days=race % 340, minutes=race
            )
            race_ids.append(f"{year}{race:012d}")
            freeze_at.append(start - timedelta(minutes=5))
            labels.append(start + timedelta(days=1))
            race_years.append(year)
            group_sizes.append(size)
            signal = generator.normal(size=size)
            strength = signal_scale * signal
            if random_finishes:
                order = generator.permutation(size)
            else:
                order = np.argsort(-(strength + generator.gumbel(size=size)))
            positions = np.empty(size, dtype=np.int64)
            positions[order] = np.arange(1, size + 1)
            win = np.exp(strength - strength.max())
            win /= win.sum()
            noisy = win * np.exp(generator.normal(scale=0.3, size=size))
            race_odds = 0.8 / (noisy / noisy.sum())
            race_odds = np.maximum(race_odds, 1.0)
            if incomplete_market_race and race == 0:
                race_odds[0] = np.nan
            for horse in range(size):
                horse_ids.append(f"h{year}-{race}-{horse}")
                features.append(
                    [float(signal[horse]), float(generator.normal()), float(race_odds[horse])]
                )
                finishes.append(int(positions[horse]))
                odds.append(float(race_odds[horse]))
    return RaceArrays(
        race_ids=tuple(race_ids),
        freeze_at=tuple(freeze_at),
        label_usable_after=tuple(labels),
        years=np.asarray(race_years, dtype=np.int64),
        group_sizes=np.asarray(group_sizes, dtype=np.int64),
        horse_ids=tuple(horse_ids),
        features=np.asarray(features, dtype=np.float64),
        feature_names=FEATURE_NAMES,
        finish_positions=np.asarray(finishes, dtype=np.int64),
        market_odds=np.asarray(odds, dtype=np.float64),
    )


def pl_parameters() -> dict[str, object]:
    """Return small deterministic LightGBM parameters for PL tests."""
    return {
        "learning_rate": 0.1,
        "num_leaves": 7,
        "min_data_in_leaf": 20,
        "num_threads": 1,
        "seed": 0,
        "deterministic": True,
        "force_col_wise": True,
    }
