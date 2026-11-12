"""Train the final top-three Plackett--Luce model on one reference datamart (ADR-038).

The final fit is the yearly evaluation (ADR-035) without a test year: train runs from
``train_start_year`` through ``valid_year - 1``, ``valid_year`` early-stops the booster
and calibrates the temperature, and the same functions do both. No I/O happens here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

import numpy as np
import numpy.typing as npt

from models.artifacts.pl_model import PLModelRecord
from models.backends.lightgbm import PLBoosterFit, fit_native_pl_booster, validate_pl_parameters
from models.dataset.race_arrays import RaceArrays
from models.evaluation.yearly_folds import FinalFitAudit, plan_final_fit
from models.experiments.pl_evaluation import PLVariant
from models.probability.calibration import TemperatureCalibration, calibrate_temperature
from models.probability.plackett_luce import RaceLayout


@dataclass(frozen=True)
class PLTrainingSettings:
    """Hold the validated settings of one final PL fit."""

    train_start_year: int
    valid_year: int
    variant: PLVariant
    lightgbm: Mapping[str, object]
    num_boost_round: int
    early_stopping_rounds: int
    temperature_bounds: tuple[float, float]

    def __post_init__(self) -> None:
        """Reject reserved LightGBM keys, non-positive rounds and invalid bounds."""
        validate_pl_parameters(self.lightgbm)
        for name in ("train_start_year", "valid_year", "num_boost_round", "early_stopping_rounds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not self.variant.name:
            raise ValueError("PL variant name must be a nonempty string")
        if len(set(self.variant.excluded_columns)) != len(self.variant.excluded_columns):
            raise ValueError("PL variant excluded_columns must be unique")
        lower, upper = self.temperature_bounds
        if not (isfinite(lower) and isfinite(upper) and 0 < lower < upper):
            raise ValueError("temperature_bounds must be finite with 0 < lower < upper")


@dataclass(frozen=True)
class FinalPLFit:
    """Hold the final booster, its temperature, audit and per-column missingness."""

    settings: PLTrainingSettings
    fit: PLBoosterFit
    temperature: TemperatureCalibration
    audit: FinalFitAudit
    feature_names: tuple[str, ...]
    # Whether each column had a missing value in train; LightGBM routes a missing value
    # in a column without one in train to the zero branch, so prediction must reject it.
    nullable_in_training: tuple[bool, ...]
    train_races: int
    train_rows: int
    valid_races: int
    valid_rows: int
    valid_features: npt.NDArray[np.float64]
    valid_scores: npt.NDArray[np.float64]


def variant_columns(available: Sequence[str], variant: PLVariant) -> tuple[str, ...]:
    """Return the datamart columns a variant keeps, in datamart order.

    Raises:
        ValueError: If an excluded column is unknown or every column is excluded.
    """
    unknown = sorted(set(variant.excluded_columns) - set(available))
    if unknown:
        raise ValueError(f"PL variant {variant.name} excludes unknown columns: {unknown!r}")
    kept = tuple(name for name in available if name not in set(variant.excluded_columns))
    if not kept:
        raise ValueError(f"PL variant {variant.name} excludes every column")
    return kept


def train_final_pl(arrays: RaceArrays, settings: PLTrainingSettings) -> FinalPLFit:
    """Fit the final booster and its temperature exactly as one evaluation fold does."""
    names = variant_columns(arrays.feature_names, settings.variant)
    plan = plan_final_fit(
        arrays, train_start_year=settings.train_start_year, valid_year=settings.valid_year
    )
    split = plan.materialize(arrays)
    train = split.train.columns(names)
    valid = split.valid.columns(names)
    nullable = tuple(bool(np.isnan(train.features[:, index]).any()) for index in range(len(names)))
    # LightGBM bins such a value as 0, which would silently shift early stopping and the
    # temperature; prediction rejects the same values (ADR-038).
    unseen = [
        name
        for index, name in enumerate(names)
        if not nullable[index] and np.isnan(valid.features[:, index]).any()
    ]
    if unseen:
        raise ValueError(f"valid year has missing values in columns complete in train: {unseen!r}")
    fit = fit_native_pl_booster(
        train,
        valid,
        parameters=settings.lightgbm,
        num_boost_round=settings.num_boost_round,
        early_stopping_rounds=settings.early_stopping_rounds,
    )
    valid_scores = fit.predict_scores(valid)
    temperature = calibrate_temperature(
        valid_scores,
        valid.finish_positions,
        RaceLayout.from_group_sizes(valid.group_sizes.tolist()),
        temperature_bounds=settings.temperature_bounds,
    )
    return FinalPLFit(
        settings=settings,
        fit=fit,
        temperature=temperature,
        audit=split.audit,
        feature_names=names,
        nullable_in_training=nullable,
        train_races=len(train.race_ids),
        train_rows=int(train.features.shape[0]),
        valid_races=len(valid.race_ids),
        valid_rows=int(valid.features.shape[0]),
        valid_features=valid.features,
        valid_scores=valid_scores,
    )


def pl_model_record(
    final: FinalPLFit,
    *,
    source_datamart: Mapping[str, object],
    provenance: Mapping[str, object],
    config: Mapping[str, object],
) -> PLModelRecord:
    """Describe a final fit for the artifact; the caller supplies the datamart binding."""
    settings = final.settings
    audit = final.audit
    return PLModelRecord(
        feature_names=final.feature_names,
        nullable_in_training=final.nullable_in_training,
        variant=settings.variant.name,
        excluded_columns=settings.variant.excluded_columns,
        best_iteration=final.fit.best_iteration,
        best_valid_nll=final.fit.best_valid_nll,
        num_boost_round=settings.num_boost_round,
        early_stopping_rounds=settings.early_stopping_rounds,
        lightgbm=settings.lightgbm,
        temperature=final.temperature.temperature,
        temperature_bounds=settings.temperature_bounds,
        raw_valid_nll=final.temperature.raw_valid_nll,
        calibrated_valid_nll=final.temperature.calibrated_valid_nll,
        temperature_at_bound=final.temperature.at_bound,
        train_start_year=settings.train_start_year,
        valid_year=settings.valid_year,
        train_races=final.train_races,
        train_rows=final.train_rows,
        valid_races=final.valid_races,
        valid_rows=final.valid_rows,
        purged_train_races=audit.purged_train_races,
        valid_first_freeze_at=audit.valid_first_freeze_at,
        train_max_label_usable_after=audit.train_max_label_usable_after,
        valid_max_label_usable_after=audit.valid_max_label_usable_after,
        label_usable_through=audit.label_usable_through,
        source_datamart=source_datamart,
        provenance=provenance,
        config=config,
    )


__all__ = [
    "FinalPLFit",
    "PLTrainingSettings",
    "pl_model_record",
    "train_final_pl",
    "variant_columns",
]
