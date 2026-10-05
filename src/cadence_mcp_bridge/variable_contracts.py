"""Local numeric contracts. Reviewed bounds never authorize Cadence execution."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cadence_mcp_bridge.models import ContractModel

LogicalId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$", max_length=64)]
BindingName = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$", max_length=64)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Unit = Literal["V", "A", "ohm", "F", "s", "Hz", "K", "degC", "1"]
NumberText = Annotated[str, Field(min_length=1, max_length=48)]
NumericDenial = Literal[
    "unqualified_range",
    "nonintegral_value",
    "fixed_value_mismatch",
    "outside_reviewed_range",
    "off_grid",
]
CheckReason = Literal[
    "numeric_contract_matched",
    "fixed_constraint_matched",
    "unregistered_variable",
    "wrong_unit",
    "read_only_variable",
    "unqualified_range",
    "nonintegral_value",
    "fixed_value_mismatch",
    "outside_reviewed_range",
    "off_grid",
    "copy_policy_denied",
]


def number_text(value: str) -> str:
    if (
        type(value) is not str
        or len(value) > 48
        or re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is None
    ):
        raise ValueError("bounded decimal text required")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("invalid decimal") from None
    exponent = number.as_tuple().exponent
    if not number.is_finite() or not isinstance(exponent, int) or abs(exponent) > 40:
        raise ValueError("decimal exponent exceeds bound")
    if abs(number.adjusted()) > 30:
        raise ValueError("decimal magnitude exceeds bound")
    with localcontext() as context:
        context.prec = 128
        canonical = "0" if number == 0 else format(number.normalize(), "f")
    if len(canonical) > 48:
        raise ValueError("canonical decimal exceeds bound")
    return canonical


def canonical_digest(value: BaseModel) -> str:
    data = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class VariableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class VariableContract(VariableModel):
    logical_id: LogicalId
    cadence_binding: BindingName
    unit: Unit
    value_type: Literal["real", "integer"]
    default: NumberText | None
    mutation_policy: Literal["read_only", "fixed", "owned_copy_only"]
    range_status: Literal["unqualified", "qualified"]
    minimum: NumberText | None
    maximum: NumberText | None
    step_policy: Literal["unqualified", "continuous", "grid", "fixed"]
    step: NumberText | None
    fixed_value: NumberText | None
    review_id: LogicalId | None

    @field_validator("default", "minimum", "maximum", "step", "fixed_value", mode="before")
    @classmethod
    def decimal_fields(cls, value: Any) -> str | None:
        return None if value is None else number_text(value)

    @model_validator(mode="after")
    def coherent_numeric_policy(self) -> Self:
        numbers = (self.default, self.minimum, self.maximum, self.step, self.fixed_value)
        if self.value_type == "integer" and any(
            value is not None and Decimal(value) != Decimal(value).to_integral_value()
            for value in numbers
        ):
            raise ValueError("integer contract requires integral numbers")
        if self.mutation_policy == "fixed":
            if (
                self.fixed_value is None
                or self.default != self.fixed_value
                or self.range_status != "unqualified"
                or self.step_policy != "fixed"
            ):
                raise ValueError("fixed constraint is distinct from electrical range qualification")
        elif self.fixed_value is not None or self.step_policy == "fixed":
            raise ValueError("fixed value requires fixed policy")
        if self.range_status == "unqualified":
            if any(
                value is not None
                for value in (self.minimum, self.maximum, self.step, self.review_id)
            ):
                raise ValueError("unqualified bounds cannot become defaults or reviewed limits")
            if self.mutation_policy != "fixed" and (
                self.default is not None or self.step_policy != "unqualified"
            ):
                raise ValueError("unqualified variable has no default or step")
        else:
            if self.minimum is None or self.maximum is None or self.review_id is None:
                raise ValueError("qualified range requires bounds and a separate review record")
            lower, upper = Decimal(self.minimum), Decimal(self.maximum)
            if lower >= upper or self.step_policy not in ("continuous", "grid"):
                raise ValueError("invalid reviewed range or step policy")
            if self.step_policy == "continuous" and self.step is not None:
                raise ValueError("continuous policy has no grid step")
            if self.step_policy == "grid" and (self.step is None or Decimal(self.step) <= 0):
                raise ValueError("positive grid step required")
            if self.default is not None and self.check_number(self.default) is not None:
                raise ValueError("default outside reviewed numeric contract")
        return self

    def check_number(self, value: str) -> NumericDenial | None:
        number = Decimal(value)
        if self.value_type == "integer" and number != number.to_integral_value():
            return "nonintegral_value"
        if self.mutation_policy == "fixed":
            return None if value == self.fixed_value else "fixed_value_mismatch"
        if self.range_status != "qualified" or self.minimum is None or self.maximum is None:
            return "unqualified_range"
        lower, upper = Decimal(self.minimum), Decimal(self.maximum)
        if not lower <= number <= upper:
            return "outside_reviewed_range"
        if self.step_policy == "grid" and self.step is not None:
            with localcontext() as context:
                context.prec = 128
                if (number - lower) % Decimal(self.step) != 0:
                    return "off_grid"
        return None


class DesignVariables(VariableModel):
    design_id: LogicalId
    design_profile_sha256: Digest
    variables: Annotated[tuple[VariableContract, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def no_aliases(self) -> Self:
        for ids in (
            [variable.logical_id for variable in self.variables],
            [variable.cadence_binding for variable in self.variables],
        ):
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate variable or binding alias")
        return self


class RangeReview(VariableModel):
    review_id: LogicalId
    design_id: LogicalId
    design_profile_sha256: Digest
    variable_contract_sha256: Digest
    evidence_id: LogicalId
    evidence_sha256: Digest
    scope: Literal["operator_reviewed_project_numeric_contract"]


class VariableDescription(ContractModel):
    logical_id: LogicalId
    unit: Unit
    value_type: Literal["real", "integer"]
    default: NumberText | None
    mutation_policy: Literal["read_only", "fixed", "owned_copy_only"]
    range_status: Literal["unqualified", "qualified"]
    minimum: NumberText | None
    maximum: NumberText | None
    step_policy: Literal["unqualified", "continuous", "grid", "fixed"]
    step: NumberText | None
    fixed_value: NumberText | None
    range_authority: Literal["none", "operator_review_record"]
    execution_authorized: Literal[False] = False


class VariableList(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    declared_variables: tuple[LogicalId, ...]
    variables: tuple[VariableDescription, ...]
    missing_contracts: tuple[LogicalId, ...]
    qualification_scope: Literal["local_numeric_contract_only"] = "local_numeric_contract_only"
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class VariableValue(VariableModel):
    value: NumberText
    unit: Unit

    @field_validator("value", mode="before")
    @classmethod
    def canonical_value(cls, value: Any) -> str:
        return number_text(value)


class VariableValuesRequest(VariableModel):
    design_id: LogicalId
    values: Annotated[dict[LogicalId, VariableValue], Field(min_length=1, max_length=32)]


class CheckedVariable(ContractModel):
    logical_id: LogicalId
    value: NumberText
    unit: Unit
    admissible: bool
    reason: CheckReason


class VariableValuesResult(ContractModel):
    design_id: LogicalId
    values: tuple[CheckedVariable, ...]
    locally_admissible: bool
    execution_authorized: Literal[False] = False
    check_scope: Literal["explicit_values_no_defaults_no_remote_execution"] = (
        "explicit_values_no_defaults_no_remote_execution"
    )
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


def describe_variables(
    design_id: str, declared: tuple[str, ...], contracts: DesignVariables | None
) -> VariableList:
    descriptions = []
    for variable in contracts.variables if contracts is not None else ():
        fields = variable.model_dump(exclude={"cadence_binding", "review_id"})
        descriptions.append(
            VariableDescription(
                **fields,
                range_authority="operator_review_record"
                if variable.range_status == "qualified"
                else "none",
            )
        )
    mapped = {item.logical_id for item in descriptions}
    return VariableList(
        design_id=design_id,
        declared_variables=declared,
        variables=tuple(descriptions),
        missing_contracts=tuple(item for item in declared if item not in mapped),
    )


def check_values(
    request: VariableValuesRequest, contracts: DesignVariables | None, copy_policy: str
) -> VariableValuesResult:
    mapped = {} if contracts is None else {v.logical_id: v for v in contracts.variables}
    rows = []
    for logical_id, supplied in request.values.items():
        variable = mapped.get(logical_id)
        reason: CheckReason | None
        if variable is None:
            reason = "unregistered_variable"
        elif supplied.unit != variable.unit:
            reason = "wrong_unit"
        elif variable.mutation_policy == "read_only":
            reason = "read_only_variable"
        elif variable.mutation_policy == "owned_copy_only" and copy_policy != "owned_copy_only":
            reason = "copy_policy_denied"
        else:
            reason = variable.check_number(supplied.value)
        rows.append(
            CheckedVariable(
                logical_id=logical_id,
                value=supplied.value,
                unit=supplied.unit,
                admissible=reason is None,
                reason=reason
                if reason is not None
                else (
                    "fixed_constraint_matched"
                    if variable is not None and variable.mutation_policy == "fixed"
                    else "numeric_contract_matched"
                ),
            )
        )
    return VariableValuesResult(
        design_id=request.design_id,
        values=tuple(rows),
        locally_admissible=all(row.admissible for row in rows),
    )
