"""Verify numerical feature formulas and strict as-of source boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from math import log, sqrt
from typing import cast

import pytest

from make_features.basic_conditions_and_weight import calculate_basic_conditions_and_weight
from make_features.condition_adjusted_ability import calculate_condition_adjusted_ability
from make_features.condition_suitability import calculate_condition_suitability
from make_features.contracts.observations import (
    CalculatedValues,
    CalculationParameters,
    Section,
    SourceEvidence,
)
from make_features.expected_race_development import calculate_expected_race_development
from make_features.generation.observations import CalculationContext, prepare_context
from make_features.generation.statistics import summaries
from make_features.hill_and_wood_workouts import calculate_hill_and_wood_workouts
from make_features.history_volume_and_missingness import calculate_history_volume_and_missingness
from make_features.jockey_combination import calculate_jockey_combination
from make_features.jockey_performance import calculate_jockey_performance
from make_features.market_characteristics import calculate_market_characteristics
from make_features.opponent_pagerank import calculate_opponent_pagerank
from make_features.past_body_weight import calculate_past_body_weight
from make_features.past_lap_and_running_style import calculate_past_lap_and_running_style
from make_features.past_racing_ability import calculate_past_racing_ability
from make_features.pedigree_suitability import calculate_pedigree_suitability
from make_features.recent_performance import calculate_recent_performance
from make_features.recent_stability import calculate_recent_stability
from make_features.rest_and_condition_change import calculate_rest_and_condition_change
from make_features.running_style_and_position import calculate_running_style_and_position
from make_features.same_gate_and_trainer_relative import calculate_same_gate_and_trainer_relative
from make_features.serialization.observations import normalized_payload, parse_observation_inputs
from make_features.trainer_performance import calculate_trainer_performance
from make_features.validation.observations import (
    select_versions,
    validate_evidence,
    validate_parameters,
)
from make_features.within_race_relative import calculate_within_race_relative
from tests.observation_fixtures import at, evidence, observations, parameters, race, result_runner

type Calculator = Callable[[CalculationContext, str], CalculatedValues]


def test_market_revision_preserves_the_earlier_anchor_version() -> None:
    source = observations()
    old, current = source.markets
    revision = replace(
        old,
        evidence=replace(
            old.evidence,
            version=2,
            published_at=at(10, 14, 48),
            received_at=at(10, 14, 48),
        ),
        pair_evidence=replace(
            old.pair_evidence,
            version=2,
            published_at=at(10, 14, 48),
            received_at=at(10, 14, 48),
        ),
    )
    baseline = calculate_market_characteristics(prepare_context(source, parameters()), "A")
    for records in ((old, revision, current), (revision, current, old)):
        actual = calculate_market_characteristics(
            prepare_context(replace(source, markets=records), parameters()), "A"
        )
        assert actual.values == baseline.values
        assert old.evidence in actual.dependencies


@pytest.mark.parametrize("clock", ["horse", "pair"])
def test_market_revision_requires_both_actual_receipt_clocks_at_each_anchor(clock: str) -> None:
    source = observations()
    old, current = source.markets
    revised_evidence = replace(old.evidence, version=2, published_at=at(10, 14, 40))
    revised_pair = replace(old.pair_evidence, version=2, published_at=at(10, 14, 40))
    revision = replace(
        old,
        evidence=replace(
            revised_evidence, received_at=at(10, 14, 45) if clock == "horse" else at(10, 14, 40)
        ),
        pair_evidence=replace(
            revised_pair, received_at=at(10, 14, 45) if clock == "pair" else at(10, 14, 40)
        ),
    )
    actual = calculate_market_characteristics(
        prepare_context(replace(source, markets=(old, revision, current)), parameters()), "A"
    )
    assert actual.values["market_odds_ratio"] == 2
    assert old.evidence in actual.dependencies
    future = replace(
        old,
        evidence=replace(old.evidence, version=3, published_at=at(11), received_at=at(11)),
        pair_evidence=replace(
            old.pair_evidence, version=3, published_at=at(11), received_at=at(11)
        ),
    )
    with_future = calculate_market_characteristics(
        prepare_context(replace(source, markets=(old, revision, current, future)), parameters()),
        "A",
    )
    assert with_future == actual


def test_known_different_historical_assignment_excludes_a_runner_with_unknown_other_assignment() -> (
    None
):
    source = observations()
    latest = source.history[-1]
    b = replace(latest.runners[1], trainer_id=None, missing_reasons={"trainer_id": "not_recorded"})
    changed = replace(latest, runners=(latest.runners[0], b, *latest.runners[2:]))
    actual = calculate_jockey_combination(
        prepare_context(replace(source, history=(*source.history[:-1], changed)), parameters()), "A"
    )
    baseline = calculate_jockey_combination(prepare_context(source, parameters()), "A")
    assert (
        actual.values["jockey_trainer_start_count"] == baseline.values["jockey_trainer_start_count"]
    )
    assert actual.values["jockey_trainer_win_rate"] == baseline.values["jockey_trainer_win_rate"]


@pytest.mark.parametrize("unknown", ["jockey_id", "trainer_id"])
def test_unknown_historical_assignment_does_not_become_a_known_nonmatch(unknown: str) -> None:
    source = observations()
    latest = source.history[-1]
    original = latest.runners[0]
    runner = replace(
        original,
        jockey_id=None if unknown == "jockey_id" else original.jockey_id,
        trainer_id=None if unknown == "trainer_id" else original.trainer_id,
        missing_reasons={unknown: "not_recorded"},
    )
    latest = replace(latest, runners=(runner, *latest.runners[1:]))
    context = prepare_context(replace(source, history=(*source.history[:-1], latest)), parameters())
    result = calculate_jockey_combination(context, "A")
    prefixes = ("horse_jockey", "jockey_trainer") if unknown == "jockey_id" else ("jockey_trainer",)
    for prefix in prefixes:
        for key in ("start_count", "win_rate", "top3_rate", "smoothed_win_rate"):
            assert result.values[f"{prefix}_{key}"] is None
            assert "unknown" in result.missing_reasons[f"{prefix}_{key}"]
    if unknown == "jockey_id":
        assert result.values["horse_jockey_frequency"] is None


def test_graph_decay_uses_race_time_when_identical_results_are_revised_later() -> None:
    source = observations()
    p = replace(parameters(), graph_half_life_days=1.0)
    baseline = calculate_opponent_pagerank(prepare_context(source, p), "A")
    last = source.history[-1]
    revision = replace(
        last,
        evidence=replace(
            last.evidence,
            version=2,
            event_at=at(10, 14),
            published_at=at(10, 14),
            received_at=at(10, 14),
        ),
    )
    actual = calculate_opponent_pagerank(
        prepare_context(replace(source, history=(*source.history, revision)), p), "A"
    )
    assert actual.values == baseline.values


def test_revision_order_checks_every_available_version_independent_of_input_order() -> None:
    original = observations().history[-1]
    versions = tuple(
        replace(
            original,
            evidence=replace(
                original.evidence, version=version, published_at=at(day), received_at=at(day)
            ),
        )
        for version, day in ((3, 12), (1, 11), (2, 10))
    )
    for records in (versions, versions[::-1], (versions[1], versions[0], versions[2])):
        with pytest.raises(ValueError, match="revision order"):
            select_versions(records, lambda r: r.race_id, at(15))


@pytest.mark.parametrize("measurement", ["runner", "race"])
def test_non600_metre_closing_measurements_are_rejected_even_when_consistent(
    measurement: str,
) -> None:
    source = observations()
    latest = source.history[-1]
    if measurement == "runner":
        latest = replace(
            latest,
            runners=tuple(
                replace(r, last3f_distance_m=400, last3f_sec=23.0) for r in latest.runners
            ),
        )
    else:
        latest = replace(latest, race_last3f_distance_m=400, race_last3f_sec=23.0)
    with pytest.raises(ValueError, match=r"measurement distance.*600"):
        prepare_context(replace(source, history=(*source.history[:-1], latest)), parameters())


@pytest.mark.parametrize(
    ("attribute", "prefix"), [("gate", "same_gate"), ("trainer_id", "same_trainer")]
)
def test_unknown_peer_group_prevents_claiming_the_complete_peer_set(
    attribute: str, prefix: str
) -> None:
    source = observations()
    runners = list(source.card.runners)
    runners[1] = replace(
        runners[1],
        gate=None if attribute == "gate" else runners[1].gate,
        trainer_id=None if attribute == "trainer_id" else runners[1].trainer_id,
    )
    context = prepare_context(
        replace(source, card=replace(source.card, runners=tuple(runners))), parameters()
    )
    result = calculate_same_gate_and_trainer_relative(context, "A")
    for key in ("peer_count", "known_peer_count", "ability_diff", "ability_rank"):
        assert result.values[f"{prefix}_{key}"] is None
        assert "unknown" in result.missing_reasons[f"{prefix}_{key}"]


@pytest.mark.parametrize(
    ("calculator", "column", "expected"),
    [
        (calculate_recent_performance, "past_win_rate", 1 / 3),
        (calculate_past_racing_ability, "past_velocity_mps_lag1", 1600 / 98),
        (calculate_condition_adjusted_ability, "past_condition_time_advantage", 3.5 / sqrt(2.75)),
        (calculate_recent_stability, "past_elapsed_sec_mean", 313 / 3),
        (calculate_condition_suitability, "horse_condition_top3_rate", 2 / 3),
        (calculate_rest_and_condition_change, "days_since_previous_start", 1),
        (calculate_jockey_performance, "jockey_win_rate", 1 / 3),
        (calculate_trainer_performance, "trainer_top3_rate", 2 / 3),
        (calculate_within_race_relative, "relative_elapsed_sec_mean_diff", 1),
        (calculate_basic_conditions_and_weight, "carried_weight_delta_kg", 1),
        (calculate_jockey_combination, "horse_jockey_frequency", 1),
        (calculate_running_style_and_position, "past_corner4_relative_mean", 2 / 3),
        (calculate_expected_race_development, "opponent_front_share", 1),
        (calculate_pedigree_suitability, "sire_condition_win_rate", 1 / 3),
        (calculate_history_volume_and_missingness, "past_metric_valid_count", 3),
        (calculate_past_body_weight, "past_weight_std_kg", sqrt(32 / 3)),
        (calculate_hill_and_wood_workouts, "hc_same_day_course_diff_sec", -2),
        (
            calculate_past_lap_and_running_style,
            "past_pace_velocity_gap_mps_lag1",
            800 / 48 - 800 / 50,
        ),
        (calculate_market_characteristics, "market_pair_support_i", 4 / 11),
        (
            calculate_same_gate_and_trainer_relative,
            "same_gate_ability_diff",
            (6 / sqrt(2.75) - 4 / sqrt(8 / 3) - 1.5) / 3,
        ),
        (calculate_opponent_pagerank, "opponent_graph_start_count", 3),
    ],
)
def test_each_group_calculates_hand_checked_values(
    calculator: Calculator, column: str, expected: float
) -> None:
    context = prepare_context(observations(), parameters())
    result = calculator(context, "A")
    assert result.values[column] == pytest.approx(expected)
    assert result.dependencies
    assert all(e.available_at <= context.cutoff for e in result.dependencies)


def test_lags_signed_gap_partial_ranks_and_position_gain() -> None:
    context = prepare_context(observations(), parameters())
    finish = calculate_recent_performance(context, "A").values
    assert [finish[f"past_finish_lag{i}"] for i in range(1, 5)] == [1, 4, 2, None]
    assert finish["past_finish_relative_lag2"] == 1
    performance = calculate_past_racing_ability(context, "A").values
    assert performance["past_signed_gap_sec_lag1"] == -1.2
    assert performance["past_last3f_rank_lag1"] == 2
    assert performance["past_last3f_relative_lag1"] == pytest.approx(1 / 3)
    assert calculate_running_style_and_position(context, "A").values[
        "past_corner4_to_finish_relative_gain_lag3"
    ] == pytest.approx(2 / 3)
    relative = calculate_within_race_relative(context, "A").values
    assert relative["relative_elapsed_sec_known_count"] == 3
    assert relative["relative_elapsed_sec_rank"] == 3
    strict = prepare_context(observations(), replace(parameters(), partial_rank=False))
    assert calculate_within_race_relative(strict, "A").values["relative_elapsed_sec_rank"] is None


def test_shared_formula_uses_population_std_elapsed_days_and_no_missing_window_fill() -> None:
    summary = summaries([2.0, 4.0, 6.0], [at(1), at(2), at(3)], at(3), 1.0)
    assert summary["mean"] == 4
    assert summary["std"] == pytest.approx(sqrt(8 / 3))
    assert summary["trend"] == 2
    assert summary["ewma"] == pytest.approx(34 / 7)
    missing = summaries([2.0, None, 6.0], [at(1), at(2), at(3)], at(3), 1.0)
    assert missing["mean"] is None
    assert missing["valid_count"] == 2
    assert summaries([2.0], [at(1)], at(3), 1.0)["std"] is None
    assert summaries([2.0, 3.0], [at(1), at(1)], at(3), 1.0)["trend"] is None


def test_references_exclude_the_start_itself_and_future_winners() -> None:
    source = observations()
    p = parameters()
    result = calculate_condition_adjusted_ability(prepare_context(source, p), "A")
    assert result.values["past_condition_reference_count_lag1"] == 4
    assert result.values["past_condition_reference_count_lag3"] == 2
    # The first horse start uses only 100/104-second winners, never its own race.
    expected = (3.5 / sqrt(2.75) - 8 / sqrt(8 / 3) - 1.5) / 3
    assert result.values["past_ability_time_mean"] == pytest.approx(expected)
    future = race(
        "future", 11, (result_runner("A", 1, 1.0, 1, 500.0), result_runner("B", 2, 2.0, 2, 500.0))
    )
    target_result = replace(future, race_id=source.card.race_id)
    augmented = replace(source, history=(*source.history, future, target_result))
    assert calculate_condition_adjusted_ability(prepare_context(augmented, p), "A") == result


def test_coverage_and_missing_measurements_are_distinguished() -> None:
    source = observations()
    ctx = prepare_context(source, parameters())
    first = calculate_history_volume_and_missingness(ctx, "N").values
    assert first["past_observed_start_count"] == 0
    assert first["is_first_condition"] is True
    assert first["past_missing_reason"] == "no_history"
    incomplete = replace(
        source,
        coverage=tuple(
            replace(c, complete=False) if c.kind == "history" else c for c in source.coverage
        ),
    )
    ctx = prepare_context(incomplete, parameters())
    unknown = calculate_history_volume_and_missingness(ctx, "N").values
    assert unknown["is_first_condition"] is None
    assert unknown["past_missing_reason"] == "not_collected"
    with pytest.raises(ValueError, match="history coverage is incomplete"):
        calculate_recent_performance(ctx, "N")
    last = source.history[-1]
    runner = replace(
        last.runners[0], elapsed_sec=None, missing_reasons={"elapsed_sec": "not_measured"}
    )
    missing = replace(
        source, history=(*source.history[:-1], replace(last, runners=(runner, *last.runners[1:])))
    )
    ctx = prepare_context(missing, parameters())
    assert calculate_recent_stability(ctx, "A").values["past_elapsed_sec_mean"] is None
    assert calculate_recent_stability(ctx, "A").values["past_elapsed_sec_valid_count"] == 2


def test_evidence_is_required_and_naive_clocks_are_not_inferred() -> None:
    with pytest.raises(ValueError, match="SourceEvidence is required"):
        validate_evidence(cast(SourceEvidence, None))
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_evidence(replace(evidence("bad", at(1)), received_at=datetime(2026, 6, 1)))
    with pytest.raises(ValueError, match="SHA-256"):
        validate_evidence(replace(evidence("bad", at(1)), content_hash="unknown"))
    with pytest.raises(ValueError, match="raw/Parquet"):
        parse_observation_inputs({"rows": [{"KettoNum": "A"}]})
    payload = normalized_payload(observations())
    assert isinstance(payload, dict)
    card = payload["card"]
    assert isinstance(card, dict)
    del card["evidence"]
    with pytest.raises(ValueError, match="evidence"):
        parse_observation_inputs({"schema_version": 1, "observations": [payload]})


def test_revision_conflicts_incomplete_results_and_unresolved_exceptions_fail() -> None:
    source = observations()
    duplicate = replace(
        source.history[-1],
        runners=tuple(replace(r, elapsed_sec=500.0) for r in source.history[-1].runners),
    )
    with pytest.raises(ValueError, match="conflicting source version"):
        prepare_context(replace(source, history=(*source.history, duplicate)), parameters())
    race_ = source.history[-1]
    for altered, message in (
        (replace(race_, complete=False), "complete"),
        (replace(race_, runners=race_.runners[:-1]), "complete field"),
        (
            replace(
                race_, runners=(replace(race_.runners[0], status="cancelled"), *race_.runners[1:])
            ),
            "non-normal",
        ),
        (
            replace(race_, runners=(replace(race_.runners[0], finish=2), *race_.runners[1:])),
            "finish ranks",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            prepare_context(replace(source, history=(*source.history[:-1], altered)), parameters())


@pytest.mark.parametrize(
    "p",
    [
        replace(parameters(), half_life_days=0),
        replace(parameters(), tie_policy="ordinal"),
        replace(parameters(), condition_keys=("raw_code",)),
        replace(parameters(), graph_damping=1),
        replace(parameters(), style_minimum_count=4),
    ],
)
def test_invalid_business_choices_are_rejected(p: CalculationParameters) -> None:
    with pytest.raises(
        ValueError, match=r"positive|unsupported|condition_keys|damping|style_minimum_count"
    ):
        validate_parameters(p)


def test_market_anchor_changes_sets_and_corrections() -> None:
    source = observations()
    context = prepare_context(source, parameters())
    market = calculate_market_characteristics(context, "A").values
    assert market["market_win_support"] == 0.5
    assert market["market_odds_ratio"] == 2
    assert market["market_log_odds_change"] == pytest.approx(log(2))
    assert market["market_place_width"] == pytest.approx(0.6)
    assert market["ticket_total_growth_tansyo"] == 60
    assert market["ticket_total_growth_rate_tansyo"] == 0.6
    latest = source.markets[-1]
    partial = replace(latest, pairs=latest.pairs[:-1])
    ctx = prepare_context(replace(source, markets=(*source.markets[:-1], partial)), parameters())
    assert calculate_market_characteristics(ctx, "A").values["market_pair_support_i"] is None
    decrease = replace(latest, ticket_totals={**latest.ticket_totals, "tansyo": 99})
    with pytest.raises(ValueError, match="decrease/correction"):
        calculate_market_characteristics(
            prepare_context(
                replace(source, markets=(*source.markets[:-1], decrease)), parameters()
            ),
            "A",
        )
    late = replace(
        source.markets[0], evidence=replace(source.markets[0].evidence, received_at=context.cutoff)
    )
    with pytest.raises(ValueError, match="no received"):
        calculate_market_characteristics(
            prepare_context(replace(source, markets=(late, latest)), parameters()), "A"
        )


def test_graph_direction_sum_unknown_and_nonconvergence() -> None:
    source = observations()
    single = race(
        "duel", 9, (result_runner("A", 1, 98.0, 1, 480.0), result_runner("B", 2, 100.0, 2, 500.0))
    )
    context = prepare_context(replace(source, history=(single,)), parameters())
    a = calculate_opponent_pagerank(context, "A")
    assert a.values["opponent_graph_score"] == pytest.approx(0.6)
    assert calculate_opponent_pagerank(context, "B").values[
        "opponent_graph_score"
    ] == pytest.approx(0.4)
    assert a.diagnostics["score_sum"] == pytest.approx(1)
    assert calculate_opponent_pagerank(context, "N").values["opponent_graph_score"] is None
    assert calculate_opponent_pagerank(context, "N").values["opponent_graph_known"] is False
    with pytest.raises(ValueError, match="did not converge"):
        calculate_opponent_pagerank(
            prepare_context(
                replace(source, history=(single,)), replace(parameters(), graph_max_iterations=1)
            ),
            "A",
        )


def test_lap_partial_boundary_workout_self_reference_and_unknown_categories() -> None:
    source = observations()
    last = source.history[-1]
    odd_sections = (
        replace(last.sections[0], distance_m=300),
        replace(last.sections[1], distance_m=500),
        *last.sections[2:],
    )
    # 300+500 is exactly half and is valid; 300+400 crosses halfway inside a section.
    odd_sections = (
        replace(odd_sections[0], distance_m=300),
        replace(odd_sections[1], distance_m=400),
        replace(odd_sections[2], distance_m=500),
        odd_sections[3],
    )
    altered = replace(source, history=(*source.history[:-1], replace(last, sections=odd_sections)))
    assert (
        calculate_past_lap_and_running_style(prepare_context(altered, parameters()), "A").values[
            "past_race_early_velocity_mps_lag1"
        ]
        is None
    )
    workout = calculate_hill_and_wood_workouts(prepare_context(source, parameters()), "A").values
    assert workout["hc_finish_accel_sec"] == 1
    assert workout["hc_self_reference_count"] == 1
    assert workout["hc_self_clock_diff_sec"] == -2
    assert workout["wc_last_clock_sec"] == 55
    unknown = replace(
        source, card=replace(source.card, conditions=replace(source.card.conditions, surface=None))
    )
    assert (
        calculate_condition_suitability(prepare_context(unknown, parameters()), "A").values[
            "horse_condition_start_count"
        ]
        is None
    )


def test_first_condition_checks_all_history_and_metric_validity_matches_configuration() -> None:
    source = observations()
    history = tuple(
        replace(r, conditions=replace(r.conditions, surface="dirt"))
        if r.race_id in {"r5", "r9"}
        else r
        for r in source.history
    )
    p = replace(parameters(), count_window=1, condition_window_order="window_then_filter")
    context = prepare_context(replace(source, history=history), p)
    assert calculate_condition_suitability(context, "A").values["horse_condition_start_count"] == 0
    volume = calculate_history_volume_and_missingness(context, "A").values
    assert volume["condition_observed_start_count"] == 1
    assert volume["is_first_condition"] is False
    latest = source.history[-1]
    missing = replace(
        latest,
        runners=(
            replace(
                latest.runners[0], elapsed_sec=None, missing_reasons={"elapsed_sec": "not_measured"}
            ),
            *latest.runners[1:],
        ),
    )
    changed = replace(source, history=(*source.history[:-1], missing))
    assert (
        calculate_history_volume_and_missingness(
            prepare_context(changed, replace(p, metric="last3f_sec")), "A"
        ).values["past_metric_valid_count"]
        == 3
    )
    assert (
        calculate_history_volume_and_missingness(prepare_context(changed, p), "A").values[
            "past_metric_valid_count"
        ]
        == 2
    )


def test_population_condition_rates_do_not_cut_simultaneous_starters_or_depend_on_input_order() -> (
    None
):
    source = observations()
    p = replace(parameters(), count_window=1, pedigree_include_self=True)
    first = prepare_context(source, p)
    shuffled = prepare_context(
        replace(
            source,
            history=tuple(replace(r, runners=tuple(reversed(r.runners))) for r in source.history),
        ),
        p,
    )
    for calculator, column in (
        (calculate_jockey_performance, "jockey_condition_start_count"),
        (calculate_trainer_performance, "trainer_condition_start_count"),
        (calculate_pedigree_suitability, "sire_condition_start_count"),
    ):
        assert calculator(first, "A").values == calculator(shuffled, "A").values
        assert calculator(first, "A").values[column] == 6


def test_explicit_no_smoothing_and_zero_reference_variance() -> None:
    source = observations()
    p = replace(parameters(), smoothing_alpha=0.0)
    validate_parameters(p)
    values = calculate_condition_suitability(prepare_context(source, p), "A").values
    assert values["horse_condition_smoothed_win_rate"] == values["horse_condition_win_rate"]
    refs = tuple(
        replace(r, runners=tuple(replace(runner, elapsed_sec=100.0) for runner in r.runners))
        if r.race_id.startswith("ref")
        else r
        for r in source.history
    )
    oldest_only = replace(source, history=(*refs[:2], refs[2]))
    adjusted = calculate_condition_adjusted_ability(prepare_context(oldest_only, p), "A")
    assert adjusted.values["past_condition_time_advantage"] is None
    assert adjusted.missing_reasons["past_condition_time_advantage"] == "zero_variance_reference"


def test_closing_measurement_distances_and_naive_history_are_rejected() -> None:
    source = observations()
    latest = source.history[-1]
    for distance in (400, None, 0):
        bad = replace(
            latest,
            runners=(replace(latest.runners[0], last3f_distance_m=distance), *latest.runners[1:]),
        )
        with pytest.raises(ValueError, match=r"measurement distance|positive metres"):
            prepare_context(replace(source, history=(*source.history[:-1], bad)), parameters())
    with pytest.raises(ValueError, match="timezone-aware"):
        prepare_context(
            replace(
                source,
                history=(*source.history[:-1], replace(latest, started_at=datetime(2026, 6, 9))),
            ),
            parameters(),
        )


def test_long_wood_session_uses_measured_trailing_distance_without_interpolation() -> None:
    source = observations()
    wood = source.workouts[-1]
    longer = replace(wood, sections=(Section(200, 15.0), Section(200, 15.0), *wood.sections))
    context = prepare_context(
        replace(source, workouts=(*source.workouts[:-1], longer)), parameters()
    )
    assert calculate_hill_and_wood_workouts(context, "A").values["wc_last_clock_sec"] == 55
    assert calculate_hill_and_wood_workouts(context, "A").values["wc_last_section_sec"] == 13
    broken = replace(
        longer, sections=(Section(300, 15.0), *longer.sections[:-2], Section(300, 15.0))
    )
    context = prepare_context(
        replace(source, workouts=(*source.workouts[:-1], broken)), parameters()
    )
    assert calculate_hill_and_wood_workouts(context, "A").values["wc_last_clock_sec"] is None


def test_missing_reasons_preserve_measurement_reason_and_separate_no_history() -> None:
    source = observations()
    last = source.history[-1]
    altered = replace(
        last,
        runners=(
            replace(
                last.runners[0], elapsed_sec=None, missing_reasons={"elapsed_sec": "not_measured"}
            ),
            *last.runners[1:],
        ),
    )
    context = prepare_context(
        replace(source, history=(*source.history[:-1], altered)), parameters()
    )
    measured = calculate_past_racing_ability(context, "A")
    assert measured.missing_reasons["past_elapsed_sec_lag1"] == "not_measured"
    assert (
        calculate_past_racing_ability(context, "N").missing_reasons["past_elapsed_sec_lag1"]
        == "no_history_at_lag"
    )
