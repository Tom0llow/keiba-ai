"""Build one graded race's race-day betting proposal (ADR-045). No I/O.

A proposal adds, to a published ``pl_race_prediction``, each horse's win and place
expected return ``R = P * O_hat`` at the freeze-time O1 quotes, under the estimator's
ADR-044 method, and the ADR-043 policy's reference stakes for that race alone. The
proposed stake is always zero yen: the policy lost money in the backtests, so its
stakes are recorded for reference only. Candidates are built by the backtest's own
functions with the backtest's checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from zoneinfo import ZoneInfo

from models.artifacts.betting_estimator import BettingEstimator
from models.betting.policy import (
    Bet,
    BetCandidate,
    BettingPolicy,
    RaceDecision,
    decide_races,
    place_probability,
    requested_bet,
)
from models.betting.purchase_ledger import PurchaseLedger
from models.experiments.betting_backtest import method_probabilities, race_bet_candidates
from models.experiments.betting_estimator import year_estimators
from models.experiments.pl_prediction import (
    PREDICTION_FORMAT,
    PREDICTION_FORMAT_VERSION,
    RaceTarget,
    is_after_sales_close,
)
from models.market.place_width_correction import place_width
from models.serialization.betting_inputs import FreezeQuotes, HorsePrediction, freeze_quotes
from models.serialization.final_odds_observations import ObservationHold
from models.serialization.race_subsets import JRA_FLAT_GRADED_STAKES_V1

PROPOSAL_FORMAT = "ev_race_proposal"
PROPOSAL_FORMAT_VERSION = 2
PROPOSAL_STAGE = "proposal"
O1_TABLE = "ARCHIVE_O1_ODDS_TANFUKUWAKU"
_HORSE_NUMBER = re.compile(r"[0-9]{2}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX32 = re.compile(r"[0-9a-f]{32}")
_SUM_TOLERANCE = 1e-6
_ORDER_TOLERANCE = 1e-12
_JST = ZoneInfo("Asia/Tokyo")
_OUTCOMES = {
    "purchased": "reference_bets",
    "budget_exhausted": "budget_exhausted",
    "no_eligible_bet": "no_eligible_bet",
}


class ProposalHold(Exception):
    """A race that gets no proposal, with a reason code and a readable detail."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class PredictedHorse:
    """One horse of a published prediction."""

    horse_number: str
    horse_id: str
    win: float
    top2: float
    top3: float


@dataclass(frozen=True)
class PublishedPrediction:
    """A checked ``prediction.json`` and the identities a proposal needs from it."""

    sha256: str
    model_manifest_sha256: str
    features_manifest_sha256: str
    snapshot: Mapping[str, object]
    market_snapshot_id: str
    market_o1_sha256: str
    horses: tuple[PredictedHorse, ...]


@dataclass(frozen=True)
class RaceProposal:
    """One race's ``ev_race_proposal`` payload and its stdout summary."""

    race_id: str
    after_sales_close: bool
    bets: int
    reference_stake_yen: int
    race_remaining_yen: int
    annual_remaining_yen: int
    payload: Mapping[str, object]


def read_prediction(data: bytes, target: RaceTarget) -> PublishedPrediction:
    """Check one race's ``prediction.json`` bytes against its target and return them.

    Raises:
        ProposalHold: ``prediction_invalid`` for malformed or inconsistent content,
            ``market_source_unsupported`` when the market did not come from a race-day
            fetch, and ``market_source_mismatch`` when the fetch names another race or
            freeze.
    """

    invalid = _invalid
    try:
        payload = json.loads(data, parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise invalid("prediction.json is not strict JSON") from exc
    if not isinstance(payload, dict):
        raise invalid("prediction.json must be a JSON object")
    if (
        payload.get("format") != PREDICTION_FORMAT
        or payload.get("format_version") != PREDICTION_FORMAT_VERSION
    ):
        raise invalid("prediction format is not pl_race_prediction v1")
    race = _mapping(payload.get("race"), "race")
    if (
        race.get("race_id") != target.race_id
        or _clock(race.get("scheduled_start_at")) != target.scheduled_start_at
        or _clock(race.get("freeze_at")) != target.freeze_at
    ):
        raise invalid("prediction race or schedule differs from the stored card")
    horses = _horses(payload.get("horses"))
    if race.get("field_size") != len(horses):
        raise invalid("prediction field_size differs from its horses")
    if {h.horse_number: h.horse_id for h in horses} != dict(target.horse_mapping):
        raise invalid("prediction horses differ from the stored card")
    model = _mapping(payload.get("model"), "model")
    features = _mapping(payload.get("features"), "features")
    model_sha256, features_sha256 = model.get("manifest_sha256"), features.get("manifest_sha256")
    if not _is_hex64(model_sha256) or not _is_hex64(features_sha256):
        raise invalid("prediction model or features identity is malformed")
    snapshot = _mapping(payload.get("snapshot"), "snapshot")
    source = _mapping(features.get("market_source"), "features.market_source")
    if source.get("kind") != "race_day_prediction_fetch":
        raise ProposalHold(
            "market_source_unsupported", "the prediction's market is not a race-day fetch"
        )
    tables = source.get("tables")
    version, o1_sha256 = (
        source.get("snapshot_id"),
        (tables.get(O1_TABLE) if isinstance(tables, dict) else None),
    )
    if (
        not isinstance(version, str)
        or _HEX32.fullmatch(version) is None
        or not _is_hex64(o1_sha256)
    ):
        raise invalid("prediction market source identity is malformed")
    if (
        source.get("race_id") != target.race_id
        or _clock(source.get("freeze_at")) != target.freeze_at
    ):
        raise ProposalHold(
            "market_source_mismatch", "the race-day fetch names another race or freeze"
        )
    return PublishedPrediction(
        sha256=hashlib.sha256(data).hexdigest(),
        model_manifest_sha256=cast(str, model_sha256),
        features_manifest_sha256=cast(str, features_sha256),
        snapshot=snapshot,
        market_snapshot_id=version,
        market_o1_sha256=cast(str, o1_sha256),
        horses=horses,
    )


def build_race_proposal(
    *,
    target: RaceTarget,
    prediction: PublishedPrediction,
    market_win_odds: Mapping[str, float | None],
    o1_rows: Sequence[Mapping[str, object]],
    estimator: BettingEstimator,
    computed_at: datetime,
    snapshot: Mapping[str, object],
    provenance: Mapping[str, object],
    ledger: PurchaseLedger,
    ledger_required_since: datetime,
) -> RaceProposal:
    """Build one race's proposal from its prediction, features' market and freeze O1.

    ``market_win_odds`` maps each horse ID of the race's features to the win odds the
    model saw; ``o1_rows`` are the race-day fetch's O1 rows. ``computed_at`` is the one
    clock reading taken just before this calculation. The reference stakes are capped
    by the race and calendar-year budgets less the actual purchases in ``ledger``
    (ADR-046), whose latest confirmation must reach ``ledger_required_since``.

    Raises:
        ProposalHold: ``ledger_unconfirmed`` when the ledger's latest confirmation is
            missing or earlier than ``ledger_required_since``; ADR-042's freeze-quote
            holds, ``entrant_mismatch``, ``market_odds_mismatch``,
            ``blend_market_incomplete`` and ``blend_zero_probability``, as in the
            backtest.
        ValueError: If ``computed_at`` or ``ledger_required_since`` is not
            timezone-aware, or the race ID's date is not the freeze's JST date.
    """
    if computed_at.utcoffset() is None:
        raise ValueError("computed_at must be timezone-aware")
    if ledger_required_since.utcoffset() is None:
        raise ValueError("ledger_required_since must be timezone-aware")
    record = estimator.record
    race_id = target.race_id
    freeze = target.freeze_at
    freeze_day = freeze.astimezone(_JST).date()
    if race_id[:8] != freeze_day.strftime("%Y%m%d"):
        raise ValueError("the race ID's date differs from the freeze's JST date")
    confirmed = ledger.latest_confirmation
    if confirmed is None or confirmed < ledger_required_since:
        raise ProposalHold(
            "ledger_unconfirmed",
            "the purchase ledger is not confirmed since "
            f"{ledger_required_since.astimezone(UTC).isoformat()}",
        )
    year = freeze_day.year
    race_spent = ledger.race_spent_yen(race_id)
    annual_spent = ledger.annual_spent_yen(year)
    try:
        quotes = freeze_quotes(
            race_id,
            o1_rows,
            freeze,
            max_publication_age_seconds=record.settings.max_publication_age_seconds,
        )
    except ObservationHold as hold:
        raise ProposalHold(hold.reason, str(hold)) from hold
    numbers = [horse.horse_number for horse in prediction.horses]
    if set(numbers) != set(quotes.win) or {h.horse_id for h in prediction.horses} != set(
        market_win_odds
    ):
        raise ProposalHold("entrant_mismatch", "prediction, features and O1 horses differ")
    by_number: dict[str, HorsePrediction] = {}
    for horse in prediction.horses:
        market = market_win_odds[horse.horse_id]
        quote = quotes.win[horse.horse_number]
        if (market is None) != (quote is None) or (
            market is not None and quote is not None and not math.isclose(market, quote)
        ):
            raise ProposalHold("market_odds_mismatch", f"horse {horse.horse_number}")
        by_number[horse.horse_number] = HorsePrediction(
            horse.horse_id, horse.win, horse.top2, horse.top3, market
        )
    estimators = year_estimators(record)
    method = record.method
    try:
        probabilities = method_probabilities(race_id, method, by_number, estimators)
    except ObservationHold as hold:
        raise ProposalHold(hold.reason, str(hold)) from hold
    candidates, _, _ = race_bet_candidates(
        race_id, freeze, quotes, probabilities, method, estimators
    )
    policy = record.policy
    decisions = decide_races(
        candidates,
        policy=policy,
        annual_spent_yen={year: annual_spent},
        race_spent_yen={race_id: race_spent},
    )
    requested, funded, scaled = _reference(candidates, decisions, policy)
    outcome = _OUTCOMES[decisions[0].outcome] if decisions else "no_eligible_bet"
    race_remaining = max(0, policy.race_budget_yen - race_spent)
    annual_remaining = max(0, policy.annual_budget_yen - annual_spent)
    after = is_after_sales_close(target, computed_at)
    bets = [_bet_payload(bet, funded.get((bet.bet_type, bet.horse_number), 0)) for bet in requested]
    reference_total = sum(funded.values())
    payload: dict[str, object] = {
        "format": PROPOSAL_FORMAT,
        "format_version": PROPOSAL_FORMAT_VERSION,
        "computed_at": _iso(computed_at),
        "after_sales_close": after,
        "race": {
            "race_id": race_id,
            "scheduled_start_at": _iso(target.scheduled_start_at),
            "freeze_at": _iso(freeze),
            "field_size": len(numbers),
            "race_subset": JRA_FLAT_GRADED_STAKES_V1,
            "grade_code": target.grade_code,
        },
        "snapshot": dict(snapshot),
        "prediction": {
            "sha256": prediction.sha256,
            "model_manifest_sha256": prediction.model_manifest_sha256,
            "features_manifest_sha256": prediction.features_manifest_sha256,
        },
        "estimator": {
            "manifest_sha256": estimator.manifest_sha256,
            "target_year": record.target_year,
            "method": method,
        },
        "market": {
            "snapshot_id": prediction.market_snapshot_id,
            "o1_sha256": prediction.market_o1_sha256,
            "publication_age_seconds": quotes.age_seconds,
        },
        "policy": {
            "min_expected_return": record.policy.min_expected_return,
            "kelly_fraction": record.policy.kelly_fraction,
            "bankroll_yen": record.policy.bankroll_yen,
            "annual_budget_yen": record.policy.annual_budget_yen,
            "race_budget_yen": record.policy.race_budget_yen,
            "unit_yen": record.policy.unit_yen,
        },
        "horses": _horse_payloads(prediction, probabilities, candidates, quotes, method),
        "bets": bets,
        "ledger": {
            "sha256": ledger.sha256,
            "latest_confirmation_at": _iso(confirmed),
            "required_confirmed_since": _iso(ledger_required_since),
        },
        "budget": {
            "race_spent_yen": race_spent,
            "annual_spent_yen": annual_spent,
            "race_remaining_yen": race_remaining,
            "annual_remaining_yen": annual_remaining,
            "cap_yen": min(race_remaining, annual_remaining),
        },
        "decision": {
            "outcome": outcome,
            "scaled": scaled,
            "reference_stake_yen": reference_total,
            "stake_yen": 0,
        },
        "provenance": dict(provenance),
    }
    return RaceProposal(
        race_id, after, len(bets), reference_total, race_remaining, annual_remaining, payload
    )


def proposal_json(payload: Mapping[str, object]) -> bytes:
    """Serialize a payload as sorted-key ASCII JSON without NaN, ending with a newline.

    Raises:
        ValueError: If the payload holds NaN, an infinity or a value JSON cannot encode.
    """
    try:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"race proposal is not strict JSON: {exc}") from exc
    return (text + "\n").encode("ascii")


def _reference(
    candidates: Sequence[BetCandidate],
    decisions: Sequence[RaceDecision],
    policy: BettingPolicy,
) -> tuple[list[Bet], dict[tuple[str, str], int], bool]:
    """Return every requested bet, the race-capped reference stakes and whether scaled.

    The policy drops a bet whose stake scales to zero; it stays here with zero yen.
    """
    requested = [
        bet for candidate in candidates if (bet := requested_bet(candidate, policy)) is not None
    ]
    funded: dict[tuple[str, str], int] = {}
    scaled = False
    for decision in decisions:
        scaled = scaled or decision.scaled
        for bet in decision.bets:
            funded[(bet.bet_type, bet.horse_number)] = bet.stake_yen
    order = {"win": 0, "place": 1}
    requested.sort(key=lambda bet: (order[bet.bet_type], bet.horse_number))
    return requested, funded, scaled


def _bet_payload(bet: Bet, reference_stake_yen: int) -> dict[str, object]:
    return {
        "bet_type": bet.bet_type,
        "horse_number": bet.horse_number,
        "probability": bet.probability,
        "freeze_odds": bet.freeze_odds,
        "estimated_odds": bet.estimated_odds,
        "expected_return": bet.expected_return,
        "kelly_fraction": bet.kelly_fraction,
        "requested_stake_yen": bet.requested_stake_yen,
        "reference_stake_yen": reference_stake_yen,
        "stake_yen": 0,
    }


def _horse_payloads(
    prediction: PublishedPrediction,
    probabilities: Mapping[str, tuple[float, float, float]],
    candidates: Sequence[BetCandidate],
    quotes: FreezeQuotes,
    method: str,
) -> list[dict[str, object]]:
    by_key = {(item.bet_type, item.horse_number): item for item in candidates}
    count = len(probabilities)
    basis: Literal["top3", "top2"] | None = "top3" if count >= 8 else "top2" if count >= 5 else None
    horses: list[dict[str, object]] = []
    for horse in prediction.horses:
        number = horse.horse_number
        p_win, p_top2, p_top3 = probabilities[number]
        win = by_key.get(("win", number))
        place = by_key.get(("place", number))
        low, high = quotes.place_low.get(number), quotes.place_high.get(number)
        reason: str | None = None
        if place is None:
            if basis is None:
                reason = "field_size"
            elif quotes.place.get(number) is None:
                reason = "unquoted"
            elif not method.endswith("mid") and (
                low is None or high is None or place_width(low, high) is None
            ):
                reason = "place_width_invalid"
        horses.append(
            {
                "horse_number": number,
                "horse_id": horse.horse_id,
                "win_probability": p_win,
                "place_probability": place_probability(
                    entrant_count=count, p_top2=p_top2, p_top3=p_top3
                ),
                "place_basis": basis,
                "win": None
                if win is None
                else {
                    "freeze_odds": win.freeze_odds,
                    "estimated_odds": win.estimated_odds,
                    "expected_return": win.probability * win.estimated_odds,
                },
                "place": None
                if place is None
                else {
                    "odds_low": low,
                    "odds_high_recovered": high,
                    "freeze_odds": place.freeze_odds,
                    "estimated_odds": place.estimated_odds,
                    "expected_return": place.probability * place.estimated_odds,
                },
                "place_unavailable_reason": reason,
            }
        )
    return horses


def _invalid(detail: str) -> ProposalHold:
    return ProposalHold("prediction_invalid", detail)


def _horses(value: object) -> tuple[PredictedHorse, ...]:
    if not isinstance(value, list) or not value:
        raise _invalid("prediction horses must be a non-empty list")
    horses: list[PredictedHorse] = []
    for item in value:
        entry = _mapping(item, "horse")
        number, horse_id = entry.get("horse_number"), entry.get("horse_id")
        if not isinstance(number, str) or _HORSE_NUMBER.fullmatch(number) is None:
            raise _invalid("prediction horse numbers must be two-digit strings")
        if not isinstance(horse_id, str) or not horse_id:
            raise _invalid("prediction horse IDs must be nonempty strings")
        win, top2, top3 = (_probability(entry.get(key)) for key in ("win", "top2", "top3"))
        if win > top2 + _ORDER_TOLERANCE or top2 > top3 + _ORDER_TOLERANCE:
            raise _invalid(f"horse {number}: probabilities must satisfy win <= top2 <= top3")
        horses.append(PredictedHorse(number, horse_id, win, top2, top3))
    numbers = [horse.horse_number for horse in horses]
    if numbers != sorted(set(numbers)) or len({h.horse_id for h in horses}) != len(horses):
        raise _invalid("prediction horses must be unique and sorted by horse number")
    for name, expected in (("win", 1.0), ("top2", 2.0), ("top3", 3.0)):
        total = sum(getattr(horse, name) for horse in horses)
        if abs(total - min(expected, len(horses))) > _SUM_TOLERANCE:
            raise _invalid(f"prediction {name} probabilities do not sum to {expected:g}")
    return tuple(horses)


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _invalid(f"prediction {name} must be an object")
    return cast(dict[str, object], value)


def _probability(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise _invalid("prediction probabilities must be finite and in [0, 1]")
    return float(value)


def _clock(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(cast(str, value))
    except (TypeError, ValueError) as exc:
        raise _invalid("prediction clocks must be ISO 8601") from exc
    if parsed.utcoffset() is None:
        raise _invalid("prediction clocks must be timezone-aware")
    return parsed


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _reject_constant(value: str) -> object:
    raise ValueError(f"prediction.json must not contain {value}")


__all__ = [
    "PROPOSAL_FORMAT",
    "PROPOSAL_FORMAT_VERSION",
    "PROPOSAL_STAGE",
    "ProposalHold",
    "PublishedPrediction",
    "RaceProposal",
    "build_race_proposal",
    "proposal_json",
    "read_prediction",
]
