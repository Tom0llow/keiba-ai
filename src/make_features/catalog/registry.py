"""Bind validated feature definitions to explicitly registered implementations."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from make_features.basic_conditions_and_weight import (
    BasicConditionsAndWeightBuilder,
    BasicConditionsAndWeightInput,
    calculate_basic_conditions_and_weight,
)
from make_features.condition_adjusted_ability import (
    ConditionAdjustedAbilityBuilder,
    ConditionAdjustedAbilityInput,
    calculate_condition_adjusted_ability,
)
from make_features.condition_suitability import (
    ConditionSuitabilityBuilder,
    ConditionSuitabilityInput,
    calculate_condition_suitability,
)
from make_features.contracts.observations import CalculatedValues
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.expected_race_development import (
    ExpectedRaceDevelopmentBuilder,
    ExpectedRaceDevelopmentInput,
    calculate_expected_race_development,
)
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.generation.observations import CalculationContext
from make_features.hill_and_wood_workouts import (
    HillAndWoodWorkoutsBuilder,
    HillAndWoodWorkoutsInput,
    calculate_hill_and_wood_workouts,
)
from make_features.history_volume_and_missingness import (
    HistoryVolumeAndMissingnessBuilder,
    HistoryVolumeAndMissingnessInput,
    calculate_history_volume_and_missingness,
)
from make_features.jockey_combination import (
    JockeyCombinationBuilder,
    JockeyCombinationInput,
    calculate_jockey_combination,
)
from make_features.jockey_performance import (
    JockeyPerformanceBuilder,
    JockeyPerformanceInput,
    calculate_jockey_performance,
)
from make_features.market_characteristics import (
    MarketCharacteristicsBuilder,
    MarketCharacteristicsInput,
    calculate_market_characteristics,
)
from make_features.opponent_pagerank import (
    OpponentPagerankBuilder,
    OpponentPagerankInput,
    calculate_opponent_pagerank,
)
from make_features.past_body_weight import (
    PastBodyWeightBuilder,
    PastBodyWeightInput,
    calculate_past_body_weight,
)
from make_features.past_lap_and_running_style import (
    PastLapAndRunningStyleBuilder,
    PastLapAndRunningStyleInput,
    calculate_past_lap_and_running_style,
)
from make_features.past_racing_ability import (
    PastRacingAbilityBuilder,
    PastRacingAbilityInput,
    calculate_past_racing_ability,
)
from make_features.pedigree_suitability import (
    PedigreeSuitabilityBuilder,
    PedigreeSuitabilityInput,
    calculate_pedigree_suitability,
)
from make_features.recent_performance import (
    RecentPerformanceBuilder,
    RecentPerformanceInput,
    calculate_recent_performance,
)
from make_features.recent_stability import (
    RecentStabilityBuilder,
    RecentStabilityInput,
    calculate_recent_stability,
)
from make_features.rest_and_condition_change import (
    RestAndConditionChangeBuilder,
    RestAndConditionChangeInput,
    calculate_rest_and_condition_change,
)
from make_features.running_style_and_position import (
    RunningStyleAndPositionBuilder,
    RunningStyleAndPositionInput,
    calculate_running_style_and_position,
)
from make_features.same_gate_and_trainer_relative import (
    SameGateAndTrainerRelativeBuilder,
    SameGateAndTrainerRelativeInput,
    calculate_same_gate_and_trainer_relative,
)
from make_features.trainer_performance import (
    TrainerPerformanceBuilder,
    TrainerPerformanceInput,
    calculate_trainer_performance,
)
from make_features.within_race_relative import (
    WithinRaceRelativeBuilder,
    WithinRaceRelativeInput,
    calculate_within_race_relative,
)


@dataclass(frozen=True, slots=True)
class FeatureRegistration:
    """Associate a declarative definition with its implementation types."""

    definition: FeatureDefinition
    builder_type: type[RegisteredFeatureBuilder]
    input_type: type[FeatureValuesInput]
    calculate: Callable[[CalculationContext, str], CalculatedValues]


@dataclass(frozen=True, slots=True)
class FeatureRegistry:
    """Keep one ordered immutable set of configured feature registrations."""

    features: tuple[FeatureRegistration, ...]

    @property
    def feature_ids(self) -> tuple[str, ...]:
        """Return configured IDs in their declared order."""
        return tuple(entry.definition.feature_id for entry in self.features)

    @property
    def names(self) -> tuple[str, ...]:
        """Return metadata-only registered names for table boundaries."""
        return tuple(entry.definition.name for entry in self.features)

    @property
    def definitions(self) -> tuple[FeatureDefinition, ...]:
        """Return the single definitions shared by audit and generation."""
        return tuple(entry.definition for entry in self.features)

    def by_name(self, name: str) -> FeatureRegistration:
        """Return the configured registration for one implementation name."""
        for entry in self.features:
            if entry.definition.name == name:
                return entry
        raise KeyError(name)

    def by_id(self, feature_id: str) -> FeatureRegistration:
        """Return the configured registration for one external ID."""
        for entry in self.features:
            if entry.definition.feature_id == feature_id:
                return entry
        raise KeyError(feature_id)


def create_feature_registry(definitions: Sequence[FeatureDefinition]) -> FeatureRegistry:
    """Bind a complete catalog, rejecting unknown names and missing implementations."""
    ids = [definition.feature_id for definition in definitions]
    names = [definition.name for definition in definitions]
    if len(set(ids)) != len(ids) or len(set(names)) != len(names):
        raise ValueError("feature definitions require unique IDs and names")
    if set(names) != set(_IMPLEMENTATIONS):
        unknown = sorted(set(names) - set(_IMPLEMENTATIONS))
        missing = sorted(set(_IMPLEMENTATIONS) - set(names))
        raise ValueError(
            f"feature implementation mismatch: unknown={unknown!r}, missing={missing!r}"
        )
    return FeatureRegistry(
        tuple(
            FeatureRegistration(definition, *_IMPLEMENTATIONS[definition.name])
            for definition in definitions
        )
    )


_IMPLEMENTATIONS = MappingProxyType[
    str,
    tuple[
        type[RegisteredFeatureBuilder],
        type[FeatureValuesInput],
        Callable[[CalculationContext, str], CalculatedValues],
    ],
](
    {
        "basic_conditions_and_weight": (
            BasicConditionsAndWeightBuilder,
            BasicConditionsAndWeightInput,
            calculate_basic_conditions_and_weight,
        ),
        "condition_adjusted_ability": (
            ConditionAdjustedAbilityBuilder,
            ConditionAdjustedAbilityInput,
            calculate_condition_adjusted_ability,
        ),
        "condition_suitability": (
            ConditionSuitabilityBuilder,
            ConditionSuitabilityInput,
            calculate_condition_suitability,
        ),
        "expected_race_development": (
            ExpectedRaceDevelopmentBuilder,
            ExpectedRaceDevelopmentInput,
            calculate_expected_race_development,
        ),
        "hill_and_wood_workouts": (
            HillAndWoodWorkoutsBuilder,
            HillAndWoodWorkoutsInput,
            calculate_hill_and_wood_workouts,
        ),
        "history_volume_and_missingness": (
            HistoryVolumeAndMissingnessBuilder,
            HistoryVolumeAndMissingnessInput,
            calculate_history_volume_and_missingness,
        ),
        "jockey_combination": (
            JockeyCombinationBuilder,
            JockeyCombinationInput,
            calculate_jockey_combination,
        ),
        "jockey_performance": (
            JockeyPerformanceBuilder,
            JockeyPerformanceInput,
            calculate_jockey_performance,
        ),
        "market_characteristics": (
            MarketCharacteristicsBuilder,
            MarketCharacteristicsInput,
            calculate_market_characteristics,
        ),
        "opponent_pagerank": (
            OpponentPagerankBuilder,
            OpponentPagerankInput,
            calculate_opponent_pagerank,
        ),
        "past_body_weight": (
            PastBodyWeightBuilder,
            PastBodyWeightInput,
            calculate_past_body_weight,
        ),
        "past_lap_and_running_style": (
            PastLapAndRunningStyleBuilder,
            PastLapAndRunningStyleInput,
            calculate_past_lap_and_running_style,
        ),
        "past_racing_ability": (
            PastRacingAbilityBuilder,
            PastRacingAbilityInput,
            calculate_past_racing_ability,
        ),
        "pedigree_suitability": (
            PedigreeSuitabilityBuilder,
            PedigreeSuitabilityInput,
            calculate_pedigree_suitability,
        ),
        "recent_performance": (
            RecentPerformanceBuilder,
            RecentPerformanceInput,
            calculate_recent_performance,
        ),
        "recent_stability": (
            RecentStabilityBuilder,
            RecentStabilityInput,
            calculate_recent_stability,
        ),
        "rest_and_condition_change": (
            RestAndConditionChangeBuilder,
            RestAndConditionChangeInput,
            calculate_rest_and_condition_change,
        ),
        "running_style_and_position": (
            RunningStyleAndPositionBuilder,
            RunningStyleAndPositionInput,
            calculate_running_style_and_position,
        ),
        "same_gate_and_trainer_relative": (
            SameGateAndTrainerRelativeBuilder,
            SameGateAndTrainerRelativeInput,
            calculate_same_gate_and_trainer_relative,
        ),
        "trainer_performance": (
            TrainerPerformanceBuilder,
            TrainerPerformanceInput,
            calculate_trainer_performance,
        ),
        "within_race_relative": (
            WithinRaceRelativeBuilder,
            WithinRaceRelativeInput,
            calculate_within_race_relative,
        ),
    }
)
