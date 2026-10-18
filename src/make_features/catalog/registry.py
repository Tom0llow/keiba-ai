"""Bind validated feature definitions to explicitly registered implementations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType

from make_features.basic_conditions_and_weight import (
    BasicConditionsAndWeightBuilder,
    BasicConditionsAndWeightInput,
)
from make_features.condition_adjusted_ability import (
    ConditionAdjustedAbilityBuilder,
    ConditionAdjustedAbilityInput,
)
from make_features.condition_suitability import (
    ConditionSuitabilityBuilder,
    ConditionSuitabilityInput,
)
from make_features.contracts.types import FeatureDefinition, FeatureValuesInput
from make_features.expected_race_development import (
    ExpectedRaceDevelopmentBuilder,
    ExpectedRaceDevelopmentInput,
)
from make_features.generation.base import RegisteredFeatureBuilder
from make_features.hill_and_wood_workouts import (
    HillAndWoodWorkoutsBuilder,
    HillAndWoodWorkoutsInput,
)
from make_features.history_volume_and_missingness import (
    HistoryVolumeAndMissingnessBuilder,
    HistoryVolumeAndMissingnessInput,
)
from make_features.jockey_combination import JockeyCombinationBuilder, JockeyCombinationInput
from make_features.jockey_performance import JockeyPerformanceBuilder, JockeyPerformanceInput
from make_features.market_characteristics import (
    MarketCharacteristicsBuilder,
    MarketCharacteristicsInput,
)
from make_features.opponent_pagerank import OpponentPagerankBuilder, OpponentPagerankInput
from make_features.past_body_weight import PastBodyWeightBuilder, PastBodyWeightInput
from make_features.past_lap_and_running_style import (
    PastLapAndRunningStyleBuilder,
    PastLapAndRunningStyleInput,
)
from make_features.past_racing_ability import PastRacingAbilityBuilder, PastRacingAbilityInput
from make_features.pedigree_suitability import (
    PedigreeSuitabilityBuilder,
    PedigreeSuitabilityInput,
)
from make_features.recent_performance import RecentPerformanceBuilder, RecentPerformanceInput
from make_features.recent_stability import RecentStabilityBuilder, RecentStabilityInput
from make_features.rest_and_condition_change import (
    RestAndConditionChangeBuilder,
    RestAndConditionChangeInput,
)
from make_features.running_style_and_position import (
    RunningStyleAndPositionBuilder,
    RunningStyleAndPositionInput,
)
from make_features.same_gate_and_trainer_relative import (
    SameGateAndTrainerRelativeBuilder,
    SameGateAndTrainerRelativeInput,
)
from make_features.trainer_performance import TrainerPerformanceBuilder, TrainerPerformanceInput
from make_features.within_race_relative import WithinRaceRelativeBuilder, WithinRaceRelativeInput


@dataclass(frozen=True, slots=True)
class FeatureRegistration:
    """Associate a declarative definition with its implementation types."""

    definition: FeatureDefinition
    builder_type: type[RegisteredFeatureBuilder]
    input_type: type[FeatureValuesInput]


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
    str, tuple[type[RegisteredFeatureBuilder], type[FeatureValuesInput]]
](
    {
        "basic_conditions_and_weight": (
            BasicConditionsAndWeightBuilder,
            BasicConditionsAndWeightInput,
        ),
        "condition_adjusted_ability": (
            ConditionAdjustedAbilityBuilder,
            ConditionAdjustedAbilityInput,
        ),
        "condition_suitability": (ConditionSuitabilityBuilder, ConditionSuitabilityInput),
        "expected_race_development": (ExpectedRaceDevelopmentBuilder, ExpectedRaceDevelopmentInput),
        "hill_and_wood_workouts": (HillAndWoodWorkoutsBuilder, HillAndWoodWorkoutsInput),
        "history_volume_and_missingness": (
            HistoryVolumeAndMissingnessBuilder,
            HistoryVolumeAndMissingnessInput,
        ),
        "jockey_combination": (JockeyCombinationBuilder, JockeyCombinationInput),
        "jockey_performance": (JockeyPerformanceBuilder, JockeyPerformanceInput),
        "market_characteristics": (MarketCharacteristicsBuilder, MarketCharacteristicsInput),
        "opponent_pagerank": (OpponentPagerankBuilder, OpponentPagerankInput),
        "past_body_weight": (PastBodyWeightBuilder, PastBodyWeightInput),
        "past_lap_and_running_style": (PastLapAndRunningStyleBuilder, PastLapAndRunningStyleInput),
        "past_racing_ability": (PastRacingAbilityBuilder, PastRacingAbilityInput),
        "pedigree_suitability": (PedigreeSuitabilityBuilder, PedigreeSuitabilityInput),
        "recent_performance": (RecentPerformanceBuilder, RecentPerformanceInput),
        "recent_stability": (RecentStabilityBuilder, RecentStabilityInput),
        "rest_and_condition_change": (RestAndConditionChangeBuilder, RestAndConditionChangeInput),
        "running_style_and_position": (
            RunningStyleAndPositionBuilder,
            RunningStyleAndPositionInput,
        ),
        "same_gate_and_trainer_relative": (
            SameGateAndTrainerRelativeBuilder,
            SameGateAndTrainerRelativeInput,
        ),
        "trainer_performance": (TrainerPerformanceBuilder, TrainerPerformanceInput),
        "within_race_relative": (WithinRaceRelativeBuilder, WithinRaceRelativeInput),
    }
)
