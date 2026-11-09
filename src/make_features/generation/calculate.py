"""Assemble feature-owned calculations and project them to the existing audit."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from make_features.catalog.registry import FeatureRegistry
from make_features.contracts.observations import (
    CalculatedValues,
    CalculationParameters,
    ObservationInput,
)
from make_features.contracts.types import FeatureBatchInput, FeatureBuildResult, FeatureGroupInput
from make_features.explanatory_variables import build_explanatory_variables
from make_features.generation.chronological import ChronologicalInvariantError
from make_features.generation.observations import CalculationContext, prepare_context
from make_features.validation.values import is_missing


@dataclass(frozen=True, slots=True)
class FeatureCalculationResult:
    """Pair existing audited middle rows with the complete mixed-source manifest."""

    built: FeatureBuildResult
    manifests: tuple[Mapping[str, CalculatedValues], ...]
    parameters: CalculationParameters
    source_missing_reasons: tuple[Mapping[str, Mapping[str, str]], ...]


class FeatureCalculationValueError(ValueError):
    """Identify a calculator-owned ValueError without masking invariant failures."""

    def __init__(self, feature_name: str, message: str) -> None:
        super().__init__(message)
        self.feature_name = feature_name


def calculate_features(
    observations: Sequence[ObservationInput],
    parameters: CalculationParameters,
    *,
    registry: FeatureRegistry,
) -> FeatureCalculationResult:
    """Calculate every registered group, without choosing model input columns."""
    return _calculate(observations, parameters, registry=registry, reference=False)


def calculate_reference_features(
    observations: Sequence[ObservationInput],
    parameters: CalculationParameters,
    *,
    registry: FeatureRegistry,
) -> FeatureCalculationResult:
    """Share all 21 formulas under the explicitly assumed reference boundary."""
    return _calculate(observations, parameters, registry=registry, reference=True)


def calculate_reference_context(
    context: CalculationContext, *, registry: FeatureRegistry
) -> FeatureCalculationResult:
    """Calculate one prevalidated chronological target and identify calculator holds."""
    return _calculate_contexts(
        (context,),
        context.parameters,
        registry=registry,
        identify_value_errors=True,
    )


def _calculate(
    observations: Sequence[ObservationInput],
    parameters: CalculationParameters,
    *,
    registry: FeatureRegistry,
    reference: bool,
) -> FeatureCalculationResult:
    if not observations:
        raise ValueError("calculation requires at least one normalized observation input")
    # Prepare lazily, one target at a time, as the original per-race loop did.
    contexts = (prepare_context(source, parameters, reference=reference) for source in observations)
    return _calculate_contexts(contexts, parameters, registry=registry, identify_value_errors=False)


def _calculate_contexts(
    contexts: Iterable[CalculationContext],
    parameters: CalculationParameters,
    *,
    registry: FeatureRegistry,
    identify_value_errors: bool,
) -> FeatureCalculationResult:
    batches: list[FeatureBatchInput] = []
    manifests: list[Mapping[str, CalculatedValues]] = []
    source_missing_reasons: list[Mapping[str, Mapping[str, str]]] = []
    for context in contexts:
        source = context.source
        source_missing_reasons.append(context.history_missing_reasons())
        for kind in ("history", "workouts", "pedigree", "market"):
            context.require_coverage(kind)
        for runner in source.card.runners:
            groups = {}
            manifest = {}
            for registration in registry.features:
                try:
                    calculated = registration.calculate(context, runner.horse_id)
                except ChronologicalInvariantError:
                    # Leakage guards must fail the whole build, never become a race hold.
                    raise
                except ValueError as exc:
                    if not identify_value_errors:
                        raise
                    raise FeatureCalculationValueError(
                        registration.definition.name, str(exc)
                    ) from exc
                if not calculated.dependencies:
                    raise ValueError("calculated values require source dependencies")
                feature_id = registration.definition.feature_id
                nonmissing = any(not is_missing(v) for v in calculated.values.values())
                groups[feature_id] = FeatureGroupInput(
                    feature_id=feature_id,
                    values=calculated.values,
                    available_at=max(e.available_at for e in calculated.dependencies)
                    if nonmissing
                    else None,
                    source_event_at=max(e.event_at for e in calculated.dependencies),
                    source_scope="pre_race"
                    if registration.definition.name == "market_characteristics"
                    else "historical",
                    status="confirmed" if nonmissing else "missing",
                    source_race_ids=calculated.historical_race_ids,
                    contains_target_result=False,
                    contains_future_data=False,
                )
                manifest[feature_id] = calculated
            batches.append(
                FeatureBatchInput(source.card.race_id, runner.horse_id, source.freeze_at, groups)
            )
            manifests.append(manifest)
    return FeatureCalculationResult(
        build_explanatory_variables(batches, registry=registry),
        tuple(manifests),
        parameters,
        tuple(source_missing_reasons),
    )
