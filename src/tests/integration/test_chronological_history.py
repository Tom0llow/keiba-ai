"""Shared chronological views reproduce per-race contexts and reject boundary violations."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import cast

import pytest

from make_features.contracts.observations import (
    Evidence,
    HistoricalRace,
    ObservationInput,
    ReferenceEvidence,
)
from make_features.generation.chronological import (
    ChronologicalHistory,
    ChronologicalInvariantError,
    WorkoutIndex,
    WorkoutView,
    evidence_extrema,
    shared_context,
)
from make_features.generation.observations import JST, CalculationContext, prepare_context
from make_features.reference_raw import evidence, workout
from make_features.reference_snapshot import (
    normalize_reference_history,
    normalize_reference_input,
)
from tests.reference_fixtures import RICH_TARGET_DAYS, _unique_rows, rich_raw_input


def _history(
    keys: list[str] | None = None,
) -> tuple[ChronologicalHistory, list[HistoricalRace], list[CalculationContext]]:
    raw = rich_raw_input(settings={"condition_keys": keys} if keys else None)
    normalized = normalize_reference_input(raw)
    tables = cast(dict[str, list[dict[str, object]]], raw["tables"])
    races, _ = normalize_reference_history(
        _unique_rows(tables["history_ra"] + tables["label_ra"]),
        _unique_rows(tables["history_se"] + tables["label_se"]),
        rules=cast(dict[str, object], raw["rules"]),
    )
    history = ChronologicalHistory(normalized.parameters)
    history.append(races)
    contexts = [
        prepare_context(source, normalized.parameters, reference=True)
        for source in normalized.observations
    ]
    return history, races, contexts


def test_day_views_equal_the_per_race_history_indexes_and_windows() -> None:
    history, _, contexts = _history()
    for day in RICH_TARGET_DAYS:
        same_day = [c for c in contexts if c.source.card.scheduled_start_at.date() == day]
        view = history.view(day, {})
        for context in same_day:
            assert view.races == context.races
            assert set(view.by_horse) == set(context.by_horse)
            assert {h: view.by_horse[h] for h in context.by_horse} == dict(context.by_horse)
            assert view.population == context.population
            graph_days = context.parameters.graph_days
            assert view.window(graph_days) == context.window_starts(graph_days)
            for runner in context.source.card.runners:
                if runner.jockey_id:
                    assert view.jockey_window(runner.jockey_id) == context.jockey_window(
                        runner.jockey_id
                    )
        if same_day:
            assert view.usable_through is not None
            assert view.usable_through <= min(c.cutoff for c in same_day)


@pytest.mark.parametrize("keys", [None, ["surface", "distance_m", "going"]])
def test_shared_as_of_baselines_equal_per_race_baselines_for_every_prior_start(
    keys: list[str] | None,
) -> None:
    history, _, contexts = _history(keys)
    checked = 0
    seen: set[str] = set()
    for context in contexts:
        for runner in context.source.card.runners:
            for race, _ in context.history(runner.horse_id, count=False):
                expected = context.baseline_statistics(race.started_at, race.conditions)
                actual = history.baseline_statistics(race.started_at, race.conditions)
                assert replace(actual, dependencies=()) == replace(expected, dependencies=())
                assert bool(actual.dependencies) == bool(expected.dependencies)
                for clock in ("available_at", "event_at") if expected.dependencies else ():
                    assert max(getattr(e, clock) for e in actual.dependencies) == max(
                        getattr(e, clock) for e in expected.dependencies
                    )
                checked += 1
                seen.update(
                    flag
                    for flag, present in (
                        ("unknown", expected.unknown),
                        ("unmeasured", expected.unmeasured_clock),
                        ("subset", expected.matched_count > 0),
                        ("none", expected.matched_count == 0 and not expected.unknown),
                    )
                    if present
                )
    assert checked > 50
    assert seen >= ({"unknown", "subset"} if keys else {"unmeasured", "subset", "none"})


def test_dependency_summary_keeps_both_clock_maxima_even_before_freeze() -> None:
    freeze = datetime(2026, 12, 20, 14, 55, tzinfo=JST)
    items = [
        evidence(
            f"e{i}",
            "test",
            i,
            event=freeze - timedelta(hours=h),
            usable=freeze - timedelta(hours=u),
            basis="b",
            event_basis="e",
        )
        for i, (h, u) in enumerate(((5, 4), (1, 3), (6, 2), (8, 8)))
    ]
    summary = evidence_extrema(items)
    assert max(e.available_at for e in summary) == max(e.available_at for e in items)
    assert max(e.event_at for e in summary) == max(e.event_at for e in items)
    assert len(summary) == 2


def _usable(value: Evidence, at: datetime) -> ReferenceEvidence:
    assert isinstance(value, ReferenceEvidence)
    return replace(value, usable_after=at)


def _declared(value: Evidence, at: datetime) -> ReferenceEvidence:
    assert isinstance(value, ReferenceEvidence)
    return replace(value, event_at=min(value.event_at, at), usable_after=at)


def test_history_index_rejects_out_of_order_duplicate_and_misaligned_races() -> None:
    _, races, contexts = _history()
    parameters = contexts[0].parameters
    ordered = sorted(races, key=lambda race: (race.started_at, race.race_id))
    late, early = ordered[-1], ordered[0]
    shifted = early.evidence.available_at + timedelta(hours=1)
    cases: list[list[HistoricalRace]] = [
        [late, early],
        [early, early],
        [replace(early, evidence=_usable(early.evidence, shifted))],
        [replace(early, started_at=early.started_at - timedelta(days=400))],
    ]
    for case in cases:
        history = ChronologicalHistory(parameters)
        history.append(case[:-1])
        with pytest.raises(ChronologicalInvariantError):
            history.append(case[-1:])


def test_views_move_forward_only_and_stale_views_fail() -> None:
    history, _, _ = _history()
    old = history.view(RICH_TARGET_DAYS[1], {})
    history.view(RICH_TARGET_DAYS[2], {})
    with pytest.raises(ChronologicalInvariantError):
        history.view(RICH_TARGET_DAYS[0], {})
    with pytest.raises(ChronologicalInvariantError):
        list(old.by_horse)
    with pytest.raises(ChronologicalInvariantError):
        history.register(replace(old.races[0].evidence, content_hash="f" * 64))


def _target_source() -> tuple[ChronologicalHistory, CalculationContext, ObservationInput]:
    history, _, contexts = _history()
    base = contexts[0].source
    population = base.coverage[0].horse_ids
    source = replace(
        base,
        coverage=tuple(
            replace(c, horse_ids=population) if c.kind in {"history", "pedigree"} else c
            for c in base.coverage
        ),
    )
    return history, contexts[0], source


def test_shared_context_rejects_evidence_later_than_freeze_in_every_source() -> None:
    history, context, source = _target_source()
    population = source.coverage[0].horse_ids
    late = source.freeze_at + timedelta(microseconds=1)
    market = source.markets[0]
    cases = {
        "card": replace(
            source, card=replace(source.card, evidence=_usable(source.card.evidence, late))
        ),
        "market": replace(
            source, markets=(replace(market, evidence=_usable(market.evidence, late)),)
        ),
        "coverage": replace(
            source,
            coverage=tuple(
                replace(c, evidence=_usable(c.evidence, late)) if c.kind == "workouts" else c
                for c in source.coverage
            ),
        ),
    }
    view = history.view(source.card.scheduled_start_at.astimezone(JST).date(), context.pedigrees)
    for name, case in cases.items():
        with pytest.raises(ChronologicalInvariantError, match=name):
            shared_context(case, view=view, workouts=WorkoutView(()), population=population)
    with pytest.raises(ChronologicalInvariantError, match="view date"):
        shared_context(
            replace(source, freeze_at=source.freeze_at + timedelta(days=1)),
            view=view,
            workouts=WorkoutView(()),
            population=population,
        )
    horse, pedigree = next(iter(context.pedigrees.items()))
    late_pedigrees = {
        **context.pedigrees,
        horse: replace(pedigree, evidence=_usable(pedigree.evidence, late)),
    }
    late_view = history.view(view.day, late_pedigrees)
    with pytest.raises(ChronologicalInvariantError, match="pedigree"):
        shared_context(source, view=late_view, workouts=WorkoutView(()), population=population)


def test_shared_results_keep_the_per_race_dependency_maxima_when_declarations_are_early() -> None:
    history, context, source = _target_source()
    early = source.freeze_at - timedelta(days=30)
    earlier = replace(
        source,
        card=replace(source.card, evidence=_declared(source.card.evidence, early)),
        coverage=tuple(replace(c, evidence=_declared(c.evidence, early)) for c in source.coverage),
    )
    expected = prepare_context(earlier, context.parameters, reference=True)
    view = history.view(source.card.scheduled_start_at.astimezone(JST).date(), expected.pedigrees)
    shared = shared_context(
        earlier, view=view, workouts=WorkoutView(()), population=source.coverage[0].horse_ids
    )
    extra = tuple(m.evidence for m in earlier.markets)
    for include_history in (True, False):
        for clock in ("available_at", "event_at"):
            values = [
                max(
                    getattr(e, clock)
                    for e in c.result(
                        {"x": 1.0}, extra=extra, include_history=include_history
                    ).dependencies
                )
                for c in (expected, shared)
            ]
            assert values[0] == values[1]
    assert max(e.available_at for e in shared.result({"x": 1.0}).dependencies) < source.freeze_at


def test_workout_views_reject_sessions_usable_after_their_date() -> None:
    _, _, contexts = _history()
    index = WorkoutIndex(contexts[0].parameters)
    row: dict[str, object] = {
        "headDataKubun": "1",
        "headMakeDate": "20270110",
        "TresenKubun": "0",
        "ChokyoDate": "20261219",
        "ChokyoTime": "0600",
        "KettoNum": "2020100001",
        **{f"LapTime{i}": "120" for i in range(1, 5)},
    }
    session = workout(row, kind="hc")
    shifted = session.evidence.available_at + timedelta(days=1)
    index.load((replace(session, evidence=_usable(session.evidence, shifted)),))
    with pytest.raises(ChronologicalInvariantError):
        index.view(date(2026, 12, 20))
