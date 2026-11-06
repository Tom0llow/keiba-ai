"""Own the approved model feature schema and semantic metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from models.dataset.calculated import CalculationContract
from models.dataset.rows import FeatureValueType, MissingValuePolicy


@dataclass(frozen=True)
class FeatureSpec:
    """Describe one numeric feature at the model boundary."""

    name: str
    generation_rule: str
    result_derived: bool
    value_type: FeatureValueType = "numeric"
    unit: str | None = None
    missing_value_policy: MissingValuePolicy = "preserve_native_missing"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("feature spec names must be non-empty strings")
        if not isinstance(self.generation_rule, str) or not self.generation_rule:
            raise ValueError("feature spec generation_rule must be a non-empty string")
        if not isinstance(self.result_derived, bool):
            raise ValueError("feature spec result_derived must be a boolean")
        if self.result_derived:
            raise ValueError("result-derived features are not allowed in the model schema")
        if self.value_type != "numeric":
            raise ValueError("feature spec value_type must be 'numeric'")
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit):
            raise ValueError("feature spec unit must be a non-empty string or None")
        if self.missing_value_policy != "preserve_native_missing":
            raise ValueError("feature spec missing_value_policy must be 'preserve_native_missing'")


_RESERVED_RESULT_FEATURE_NAME_ALIASES = frozenset(
    {
        "confirmed_time",
        "earnings",
        "final_odds",
        "finish_position",
        "finish_time",
        "harontimel3",
        "arrival",
        "arrival_rank",
        "dead_heat",
        "history_result",
        "kakuteijyuni",
        "last_3f",
        "last3f",
        "last_odds",
        "margin",
        "ninki",
        "odds_final",
        "passing_position",
        "payout",
        "payout_amount",
        "payouts",
        "popularity",
        "prize",
        "prize_money",
        "placing",
        "position",
        "refund",
        "refund_amount",
        "rank",
        "result",
        "result_rank",
        "race_result",
        "time",
        "timediff",
    }
)


_RESERVED_RESULT_FEATURE_NAME_TOKENS = frozenset(
    {
        "arrival",
        "earnings",
        "finish",
        "last3f",
        "margin",
        "passing",
        "payout",
        "placing",
        "popularity",
        "position",
        "prize",
        "rank",
        "result",
        "speed",
        "time",
        "outcome",
        "winner",
    }
)


_APPROVED_FEATURE_SPECS: Mapping[str, FeatureSpec] = MappingProxyType(
    {
        "ability": FeatureSpec(
            name="ability",
            generation_rule="pre_race_ability_v1",
            result_derived=False,
            unit="score",
        ),
        "historical_odds": FeatureSpec(
            name="historical_odds",
            generation_rule="historical_odds_v1",
            result_derived=False,
            unit="decimal",
        ),
    }
)


@dataclass(frozen=True)
class FeatureSchema:
    """Describe the ordered feature contract used by training and prediction."""

    schema_id: str
    features: tuple[FeatureSpec, ...]
    calculation_contract: CalculationContract | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_id, str) or not self.schema_id:
            raise ValueError("feature schema schema_id must be a non-empty string")
        if not self.features:
            raise ValueError("feature schema must contain at least one feature")
        names = tuple(feature.name for feature in self.features)
        validate_feature_names(names, calculation_contract=self.calculation_contract)
        if self.calculation_contract is not None:
            if self.schema_id != f"calculated-{self.calculation_contract.sha256}":
                raise ValueError("calculated schema_id does not match calculation contract")
            expected = _calculated_specs(self.calculation_contract)
            if self.features != expected:
                raise ValueError("calculated feature specifications do not match their contract")
            return
        for feature in self.features:
            if _APPROVED_FEATURE_SPECS.get(feature.name) != feature:
                raise ValueError(
                    f"feature {feature.name!r} does not match the approved feature specification"
                )

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Return the ordered names represented by this schema."""
        return tuple(feature.name for feature in self.features)

    @classmethod
    def from_names(
        cls,
        feature_names: Sequence[str],
        *,
        schema_id: str,
        generation_rule: str | None = None,
    ) -> FeatureSchema:
        """Create a schema from the approved feature allow-list."""
        names = tuple(feature_names)
        validate_feature_names(names)
        specs = tuple(_APPROVED_FEATURE_SPECS[name] for name in names)
        if generation_rule is not None and any(
            spec.generation_rule != generation_rule for spec in specs
        ):
            raise ValueError("generation_rule does not match the approved feature specification")
        return cls(
            schema_id=schema_id,
            features=specs,
        )

    def as_metadata(self) -> dict[str, object]:
        """Return a JSON-compatible schema description."""
        metadata: dict[str, object] = {
            "schema_id": self.schema_id,
            "features": [
                {
                    "generation_rule": feature.generation_rule,
                    "missing_value_policy": feature.missing_value_policy,
                    "name": feature.name,
                    "result_derived": feature.result_derived,
                    "unit": feature.unit,
                    "value_type": feature.value_type,
                }
                for feature in self.features
            ],
        }
        if self.calculation_contract is not None:
            metadata["calculation_contract"] = self.calculation_contract.as_metadata()
        return metadata

    @classmethod
    def calculated(cls, contract: CalculationContract) -> FeatureSchema:
        """Create only code-approved numeric specifications for a verified contract."""
        return cls(f"calculated-{contract.sha256}", _calculated_specs(contract), contract)

    @classmethod
    def from_metadata(cls, value: object) -> FeatureSchema:
        """Read semantic metadata and revalidate every specification."""
        if not isinstance(value, dict):
            raise ValueError("feature_schema must be an object")
        data = cast(dict[str, object], value)
        raw_features = data.get("features")
        if not isinstance(raw_features, list):
            raise ValueError("feature_schema requires features")
        specs = []
        for raw in raw_features:
            if not isinstance(raw, dict):
                raise ValueError("feature specifications must be objects")
            feature = cast(dict[str, object], raw)
            if set(feature) != {
                "name",
                "generation_rule",
                "result_derived",
                "value_type",
                "unit",
                "missing_value_policy",
            }:
                raise ValueError("invalid feature specification fields")
            specs.append(
                FeatureSpec(
                    name=cast(str, feature["name"]),
                    generation_rule=cast(str, feature["generation_rule"]),
                    result_derived=cast(bool, feature["result_derived"]),
                    value_type=cast(FeatureValueType, feature["value_type"]),
                    unit=cast(str | None, feature["unit"]),
                    missing_value_policy=cast(MissingValuePolicy, feature["missing_value_policy"]),
                )
            )
        contract = (
            CalculationContract.from_metadata(data["calculation_contract"])
            if "calculation_contract" in data
            else None
        )
        return cls(cast(str, data.get("schema_id")), tuple(specs), contract)


def _calculated_specs(contract: CalculationContract) -> tuple[FeatureSpec, ...]:
    return tuple(
        FeatureSpec(
            column.name,
            f"{contract.settings['implementation']}:{contract.sha256}:{column.meaning}",
            False,
            unit=column.unit,
        )
        for column in contract.columns()
    )


def validate_feature_names(
    feature_names: Sequence[str], *, calculation_contract: CalculationContract | None = None
) -> None:
    """Validate ordered model feature names against the approved numeric allow-list."""
    if not feature_names:
        raise ValueError("at least one feature is required")
    if any(not isinstance(name, str) or not name for name in feature_names):
        raise ValueError("feature names must be non-empty strings")
    if len(set(feature_names)) != len(feature_names):
        raise ValueError("feature names must be unique")
    if calculation_contract is not None:
        if tuple(feature_names) != calculation_contract.names:
            raise ValueError("calculated feature names do not match their verified contract")
        calculation_contract.columns()
        return
    reserved = sorted(name for name in feature_names if _is_reserved_result_feature_name(name))
    if reserved:
        raise ValueError(f"result-derived feature names are reserved: {reserved!r}")
    unapproved = sorted(name for name in feature_names if name not in _APPROVED_FEATURE_SPECS)
    if unapproved:
        raise ValueError(f"feature names are outside the approved allow-list: {unapproved!r}")


def _is_reserved_result_feature_name(name: str) -> bool:
    normalized = "".join(character for character in name.casefold() if character.isalnum())
    if normalized == "odds":
        return True
    reserved = {
        "".join(character for character in alias.casefold() if character.isalnum())
        for alias in _RESERVED_RESULT_FEATURE_NAME_ALIASES
    }
    return (
        normalized in reserved
        or normalized.startswith("pay")
        or any(
            normalized == token or normalized.startswith(token) or normalized.endswith(token)
            for token in _RESERVED_RESULT_FEATURE_NAME_TOKENS
        )
    )
