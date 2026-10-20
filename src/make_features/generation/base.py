"""Share feature-row generation and validated Arrow table construction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

import pyarrow as pa

from make_features.contracts.rows import FeatureTableRow
from make_features.contracts.types import (
    FeatureAudit,
    FeatureBatchInput,
    FeatureBuildError,
    FeatureDefinition,
    FeatureValuesInput,
)
from make_features.generation.normalization import input_batches, require_feature_input_type
from make_features.tables.build import build_feature_table
from make_features.tables.schema import IntermediateFeatureTable
from make_features.validation.audit import audit_feature_inputs


class FeatureBuilder[InputT](ABC):
    """Build one feature table while leaving calculation to its owning module."""

    feature_name: str
    definition: FeatureDefinition | None

    def __init__(self, definition: FeatureDefinition | None = None) -> None:
        if definition is not None and definition.name != self.feature_name:
            raise ValueError("definition name must match the builder implementation")
        self.definition = definition

    def build(
        self,
        records: Sequence[InputT],
        *,
        column_types: Mapping[str, pa.DataType] | None = None,
    ) -> IntermediateFeatureTable:
        """Generate rows and construct a table with explicit value-column types."""
        return build_feature_table(
            self.feature_name,
            self.build_rows(records),
            column_types=column_types,
            registered_names=() if self.definition is None else (self.definition.name,),
        )

    def build_rows(self, records: Sequence[InputT]) -> list[FeatureTableRow]:
        """Return feature-owned normalized rows without writing any artifacts."""
        return self._build_rows(records)

    @abstractmethod
    def _build_rows(self, records: Sequence[InputT]) -> list[FeatureTableRow]:
        """Normalize feature-specific inputs and calculate their value rows."""


class RegisteredFeatureBuilder(FeatureBuilder[FeatureValuesInput]):
    """Audit configured feature inputs before delegating their row normalization."""

    definition: FeatureDefinition
    input_type: type[FeatureValuesInput]

    def __init__(self, definition: FeatureDefinition) -> None:
        super().__init__(definition)
        self.definition = definition

    def audit_batches(
        self, records: Sequence[FeatureBatchInput], audit: FeatureAudit
    ) -> FeatureAudit:
        """Append feature-owned checks to the shared batch audit."""
        return audit

    def _build_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        require_feature_input_type(records, self.input_type)
        batches = input_batches(records, self.definition.feature_id)
        audit = audit_feature_inputs(batches, required_feature_ids=(self.definition.feature_id,))
        if not audit.valid:
            raise FeatureBuildError(audit)
        audit = self.audit_batches(batches, audit)
        if not audit.valid:
            raise FeatureBuildError(audit)
        return self._build_audited_rows(records)

    def _build_audited_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        require_feature_input_type(records, self.input_type)
        return self._normalize_rows(records)

    @abstractmethod
    def _normalize_rows(self, records: Sequence[FeatureValuesInput]) -> list[FeatureTableRow]:
        """Normalize inputs whose shared and feature-owned audits have succeeded."""
