"""Register explanatory-variable identifiers and their individual builders."""

from __future__ import annotations

from types import MappingProxyType

from features.basic_conditions_and_weight import SPEC as F10_SPEC
from features.basic_conditions_and_weight import (
    BasicConditionsAndWeightBuilder,
    BasicConditionsAndWeightInput,
)
from features.common.base import FeatureBuilder
from features.common.types import FeatureValuesInput
from features.condition_adjusted_ability import SPEC as F03_SPEC
from features.condition_adjusted_ability import (
    ConditionAdjustedAbilityBuilder,
    ConditionAdjustedAbilityInput,
)
from features.condition_suitability import SPEC as F05_SPEC
from features.condition_suitability import ConditionSuitabilityBuilder, ConditionSuitabilityInput
from features.expected_race_development import SPEC as F13_SPEC
from features.expected_race_development import (
    ExpectedRaceDevelopmentBuilder,
    ExpectedRaceDevelopmentInput,
)
from features.hill_and_wood_workouts import SPEC as F17_SPEC
from features.hill_and_wood_workouts import HillAndWoodWorkoutsBuilder, HillAndWoodWorkoutsInput
from features.history_volume_and_missingness import SPEC as F15_SPEC
from features.history_volume_and_missingness import (
    HistoryVolumeAndMissingnessBuilder,
    HistoryVolumeAndMissingnessInput,
)
from features.jockey_combination import SPEC as F11_SPEC
from features.jockey_combination import JockeyCombinationBuilder, JockeyCombinationInput
from features.jockey_performance import SPEC as F07_SPEC
from features.jockey_performance import JockeyPerformanceBuilder, JockeyPerformanceInput
from features.market_characteristics import SPEC as F19_SPEC
from features.market_characteristics import MarketCharacteristicsBuilder, MarketCharacteristicsInput
from features.opponent_pagerank import SPEC as F21_SPEC
from features.opponent_pagerank import OpponentPagerankBuilder, OpponentPagerankInput
from features.past_body_weight import SPEC as F16_SPEC
from features.past_body_weight import PastBodyWeightBuilder, PastBodyWeightInput
from features.past_lap_and_running_style import SPEC as F18_SPEC
from features.past_lap_and_running_style import (
    PastLapAndRunningStyleBuilder,
    PastLapAndRunningStyleInput,
)
from features.past_racing_ability import SPEC as F02_SPEC
from features.past_racing_ability import PastRacingAbilityBuilder, PastRacingAbilityInput
from features.pedigree_suitability import SPEC as F14_SPEC
from features.pedigree_suitability import PedigreeSuitabilityBuilder, PedigreeSuitabilityInput
from features.recent_performance import SPEC as F01_SPEC
from features.recent_performance import RecentPerformanceBuilder, RecentPerformanceInput
from features.recent_stability import SPEC as F04_SPEC
from features.recent_stability import RecentStabilityBuilder, RecentStabilityInput
from features.rest_and_condition_change import SPEC as F06_SPEC
from features.rest_and_condition_change import (
    RestAndConditionChangeBuilder,
    RestAndConditionChangeInput,
)
from features.running_style_and_position import SPEC as F12_SPEC
from features.running_style_and_position import (
    RunningStyleAndPositionBuilder,
    RunningStyleAndPositionInput,
)
from features.same_gate_and_trainer_relative import SPEC as F20_SPEC
from features.same_gate_and_trainer_relative import (
    SameGateAndTrainerRelativeBuilder,
    SameGateAndTrainerRelativeInput,
)
from features.trainer_performance import SPEC as F08_SPEC
from features.trainer_performance import TrainerPerformanceBuilder, TrainerPerformanceInput
from features.within_race_relative import SPEC as F09_SPEC
from features.within_race_relative import WithinRaceRelativeBuilder, WithinRaceRelativeInput

FEATURE_GROUP_SPECS = (
    F01_SPEC,
    F02_SPEC,
    F03_SPEC,
    F04_SPEC,
    F05_SPEC,
    F06_SPEC,
    F07_SPEC,
    F08_SPEC,
    F09_SPEC,
    F10_SPEC,
    F11_SPEC,
    F12_SPEC,
    F13_SPEC,
    F14_SPEC,
    F15_SPEC,
    F16_SPEC,
    F17_SPEC,
    F18_SPEC,
    F19_SPEC,
    F20_SPEC,
    F21_SPEC,
)
FEATURE_GROUP_IDS = tuple(spec.feature_id for spec in FEATURE_GROUP_SPECS)

FEATURE_BUILDERS = MappingProxyType[str, FeatureBuilder[FeatureValuesInput]](
    {
        "F01": RecentPerformanceBuilder(),
        "F02": PastRacingAbilityBuilder(),
        "F03": ConditionAdjustedAbilityBuilder(),
        "F04": RecentStabilityBuilder(),
        "F05": ConditionSuitabilityBuilder(),
        "F06": RestAndConditionChangeBuilder(),
        "F07": JockeyPerformanceBuilder(),
        "F08": TrainerPerformanceBuilder(),
        "F09": WithinRaceRelativeBuilder(),
        "F10": BasicConditionsAndWeightBuilder(),
        "F11": JockeyCombinationBuilder(),
        "F12": RunningStyleAndPositionBuilder(),
        "F13": ExpectedRaceDevelopmentBuilder(),
        "F14": PedigreeSuitabilityBuilder(),
        "F15": HistoryVolumeAndMissingnessBuilder(),
        "F16": PastBodyWeightBuilder(),
        "F17": HillAndWoodWorkoutsBuilder(),
        "F18": PastLapAndRunningStyleBuilder(),
        "F19": MarketCharacteristicsBuilder(),
        "F20": SameGateAndTrainerRelativeBuilder(),
        "F21": OpponentPagerankBuilder(),
    }
)
FEATURE_INPUT_TYPES = MappingProxyType[str, type[FeatureValuesInput]](
    {
        "F01": RecentPerformanceInput,
        "F02": PastRacingAbilityInput,
        "F03": ConditionAdjustedAbilityInput,
        "F04": RecentStabilityInput,
        "F05": ConditionSuitabilityInput,
        "F06": RestAndConditionChangeInput,
        "F07": JockeyPerformanceInput,
        "F08": TrainerPerformanceInput,
        "F09": WithinRaceRelativeInput,
        "F10": BasicConditionsAndWeightInput,
        "F11": JockeyCombinationInput,
        "F12": RunningStyleAndPositionInput,
        "F13": ExpectedRaceDevelopmentInput,
        "F14": PedigreeSuitabilityInput,
        "F15": HistoryVolumeAndMissingnessInput,
        "F16": PastBodyWeightInput,
        "F17": HillAndWoodWorkoutsInput,
        "F18": PastLapAndRunningStyleInput,
        "F19": MarketCharacteristicsInput,
        "F20": SameGateAndTrainerRelativeInput,
        "F21": OpponentPagerankInput,
    }
)
