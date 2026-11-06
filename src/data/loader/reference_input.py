"""Read a bounded fixed snapshot; all field interpretation stays outside data I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import cast

from data.loader.fixed_snapshot import FixedSnapshot


def read_reference_tables(
    snapshot: FixedSnapshot,
    *,
    races: Sequence[dict[str, object]],
    history_start: str,
    days_window: int,
    venues: Sequence[str],
    include_labels: bool,
    columns: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    """Load complete race/peer populations using explicit projection and predicates."""
    identities = [cast(str, r["race_id"]) for r in races]
    target_dates = [datetime.strptime(identity[:8], "%Y%m%d").date() for identity in identities]
    history_end = (max(target_dates) - timedelta(days=1)).strftime("%Y%m%d")
    first_workout = (min(target_dates) - timedelta(days=days_window + 1)).strftime("%Y%m%d")
    tables: dict[str, object] = {}
    for suffix, table in (("ra", "NL_RA_RACE"), ("se", "NL_SE_RACE_UMA")):
        tables[f"history_{suffix}"] = snapshot.read_period(
            table,
            columns=columns[f"history_{suffix}"],
            start=history_start.replace("-", ""),
            end=history_end,
            venues=venues,
        )
        tables[f"target_{suffix}"] = snapshot.read_races(
            table, identities, columns=columns[f"target_{suffix}"]
        )
        tables[f"label_{suffix}"] = (
            snapshot.read_races(table, identities, columns=columns[f"history_{suffix}"])
            if include_labels
            else []
        )
    tables["o1"] = snapshot.read_races(
        "ARCHIVE_O1_ODDS_TANFUKUWAKU", identities, columns=columns["o1"]
    )
    tables["o2"] = snapshot.read_races("ARCHIVE_O2_ODDS_UMAREN", identities, columns=columns["o2"])
    for kind, table in (("hc", "NL_HC_HANRO"), ("wc", "NL_WC_WOOD")):
        tables[kind] = snapshot.read_period(
            table,
            columns=columns[kind],
            date_column="ChokyoDate",
            start=first_workout,
            end=history_end,
        )
    horses = sorted(
        {
            cast(str, row["KettoNum"])
            for name in ("history_se", "target_se")
            for row in cast(list[dict[str, object]], tables[name])
            if isinstance(row.get("KettoNum"), str)
        }
    )
    tables["um"] = snapshot.read_identifiers(
        "NL_UM_UMA", columns=columns["um"], column="KettoNum", identities=horses
    )
    return tables
