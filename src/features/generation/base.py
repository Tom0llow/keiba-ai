"""Share feature-row generation and validated Arrow table construction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

import pyarrow as pa

from features.contracts.rows import FeatureTableRow
from features.contracts.types import FeatureDefinition
from features.tables.build import build_feature_table
from features.tables.schema import IntermediateFeatureTable


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
