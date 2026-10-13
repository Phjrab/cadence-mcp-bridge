"""Operator-owned generic targets over integrity-checked native result projections."""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.operator_operations import bounded_document
from cadence_mcp_bridge.specifications import Comparison, compare_numeric_target
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)


class NativeSpecificationContract(VariableModel):
    schema_version: Literal[1] = 1
    spec_id: LogicalId
    design_id: LogicalId
    measurement_id: LogicalId
    # The plan binds all explicit numeric inputs, analysis, registry/PDK/runtime and
    # authority. Runner manifest binds ADE stimulus/model/temp and reader definitions.
    operation_plan_sha256: Digest
    reader_registration_sha256: Digest
    metric: Literal["dc_voltage", "dc_supply_power", "ac_gain_db", "tran_last", "tran_mean"]
    signal_id: LogicalId | None = None
    frequency_hz: NumberText | None = None
    unit: Literal["V", "W", "dB"]
    comparison: Comparison
    target: NumberText | None
    upper_target: NumberText | None = None
    goal_id: LogicalId | None

    @field_validator("target", "upper_target", "frequency_hz", mode="before")
    @classmethod
    def decimals(cls, value: Any) -> str | None:
        return None if value is None else number_text(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.target is None:
            if self.goal_id is not None or self.upper_target is not None:
                raise ValueError("unselected target has no goal or upper bound")
        elif self.goal_id is None:
            raise ValueError("target requires an operator-owned goal")
        elif self.comparison == "range":
            if self.upper_target is None or Decimal(self.target) > Decimal(self.upper_target):
                raise ValueError("range requires ordered bounds")
        elif self.upper_target is not None:
            raise ValueError("only range accepts upper bound")
        if self.metric == "ac_gain_db":
            if (
                self.unit != "dB"
                or self.signal_id is not None
                or self.frequency_hz is None
                or Decimal(self.frequency_hz) <= 0
            ):
                raise ValueError("gain needs an exact frequency and dB unit")
        elif self.metric == "dc_supply_power":
            if self.unit != "W" or self.signal_id is not None or self.frequency_hz is not None:
                raise ValueError("power needs W and the registered supply scope")
        elif self.unit != "V" or self.signal_id is None or self.frequency_hz is not None:
            raise ValueError("voltage summary needs a logical signal and V unit")
        return self


class NativeSpecificationCatalog(VariableModel):
    schema_version: Literal[1] = 1
    specifications: Annotated[tuple[NativeSpecificationContract, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len({s.spec_id for s in self.specifications}) != len(self.specifications):
            raise ValueError("distinct specification IDs required")
        return self


class NativeSpecificationQuery(VariableModel):
    spec_id: LogicalId
    expected_contract_sha256: Digest
    operation_id: OperationId | None = None
    expected_plan_sha256: Digest | None = None

    @model_validator(mode="after")
    def pair(self) -> Self:
        if (self.operation_id is None) != (self.expected_plan_sha256 is None):
            raise ValueError("operation ID needs its exact plan hash")
        return self


class NativeSpecificationResult(ContractModel):
    spec_id: LogicalId
    contract_sha256: Digest
    operation_id: OperationId | None
    status: Literal[
        "PASS", "FAIL", "NOT_EVALUATED", "MISSING_MEASUREMENT", "CONDITION_MISMATCH", "UNQUALIFIED"
    ]
    value: float | None = None
    unit: Literal["V", "W", "dB"]
    measurement_result_sha256: Digest | None = None
    execution_authorized: Literal[False] = False


def project_specification(
    contract: NativeSpecificationContract, result: dict[str, Any]
) -> float | None:
    analysis = {
        "dc_voltage": "dc",
        "dc_supply_power": "dc",
        "ac_gain_db": "ac",
        "tran_last": "tran",
        "tran_mean": "tran",
    }[contract.metric]
    if result.get("analysis") != analysis:
        return None
    try:
        if contract.metric == "dc_supply_power":
            value = result["power"]["supply_w"]
        elif contract.metric == "ac_gain_db":
            value = next(
                p["gain_db"]
                for p in result["transfer"]
                if float(p["frequency_hz"])
                == float(format(float(contract.frequency_hz or "0"), ".16g"))
            )
        else:
            key = "nodes" if contract.metric == "dc_voltage" else "transient"
            field = {"dc_voltage": "value", "tran_last": "last", "tran_mean": "time_weighted_mean"}[
                contract.metric
            ]
            point = next(p for p in result[key] if p["logical_id"] == contract.signal_id)
            if point["unit"] != contract.unit:
                return None
            value = point[field]
        if type(value) not in (int, float) or not math.isfinite(value):
            return None
        return float(value)
    except (KeyError, TypeError, ValueError, StopIteration):
        return None


class NativeSpecificationSupervisor:
    def __init__(self, native: NativeOperationService) -> None:
        self.native = native

    def contracts(self) -> tuple[NativeSpecificationContract, ...]:
        self.native.current()
        binding = self.native.context.binding
        if binding.native_specifications is None:
            return ()
        raw = bounded_document(binding.native_specifications)
        if hashlib.sha256(raw).hexdigest() != binding.native_specifications_sha256:
            raise ConfigurationError("Native specification catalog changed; review and restart")
        catalog = NativeSpecificationCatalog.model_validate_json(raw)
        for c in catalog.specifications:
            self.native.context.resolve(c.design_id)
        return catalog.specifications

    def listing(self) -> dict[str, object]:
        return {
            "specifications": [
                dict(contract=c.model_dump(mode="json"), contract_sha256=canonical_digest(c))
                for c in self.contracts()
            ],
            "execution_authorized": False,
        }

    async def result(self, query: NativeSpecificationQuery) -> NativeSpecificationResult:
        c = next((c for c in self.contracts() if c.spec_id == query.spec_id), None)
        if c is None or canonical_digest(c) != query.expected_contract_sha256:
            raise InvalidInputError("Native specification contract is missing or stale")
        fields: dict[str, Any] = dict(
            spec_id=c.spec_id,
            contract_sha256=canonical_digest(c),
            operation_id=query.operation_id,
            unit=c.unit,
        )
        if c.target is None:
            return NativeSpecificationResult(**fields, status="NOT_EVALUATED")
        if query.operation_id is None or query.expected_plan_sha256 is None:
            return NativeSpecificationResult(**fields, status="MISSING_MEASUREMENT")
        # Failed/missing simulator results propagate as errors; never specification FAIL.
        result = await self.native.result(
            NativeOperationQuery(
                operation_id=query.operation_id, expected_plan_sha256=query.expected_plan_sha256
            )
        )
        data = result.result
        if (
            result.plan_sha256 != c.operation_plan_sha256
            or data.get("reader_registration_sha256") != c.reader_registration_sha256
            or data.get("design_id") != c.design_id
            or data.get("measurement_id") != c.measurement_id
        ):
            return NativeSpecificationResult(**fields, status="CONDITION_MISMATCH")
        value = project_specification(c, data)
        if value is None:
            return NativeSpecificationResult(**fields, status="UNQUALIFIED")
        status = compare_numeric_target(c.comparison, Decimal(str(value)), c.target, c.upper_target)
        return NativeSpecificationResult(
            **fields, status=status, value=value, measurement_result_sha256=canonical_digest(result)
        )
