"""Local registered 1D planning only; numeric reviews never authorize execution."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.analyses import AnalysisSelection
from cadence_mcp_bridge.analysis_service import AnalysisSupervisor
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.measurement_service import MeasurementSupervisor
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.registered_measurements import MeasurementSelection
from cadence_mcp_bridge.sweeps import MAX_POINTS
from cadence_mcp_bridge.variable_contracts import (
    CheckedVariable,
    Digest,
    LogicalId,
    NumberText,
    Unit,
    VariableDescription,
    VariableModel,
    VariableValue,
    VariableValuesRequest,
    canonical_digest,
    number_text,
)

SweepBlocker = Literal[
    "axis_range_unqualified",
    "axis_not_mutable",
    "copy_policy_denied",
    "analysis_unqualified",
    "measurement_unqualified",
    "parameterized_adapter_unqualified",
]


class DesignSweepSelection(VariableModel):
    design_id: LogicalId
    analysis_id: LogicalId
    variable_id: LogicalId
    measurement_ids: Annotated[tuple[LogicalId, ...], Field(min_length=1, max_length=32)]

    @field_validator("measurement_ids", mode="before")
    @classmethod
    def json_array(cls, value: Any) -> tuple[str, ...]:
        if type(value) not in (list, tuple):
            raise ValueError("measurement IDs require a bounded JSON array")
        return tuple(value)

    @model_validator(mode="after")
    def distinct_measurements(self) -> Self:
        if len(set(self.measurement_ids)) != len(self.measurement_ids):
            raise ValueError("duplicate measurement ID")
        return self


class DesignSweepLinear(VariableModel):
    start: NumberText
    stop: NumberText
    step: NumberText

    @field_validator("start", "stop", "step", mode="before")
    @classmethod
    def decimals(cls, value: Any) -> str:
        return number_text(value)


class DesignSweepRequest(DesignSweepSelection):
    expected_contract_sha256: Digest
    unit: Unit
    values: Annotated[tuple[NumberText, ...] | None, Field(min_length=1, max_length=MAX_POINTS)] = (
        None
    )
    linear: DesignSweepLinear | None = None
    fixed: Annotated[dict[LogicalId, VariableValue], Field(max_length=32)]
    initial_condition: Literal["independent"] = "independent"

    @field_validator("values", mode="before")
    @classmethod
    def decimals(cls, value: Any) -> tuple[str, ...] | None:
        if value is None:
            return None
        if type(value) not in (list, tuple):
            raise ValueError("values require a bounded JSON array")
        return tuple(number_text(v) for v in value)

    @model_validator(mode="after")
    def one_axis(self) -> Self:
        if (self.values is None) == (self.linear is None):
            raise ValueError("select explicit values or an exact linear range")
        return self


class DesignSweepDescription(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    analysis_id: LogicalId
    variable_id: LogicalId
    measurement_ids: tuple[LogicalId, ...]
    contract_sha256: Digest
    registry_sha256: Digest
    pdk_registry_sha256: Digest
    analysis_plan_hash: Digest
    axis: VariableDescription
    required_fixed_ids: Annotated[tuple[LogicalId, ...], Field(max_length=31)]
    maximum_points: Literal[16] = 16
    planning_scope: Literal["local_registered_1d_contract_only"] = (
        "local_registered_1d_contract_only"
    )
    parameterized_execution: Literal["unqualified"] = "unqualified"
    blocking_reasons: tuple[SweepBlocker, ...]
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class DesignSweepPointPlan(ContractModel):
    index: Annotated[int, Field(ge=0, lt=MAX_POINTS)]
    requested_value: NumberText
    axis_check: CheckedVariable
    locally_admissible: bool
    state: Literal["NOT_RUN"] = "NOT_RUN"


class DesignSweepPlan(ContractModel):
    contract_version: Literal[1] = 1
    plan_hash: Digest
    contract: DesignSweepDescription
    canonical_values: Annotated[tuple[NumberText, ...], Field(min_length=1, max_length=MAX_POINTS)]
    canonical_fixed: dict[LogicalId, VariableValue]
    fixed_checks: Annotated[tuple[CheckedVariable, ...], Field(max_length=31)]
    points: Annotated[tuple[DesignSweepPointPlan, ...], Field(min_length=1, max_length=MAX_POINTS)]
    point_count: Annotated[int, Field(ge=1, le=MAX_POINTS)]
    locally_admissible: bool
    execution_authorized: Literal[False] = False
    initial_condition: Literal["independent"] = "independent"
    reservation_state: Literal["not_reserved"] = "not_reserved"
    durable_admission: Literal["not_created"] = "not_created"
    cancellation: Literal["no_execution_to_cancel"] = "no_execution_to_cancel"
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


def expand_values(request: DesignSweepRequest) -> tuple[str, ...]:
    """Exact bounded Decimal arithmetic, independent of caller decimal context."""
    if request.values is not None:
        values = request.values
    else:
        assert request.linear is not None
        with localcontext() as context:
            context.prec = 128
            start, stop, step = (
                Decimal(getattr(request.linear, n)) for n in ("start", "stop", "step")
            )
            if step == 0 or (stop - start) * step < 0:
                raise InvalidInputError("Sweep step is zero or has the wrong direction")
            distance = (stop - start) / step
            if distance != distance.to_integral_value() or not 0 <= distance < MAX_POINTS:
                raise InvalidInputError("Sweep must land exactly on stop within 16 points")
            try:
                values = tuple(number_text(str(start + i * step)) for i in range(int(distance) + 1))
            except ValueError:
                raise InvalidInputError("Expanded sweep decimal exceeds its bound") from None
    if len(set(values)) != len(values):
        raise InvalidInputError("Duplicate canonical sweep values")
    return values


class RegisteredSweepPlanner:
    def __init__(
        self,
        registry: RegistryBase,
        analyses: AnalysisSupervisor,
        measurements: MeasurementSupervisor,
    ) -> None:
        self.registry = registry
        self.analyses = analyses
        self.measurements = measurements

    def describe(self, selection: DesignSweepSelection) -> DesignSweepDescription:
        profile = self.registry.profile(selection.design_id)
        variables = self.registry.variables(selection.design_id)
        axis = next((v for v in variables.variables if v.logical_id == selection.variable_id), None)
        if axis is None or variables.missing_contracts:
            raise InvalidInputError("Sweep requires all declared variable contracts")
        analysis = self.analyses.plan(
            AnalysisSelection(
                design_id=selection.design_id,
                analysis_id=selection.analysis_id,
            )
        )
        measurements = tuple(
            self.measurements.describe(
                MeasurementSelection(
                    design_id=selection.design_id,
                    measurement_id=n,
                )
            )
            for n in sorted(selection.measurement_ids)
        )
        if any(m.analysis_id != selection.analysis_id for m in measurements):
            raise InvalidInputError("Sweep measurements must bind the selected analysis")
        reasons: list[SweepBlocker] = []
        if axis.range_status != "qualified":
            reasons.append("axis_range_unqualified")
        if axis.mutation_policy != "owned_copy_only":
            reasons.append("axis_not_mutable")
        if profile.work_copy_policy != "owned_copy_only":
            reasons.append("copy_policy_denied")
        if not analysis.dispatch_eligible:
            reasons.append("analysis_unqualified")
        if any(not m.read_eligible for m in measurements):
            reasons.append("measurement_unqualified")
        # All currently compiled physical analyses have fixed inputs, no variable route.
        reasons.append("parameterized_adapter_unqualified")
        unsigned = DesignSweepDescription(
            contract_sha256="0" * 64,
            design_id=selection.design_id,
            analysis_id=selection.analysis_id,
            variable_id=selection.variable_id,
            measurement_ids=tuple(sorted(selection.measurement_ids)),
            registry_sha256=self.registry.sweep_identity_digest(),
            pdk_registry_sha256=canonical_digest(self.analyses.pdks),
            analysis_plan_hash=analysis.plan_hash,
            axis=axis,
            required_fixed_ids=tuple(
                sorted(set(profile.allowed_variables) - {selection.variable_id})
            ),
            blocking_reasons=tuple(reasons),
        )
        return unsigned.model_copy(update={"contract_sha256": canonical_digest(unsigned)})

    def plan(self, request: DesignSweepRequest) -> DesignSweepPlan:
        contract = self.describe(request)
        if request.expected_contract_sha256 != contract.contract_sha256:
            raise InvalidInputError("Sweep contract does not match the current registry")
        if request.unit != contract.axis.unit:
            raise InvalidInputError("Sweep axis unit mismatch")
        if set(request.fixed) != set(contract.required_fixed_ids):
            raise InvalidInputError("Sweep requires exactly all non-axis values; no defaults")
        values = expand_values(request)
        fixed = dict(sorted(request.fixed.items()))
        points = []
        fixed_checks: tuple[CheckedVariable, ...] = ()
        for index, value in enumerate(values):
            checks = self.registry.check_variables(
                VariableValuesRequest(
                    design_id=request.design_id,
                    values={
                        **fixed,
                        request.variable_id: VariableValue(value=value, unit=request.unit),
                    },
                )
            )
            # A fixed constraint may be checked, but never swept as a mutable axis.
            admissible = (
                checks.locally_admissible and contract.axis.mutation_policy == "owned_copy_only"
            )
            fixed_checks = tuple(c for c in checks.values if c.logical_id != request.variable_id)
            points.append(
                DesignSweepPointPlan(
                    index=index,
                    requested_value=value,
                    axis_check=next(
                        c for c in checks.values if c.logical_id == request.variable_id
                    ),
                    locally_admissible=admissible,
                )
            )
        unsigned = DesignSweepPlan(
            plan_hash="0" * 64,
            contract=contract,
            canonical_values=values,
            canonical_fixed=fixed,
            fixed_checks=fixed_checks,
            points=tuple(points),
            point_count=len(values),
            locally_admissible=all(p.locally_admissible for p in points),
        )
        return unsigned.model_copy(update={"plan_hash": canonical_digest(unsigned)})
