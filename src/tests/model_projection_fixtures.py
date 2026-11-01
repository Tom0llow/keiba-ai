"""Explicit synthetic all-group projections; these are not production settings."""

from dataclasses import replace
from datetime import timedelta

from make_features.contracts.observations import HistoricalRace, ObservationInput
from tests.observation_fixtures import at, evidence, observations, race, result_runner

SELECTED_COLUMNS = (
    "recent_performance__past_finish_lag1",
    "past_racing_ability__past_velocity_mps_lag1",
    "condition_adjusted_ability__past_ability_time_mean",
    "recent_stability__past_elapsed_sec_mean",
    "condition_suitability__horse_condition_smoothed_win_rate",
    "rest_and_condition_change__days_since_previous_start",
    "jockey_performance__jockey_smoothed_win_rate",
    "trainer_performance__trainer_smoothed_win_rate",
    "within_race_relative__relative_elapsed_sec_rank",
    "basic_conditions_and_weight__race_distance_m",
    "jockey_combination__horse_jockey_win_rate",
    "running_style_and_position__past_corner4_relative_lag1",
    "expected_race_development__opponent_front_share",
    "pedigree_suitability__sire_condition_win_rate",
    "history_volume_and_missingness__past_observed_start_count",
    "past_body_weight__past_weight_lag1_kg",
    "hill_and_wood_workouts__hc_last_clock_sec",
    "past_lap_and_running_style__past_pace_velocity_gap_mps_lag1",
    "market_characteristics__market_win_odds",
    "same_gate_and_trainer_relative__same_gate_ability_diff",
    "opponent_pagerank__opponent_graph_score",
)


def frozen_input(day: int) -> ObservationInput:
    """Retain the same prior history and observe a complete later synthetic card."""
    source = observations()
    delta = timedelta(days=day - 10)
    race_id = f"target-{day}"
    return replace(
        source,
        freeze_at=source.freeze_at + delta,
        card=replace(
            source.card,
            race_id=race_id,
            scheduled_start_at=source.card.scheduled_start_at + delta,
            evidence=evidence(f"card-{day}", at(day, 10)),
        ),
        coverage=tuple(
            replace(
                c,
                end_at=c.end_at + delta,
                evidence=evidence(f"coverage-{day}-{c.kind}", source.freeze_at + delta),
            )
            for c in source.coverage
        ),
        markets=tuple(
            replace(
                m,
                race_id=race_id,
                evidence=evidence(f"market-{day}-{i}", m.evidence.event_at + delta),
                pair_evidence=evidence(f"pairs-{day}-{i}", m.pair_evidence.event_at + delta),
            )
            for i, m in enumerate(source.markets)
        ),
    )


def target_result(day: int) -> HistoricalRace:
    """Provide a separately observed complete normal result after the frozen card."""
    result = race(
        f"target-{day}",
        day,
        tuple(
            result_runner(horse, i, 97.0 + i, i, 480.0 + i)
            for i, horse in enumerate(("A", "B", "C", "N"), 1)
        ),
    )
    return replace(
        result, started_at=at(day, 15), evidence=evidence(f"result-{day}", at(day, 15, 5))
    )
