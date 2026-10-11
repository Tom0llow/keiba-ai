"""Shared type for one design-level candidate feature specification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CandidateGroupSpec:
    """Describe one design-level candidate feature group."""

    group_id: str
    label: str


__all__ = ["CandidateGroupSpec"]
