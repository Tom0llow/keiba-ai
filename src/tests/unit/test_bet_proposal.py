"""Tests for one race's ADR-045 race-day proposal against the backtest's own candidates."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from models.artifacts.betting_estimator import BettingEstimator
from models.betting.methods import METHODS, Method
from models.betting.policy import BettingPolicy, decide_races, requested_bet
from models.experiments import betting_backtest as backtest
from models.experiments.bet_proposal import (
    O1_TABLE,
    ProposalHold,
    RaceProposal,
    build_race_proposal,
    proposal_json,
    read_prediction,
)
from models.experiments.betting_backtest import GradedRaceInput
from models.experiments.betting_estimator import year_estimators
from models.experiments.pl_prediction import RaceTarget
from models.serialization.betting_inputs import race_predictions
from tests.betting_estimator_fixtures import estimator_record, estimator_settings
from tests.betting_fixtures import (
    HORSES,
    P_TOP2,
    P_TOP3,
    P_WIN,
    WIN_CODES,
    horse_id,
    hr_row,
    o1_row,
    prediction_rows,
    ra_row,
    race_id,
    se_rows,
)

RACE = race_id(2025)
START = datetime(2025, 6, 15, 6, 30, tzinfo=UTC)
FREEZE = START - timedelta(minutes=5)
TARGET = RaceTarget(RACE, START, FREEZE, {h: horse_id(RACE, h) for h in HORSES}, "A")
SNAPSHOT = {"snapshot_id": "e" * 32, "tables": {"NL_RA_RACE": "1" * 64}}
MARKET = {horse_id(RACE, h): int(code) / 10 for h, code in zip(HORSES, WIN_CODES, strict=True)}
Payload = dict[str, object]


def _payload(**changes: object) -> Payload:
    payload: Payload = {
        "format": "pl_race_prediction",
        "format_version": 1,
        "computed_at": (FREEZE + timedelta(seconds=10)).isoformat(),
        "after_sales_close": False,
        "race": {
            "race_id": RACE,
            "scheduled_start_at": START.isoformat(),
            "freeze_at": FREEZE.isoformat(),
            "field_size": len(HORSES),
            "race_subset": "jra_flat_graded_stakes_v1",
            "grade_code": "A",
        },
        "model": {"manifest_sha256": "a" * 64},
        "features": {
            "manifest_sha256": "b" * 64,
            "market_source": {
                "kind": "race_day_prediction_fetch",
                "race_id": RACE,
                "freeze_at": FREEZE.astimezone(_JST).isoformat(),
                "snapshot_id": "d" * 32,
                "tables": {O1_TABLE: "c" * 64},
            },
        },
        "snapshot": SNAPSHOT,
        "horses": [
            {
                "horse_number": h,
                "horse_id": horse_id(RACE, h),
                "score": 0.0,
                "win": P_WIN[i],
                "top2": P_TOP2[i],
                "top3": P_TOP3[i],
            }
            for i, h in enumerate(HORSES)
        ],
    }
    payload.update(changes)
    return payload


_JST = ZoneInfo("Asia/Tokyo")


def _bytes(payload: Payload) -> bytes:
    return json.dumps(payload).encode("ascii")


def _estimator(method: Method, policy: BettingPolicy | None = None) -> BettingEstimator:
    record = estimator_record(target_year=2025, winner=method)
    if policy is not None:
        record = replace(record, policy=policy)
    return BettingEstimator("f" * 64, {}, record)


def _propose(
    method: Method = "pl_mid",
    *,
    payload: Payload | None = None,
    market: Mapping[str, float | None] | None = None,
    o1: list[dict[str, object]] | None = None,
    at: datetime | None = None,
    policy: BettingPolicy | None = None,
) -> RaceProposal:
    return build_race_proposal(
        target=TARGET,
        prediction=read_prediction(_bytes(payload or _payload()), TARGET),
        market_win_odds=MARKET if market is None else market,
        o1_rows=o1 or [o1_row(RACE)],
        estimator=_estimator(method, policy),
        computed_at=at or FREEZE + timedelta(seconds=20),
        snapshot=SNAPSHOT,
        provenance={"fixture": True},
    )


@pytest.mark.parametrize("method", METHODS)
def test_each_method_gives_the_backtest_candidates_and_policy_stakes(method: Method) -> None:
    proposal = _propose(method)
    record = _estimator(method).record
    race = GradedRaceInput(RACE, [ra_row(RACE)], [o1_row(RACE)], se_rows(RACE), [hr_row(RACE)])
    prediction = race_predictions(prediction_rows(RACE), variant="all_columns", test_years=(2025,))
    candidates, _, _ = backtest._race_candidates(
        race,
        prediction[RACE],
        method,
        year_estimators(record),
        estimator_settings((2023, 2024)),
    )
    requested = {
        (bet.bet_type, bet.horse_number): bet
        for candidate in candidates
        if (bet := requested_bet(candidate, record.policy)) is not None
    }
    funded = {
        (bet.bet_type, bet.horse_number): bet
        for decision in decide_races(candidates, policy=record.policy)
        for bet in decision.bets
    }
    payload = proposal.payload
    bets = payload["bets"]
    assert isinstance(bets, list)
    assert {(bet["bet_type"], bet["horse_number"]) for bet in bets} == set(requested)
    for bet in bets:
        key = (bet["bet_type"], bet["horse_number"])
        expected = requested[key]
        assert bet["probability"] == expected.probability
        assert bet["estimated_odds"] == expected.estimated_odds
        assert bet["requested_stake_yen"] == expected.requested_stake_yen
        assert bet["reference_stake_yen"] == (funded[key].stake_yen if key in funded else 0)
        assert bet["stake_yen"] == 0
    horses = {item["horse_number"]: item for item in _items(payload["horses"])}
    for candidate in candidates:
        entry = horses[candidate.horse_number][candidate.bet_type]
        assert entry["estimated_odds"] == candidate.estimated_odds
        assert entry["expected_return"] == candidate.probability * candidate.estimated_odds
    decision = payload["decision"]
    assert decision == {
        "outcome": "reference_bets" if bets else "no_eligible_bet",
        "scaled": any(d.scaled for d in decide_races(candidates, policy=record.policy)),
        "reference_stake_yen": sum(bet.stake_yen for bet in funded.values()),
        "stake_yen": 0,
    }
    assert payload["estimator"] == {
        "manifest_sha256": "f" * 64,
        "target_year": 2025,
        "method": method,
    }
    assert proposal.bets == len(bets)
    proposal_json(payload)


def test_a_bet_scaled_to_zero_stays_with_its_requested_stake() -> None:
    full = _propose()
    requested = [bet["requested_stake_yen"] for bet in _items(full.payload["bets"])]
    total = sum(requested)

    for budget in (1000, 200):
        proposal = _propose(policy=BettingPolicy(race_budget_yen=budget))
        bets = proposal.payload["bets"]
        assert isinstance(bets, list)
        assert [bet["requested_stake_yen"] for bet in bets] == requested
        assert [bet["reference_stake_yen"] for bet in bets] == [
            stake * budget // total // 100 * 100 for stake in requested
        ]
        assert proposal.payload["decision"]["scaled"] is True  # type: ignore[index]
    assert _propose(policy=BettingPolicy(race_budget_yen=200)).reference_stake_yen == 0


def test_after_sales_close_follows_the_clock_reading() -> None:
    close = START - timedelta(minutes=2)

    assert _propose(at=close).after_sales_close is False
    assert _propose(at=close + timedelta(microseconds=1)).after_sales_close is True


def _hold(action: Callable[[], object]) -> str:
    with pytest.raises(ProposalHold) as caught:
        action()
    return caught.value.reason


def _horse(index: int, **changes: object) -> list[dict[str, object]]:
    horses = _items(json.loads(json.dumps(_payload()["horses"])))
    horses[index].update(changes)
    return horses


def _items(value: object) -> list[dict[str, Any]]:
    assert isinstance(value, list)
    return cast(list[dict[str, Any]], value)


def _race(**changes: object) -> dict[str, object]:
    race = _payload()["race"]
    assert isinstance(race, dict)
    return {**race, **changes}


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"{", "prediction_invalid"),
        (b'{"x": NaN}', "prediction_invalid"),
        (_bytes(_payload(format_version=2)), "prediction_invalid"),
        (_bytes(_payload(race=_race(field_size=7))), "prediction_invalid"),
        (_bytes(_payload(race=_race(race_id=race_id(2025, 2)))), "prediction_invalid"),
        (_bytes(_payload(horses=list(reversed(_horse(0))))), "prediction_invalid"),
        (_bytes(_payload(horses=_horse(0, win=0.5))), "prediction_invalid"),
        (_bytes(_payload(horses=_horse(0, top2=0.3))), "prediction_invalid"),
        (_bytes(_payload(horses=_horse(0, horse_number="1"))), "prediction_invalid"),
        (_bytes(_payload(model={"manifest_sha256": "x"})), "prediction_invalid"),
        (_bytes(_payload(horses=_horse(0, horse_id="9999999999"))), "prediction_invalid"),
        (
            _bytes(
                _payload(
                    features={
                        "manifest_sha256": "b" * 64,
                        "market_source": {"kind": "complete_snapshot"},
                    }
                )
            ),
            "market_source_unsupported",
        ),
    ],
)
def test_a_malformed_or_foreign_prediction_is_held(data: bytes, reason: str) -> None:
    assert _hold(lambda: read_prediction(data, TARGET)) == reason


def test_a_fetch_of_another_race_or_freeze_is_held_and_offsets_do_not_matter() -> None:
    def source(**changes: object) -> bytes:
        payload = _payload()
        features = json.loads(json.dumps(payload["features"]))
        features["market_source"].update(changes)
        return _bytes(_payload(features=features))

    assert read_prediction(source(freeze_at=FREEZE.isoformat()), TARGET).market_snapshot_id
    for data in (source(race_id=race_id(2025, 2)), source(freeze_at=START.isoformat())):
        with pytest.raises(ProposalHold) as caught:
            read_prediction(data, TARGET)
        assert caught.value.reason == "market_source_mismatch"


def test_market_and_entrant_checks_hold_the_race_as_the_backtest_does() -> None:
    stale = [o1_row(RACE, clock="1514")]
    assert _hold(lambda: _propose(o1=stale)) == "stale_publication"
    missing = {key: value for key, value in MARKET.items() if not key.endswith("08")}
    assert _hold(lambda: _propose(market=missing)) == "entrant_mismatch"
    changed = {**MARKET, horse_id(RACE, "01"): 3.1}
    assert _hold(lambda: _propose(market=changed)) == "market_odds_mismatch"
    broken = [{**o1_row(RACE), "HappyoTime": "bad"}]
    assert _hold(lambda: _propose(o1=broken)) == "invalid_publication"

    unnumbered = [{**o1_row(RACE), "OddsTansyoInfo0Umaban": None}]
    assert _hold(lambda: _propose(o1=unnumbered)) == "invalid_quote"


@pytest.mark.parametrize("method", ["pl_mid", "pl_width"])
def test_an_unquoted_horse_gives_the_backtest_candidates(method: Method) -> None:
    codes = (*WIN_CODES[:7], "0000")
    o1 = [o1_row(RACE, win_codes=codes)]
    market: dict[str, float | None] = {**MARKET, horse_id(RACE, "08"): None}
    record = _estimator(method).record
    race = GradedRaceInput(RACE, [ra_row(RACE)], o1, se_rows(RACE), [hr_row(RACE)])
    rows = prediction_rows(RACE, market={"08": None})
    prediction = race_predictions(rows, variant="all_columns", test_years=(2025,))
    candidates, _, _ = backtest._race_candidates(
        race, prediction[RACE], method, year_estimators(record), estimator_settings((2023, 2024))
    )

    proposal = _propose(method, o1=o1, market=market)

    horses = {item["horse_number"]: item for item in _items(proposal.payload["horses"])}
    expected = {(item.bet_type, item.horse_number): item for item in candidates}
    produced = {
        (kind, number)
        for number, item in horses.items()
        for kind in ("win", "place")
        if item[kind] is not None
    }
    assert produced == set(expected)
    assert ("win", "08") not in produced
    for (kind, number), candidate in expected.items():
        entry = horses[number][kind]
        assert entry["freeze_odds"] == candidate.freeze_odds
        assert entry["estimated_odds"] == candidate.estimated_odds
        assert entry["expected_return"] == candidate.probability * candidate.estimated_odds


def test_an_unquoted_horse_skips_its_win_bet_or_holds_a_blend() -> None:
    codes = (*WIN_CODES[:7], "0000")
    o1 = [o1_row(RACE, win_codes=codes)]
    market = {**MARKET, horse_id(RACE, "08"): None}

    proposal = _propose("pl_mid", o1=o1, market=market)
    horses = {item["horse_number"]: item for item in _items(proposal.payload["horses"])}
    assert horses["08"]["win"] is None
    assert horses["08"]["place"] is not None
    assert _hold(lambda: _propose("blend_mid", o1=o1, market=market)) == "blend_market_incomplete"


def test_a_zero_win_probability_holds_only_a_blend() -> None:
    horses = _horse(7, win=0.0)
    horses[6]["win"] = P_WIN[6] + P_WIN[7]
    payload = _payload(horses=horses)

    assert _propose("pl_width", payload=payload).payload["horses"]
    assert _hold(lambda: _propose("blend_width", payload=payload)) == "blend_zero_probability"


def test_an_eight_horse_race_bases_every_place_bet_on_top3() -> None:
    proposal = _propose("pl_mid")
    horses = proposal.payload["horses"]
    assert isinstance(horses, list)
    assert {item["place_basis"] for item in horses} == {"top3"}
    assert all(item["place_unavailable_reason"] is None for item in horses)
