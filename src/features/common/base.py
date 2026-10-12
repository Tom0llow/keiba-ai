"""Share feature-row generation and validated Arrow table construction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

import pyarrow as pa

from features.common.feature_table import (
    FeatureTableRow,
    IntermediateFeatureTable,
    build_feature_table,
)


class FeatureBuilder[InputT](ABC):
    """Build one feature table while leaving calculation to its owning module."""

    feature_name: str

    def build(
        self,
        records: Sequence[InputT],
        *,
        column_types: Mapping[str, pa.DataType] | None = None,
    ) -> IntermediateFeatureTable:
        """Generate rows and construct a table with explicit value-column types."""
        return build_feature_table(
            self.feature_name, self.build_rows(records), column_types=column_types
        )

    def build_rows(self, records: Sequence[InputT]) -> list[FeatureTableRow]:
        """Return feature-owned normalized rows without writing any artifacts."""
        return self._build_rows(records)

    @abstractmethod
    def _build_rows(self, records: Sequence[InputT]) -> list[FeatureTableRow]:
        """Normalize feature-specific inputs and calculate their value rows."""
