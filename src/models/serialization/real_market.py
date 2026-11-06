"""Project pinned published quotes and separately validate minimal result evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import cast

from make_features.real_market import (
    JST,
    KEY_COLUMNS,
    MARKET_COLUMN,
    O1_TABLE,
    RA_TABLE,
    RECEPTION_BASIS,
    SE_TABLE,
    canonical_hash,
    latest_o1,
    publication,
    race_key,
    schedule,
    timestamp,
    validate_market_settings,
    validate_races,
    win_quotes,
)
from models.dataset.calculated import CalculationContract
from models.dataset.rows import FeatureInput
from models.dataset.schema import FeatureSchema


@dataclass(frozen=True)
class SnapshotResultLabel:
    """A declared label-use boundary, distinct from actual provider/reception clocks."""

    race_id: str
    usable_after: datetime
    assurance: str
    payload: dict[str, object]


def market_assurance(settings: Mapping[str, object]) -> dict[str, object]:
    """Make the reception and schedule assumptions visible in every downstream artifact."""
    return {
        "implementation": "published_win_market_v1",
        "reception_basis": RECEPTION_BASIS,
        "received_at": None,
        "schedule_basis": settings["schedule_basis"],
        "historical_reception_verified": False,
    }


def prepare_real_market_payload(
    *,
    settings: Mapping[str, object],
    races: Sequence[dict[str, object]],
    odds_rows: Sequence[dict[str, object]],
    snapshot: Mapping[str, object],
    schedule_rows: Sequence[dict[str, object]] = (),
    result_rows: Sequence[dict[str, object]] | None = None,
    result_races: Sequence[dict[str, object]] = (),
    label_settings: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build one approved numeric column, with no feature dependency on final SE results."""
    parameters = validate_market_settings(dict(settings))
    manifest = validate_races(list(races))
    contract = CalculationContract.published_market(parameters)
    schema = FeatureSchema.calculated(contract)
    calculation_races: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    for race in manifest:
        race_id = cast(str, race["race_id"])
        stored = (
            _unique_race_row(schedule_rows, race_id)
            if parameters["schedule_basis"] == "assumed_stored_schedule"
            else None
        )
        _, freeze = schedule(race, parameters, stored)
        selected = latest_o1(odds_rows, race)
        published = publication(selected)
        quotes = win_quotes(selected)
        calculation_races.append(
            {
                "manifest": dict(race),
                "selected_o1": selected,
                "selected_o1_sha256": canonical_hash(selected),
                "schedule_row": stored,
                "schedule_row_sha256": canonical_hash(stored) if stored is not None else None,
                "published_at": published.isoformat(),
                "received_at": None,
                "reception_basis": RECEPTION_BASIS,
                "horse_mapping": [
                    {"horse_id": horse, "umaban": horse, "missing_reason": reason}
                    for horse, _, reason in quotes
                ],
            }
        )
        for horse, value, _ in quotes:
            records.append(
                {
                    "race_id": race_id,
                    "horse_id": horse,
                    "freeze_at": freeze.isoformat(),
                    "features": {MARKET_COLUMN: value},
                    "available_at": {MARKET_COLUMN: published.isoformat()},
                }
            )
    records.sort(key=lambda r: (timestamp(r["freeze_at"]), str(r["race_id"]), str(r["horse_id"])))
    evidence: dict[str, object] = {
        "format_version": 1,
        "parameters": parameters,
        "snapshot": dict(snapshot),
        "snapshot_sha256": canonical_hash(snapshot),
        "races": calculation_races,
    }
    _validate_snapshot(
        snapshot,
        needs_ra=bool(schedule_rows) or result_rows is not None,
        needs_se=result_rows is not None,
    )
    payload: dict[str, object] = {
        "schema_id": schema.schema_id,
        "feature_names": list(schema.feature_names),
        "feature_schema": schema.as_metadata(),
        "records": records,
        "calculation": evidence,
        "assurance": market_assurance(parameters),
    }
    if result_rows is not None:
        if label_settings is None:
            raise ValueError("results require explicit label settings")
        sources = []
        for race in manifest:
            race_id = cast(str, race["race_id"])
            source: dict[str, object] = {
                "kind": "snapshot_result_v1",
                "race_id": race_id,
                "settings": dict(label_settings),
                "manifest": dict(race),
                "raw_ra": _unique_race_row(result_races, race_id),
                "raw_se": [dict(row) for row in result_rows if _row_matches(row, race_id)],
                "received_at": None,
                "result_published_at": None,
                "snapshot_sha256": canonical_hash(snapshot),
            }
            source["raw_sha256"] = canonical_hash({"ra": source["raw_ra"], "se": source["raw_se"]})
            source_records = [r for r in records if r["race_id"] == race_id]
            label = _parse_result(source, source_records, attach=True)
            source["usable_after"] = label.usable_after.isoformat()
            source["assurance"] = label.assurance
            sources.append(source)
        payload["label_sources"] = sources
    elif label_settings is not None:
        raise ValueError("label settings cannot be used without result rows")
    return payload


def validate_real_market_payload(
    payload: Mapping[str, object], schema: FeatureSchema, rows: Sequence[FeatureInput]
) -> None:
    """Recompute model values, missing reasons, mapping and boundaries from original rows."""
    evidence = payload.get("calculation")
    if (
        not isinstance(evidence, dict)
        or set(evidence) != {"format_version", "parameters", "snapshot", "snapshot_sha256", "races"}
        or type(evidence["format_version"]) is not int
        or evidence["format_version"] != 1
    ):
        raise ValueError("published market requires complete calculation evidence")
    parameters = validate_market_settings(evidence["parameters"])
    if CalculationContract.published_market(parameters) != schema.calculation_contract:
        raise ValueError("published market settings differ from feature schema")
    if payload.get("assurance") != market_assurance(parameters):
        raise ValueError("published market assurance differs from explicit assumptions")
    snapshot = evidence["snapshot"]
    if not isinstance(snapshot, dict) or evidence["snapshot_sha256"] != canonical_hash(snapshot):
        raise ValueError("snapshot manifest hash mismatch")
    _validate_snapshot(
        snapshot,
        needs_ra=parameters["schedule_basis"] == "assumed_stored_schedule"
        or "label_sources" in payload,
        needs_se="label_sources" in payload,
    )
    races = evidence["races"]
    if not isinstance(races, list) or not races or any(not isinstance(r, dict) for r in races):
        raise ValueError("published market requires race evidence")
    manifests: list[dict[str, object]] = []
    odds: list[dict[str, object]] = []
    schedules: list[dict[str, object]] = []
    for entry in races:
        if not isinstance(entry.get("manifest"), dict) or not isinstance(
            entry.get("selected_o1"), dict
        ):
            raise ValueError("published market requires original source rows")
        selected = entry["selected_o1"]
        stored = entry.get("schedule_row")
        if entry.get("selected_o1_sha256") != canonical_hash(selected) or entry.get(
            "schedule_row_sha256"
        ) != (canonical_hash(stored) if stored is not None else None):
            raise ValueError("selected original source row hash mismatch")
        manifests.append(entry["manifest"])
        odds.append(selected)
        if isinstance(stored, dict):
            schedules.append(stored)
    recomputed = prepare_real_market_payload(
        settings=parameters,
        races=manifests,
        odds_rows=odds,
        snapshot=snapshot,
        schedule_rows=schedules,
    )
    if recomputed["calculation"] != evidence:
        raise ValueError("published market calculation evidence differs from recomputation")
    expected = cast(list[dict[str, object]], recomputed["records"])
    actual = [
        {
            "race_id": row.race_id,
            "horse_id": row.horse_id,
            "freeze_at": timestamp(row.freeze_at).isoformat(),
            "features": dict(row.features),
            "available_at": {k: timestamp(v).isoformat() for k, v in row.available_at.items()},
        }
        for row in rows
    ]
    if actual != expected:
        raise ValueError("published market values or availability differ from original O1")
    if any(row.finish_position is not None for row in rows) or "label_sources" in payload:
        parse_snapshot_labels(payload, required=True)


def parse_snapshot_labels(
    payload: Mapping[str, object], *, required: bool
) -> tuple[SnapshotResultLabel, ...]:
    """Verify every label against a complete, normal, separately evidenced SE result."""
    sources = payload.get("label_sources")
    if sources is None and not required:
        return ()
    if (
        not isinstance(sources, list)
        or not sources
        or any(not isinstance(v, dict) for v in sources)
    ):
        raise ValueError("published market training requires complete label_sources")
    records = payload.get("records")
    if not isinstance(records, list) or any(not isinstance(v, dict) for v in records):
        raise ValueError("result evidence requires model records")
    evidence = payload.get("calculation")
    if not isinstance(evidence, dict):
        raise ValueError("result evidence requires snapshot calculation")
    by_race: dict[str, list[dict[str, object]]] = {}
    for record in records:
        by_race.setdefault(cast(str, record.get("race_id")), []).append(record)
    labels = []
    seen: set[str] = set()
    calculation_races = evidence.get("races")
    if not isinstance(calculation_races, list):
        raise ValueError("label sources require calculation race manifests")
    manifests = {
        entry["manifest"]["race_id"]: entry["manifest"]
        for entry in calculation_races
        if isinstance(entry, dict) and isinstance(entry.get("manifest"), dict)
    }
    for source in sources:
        race_id = source.get("race_id")
        if (
            not isinstance(race_id, str)
            or race_id in seen
            or race_id not in by_race
            or source.get("snapshot_sha256") != evidence.get("snapshot_sha256")
            or source.get("manifest") != manifests.get(race_id)
        ):
            raise ValueError("label race identities or snapshot differ")
        seen.add(race_id)
        label = _parse_result(source, by_race[race_id], attach=False)
        if (
            source.get("usable_after") != label.usable_after.isoformat()
            or source.get("assurance") != label.assurance
        ):
            raise ValueError("label use boundary or assurance differs from result evidence")
        labels.append(label)
    if seen != set(by_race):
        raise ValueError("complete labels required for every explicit race")
    return tuple(labels)


def _parse_result(
    source: dict[str, object], records: Sequence[dict[str, object]], *, attach: bool
) -> SnapshotResultLabel:
    race_id = cast(str, source.get("race_id"))
    fields = {
        "kind",
        "race_id",
        "settings",
        "manifest",
        "raw_ra",
        "raw_se",
        "received_at",
        "result_published_at",
        "snapshot_sha256",
        "raw_sha256",
    }
    if not attach:
        fields |= {"usable_after", "assurance"}
    if set(source) != fields:
        raise ValueError("result evidence fields differ from its versioned contract")
    race_key(race_id)
    race, ra, se, settings = (
        source.get("manifest"),
        source.get("raw_ra"),
        source.get("raw_se"),
        source.get("settings"),
    )
    if (
        source.get("kind") != "snapshot_result_v1"
        or source.get("received_at") is not None
        or source.get("result_published_at") is not None
        or not isinstance(race, dict)
        or race.get("race_id") != race_id
        or not isinstance(ra, dict)
        or not isinstance(se, list)
        or not se
        or any(not isinstance(r, dict) for r in se)
        or not isinstance(settings, dict)
        or set(settings) != {"basis", "result_delay_days"}
    ):
        raise ValueError(f"{race_id}: invalid minimal result evidence")
    if source.get("raw_sha256") != canonical_hash({"ra": ra, "se": se}):
        raise ValueError(f"{race_id}: original result row hash mismatch")
    start = timestamp(race.get("scheduled_start_at"))
    if any(timestamp(r["freeze_at"]) != timestamp(race.get("freeze_at")) for r in records):
        raise ValueError(f"{race_id}: result and feature freeze boundaries differ")
    if not _row_matches(ra, race_id) or ra.get("headDataKubun") != "7":
        raise ValueError(f"{race_id}: RA result must be normal finalized phase 7")
    runners: dict[str, int] = {}
    for row in se:
        horse = row.get("Umaban")
        finish = row.get("KakuteiJyuni")
        if (
            not _row_matches(row, race_id)
            or row.get("headDataKubun") != "7"
            or row.get("IJyoCD") != "0"
            or row.get("DochakuKubun") != "0"
            or not isinstance(horse, str)
            or re.fullmatch(r"[0-9]{2}", horse) is None
            or horse in runners
            or not isinstance(finish, str)
            or re.fullmatch(r"[0-9]{2}", finish) is None
        ):
            raise ValueError(
                f"{race_id}: SE results must be unique, normal finalized runners without ties"
            )
        runners[horse] = int(finish)
    if (
        set(runners) != {r["horse_id"] for r in records}
        or sorted(runners.values()) != list(range(1, len(runners) + 1))
        or any(ra.get(field) != f"{len(runners):02d}" for field in ("SyussoTosu", "NyusenTosu"))
    ):
        raise ValueError(
            f"{race_id}: complete contiguous results must match the intermediate O1 horse set"
        )
    if settings["basis"] == "provided_result_evidence":
        if (
            settings["result_delay_days"] is not None
            or not isinstance(race.get("result_source"), str)
            or not race["result_source"]
        ):
            raise ValueError(f"{race_id}: strict results require explicit known_at/source")
        usable = timestamp(race.get("result_known_at"))
        assurance = "provided_result_clock_snapshot_revision_unverified"
    elif settings["basis"] == "assumed_snapshot_results":
        days = settings["result_delay_days"]
        if type(days) is not int or days < 1 or race.get("result_known_at") is not None:
            raise ValueError(
                f"{race_id}: assumed results require explicit positive result_delay_days and null known_at"
            )
        declared_date = start.astimezone(JST).date() + timedelta(days=days)
        usable = datetime.combine(declared_date + timedelta(days=1), time.min, JST)
        assurance = "assumed_snapshot_results_revision_time_unverified"
    else:
        raise ValueError("unsupported explicit label basis")
    if usable <= start:
        raise ValueError(f"{race_id}: result use boundary must follow scheduled start")
    for row in (ra, *se):
        value = row.get("headMakeDate")
        if not isinstance(value, str) or re.fullmatch(r"[0-9]{8}", value) is None:
            raise ValueError(f"{race_id}: result headMakeDate is required")
        made = datetime.strptime(value, "%Y%m%d").date()
        if (
            made < start.astimezone(JST).date()
            or made > usable.astimezone(JST).date()
            or (
                settings["basis"] == "assumed_snapshot_results"
                and made >= usable.astimezone(JST).date()
            )
        ):
            raise ValueError(f"{race_id}: result created after the declared label-use date")
    for record in records:
        finish = runners[cast(str, record["horse_id"])]
        if attach:
            record["finish_position"] = finish
        elif type(record.get("finish_position")) is not int or record["finish_position"] != finish:
            raise ValueError(f"{race_id}: model labels differ from original SE results")
    return SnapshotResultLabel(race_id, usable, assurance, source)


def _row_matches(row: Mapping[str, object], race_id: str) -> bool:
    return tuple(row.get(key) for key in KEY_COLUMNS) == race_key(race_id)


def _unique_race_row(rows: Sequence[dict[str, object]], race_id: str) -> dict[str, object]:
    values = {canonical_hash(row): row for row in rows if _row_matches(row, race_id)}
    if len(values) != 1:
        raise ValueError(f"{race_id}: expected one unambiguous RA row")
    return next(iter(values.values()))


def _validate_snapshot(value: Mapping[str, object], *, needs_ra: bool, needs_se: bool) -> None:
    tables = value.get("tables")
    required = (
        {O1_TABLE} | ({RA_TABLE} if needs_ra else set()) | ({SE_TABLE} if needs_se else set())
    )
    if (
        set(value) != {"snapshot_id", "snapshot_path", "tables"}
        or not isinstance(value.get("snapshot_id"), str)
        or not value["snapshot_id"]
        or not isinstance(value.get("snapshot_path"), str)
        or not isinstance(tables, dict)
        or not required <= set(tables) <= {O1_TABLE, RA_TABLE, SE_TABLE}
    ):
        raise ValueError("snapshot manifest tables differ from the required sources")
    for table, metadata in tables.items():
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"file", "sha256"}
            or metadata["file"] != f"{table}.parquet"
            or not isinstance(metadata["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]) is None
        ):
            raise ValueError("snapshot table file identity requires SHA-256")
