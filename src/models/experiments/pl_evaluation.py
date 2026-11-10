"""Assemble yearly-fold top-three Plackett--Luce training, calibration and evaluation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from time import perf_counter

import numpy as np
import numpy.typing as npt
import pyarrow as pa

from models.backends.lightgbm import fit_native_pl_booster, validate_pl_parameters
from models.dataset.race_arrays import RaceArrays
from models.evaluation.probability_metrics import (
    MarketWinProbabilities,
    RaceProbabilityMetrics,
    market_win_probabilities,
    odds_calibration_table,
    paired_bootstrap_comparison,
    race_probability_metrics,
    top3_probability_calibration_tables,
)
from models.evaluation.yearly_folds import YearlyFold, plan_yearly_folds
from models.probability.calibration import calibrate_temperature
from models.probability.plackett_luce import (
    MarginalProbabilities,
    RaceLayout,
    top3_marginal_probabilities,
)
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1

type FloatArray = npt.NDArray[np.float64]
type Progress = Callable[[Mapping[str, object]], None]

COMPARED_METRICS = (
    "winner_log_loss",
    "multiclass_brier",
    "exacta_log_loss",
    "quinella_log_loss",
    "trifecta_log_loss",
    "trio_log_loss",
)
PREDICTION_SCHEMA = pa.schema(
    [
        pa.field("variant", pa.string(), nullable=False),
        pa.field("test_year", pa.int64(), nullable=False),
        pa.field("race_id", pa.string(), nullable=False),
        pa.field("horse_id", pa.string(), nullable=False),
        pa.field("finish_position", pa.int64(), nullable=False),
        pa.field("score", pa.float64(), nullable=False),
        pa.field("temperature", pa.float64(), nullable=False),
        pa.field("p_win", pa.float64(), nullable=False),
        pa.field("p_top2", pa.float64(), nullable=False),
        pa.field("p_top3", pa.float64(), nullable=False),
        pa.field("market_win_odds", pa.float64(), nullable=True),
        pa.field("market_q", pa.float64(), nullable=True),
        pa.field("in_jra_flat_graded_stakes", pa.bool_(), nullable=False),
    ]
)


@dataclass(frozen=True)
class PLVariant:
    """Name one feature set by the datamart columns it excludes."""

    name: str
    excluded_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class PLEvaluationSettings:
    """Hold the validated settings of one yearly-fold PL evaluation."""

    train_start_year: int
    test_years: tuple[int, ...]
    variants: tuple[PLVariant, ...]
    lightgbm: Mapping[str, object]
    num_boost_round: int
    early_stopping_rounds: int
    temperature_bounds: tuple[float, float]
    probability_chunk_races: int
    bootstrap_resamples: int
    bootstrap_seed: int
    bootstrap_confidence: float
    probability_bands: tuple[float, ...]
    odds_bands: tuple[float, ...]

    def __post_init__(self) -> None:
        """Reject empty or ambiguous variants."""
        if not self.variants:
            raise ValueError("at least one PL variant is required")
        names = [variant.name for variant in self.variants]
        if any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("PL variant names must be unique nonempty strings")
        for variant in self.variants:
            if len(set(variant.excluded_columns)) != len(variant.excluded_columns):
                raise ValueError("PL variant excluded_columns must be unique")
        validate_pl_parameters(self.lightgbm)
        for name in ("num_boost_round", "early_stopping_rounds", "probability_chunk_races"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class PLEvaluation:
    """Hold the JSON-compatible evaluation report and per-horse test predictions."""

    report: dict[str, object]
    predictions: pa.Table


@dataclass
class _Pooled:
    all_raw: list[RaceProbabilityMetrics] = field(default_factory=list)
    all_calibrated: list[RaceProbabilityMetrics] = field(default_factory=list)
    complete_raw: list[RaceProbabilityMetrics] = field(default_factory=list)
    complete_calibrated: list[RaceProbabilityMetrics] = field(default_factory=list)
    market: list[RaceProbabilityMetrics] = field(default_factory=list)


@dataclass
class _PooledSubset(_Pooled):
    calibrated_marginals: list[MarginalProbabilities] = field(default_factory=list)
    market_marginals: list[MarginalProbabilities] = field(default_factory=list)
    finish_positions: list[npt.NDArray[np.int64]] = field(default_factory=list)
    group_sizes: list[npt.NDArray[np.int64]] = field(default_factory=list)


@dataclass(frozen=True)
class _SubsetContext:
    race_indices: npt.NDArray[np.int64]
    complete_indices: npt.NDArray[np.int64]
    complete: RaceArrays | None
    complete_rows: npt.NDArray[np.bool_] | None
    market_metrics: RaceProbabilityMetrics | None
    market_marginals: MarginalProbabilities | None
    market_calibration: dict[str, object] | None


def evaluate_pl(
    arrays: RaceArrays,
    settings: PLEvaluationSettings,
    *,
    race_subsets: Mapping[str, frozenset[str]],
    progress: Progress | None = None,
) -> PLEvaluation:
    """Train, calibrate and evaluate every variant on every yearly fold.

    Each fold trains on its train races, early-stops and calibrates one
    temperature on its valid races, and scores only its test races. Test
    finishing positions are used only to calculate metrics. The market
    baseline uses normalized inverse win odds only in races where every horse
    has finite positive odds; exotic baselines expand that market with the
    same Plackett--Luce (Harville) formulas.

    Args:
        race_subsets: Named race identifiers to report alongside the full test
            population. It must contain ``jra_flat_graded_stakes_v1``, which also
            fills the predictions' ``in_jra_flat_graded_stakes`` column; an empty
            set means every test race was classified as outside the subset.
            Subsets affect test scoring only, never training.

    Raises:
        ValueError: If a variant excludes unknown columns or leaves no feature,
            or if a subset mapping is invalid.
    """
    feature_sets = _feature_sets(arrays.feature_names, settings.variants)
    validated_subsets = _validate_race_subsets(race_subsets)
    # Validate and audit every fold first, then copy one fold at a time: expanding
    # train windows overlap, so holding every fold would multiply peak memory.
    plans = plan_yearly_folds(
        arrays, train_start_year=settings.train_start_year, test_years=settings.test_years
    )
    pooled = {variant.name: _Pooled() for variant in settings.variants}
    pooled_subsets = {
        variant.name: {name: _PooledSubset() for name in validated_subsets}
        for variant in settings.variants
    }
    prediction_tables: list[pa.Table] = []
    fold_reports: list[dict[str, object]] = []
    for plan in plans:
        fold = plan.materialize(arrays)
        fold_reports.append(
            _evaluate_fold(
                fold,
                settings,
                feature_sets,
                validated_subsets,
                pooled,
                pooled_subsets,
                prediction_tables,
                progress,
            )
        )
        del fold
    pooled_report = {
        name: _pooled_report(values, pooled_subsets[name], settings)
        for name, values in pooled.items()
    }
    report: dict[str, object] = {
        "train_start_year": settings.train_start_year,
        "test_years": list(settings.test_years),
        "variants": [
            {
                "name": variant.name,
                "excluded_columns": list(variant.excluded_columns),
                "feature_names": list(feature_sets[variant.name]),
            }
            for variant in settings.variants
        ],
        "market_baseline": "normalized_inverse_win_odds_with_harville_expansion",
        "folds": fold_reports,
        "pooled": pooled_report,
    }
    predictions = (
        pa.concat_tables(prediction_tables)
        if prediction_tables
        else PREDICTION_SCHEMA.empty_table()
    )
    return PLEvaluation(report, predictions)


def _feature_sets(
    feature_names: tuple[str, ...], variants: Sequence[PLVariant]
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for variant in variants:
        unknown = sorted(set(variant.excluded_columns) - set(feature_names))
        if unknown:
            raise ValueError(f"PL variant {variant.name!r} excludes unknown columns: {unknown!r}")
        selected = tuple(name for name in feature_names if name not in variant.excluded_columns)
        if not selected:
            raise ValueError(f"PL variant {variant.name!r} leaves no feature column")
        result[variant.name] = selected
    return result


def _validate_race_subsets(
    race_subsets: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    if not isinstance(race_subsets, Mapping):
        raise ValueError("race_subsets must be a mapping of names to frozensets")
    result: dict[str, frozenset[str]] = {}
    for name, race_ids in race_subsets.items():
        if not isinstance(name, str) or not name:
            raise ValueError("race subset names must be nonempty strings")
        if not isinstance(race_ids, frozenset) or any(
            not isinstance(race_id, str) or not race_id for race_id in race_ids
        ):
            raise ValueError("race subset identifiers must be frozensets of nonempty strings")
        result[name] = race_ids
    if JRA_FLAT_GRADED_STAKES_V1 not in result:
        # The persisted predictions column must never claim "not graded" for
        # races that were not classified at all.
        raise ValueError(f"race_subsets must contain {JRA_FLAT_GRADED_STAKES_V1!r}")
    return result


def _evaluate_fold(
    fold: YearlyFold,
    settings: PLEvaluationSettings,
    feature_sets: Mapping[str, tuple[str, ...]],
    race_subsets: Mapping[str, frozenset[str]],
    pooled: Mapping[str, _Pooled],
    pooled_subsets: Mapping[str, Mapping[str, _PooledSubset]],
    prediction_tables: list[pa.Table],
    progress: Progress | None,
) -> dict[str, object]:
    test = fold.test
    test_layout = _layout(test)
    market = market_win_probabilities(test.market_odds, test_layout)
    complete_indices = np.flatnonzero(market.complete_races)
    market_metrics: RaceProbabilityMetrics | None = None
    market_tables: dict[str, object] | None = None
    if len(complete_indices):
        complete = test.subset(complete_indices.tolist())
        complete_layout = _layout(complete)
        complete_rows = _row_mask(test, market.complete_races)
        market_scores = np.log(market.market_q[complete_rows])
        market_metrics = race_probability_metrics(
            market_scores,
            complete.finish_positions,
            complete_layout,
            probability_chunk_races=settings.probability_chunk_races,
        )
        market_marginals = top3_marginal_probabilities(
            market_scores, complete_layout, chunk_races=settings.probability_chunk_races
        )
        market_tables = _asdict_payload(
            top3_probability_calibration_tables(
                market_marginals,
                complete.finish_positions,
                complete_layout,
                settings.probability_bands,
            )
        )
    subset_contexts = _subset_contexts(test, market, race_subsets, settings)

    variants: dict[str, object] = {}
    for variant in settings.variants:
        started = perf_counter()
        names = feature_sets[variant.name]
        train = fold.train.columns(names)
        valid = fold.valid.columns(names)
        test_features = test.columns(names)
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
            _layout(valid),
            temperature_bounds=settings.temperature_bounds,
        )
        test_scores = fit.predict_scores(test_features)
        raw = race_probability_metrics(
            test_scores,
            test.finish_positions,
            test_layout,
            probability_chunk_races=settings.probability_chunk_races,
        )
        calibrated = race_probability_metrics(
            test_scores,
            test.finish_positions,
            test_layout,
            temperature=temperature.temperature,
            probability_chunk_races=settings.probability_chunk_races,
        )
        marginals = top3_marginal_probabilities(
            test_scores,
            test_layout,
            temperature=temperature.temperature,
            chunk_races=settings.probability_chunk_races,
        )
        variant_pool = pooled[variant.name]
        variant_pool.all_raw.append(raw)
        variant_pool.all_calibrated.append(calibrated)
        market_report: dict[str, object] | None = None
        if market_metrics is not None:
            complete_raw = _select_races(raw, complete_indices)
            complete_calibrated = _select_races(calibrated, complete_indices)
            variant_pool.complete_raw.append(complete_raw)
            variant_pool.complete_calibrated.append(complete_calibrated)
            variant_pool.market.append(market_metrics)
            complete_marginals = MarginalProbabilities(
                win=marginals.win[complete_rows],
                top2=marginals.top2[complete_rows],
                top3=marginals.top3[complete_rows],
            )
            market_report = _market_report(
                complete_raw,
                complete_calibrated,
                market_metrics,
                settings,
                calibration=_asdict_payload(
                    top3_probability_calibration_tables(
                        complete_marginals,
                        complete.finish_positions,
                        complete_layout,
                        settings.probability_bands,
                    )
                ),
            )
        subset_reports = _variant_subset_reports(
            subset_contexts,
            raw,
            calibrated,
            marginals,
            settings,
            pooled_subsets[variant.name],
        )
        variants[variant.name] = {
            "feature_names": list(names),
            "best_iteration": fit.best_iteration,
            "best_valid_nll": fit.best_valid_nll,
            "temperature": asdict(temperature),
            "all_test_races": {
                "raw": _summary(raw),
                "calibrated": _summary(calibrated),
            },
            "market_complete_races": market_report,
            "subsets": subset_reports,
            "calibration": {
                "probability": _asdict_payload(
                    top3_probability_calibration_tables(
                        marginals, test.finish_positions, test_layout, settings.probability_bands
                    )
                ),
                "odds": [
                    asdict(item)
                    for item in odds_calibration_table(
                        test.market_odds,
                        marginals.win,
                        market.market_q,
                        test.finish_positions,
                        test_layout,
                        settings.odds_bands,
                    )
                ],
            },
        }
        prediction_tables.append(
            _prediction_table(
                variant.name,
                fold.test_year,
                test,
                test_scores,
                temperature.temperature,
                marginals.win,
                marginals.top2,
                marginals.top3,
                market.market_q,
                race_subsets,
            )
        )
        if progress is not None:
            progress(
                {
                    "variant": variant.name,
                    "test_year": fold.test_year,
                    "best_iteration": fit.best_iteration,
                    "temperature": temperature.temperature,
                    "fold_seconds": perf_counter() - started,
                }
            )

    audit = fold.audit
    return {
        "test_year": fold.test_year,
        "valid_year": fold.test_year - 1,
        "train_years": [settings.train_start_year, fold.test_year - 2],
        "counts": {
            "train_races": len(fold.train.race_ids),
            "train_rows": len(fold.train.horse_ids),
            "train_purged_races": audit.purged_train_races,
            "valid_races": len(fold.valid.race_ids),
            "valid_rows": len(fold.valid.horse_ids),
            "valid_purged_races": audit.purged_valid_races,
            "test_races": len(test.race_ids),
            "test_rows": len(test.horse_ids),
            "test_market_complete_races": len(complete_indices),
            "test_market_incomplete_races": market.incomplete_race_count,
        },
        "label_audit": {
            "valid_first_freeze_at": audit.valid_first_freeze_at.isoformat(),
            "test_first_freeze_at": audit.test_first_freeze_at.isoformat(),
            "train_max_label_usable_after": audit.train_max_label_usable_after.isoformat(),
            "valid_max_label_usable_after": audit.valid_max_label_usable_after.isoformat(),
        },
        "market": None if market_metrics is None else _summary(market_metrics),
        "market_calibration": market_tables,
        "subsets": {
            name: None if context is None else _subset_fold_report(context)
            for name, context in subset_contexts.items()
        },
        "variants": variants,
    }


def _market_report(
    raw: RaceProbabilityMetrics,
    calibrated: RaceProbabilityMetrics,
    market: RaceProbabilityMetrics,
    settings: PLEvaluationSettings,
    *,
    calibration: dict[str, object] | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "race_count": len(market.winner_log_loss),
        "raw": _summary(raw),
        "calibrated": _summary(calibrated),
        "market": _summary(market),
        "comparison": {
            "raw": _comparisons(raw, market, settings),
            "calibrated": _comparisons(calibrated, market, settings),
        },
    }
    if calibration is not None:
        report["calibration"] = calibration
    return report


def _subset_contexts(
    test: RaceArrays,
    market: MarketWinProbabilities,
    race_subsets: Mapping[str, frozenset[str]],
    settings: PLEvaluationSettings,
) -> dict[str, _SubsetContext | None]:
    result: dict[str, _SubsetContext | None] = {}
    for name, race_ids in race_subsets.items():
        race_indices = np.asarray(
            [index for index, race_id in enumerate(test.race_ids) if race_id in race_ids],
            dtype=np.int64,
        )
        if not len(race_indices):
            result[name] = None
            continue
        complete_indices = race_indices[market.complete_races[race_indices]]
        if not len(complete_indices):
            result[name] = _SubsetContext(
                race_indices=race_indices,
                complete_indices=complete_indices,
                complete=None,
                complete_rows=None,
                market_metrics=None,
                market_marginals=None,
                market_calibration=None,
            )
            continue
        complete_mask = np.zeros(len(test.race_ids), dtype=np.bool_)
        complete_mask[complete_indices] = True
        complete_rows = _row_mask(test, complete_mask)
        complete = test.subset(complete_indices.tolist())
        complete_layout = _layout(complete)
        market_scores = np.log(market.market_q[complete_rows])
        market_metrics = race_probability_metrics(
            market_scores,
            complete.finish_positions,
            complete_layout,
            probability_chunk_races=settings.probability_chunk_races,
        )
        market_marginals = top3_marginal_probabilities(
            market_scores,
            complete_layout,
            chunk_races=settings.probability_chunk_races,
        )
        result[name] = _SubsetContext(
            race_indices=race_indices,
            complete_indices=complete_indices,
            complete=complete,
            complete_rows=complete_rows,
            market_metrics=market_metrics,
            market_marginals=market_marginals,
            market_calibration=_asdict_payload(
                top3_probability_calibration_tables(
                    market_marginals,
                    complete.finish_positions,
                    complete_layout,
                    settings.probability_bands,
                )
            ),
        )
    return result


def _subset_fold_report(context: _SubsetContext) -> dict[str, object]:
    """Return model-independent subset counts and market calibration."""
    return {
        "race_count": len(context.race_indices),
        "market_complete_race_count": len(context.complete_indices),
        "market_incomplete_race_count": len(context.race_indices) - len(context.complete_indices),
        "market": None if context.market_metrics is None else _summary(context.market_metrics),
        "market_calibration": context.market_calibration,
    }


def _variant_subset_reports(
    contexts: Mapping[str, _SubsetContext | None],
    raw: RaceProbabilityMetrics,
    calibrated: RaceProbabilityMetrics,
    marginals: MarginalProbabilities,
    settings: PLEvaluationSettings,
    pooled: Mapping[str, _PooledSubset],
) -> dict[str, object | None]:
    """Return one variant's subset reports and retain their pooled inputs."""
    result: dict[str, object | None] = {}
    for name, context in contexts.items():
        if context is None:
            result[name] = None
            continue
        subset_pool = pooled[name]
        subset_raw = _select_races(raw, context.race_indices)
        subset_calibrated = _select_races(calibrated, context.race_indices)
        subset_pool.all_raw.append(subset_raw)
        subset_pool.all_calibrated.append(subset_calibrated)
        market_report: dict[str, object] | None = None
        if (
            context.complete is not None
            and context.complete_rows is not None
            and context.market_metrics is not None
            and context.market_marginals is not None
        ):
            complete_raw = _select_races(raw, context.complete_indices)
            complete_calibrated = _select_races(calibrated, context.complete_indices)
            complete_marginals = MarginalProbabilities(
                win=marginals.win[context.complete_rows],
                top2=marginals.top2[context.complete_rows],
                top3=marginals.top3[context.complete_rows],
            )
            subset_pool.complete_raw.append(complete_raw)
            subset_pool.complete_calibrated.append(complete_calibrated)
            subset_pool.market.append(context.market_metrics)
            subset_pool.calibrated_marginals.append(complete_marginals)
            subset_pool.market_marginals.append(context.market_marginals)
            subset_pool.finish_positions.append(context.complete.finish_positions)
            subset_pool.group_sizes.append(context.complete.group_sizes)
            market_report = _market_report(
                complete_raw,
                complete_calibrated,
                context.market_metrics,
                settings,
                calibration=_subset_calibration(
                    complete_marginals,
                    context.market_marginals,
                    context.complete.finish_positions,
                    _layout(context.complete),
                    settings,
                ),
            )
        result[name] = {
            "all_test_races": {
                "raw": _summary(subset_raw),
                "calibrated": _summary(subset_calibrated),
            },
            "market_complete_races": market_report,
        }
    return result


def _subset_calibration(
    calibrated: MarginalProbabilities,
    market: MarginalProbabilities,
    finish_positions: npt.NDArray[np.int64],
    layout: RaceLayout,
    settings: PLEvaluationSettings,
) -> dict[str, object]:
    """Return calibrated-model and market calibration tables for one subset."""
    return {
        "calibrated_model": _asdict_payload(
            top3_probability_calibration_tables(
                calibrated,
                finish_positions,
                layout,
                settings.probability_bands,
            )
        ),
        "market": _asdict_payload(
            top3_probability_calibration_tables(
                market,
                finish_positions,
                layout,
                settings.probability_bands,
            )
        ),
    }


def _pooled_report(
    values: _Pooled,
    subsets: Mapping[str, _PooledSubset],
    settings: PLEvaluationSettings,
) -> dict[str, object]:
    all_raw = _concatenate(values.all_raw)
    all_calibrated = _concatenate(values.all_calibrated)
    report: dict[str, object] = {
        "all_test_races": {"raw": _summary(all_raw), "calibrated": _summary(all_calibrated)},
        "market_complete_races": None,
        "subsets": {
            name: _pooled_subset_report(subset, settings) for name, subset in subsets.items()
        },
    }
    if values.market:
        complete_raw = _concatenate(values.complete_raw)
        complete_calibrated = _concatenate(values.complete_calibrated)
        market = _concatenate(values.market)
        report["market_complete_races"] = _market_report(
            complete_raw, complete_calibrated, market, settings
        )
    return report


def _pooled_subset_report(
    values: _PooledSubset,
    settings: PLEvaluationSettings,
) -> dict[str, object] | None:
    if not values.all_raw:
        return None
    all_raw = _concatenate(values.all_raw)
    all_calibrated = _concatenate(values.all_calibrated)
    report: dict[str, object] = {
        "all_test_races": {"raw": _summary(all_raw), "calibrated": _summary(all_calibrated)},
        "market_complete_races": None,
    }
    if values.market:
        complete_raw = _concatenate(values.complete_raw)
        complete_calibrated = _concatenate(values.complete_calibrated)
        market = _concatenate(values.market)
        finish_positions = np.concatenate(values.finish_positions)
        layout = RaceLayout.from_group_sizes(np.concatenate(values.group_sizes).tolist())
        report["market_complete_races"] = _market_report(
            complete_raw,
            complete_calibrated,
            market,
            settings,
            calibration=_subset_calibration(
                _concatenate_marginals(values.calibrated_marginals),
                _concatenate_marginals(values.market_marginals),
                finish_positions,
                layout,
                settings,
            ),
        )
    return report


def _comparisons(
    model: RaceProbabilityMetrics,
    market: RaceProbabilityMetrics,
    settings: PLEvaluationSettings,
) -> dict[str, object]:
    return {
        name: asdict(
            paired_bootstrap_comparison(
                getattr(model, name),
                getattr(market, name),
                resamples=settings.bootstrap_resamples,
                seed=settings.bootstrap_seed,
                confidence=settings.bootstrap_confidence,
            )
        )
        for name in COMPARED_METRICS
    }


def _summary(metrics: RaceProbabilityMetrics) -> dict[str, object]:
    return {
        "race_count": len(metrics.winner_log_loss),
        **{name: float(np.mean(getattr(metrics, name))) for name in COMPARED_METRICS},
        "stage_nll": [float(value) for value in metrics.stage_nll.mean(axis=0)],
    }


def _select_races(
    metrics: RaceProbabilityMetrics, indices: npt.NDArray[np.int64]
) -> RaceProbabilityMetrics:
    return RaceProbabilityMetrics(
        **{name: getattr(metrics, name)[indices] for name in (*COMPARED_METRICS, "stage_nll")}
    )


def _concatenate(values: Sequence[RaceProbabilityMetrics]) -> RaceProbabilityMetrics:
    return RaceProbabilityMetrics(
        **{
            name: np.concatenate([getattr(value, name) for value in values])
            for name in (*COMPARED_METRICS, "stage_nll")
        }
    )


def _concatenate_marginals(values: Sequence[MarginalProbabilities]) -> MarginalProbabilities:
    """Return one horse-row sequence from consecutive race marginal arrays."""
    return MarginalProbabilities(
        win=np.concatenate([value.win for value in values]),
        top2=np.concatenate([value.top2 for value in values]),
        top3=np.concatenate([value.top3 for value in values]),
    )


def _layout(arrays: RaceArrays) -> RaceLayout:
    return RaceLayout.from_group_sizes(arrays.group_sizes.tolist())


def _row_mask(arrays: RaceArrays, race_mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    return np.repeat(race_mask, arrays.group_sizes)


def _asdict_payload(value: object) -> dict[str, object]:
    return {
        name: [asdict(item) for item in getattr(value, name)] for name in ("win", "top2", "top3")
    }


def _nullable(values: FloatArray) -> list[float | None]:
    return [None if np.isnan(value) else float(value) for value in values]


def _prediction_table(
    variant: str,
    test_year: int,
    test: RaceArrays,
    scores: FloatArray,
    temperature: float,
    p_win: FloatArray,
    p_top2: FloatArray,
    p_top3: FloatArray,
    market_q: FloatArray,
    race_subsets: Mapping[str, frozenset[str]],
) -> pa.Table:
    race_ids = np.repeat(np.asarray(test.race_ids, dtype=object), test.group_sizes)
    row_count = len(test.horse_ids)
    return pa.Table.from_pydict(
        {
            "variant": [variant] * row_count,
            "test_year": [test_year] * row_count,
            "race_id": race_ids.tolist(),
            "horse_id": list(test.horse_ids),
            "finish_position": test.finish_positions.tolist(),
            "score": scores.tolist(),
            "temperature": [temperature] * row_count,
            "p_win": p_win.tolist(),
            "p_top2": p_top2.tolist(),
            "p_top3": p_top3.tolist(),
            "market_win_odds": _nullable(test.market_odds),
            "market_q": _nullable(market_q),
            "in_jra_flat_graded_stakes": [
                race_id in race_subsets[JRA_FLAT_GRADED_STAKES_V1] for race_id in race_ids
            ],
        },
        schema=PREDICTION_SCHEMA,
    )


__all__ = [
    "COMPARED_METRICS",
    "PREDICTION_SCHEMA",
    "PLEvaluation",
    "PLEvaluationSettings",
    "PLVariant",
    "evaluate_pl",
]
