"""Small normalized, timestamped examples; values are test choices, not defaults."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from hashlib import sha256

import pyarrow as pa

from make_features.contracts.observations import (
    CalculationParameters,
    CardRunner,
    Conditions,
    Coverage,
    HistoricalRace,
    HistoricalRunner,
    HorseOdds,
    MarketObservation,
    ObservationInput,
    PairOdds,
    PedigreeObservation,
    RaceCard,
    Section,
    SourceEvidence,
    Workout,
)
from make_features.generation.observations import JST


def at(day: int, hour: int = 12, minute: int = 0) -> datetime:
    """Return a controlled June 2026 JST clock."""
    return datetime(2026, 6, day, hour, minute, tzinfo=JST)


def evidence(identifier: str, time: datetime) -> SourceEvidence:
    """Declare test-only source observations without inferring any production clock."""
    return SourceEvidence(
        identifier, "fixture", 1, sha256(identifier.encode()).hexdigest(), time, time, time
    )


def parameters() -> CalculationParameters:
    """Return explicit calculation choices for hand-checkable fixtures."""
    return CalculationParameters(
        rule_id="test-formulas-v1",
        evidence=evidence("rules", at(1, 0)),
        history_start=date(2026, 6, 1),
        lag_count=4,
        count_window=3,
        days_window=30,
        half_life_days=1.0,
        condition_keys=("surface", "distance_m"),
        condition_window_order="filter_then_window",
        smoothing_alpha=2.0,
        minimum_count=1,
        partial_rank=True,
        tie_policy="competition",
        metric="elapsed_sec",
        metric_direction="lower",
        class_order=("low", "high"),
        style_window=3,
        style_minimum_count=1,
        leader_threshold=0.5,
        front_threshold=0.7,
        pedigree_include_self=False,
        workout_distance_m=800,
        workout_section_distance_m=200,
        market_anchor_seconds=600,
        market_max_age_seconds=120,
        market_version_tolerance_seconds=0,
        graph_days=30,
        graph_half_life_days=None,
        graph_edge_rule="all_pairs",
        graph_base_weight="inverse_field_minus_one",
        graph_damping=0.5,
        graph_tolerance=1e-12,
        graph_max_iterations=200,
    )


def result_runner(
    horse: str, finish: int, clock: float, corner: int, body: float
) -> HistoricalRunner:
    """Supply a complete normal result with different historical staff assignments."""
    jockey = {"A": "J1", "B": "J2", "C": "J1", "D": "J4"}.get(horse, "J5")
    trainer = {"A": "T1", "B": "T1", "C": "T2", "D": "T4"}.get(horse, "T5")
    return HistoricalRunner(
        horse,
        finish,
        "normal",
        jockey,
        trainer,
        clock,
        -1.2 if finish == 1 else 1.2,
        {"A": 35.0, "B": 36.0, "C": 34.0, "D": 37.0}.get(horse, 36.0),
        600,
        corner,
        body,
        56.0,
        {},
    )


def race(identifier: str, day: int, runners: tuple[HistoricalRunner, ...]) -> HistoricalRace:
    """Create a complete normal population with a separate actual result event."""
    winner_time = next(r.elapsed_sec for r in runners if r.finish == 1)
    assert winner_time is not None
    return HistoricalRace(
        identifier,
        at(day),
        Conditions(1600, "turf", "V", "C", "good", "low"),
        runners,
        tuple(r.horse_id for r in runners),
        True,
        tuple(Section(400, winner_time / 4) for _ in range(4)),
        34.5,
        600,
        evidence(identifier, at(day, 12, 5)),
    )


def observations() -> ObservationInput:
    """Return varied histories, a first observer, workouts and two complete markets."""
    early = (
        race(
            "ref1",
            1,
            (result_runner("X", 1, 100.0, 1, 500.0), result_runner("Y", 2, 102.0, 2, 500.0)),
        ),
        race(
            "ref2",
            2,
            (result_runner("X", 1, 104.0, 1, 500.0), result_runner("Y", 2, 106.0, 2, 500.0)),
        ),
    )
    past = (
        race(
            "r3",
            3,
            (
                result_runner("A", 2, 105.0, 4, 480.0),
                result_runner("B", 1, 102.0, 1, 500.0),
                result_runner("C", 3, 106.0, 3, 490.0),
                result_runner("D", 4, 108.0, 2, 510.0),
            ),
        ),
        race(
            "r5",
            5,
            (
                result_runner("A", 4, 110.0, 4, 484.0),
                result_runner("B", 2, 106.0, 1, 502.0),
                result_runner("C", 1, 100.0, 2, 492.0),
                result_runner("D", 3, 108.0, 3, 512.0),
            ),
        ),
        race(
            "r9",
            9,
            (
                result_runner("A", 1, 98.0, 1, 488.0),
                result_runner("B", 4, 104.0, 2, 504.0),
                result_runner("C", 2, 99.0, 3, 494.0),
                result_runner("D", 3, 101.0, 4, 514.0),
            ),
        ),
    )
    past = (
        *past[:-1],
        replace(
            past[-1],
            sections=(
                Section(400, 24.0),
                Section(400, 24.0),
                Section(400, 25.0),
                Section(400, 25.0),
            ),
        ),
    )
    ids = ("A", "B", "C", "N")
    card = RaceCard(
        "target",
        at(10, 15),
        Conditions(1800, "turf", "V", "C", "good", "high"),
        (
            CardRunner("A", "01", 1, 4, "female", 57.0, "J1", "T1", True),
            CardRunner("B", "02", 1, 4, "male", 55.0, "J2", "T1", True),
            CardRunner("C", "03", 2, 3, "female", 56.0, "J1", "T2", True),
            CardRunner("N", "04", 3, 3, "male", 55.0, "J3", "T3", True),
        ),
        ids,
        True,
        evidence("card", at(10, 10)),
    )
    # Use distance 1600 in target so condition baselines and rates are comparable.
    card = replace(card, conditions=replace(card.conditions, distance_m=1600))
    freeze = at(10, 14, 50)
    population = (*ids, "D", "X", "Y")
    coverage = tuple(
        Coverage(
            kind,
            datetime(2026, 5, 1, tzinfo=JST),
            freeze,
            population,
            True,
            "test JRA normalized population",
            evidence("coverage-" + kind, freeze),
        )
        for kind in ("history", "workouts", "pedigree", "market")
    )
    pedigree = tuple(
        PedigreeObservation(
            horse,
            {"A": "S1", "B": "S1", "C": "S2"}.get(horse, "S" + horse),
            {"A": "M1", "B": "M2", "C": "M1"}.get(horse, "M" + horse),
            evidence("pedigree-" + horse, at(1, 0)),
        )
        for horse in population
    )
    workouts = tuple(
        Workout(
            horse,
            kind,
            "facility",
            "course",
            "right",
            tuple(Section(200, value) for value in sections),
            evidence(identifier, at(day, 6)),
        )
        for identifier, horse, kind, day, sections in (
            ("old-hc", "A", "hc", 6, (14.0, 13.0, 13.0, 12.0)),
            ("last-hc", "A", "hc", 8, (13.0, 12.0, 13.0, 12.0)),
            ("peer-b", "B", "hc", 8, (13.0, 13.0, 13.0, 12.0)),
            ("peer-c", "C", "hc", 8, (14.0, 14.0, 13.0, 12.0)),
            ("wood", "A", "wc", 8, (14.0, 14.0, 14.0, 13.0)),
        )
    )
    pair_values = (
        ("A", "B", 2.0),
        ("A", "C", 4.0),
        ("A", "N", 4.0),
        ("B", "C", 8.0),
        ("B", "N", 8.0),
        ("C", "N", 8.0),
    )
    markets = tuple(
        MarketObservation(
            "target",
            tuple(HorseOdds(horse, odd, 1.2, 1.8) for horse, odd in zip(ids, odds, strict=True)),
            tuple(PairOdds((a, b), odd) for a, b, odd in pair_values),
            ids,
            tuple((a, b) for a, b, _ in pair_values),
            {"tansyo": total, "fukusyo": total, "wakuren": total, "umaren": total},
            evidence(identifier, time),
            evidence(identifier + "-pair", time),
        )
        for identifier, time, odds, total in (
            ("market0", freeze - timedelta(seconds=660), (1.0, 4.0, 8.0, 8.0), 100),
            ("market1", freeze - timedelta(seconds=60), (2.0, 4.0, 8.0, 8.0), 160),
        )
    )
    return ObservationInput(freeze, card, (*early, *past), coverage, workouts, pedigree, markets)


def fixture_column_types(name: str) -> dict[str, pa.DataType]:
    """Declare the intended fixture column types independently of computed values."""
    schemas: dict[str, dict[str, pa.DataType]] = {}

    def declared(names: str, dtype: pa.DataType) -> dict[str, pa.DataType]:
        return dict.fromkeys(names.split(), dtype)

    def performance(prefix: str) -> dict[str, pa.DataType]:
        return {
            f"{prefix}_{key}": dtype
            for key, dtype in {
                **declared("start_count", pa.int64()),
                **declared("small_sample", pa.bool_()),
                **declared(
                    "win_rate top3_rate relative_finish_mean smoothed_win_rate smoothed_top3_rate prior_win_rate prior_top3_rate",
                    pa.float64(),
                ),
            }.items()
        }

    schemas["recent_performance"] = {
        **{f"past_finish_lag{k}": pa.int64() for k in range(1, 5)},
        **{f"past_finish_relative_lag{k}": pa.float64() for k in range(1, 5)},
        **declared("past_start_count", pa.int64()),
        **declared("past_win_rate past_top3_rate", pa.float64()),
        **declared("past_small_sample", pa.bool_()),
    }
    schemas["past_racing_ability"] = {
        f"past_{column}_lag{k}": dtype
        for k in range(1, 5)
        for column, dtype in {
            **declared(
                "elapsed_sec signed_gap_sec velocity_mps last3f_sec last3f_rank last3f_relative",
                pa.float64(),
            ),
            **declared("last3f_known_count", pa.int64()),
        }.items()
    }
    schemas["condition_adjusted_ability"] = {
        **declared(
            "past_condition_time_advantage past_condition_velocity_advantage past_ability_time_mean past_ability_time_ewma past_ability_velocity_mean past_ability_velocity_ewma",
            pa.float64(),
        ),
        **declared("past_condition_reference_count", pa.int64()),
        **{f"past_condition_reference_count_lag{k}": pa.int64() for k in range(1, 4)},
    }
    schemas["recent_stability"] = {
        f"past_elapsed_sec_{column}": dtype
        for column, dtype in {
            **declared("mean max std ewma trend", pa.float64()),
            **declared("count valid_count", pa.int64()),
        }.items()
    }
    schemas["condition_suitability"] = performance("horse_condition")
    schemas["rest_and_condition_change"] = {
        **declared("days_since_previous_start starts_in_window_days distance_delta_m", pa.int64()),
        **declared("surface_changed", pa.bool_()),
        **declared("class_transition", pa.string()),
    }
    for feature, prefix in (("jockey_performance", "jockey"), ("trainer_performance", "trainer")):
        schemas[feature] = {**performance(prefix), **performance(prefix + "_condition")}
    schemas["within_race_relative"] = {
        f"relative_elapsed_sec_{column}": dtype
        for column, dtype in {
            **declared("rank mean_diff leader_gap zscore", pa.float64()),
            **declared("known_count field_size", pa.int64()),
        }.items()
    }
    schemas["basic_conditions_and_weight"] = {
        **declared("race_distance_m horse_age_years gate_number frozen_field_size", pa.int64()),
        **declared("horse_number sex surface venue course going class_code", pa.string()),
        **declared("carried_weight_kg carried_weight_delta_kg", pa.float64()),
    }
    schemas["jockey_combination"] = {
        **performance("horse_jockey"),
        **performance("jockey_trainer"),
        **declared("horse_jockey_frequency", pa.float64()),
        **declared("jockey_changed_since_previous", pa.bool_()),
    }
    schemas["running_style_and_position"] = {
        **{
            f"past_{column}_lag{k}": dtype
            for k in range(1, 5)
            for column, dtype in {
                **declared("corner4_relative corner4_to_finish_relative_gain", pa.float64()),
                **declared("corner4_to_finish_gain", pa.int64()),
            }.items()
        },
        **declared("past_corner4_relative_mean past_corner4_relative_std", pa.float64()),
        **declared("past_corner4_valid_count", pa.int64()),
    }
    schemas["expected_race_development"] = {
        **declared("pre_race_style", pa.string()),
        **declared(
            "field_leader_count field_front_count style_unknown_count opponent_leader_count opponent_front_count opponent_unknown_count opponent_known_count",
            pa.int64(),
        ),
        **declared("opponent_front_share", pa.float64()),
    }
    schemas["pedigree_suitability"] = {
        **performance("sire_condition"),
        **performance("broodmare_sire_condition"),
        **declared(
            "sire_condition_offspring_count broodmare_sire_condition_offspring_count", pa.int64()
        ),
    }
    schemas["history_volume_and_missingness"] = {
        **declared(
            "past_observed_start_count condition_observed_start_count past_metric_valid_count",
            pa.int64(),
        ),
        **declared(
            "history_complete is_first_observed_start is_first_condition has_metric_history",
            pa.bool_(),
        ),
        **declared("past_missing_reason", pa.string()),
    }
    schemas["past_body_weight"] = {
        **declared(
            "past_weight_lag1_kg past_weight_delta_last2_kg past_weight_mean_kg past_weight_std_kg past_weight_vs_mean_kg past_weight_ratio_mean",
            pa.float64(),
        ),
        **declared("past_weight_valid_count", pa.int64()),
    }
    schemas["hill_and_wood_workouts"] = {
        f"{prefix}_{column}": dtype
        for prefix in ("hc", "wc")
        for column, dtype in {
            **declared(
                "last_clock_sec last_section_sec finish_accel_sec clock_mean_sec clock_best_sec self_clock_diff_sec same_day_course_diff_sec",
                pa.float64(),
            ),
            **declared("workout_count self_reference_count same_day_reference_count", pa.int64()),
        }.items()
    }
    schemas["past_lap_and_running_style"] = {
        f"past_{column}_lag{k}": pa.float64()
        for k in range(1, 5)
        for column in [
            "race_early_velocity_mps",
            "race_late_velocity_mps",
            "pace_velocity_gap_mps",
            "last3f_vs_race_sec",
        ]
    }
    schemas["market_characteristics"] = {
        **declared(
            "market_win_odds market_place_low market_place_high market_place_width market_win_support market_win_rank market_pair_support_i market_odds_ratio market_log_odds_change market_rank_change",
            pa.float64(),
        ),
        **declared("market_pair_known_opponent_count", pa.int64()),
        **declared("market_complete_win_set market_complete_pair_set", pa.bool_()),
        **{
            f"ticket_total_{prefix}{ticket}": dtype
            for ticket in ("tansyo", "fukusyo", "wakuren", "umaren")
            for prefix, dtype in (
                ("", pa.int64()),
                ("growth_", pa.int64()),
                ("growth_rate_", pa.float64()),
            )
        },
    }
    schemas["same_gate_and_trainer_relative"] = {
        f"{prefix}_{column}": dtype
        for prefix in ("same_gate", "same_trainer")
        for column, dtype in {
            **declared("peer_count known_peer_count", pa.int64()),
            **declared("ability_diff ability_rank", pa.float64()),
        }.items()
    }
    schemas["opponent_pagerank"] = {
        **declared("opponent_graph_score", pa.float64()),
        **declared("opponent_graph_known", pa.bool_()),
        **declared("opponent_graph_start_count unique_opponent_count", pa.int64()),
    }
    return schemas[name]
