"""Normalize bounded projected Parquet rows under explicit reference assumptions."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import cast

from make_features.contracts.observations import (
    CalculationParameters,
    Coverage,
    HorseOdds,
    MarketObservation,
    ObservationInput,
    PairOdds,
    PedigreeObservation,
    RaceCard,
)
from make_features.real_market import (
    JST,
    O1_TABLE,
    canonical_hash,
    latest_o1,
    publication,
    timestamp,
    validate_races,
    win_quotes,
)
from make_features.reference_raw import (
    CARD_RA_COLUMNS,
    CARD_SE_COLUMNS,
    O2_TABLE,
    UM_TABLE,
    card_runner,
    conditions,
    evidence,
    historical_race,
    identifier,
    normal_result,
    race_identity,
    scheduled_start,
    text,
    validate_reference_projections,
    workout,
)
from make_features.reference_rules import validate_reference_rules
from make_features.serialization.observations import parse_calculation_parameters


@dataclass(frozen=True)
class ReferenceNormalization:
    """Keep normalized sources, explicit whole-race holds and separate labels."""

    observations: tuple[ObservationInput, ...]
    parameters: CalculationParameters
    held_races: tuple[dict[str, object], ...]
    labels: tuple[dict[str, object], ...]


def _groups(rows: Sequence[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        result.setdefault(race_identity(row), []).append(row)
    return result


def _one(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    unique = {canonical_hash(row): row for row in rows}
    if len(unique) != 1:
        raise ValueError("ambiguous_or_missing_race_row")
    return next(iter(unique.values()))


def _quote(value: object, *, digits: int) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("odds require raw nullable strings")
    value = value.strip()
    if not value or set(value) in ({"0"}, {"-"}, {"*"}, {"9"}):
        return None
    if re.fullmatch(r"[0-9]{" + str(digits) + r"}", value) is None or int(value) < 10:
        raise ValueError("invalid decimal odds encoding")
    return int(value) / 10


def market_at(
    o1_rows: Sequence[dict[str, object]],
    o2_rows: Sequence[dict[str, object]],
    *,
    race_id: str,
    cutoff: datetime,
    mapping: Mapping[str, str],
) -> MarketObservation:
    """Synchronize latest phase-1 horse and unordered-pair quotes at each anchor."""
    manifest = {"race_id": race_id, "freeze_at": cutoff.isoformat()}
    o1, o2 = latest_o1(o1_rows, manifest), latest_o1(o2_rows, manifest)
    p1, p2 = publication(o1), publication(o2)
    win = {number: value for number, value, _ in win_quotes(o1)}
    if set(win) != set(mapping):
        raise ValueError("intermediate market horse set differs from stored entrant mapping")
    places: dict[str, tuple[float | None, float | None]] = {}
    for i in range(28):
        number = identifier(o1, f"OddsFukusyoInfo{i}Umaban")
        if number is None:
            continue
        if number not in mapping or number in places:
            raise ValueError("invalid place quote horse mapping")
        places[number] = (
            _quote(o1.get(f"OddsFukusyoInfo{i}OddsLow"), digits=4),
            _quote(o1.get(f"OddsFukusyoInfo{i}OddsHigh"), digits=4),
        )
    horses = tuple(
        HorseOdds(mapping[number], value, *places.get(number, (None, None)))
        for number, value in sorted(win.items())
    )
    pairs = []
    seen: set[tuple[str, str]] = set()
    for i in range(153):
        code = identifier(o2, f"OddsUmarenInfo{i}Kumi")
        if code is None:
            continue
        if (
            re.fullmatch(r"[0-9]{4}", code) is None
            or code[:2] not in mapping
            or code[2:] not in mapping
            or code[:2] >= code[2:]
        ):
            raise ValueError("invalid unordered O2 pair mapping")
        ordered_ids = sorted((mapping[code[:2]], mapping[code[2:]]))
        ids = (ordered_ids[0], ordered_ids[1])
        if ids in seen:
            raise ValueError("duplicate unordered O2 pair")
        seen.add(ids)
        pairs.append(PairOdds(ids, _quote(o2.get(f"OddsUmarenInfo{i}Odds"), digits=6)))
    totals = {}
    for kind, row, column in (
        ("tansyo", o1, "TotalHyosuTansyo"),
        ("fukusyo", o1, "TotalHyosuFukusyo"),
        ("wakuren", o1, "TotalHyosuWakuren"),
        ("umaren", o2, "TotalHyosuUmaren"),
    ):
        raw = text(row, column)
        if raw is None or re.fullmatch(r"[0-9]+", raw) is None:
            raise ValueError(f"missing or invalid market ticket total: {column}")
        # JV-Data totals are 100-yen ticket units, not yen or inferred amounts.
        totals[kind] = int(raw)
    return MarketObservation(
        race_id,
        horses,
        tuple(pairs),
        tuple(mapping.values()),
        tuple(pair.horse_ids for pair in pairs),
        totals,
        evidence(
            f"o1:{race_id}:{o1['HappyoTime']}",
            O1_TABLE,
            o1,
            event=p1,
            usable=p1,
            basis="assumed_received_at_publication",
            event_basis="actual_intermediate_publication",
            published=p1,
        ),
        evidence(
            f"o2:{race_id}:{o2['HappyoTime']}",
            O2_TABLE,
            o2,
            event=p2,
            usable=p2,
            basis="assumed_received_at_publication",
            event_basis="actual_intermediate_publication",
            published=p2,
        ),
    )


def normalize_reference_input(raw: Mapping[str, object]) -> ReferenceNormalization:
    """Reproducibly map stored rows; never fetch data or infer actual reception clocks."""
    if (
        set(raw)
        != {
            "format_version",
            "snapshot",
            "rules",
            "calculation_settings",
            "races",
            "tables",
            "include_labels",
        }
        or type(raw["format_version"]) is not int
        or raw["format_version"] != 1
        or type(raw["include_labels"]) is not bool
    ):
        raise ValueError("invalid versioned reference input")
    rules = validate_reference_rules(raw["rules"])
    manifests = validate_races(raw["races"])
    settings = raw["calculation_settings"]
    if not isinstance(settings, dict) or "evidence" in settings:
        raise ValueError("reference calculation_settings must exclude measured evidence")
    history_start_raw = settings.get("history_start")
    if not isinstance(history_start_raw, str):
        raise ValueError("reference history_start is required")
    start = datetime.combine(datetime.fromisoformat(history_start_raw).date(), time.min, JST)
    if start.year < 2005:
        raise ValueError("reference raw interpretation currently supports 2005 onward")
    selection = evidence(
        "reference-parameters:" + canonical_hash({"settings": settings, "rules": rules}),
        "reference:configuration",
        {"settings": settings, "rules": rules},
        event=start,
        usable=start,
        basis="retrospective_fixed_configuration",
        event_basis="declared_history_start_boundary_not_actual_selection_time",
    )
    from make_features.serialization.observations import normalized_payload

    parameters = parse_calculation_parameters(
        {**settings, "evidence": normalized_payload(selection)}, reference=True
    )
    tables = raw["tables"]
    names = {
        "history_ra",
        "history_se",
        "target_ra",
        "target_se",
        "o1",
        "o2",
        "hc",
        "wc",
        "um",
        "label_ra",
        "label_se",
    }
    if (
        not isinstance(tables, dict)
        or set(tables) != names
        or any(
            not isinstance(v, list) or any(not isinstance(r, dict) for r in v)
            for v in tables.values()
        )
    ):
        raise ValueError("reference input requires every explicitly projected table population")
    sources = cast(dict[str, list[dict[str, object]]], tables)
    validate_reference_projections(sources)
    history_ra, history_se = _groups(sources["history_ra"]), _groups(sources["history_se"])
    held: list[dict[str, object]] = []
    history = []
    for identity in sorted(history_ra.keys() | history_se.keys()):
        rows = history_ra.get(identity, [])
        if identity[8:10] not in cast(list[str], rules["venues"]):
            raise ValueError("reference history contains a venue outside its declared population")
        try:
            race = historical_race(
                _one(rows), history_se.get(identity, ()), days=cast(int, rules["result_delay_days"])
            )
        except ValueError as exc:
            held.append(
                {"race_id": identity, "role": "history", "reason": str(exc), "whole_race": True}
            )
            continue
        history.append(race)
    workouts = tuple(workout(row, kind=kind) for kind in ("hc", "wc") for row in sources[kind])
    target_ra, target_se = _groups(sources["target_ra"]), _groups(sources["target_se"])
    label_ra, label_se = _groups(sources["label_ra"]), _groups(sources["label_se"])
    observations = []
    labels = []
    for manifest in sorted(manifests, key=lambda r: str(r["race_id"])):
        identity = cast(str, manifest["race_id"])
        try:
            if int(identity[:4]) < 2005 or identity[8:10] not in cast(list[str], rules["venues"]):
                raise ValueError("target race is outside the declared supported population")
            ra = _one(target_ra.get(identity, ()))
            scheduled = scheduled_start(ra)
            freeze = timestamp(manifest.get("freeze_at"))
            if timestamp(
                manifest.get("scheduled_start_at")
            ) != scheduled or scheduled - freeze != timedelta(seconds=300):
                raise ValueError(
                    "freeze must equal stored scheduled start minus exactly 300 seconds"
                )
            if manifest.get("schedule_known_at") is not None:
                raise ValueError(
                    "assumed stored schedule must not claim an actual schedule_known_at"
                )
            o1 = latest_o1(sources["o1"], manifest)
            quotes = win_quotes(o1)
            if any(
                reason in {"cancelled_before_sale", "cancelled_after_sale"}
                for _, _, reason in quotes
            ):
                raise ValueError("intermediate O1 indicates a cancelled entrant")
            entrants = sorted(target_se.get(identity, ()), key=lambda r: str(r.get("Umaban")))
            safe_ra = {k: ra.get(k) for k in CARD_RA_COLUMNS}
            safe_se = [{k: row.get(k) for k in CARD_SE_COLUMNS} for row in entrants]
            runners = tuple(card_runner(row) for row in safe_se)
            mapping = {r.horse_number: r.horse_id for r in runners}
            if (
                len(mapping) != len(runners)
                or len(set(mapping.values())) != len(runners)
                or set(mapping) != {q[0] for q in quotes}
            ):
                raise ValueError(
                    "stored card permanent IDs must match complete intermediate O1 horse set"
                )
            raw_card = {"ra": safe_ra, "se": safe_se}
            card = RaceCard(
                identity,
                scheduled,
                conditions(safe_ra, target=True),
                runners,
                tuple(r.horse_id for r in runners),
                True,
                evidence(
                    f"card:{identity}",
                    "reference:stored_pre_race_fields",
                    raw_card,
                    event=freeze,
                    usable=freeze,
                    basis="stored_pre_race_fields_revision_unverified",
                    event_basis="declared_freeze_boundary_not_observed_card_event",
                ),
            )
            markets = tuple(
                market_at(
                    sources["o1"], sources["o2"], race_id=identity, cutoff=anchor, mapping=mapping
                )
                for anchor in (freeze - timedelta(seconds=parameters.market_anchor_seconds), freeze)
            )
            available_history = tuple(
                r
                for r in history
                if start.date() <= r.started_at.date() < scheduled.date()
                and r.evidence.available_at <= freeze
                and r.race_id != identity
            )
            population = tuple(
                sorted(
                    set(mapping.values())
                    | {r.horse_id for race in available_history for r in race.runners}
                )
            )
            pedigree_rows: dict[str, list[dict[str, object]]] = {}
            for row in sources["um"]:
                horse = identifier(row, "KettoNum")
                if horse is not None and horse in population:
                    pedigree_rows.setdefault(horse, []).append(row)
            pedigrees = []
            for horse in population:
                rows = pedigree_rows.get(horse, [])
                row = (
                    _one(rows)
                    if rows
                    else {"KettoNum": horse, "missing_reason": "not_in_fixed_snapshot_master"}
                )
                pedigrees.append(
                    PedigreeObservation(
                        horse,
                        identifier(row, "Ketto3Info0HansyokuNum"),
                        identifier(row, "Ketto3Info4HansyokuNum"),
                        evidence(
                            f"pedigree:{horse}",
                            UM_TABLE,
                            row,
                            event=start,
                            usable=start,
                            basis="stored_parent_identifiers_revision_unverified",
                            event_basis="declared_history_start_boundary_not_parent_registration_clock",
                        ),
                    )
                )
            coverage = tuple(
                Coverage(
                    kind,
                    start
                    if kind in {"history", "pedigree"}
                    else freeze - timedelta(days=parameters.days_window)
                    if kind == "workouts"
                    else freeze
                    - timedelta(
                        seconds=parameters.market_anchor_seconds + parameters.market_max_age_seconds
                    ),
                    freeze,
                    population if kind in {"history", "pedigree"} else tuple(mapping.values()),
                    True,
                    cast(str, rules["coverage_scope"]),
                    evidence(
                        f"coverage:{identity}:{kind}",
                        "reference:coverage_declaration",
                        {
                            "snapshot": raw["snapshot"],
                            "kind": kind,
                            "population": population,
                            "freeze": freeze.isoformat(),
                            "scope": rules["coverage_scope"],
                        },
                        event=freeze,
                        usable=freeze,
                        basis=cast(str, rules["coverage_scope"]),
                        event_basis="declared_reference_coverage_boundary",
                    ),
                )
                for kind in ("history", "pedigree", "workouts", "market")
            )
            sessions = tuple(
                w
                for w in workouts
                if freeze - timedelta(days=parameters.days_window) <= w.evidence.event_at
                and w.evidence.event_at.date() < scheduled.date()
                and w.evidence.available_at <= freeze
            )
            label = None
            if raw["include_labels"]:
                label_id, usable, finishes, result_raw = normal_result(
                    _one(label_ra.get(identity, ())),
                    label_se.get(identity, ()),
                    days=cast(int, rules["result_delay_days"]),
                )
                if set(finishes) != set(mapping.values()):
                    raise ValueError("label permanent horse set differs from frozen O1-mapped card")
                label = {
                    "kind": "reference_result_v1",
                    "race_id": label_id,
                    "raw": result_raw,
                    "raw_sha256": canonical_hash(result_raw),
                    "usable_after": usable.isoformat(),
                    "result_delay_days": rules["result_delay_days"],
                    "received_at": None,
                    "result_published_at": None,
                    "revision_time_verified": False,
                    "horse_mapping": dict(mapping),
                }
        except ValueError as exc:
            held.append(
                {"race_id": identity, "role": "target", "reason": str(exc), "whole_race": True}
            )
            continue
        observations.append(
            ObservationInput(
                freeze, card, available_history, coverage, sessions, tuple(pedigrees), markets
            )
        )
        if label is not None:
            labels.append(label)
    if not observations:
        raise ValueError("all explicitly requested reference races were held: " + str(held))
    return ReferenceNormalization(
        tuple(sorted(observations, key=lambda s: s.freeze_at)),
        parameters,
        tuple(held),
        tuple(labels),
    )
