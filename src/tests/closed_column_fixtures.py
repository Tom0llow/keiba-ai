"""Freeze the closed numeric column lists that operational artifacts depend on (ADR-051)."""

# The 36 columns of the operational reference datamart built before ADR-051, in contract
# order for lag_count=4 and metric=elapsed_sec. The 36-column variant must keep them as is.
ORIGINAL_CLOSED_COLUMNS = (
    "recent_performance__past_win_rate",
    "condition_adjusted_ability__past_ability_time_mean",
    "condition_suitability__horse_condition_smoothed_win_rate",
    "rest_and_condition_change__days_since_previous_start",
    "jockey_performance__jockey_smoothed_win_rate",
    "trainer_performance__trainer_smoothed_win_rate",
    "basic_conditions_and_weight__race_distance_m",
    "basic_conditions_and_weight__carried_weight_kg",
    "jockey_combination__horse_jockey_win_rate",
    "expected_race_development__opponent_front_share",
    "pedigree_suitability__sire_condition_win_rate",
    "history_volume_and_missingness__past_observed_start_count",
    "past_body_weight__past_weight_lag1_kg",
    "hill_and_wood_workouts__hc_last_clock_sec",
    "hill_and_wood_workouts__wc_last_clock_sec",
    "market_characteristics__market_win_odds",
    "same_gate_and_trainer_relative__same_gate_ability_diff",
    "opponent_pagerank__opponent_graph_score",
    "recent_stability__past_elapsed_sec_mean",
    "within_race_relative__relative_elapsed_sec_rank",
    "recent_performance__past_finish_lag1",
    "recent_performance__past_finish_lag2",
    "recent_performance__past_finish_lag3",
    "recent_performance__past_finish_lag4",
    "past_racing_ability__past_velocity_mps_lag1",
    "past_racing_ability__past_velocity_mps_lag2",
    "past_racing_ability__past_velocity_mps_lag3",
    "past_racing_ability__past_velocity_mps_lag4",
    "running_style_and_position__past_corner4_relative_lag1",
    "running_style_and_position__past_corner4_relative_lag2",
    "running_style_and_position__past_corner4_relative_lag3",
    "running_style_and_position__past_corner4_relative_lag4",
    "past_lap_and_running_style__past_pace_velocity_gap_mps_lag1",
    "past_lap_and_running_style__past_pace_velocity_gap_mps_lag2",
    "past_lap_and_running_style__past_pace_velocity_gap_mps_lag3",
    "past_lap_and_running_style__past_pace_velocity_gap_mps_lag4",
)
# SHA-256 of the compact JSON list of (group, column, meaning, unit) for those 36 columns.
ORIGINAL_CLOSED_COLUMNS_DEFINITION_SHA256 = (
    "5cf458335664c660faf1f0bec213fb6aaba60eeaded98aba0c11d3ec6effc25e"
)
# The columns ADR-051 appends, in contract order for lag_count=4.
ADDED_CLOSED_COLUMNS = (
    "basic_conditions_and_weight__gate_number",
    "basic_conditions_and_weight__frozen_field_size",
    "basic_conditions_and_weight__horse_age_years",
    "recent_performance__past_top3_rate",
    "past_racing_ability__past_signed_gap_sec_lag1",
    "past_racing_ability__past_signed_gap_sec_lag2",
    "past_racing_ability__past_signed_gap_sec_lag3",
    "past_racing_ability__past_signed_gap_sec_lag4",
)
