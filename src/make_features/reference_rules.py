"""Version the explicit limits of snapshot-based reference experiments."""

from __future__ import annotations

from collections.abc import Mapping

REFERENCE_IMPLEMENTATION = "snapshot_reference_21_groups_v1"
REFERENCE_BASES: dict[str, object] = {
    "source_rule_id": "jv_data_4901_reference_v1",
    "schedule_basis": "assumed_stored_schedule",
    "reception_basis": "assumed_received_at_publication",
    "card_basis": "stored_pre_race_fields_revision_unverified",
    "pedigree_basis": "stored_parent_identifiers_revision_unverified",
    "workout_basis": "previous_day_sessions_assumed_available",
    "parameter_basis": "retrospective_fixed_configuration",
    "coverage_scope": "complete_within_fixed_snapshot_selected_normal_population",
    "exception_policy": "hold_whole_race_with_reason",
    "class_policy": "unknown_class_preserve_null",
    "freeze_offset_seconds": 300,
    "minimum_supported_year": 2005,
    "venues": [f"{i:02d}" for i in range(1, 11)],
}


def validate_reference_rules(value: object) -> dict[str, object]:
    """Require every assumption by name and an explicit conservative label delay."""
    if not isinstance(value, Mapping) or set(value) != set(REFERENCE_BASES) | {"result_delay_days"}:
        raise ValueError("reference rules require the complete versioned explicit policy")
    if any(type(value[k]) is not type(v) or value[k] != v for k, v in REFERENCE_BASES.items()):
        raise ValueError("unsupported reference source interpretation or assumption")
    days = value["result_delay_days"]
    if type(days) is not int or days < 7:
        raise ValueError("reference result_delay_days must explicitly be at least 7")
    return dict(value)
