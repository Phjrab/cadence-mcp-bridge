"""Operator-owned targets and condition-bound evaluation of registered measurements."""

import json
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.analog_measurements import AnalogResult, definition
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

Comparison = Literal[">=", "<=", ">", "<", "range"]
EvaluationStatus = Literal[
    "PASS", "FAIL", "NOT_EVALUATED", "UNQUALIFIED", "MISSING_MEASUREMENT", "CONDITION_MISMATCH"
]


class SpecificationConditions(VariableModel):
    analysis_id: LogicalId
    analysis_plan_hash: Digest
    revision_id: LogicalId
    operating_point_id: LogicalId
    corner: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9-]{0,63}$", max_length=64)]
    temperature_c: NumberText
    vdd_v: NumberText
    applied_bias_values_v: tuple[NumberText, NumberText]
    # Includes load, VCM, stimulus and every effective setting, not just the fields above.
    effective_settings_sha256: Digest

    @field_validator("temperature_c", "vdd_v", mode="before")
    @classmethod
    def decimal_fields(cls, value: Any) -> str:
        return number_text(value)

    @field_validator("applied_bias_values_v")
    @classmethod
    def decimal_biases(cls, value: tuple[str, str]) -> tuple[str, str]:
        return number_text(value[0]), number_text(value[1])


class SpecificationContract(VariableModel):
    contract_version: Literal[1] = 1
    spec_id: LogicalId
    design_id: LogicalId
    measurement_id: LogicalId
    measurement_contract_sha256: Digest
    definition_sha256: Digest
    comparison: Comparison
    target: NumberText | None
    upper_target: NumberText | None = None
    unit: Literal["dB", "Hz", "deg", "W", "V", "V/s"]
    # Operator's opaque reference to a user goal; never synthesized from a measurement.
    goal_id: LogicalId | None
    conditions: SpecificationConditions

    @field_validator("contract_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer specification version required")
        return value

    @field_validator("target", "upper_target", mode="before")
    @classmethod
    def decimal_targets(cls, value: Any) -> str | None:
        return None if value is None else number_text(value)

    @model_validator(mode="after")
    def target_shape(self) -> Self:
        if self.target is None:
            if self.goal_id is not None or self.upper_target is not None:
                raise ValueError("unselected target has no goal or upper bound")
        elif self.goal_id is None:
            raise ValueError("target requires an operator-recorded user goal")
        elif self.comparison == "range":
            if self.upper_target is None or Decimal(self.target) > Decimal(self.upper_target):
                raise ValueError("inclusive range requires ordered bounds")
        elif self.upper_target is not None:
            raise ValueError("only range accepts an upper bound")
        return self


class SpecificationSelection(VariableModel):
    design_id: LogicalId
    spec_id: LogicalId


class SpecificationQuery(SpecificationSelection):
    expected_contract_sha256: Digest
    operation_id: OperationId | None = None


class SpecificationDescription(ContractModel):
    contract: SpecificationContract
    contract_sha256: Digest
    target_status: Literal["registered", "not_selected"]
    execution_authorized: Literal[False] = False

    @field_validator("contract", mode="before")
    @classmethod
    def json_contract(cls, value: Any) -> SpecificationContract:
        # SDK structured output is Python JSON (arrays), while operator inputs are
        # strict JSON contracts. Revalidate through JSON without relaxing input types.
        if isinstance(value, SpecificationContract):
            return value
        return SpecificationContract.model_validate_json(json.dumps(value))


class SpecificationList(ContractModel):
    design_id: LogicalId
    specifications: Annotated[tuple[SpecificationDescription, ...], Field(max_length=32)]
    target_status: Literal["registered", "not_selected"]
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class SpecificationEvaluation(ContractModel):
    contract_version: Literal[1] = 1
    specification: SpecificationDescription
    operation_id: OperationId | None
    status: EvaluationStatus
    reason: Literal[
        "target_not_selected",
        "measurement_not_selected",
        "measurement_unqualified",
        "measurement_conditions_differ",
        "target_met",
        "target_not_met",
    ]
    measurement: AnalogResult | None = None
    measurement_result_sha256: Digest | None = None
    scope: Literal["one_operation_exact_registered_conditions"] = (
        "one_operation_exact_registered_conditions"
    )
    execution_authorized: Literal[False] = False


def evaluate(c: SpecificationContract, measurement: AnalogResult) -> EvaluationStatus:
    """Pure comparison after exact source binding. No tolerance, conversion or optimization."""
    if (
        measurement.design_id != c.design_id
        or measurement.measurement_id != c.measurement_id
        or measurement.contract_sha256 != c.measurement_contract_sha256
        or canonical_digest(measurement.definition) != c.definition_sha256
        or measurement.definition != definition(measurement.definition.metric)
        or measurement.definition.unit != c.unit
    ):
        raise ValueError("specification source identity differs")
    if c.target is None:
        return "NOT_EVALUATED"
    if measurement.status != "QUALIFIED" or measurement.value is None:
        return "UNQUALIFIED"
    p = measurement.provenance
    if p is None:
        return "UNQUALIFIED"
    s, expected = p.settings, c.conditions
    if (
        p.analysis_plan_hash != expected.analysis_plan_hash
        or p.revision_id != expected.revision_id
        or p.operating_point_id != expected.operating_point_id
        or s.corner != expected.corner
        or Decimal(str(s.temperature_c)) != Decimal(expected.temperature_c)
        or Decimal(str(s.vdd_v)) != Decimal(expected.vdd_v)
        or tuple(Decimal(str(v)) for v in s.applied_bias_values_v)
        != tuple(Decimal(v) for v in expected.applied_bias_values_v)
        or canonical_digest(s) != expected.effective_settings_sha256
    ):
        return "CONDITION_MISMATCH"
    # Keep the source float's shortest round-trip decimal; do not round to display precision.
    value, target = Decimal(str(measurement.value)), Decimal(c.target)
    if c.comparison == "range":
        assert c.upper_target is not None
        matched = target <= value <= Decimal(c.upper_target)
    elif c.comparison == ">=":
        matched = value >= target
    elif c.comparison == "<=":
        matched = value <= target
    elif c.comparison == ">":
        matched = value > target
    else:
        matched = value < target
    return "PASS" if matched else "FAIL"
