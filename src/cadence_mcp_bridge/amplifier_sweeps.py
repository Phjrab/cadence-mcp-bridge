"""Compiled finite amplifier adapter for the existing durable sweep lifecycle."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Protocol, Self, cast
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.actual_diagnostics import SpectrumPoint
from cadence_mcp_bridge.bias_range import SOURCES, validate_grid_ac
from cadence_mcp_bridge.designs import DesignContractRegistry, RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import ContractModel, JobResult, JobStatus
from cadence_mcp_bridge.pdk_adapters import PdkRegistry
from cadence_mcp_bridge.pdk_reference import reference_adapter
from cadence_mcp_bridge.power_measurements import PowerCounter, SignedSource, delivered_power
from cadence_mcp_bridge.sweep_service import SweepBackend, SweepSupervisor
from cadence_mcp_bridge.sweeps import (
    SweepPlan,
    SweepPoint,
    SweepRequest,
    SweepResult,
    SweepStatus,
    SweepStore,
    SweepSubmission,
)
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    VariableModel,
    canonical_digest,
    number_text,
)

DESIGN: Literal["reference-differential-amplifier-tb2"] = "reference-differential-amplifier-tb2"
PROFILE: Literal["reference-amplifier-finite-grid-v1"] = "reference-amplifier-finite-grid-v1"
REGISTRY_SHA = "101901f99990e481ce54b93d65d161893b50504cee428169fee569eb6c849a1f"
REVISION: Literal["reference-amplifier-bias-grid-v1"] = "reference-amplifier-bias-grid-v1"
GRID: tuple[Literal["0.319", "0.32", "0.321"], ...] = ("0.319", "0.32", "0.321")
Finite = Annotated[float, Field(allow_inf_nan=False)]
Mode = Literal["dc", "ac"]


class AmplifierDefinition(ContractModel):
    schema_version: Literal[1] = 1
    design_id: Literal["reference-differential-amplifier-tb2"] = DESIGN
    revision_id: Literal["reference-amplifier-bias-grid-v1"] = REVISION
    variable_id: Literal["vbiasn"] = "vbiasn"
    grid_v: tuple[Literal["0.319", "0.32", "0.321"], ...] = GRID
    registry_sha256: Digest = REGISTRY_SHA
    fixed_vbiasp_v: Literal["0.702"] = "0.702"
    vdd_v: Literal["1"] = "1"
    vcm_v: Literal["0.5"] = "0.5"
    corner: Literal["nn"] = "nn"
    temperature_c: Literal[27] = 27
    load: Literal["existing_topology_no_added_external_load"] = (
        "existing_topology_no_added_external_load"
    )
    gain_definition: Literal["differential-voltage-gain-at-10hz-grid-v1"] = (
        "differential-voltage-gain-at-10hz-grid-v1"
    )
    power_definition: Literal["signed-dc-supply-rail-power-grid-v2"] = (
        "signed-dc-supply-rail-power-grid-v2"
    )
    power_sign: Literal["minus_terminal_voltage_times_positive_into_source_current"] = (
        "minus_terminal_voltage_times_positive_into_source_current"
    )
    power_scope: Literal["supply_rails_with_bias_and_input_separate_not_transient_or_DUT_only"] = (
        "supply_rails_with_bias_and_input_separate_not_transient_or_DUT_only"
    )
    qualification: Literal["finite_nominal_simulation_grid_only"] = (
        "finite_nominal_simulation_grid_only"
    )
    phase_margin: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    offset: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    cancellation: Literal["pending_points_only_active_job_not_terminated"] = (
        "pending_points_only_active_job_not_terminated"
    )


DEFINITION_SHA = canonical_digest(AmplifierDefinition())


class AmplifierSweepRequest(VariableModel):
    design_id: Literal["reference-differential-amplifier-tb2"]
    variable_id: Literal["vbiasn"]
    analysis_id: Literal["grid-dc-v1", "grid-ac-v1"]
    measurement_id: Literal["dc-supply-power-grid-v2", "gain-10hz-grid-v1"]
    values: Annotated[tuple[str, ...], Field(min_length=1, max_length=3)]
    unit: Literal["V"]
    fixed: dict[Literal["vbiasp", "vdd"], str]

    @field_validator("values", mode="before")
    @classmethod
    def canonical_values(cls, values: Any) -> tuple[str, ...]:
        if type(values) not in (list, tuple):
            raise ValueError("bounded grid array required")
        return tuple(number_text(v) for v in values)

    @model_validator(mode="after")
    def binding(self) -> Self:
        mode = "dc" if self.analysis_id == "grid-dc-v1" else "ac"
        if self.measurement_id != (
            "dc-supply-power-grid-v2" if mode == "dc" else "gain-10hz-grid-v1"
        ) or self.fixed != {"vbiasp": "0.702", "vdd": "1"}:
            raise ValueError("analysis/measurement/fixed condition mismatch")
        if len(set(self.values)) != len(self.values) or any(v not in GRID for v in self.values):
            raise ValueError("only unique qualified grid points allowed")
        return self


class AmplifierEngineRequest(SweepRequest):
    # Versioned subtype; the public legacy request schema is unchanged.
    profile_id: Literal["reference-amplifier-finite-grid-v1"] = PROFILE  # type: ignore[assignment]
    corner: Literal["nn"] = "nn"  # type: ignore[assignment]
    axis: Literal["vbiasn"] = "vbiasn"  # type: ignore[assignment]
    unit: Literal["V"] = "V"  # type: ignore[assignment]
    fixed: dict[Literal["vbiasp", "vdd"], str]  # type: ignore[assignment]
    binding: AmplifierSweepRequest


class AmplifierEnginePlan(SweepPlan):
    contract_version: Literal[2] = 2
    request: AmplifierEngineRequest
    revision_id: Literal["reference-amplifier-bias-grid-v1"] = REVISION  # type: ignore[assignment]
    classification: Literal["finite_1d_reference_amplifier"] = "finite_1d_reference_amplifier"  # type: ignore[assignment]
    definition_sha256: Digest = DEFINITION_SHA


def make_amplifier_plan(request: AmplifierSweepRequest) -> AmplifierEnginePlan:
    engine = AmplifierEngineRequest(values=request.values, fixed=request.fixed, binding=request)
    unsigned = AmplifierEnginePlan(
        plan_hash="0" * 64,
        request=engine,
        canonical_values=request.values,
        canonical_fixed={str(k): v for k, v in request.fixed.items()},
        point_count=len(request.values),
    )
    return unsigned.model_copy(update={"plan_hash": canonical_digest(unsigned)})


class AmplifierPoint(SweepPoint):
    unit: Literal["V"]  # type: ignore[assignment]
    revision_id: Literal["reference-amplifier-bias-grid-v1"] = REVISION  # type: ignore[assignment]


class AmplifierStatus(SweepStatus):
    contract_version: Literal[2] = 2
    points: tuple[AmplifierPoint, ...]
    cancellation_semantics: Literal["pending_only_active_job_continues"] = (
        "pending_only_active_job_continues"
    )


class AmplifierEngineResult(SweepResult):
    contract_version: Literal[2] = 2
    points: tuple[AmplifierPoint, ...]
    profile_id: Literal["reference-amplifier-finite-grid-v1"] = PROFILE  # type: ignore[assignment]
    axis: Literal["vbiasn"] = "vbiasn"  # type: ignore[assignment]
    unit: Literal["V"] = "V"  # type: ignore[assignment]
    cancellation_semantics: Literal["pending_only_active_job_continues"] = (
        "pending_only_active_job_continues"
    )


class AmplifierStore(SweepStore):
    PLAN_MODEL = AmplifierEnginePlan
    REQUEST_MODEL = AmplifierEngineRequest
    POINT_MODEL = AmplifierPoint

    @classmethod
    def _parse(cls, raw: str) -> dict[str, Any]:
        if len(raw) > 65536:
            raise InvalidInputError("Amplifier checkpoint exceeds bound")
        return super()._parse(raw)

    @staticmethod
    def plan_for(request: SweepRequest) -> SweepPlan:
        if not isinstance(request, AmplifierEngineRequest):
            raise InvalidInputError("compiled amplifier codec required")
        plan = make_amplifier_plan(request.binding)
        if plan.request != request:
            raise InvalidInputError("amplifier engine binding changed")
        return plan


class AmplifierChild(ContractModel):
    schema_version: Literal[2]
    definition_sha256: Digest
    revision_id: Literal["reference-amplifier-bias-grid-v1"]
    job_id: UUID
    plan_hash: Digest
    analysis: Mode
    requested_vbiasn_v: Literal["0.319", "0.32", "0.321"]
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    source_job_id: str
    source_input_sha256: Digest
    source_psf_sha256: Digest
    counter: PowerCounter
    protected_unchanged: Literal[True]
    warnings: Annotated[int, Field(ge=0, le=2, strict=True)]
    notices: Literal[0]
    scalars: dict[str, Finite] = Field(default_factory=dict, max_length=7)
    sources: Annotated[tuple[SignedSource, ...], Field(max_length=6)] = ()
    spectrum: Annotated[tuple[SpectrumPoint, ...], Field(max_length=72)] = ()

    @model_validator(mode="after")
    def qualified_shape(self) -> Self:
        if self.definition_sha256 != DEFINITION_SHA:
            raise ValueError("compiled point definition changed")
        if (
            self.job_id.version != 5
            or (self.source_job_id, self.source_input_sha256, self.source_psf_sha256)
            != SOURCES[self.analysis]
        ):
            raise ValueError("compiled deterministic child and original source required")
        if not 77 <= self.counter.count <= 82 or self.counter.result_reserved_bytes != (
            8993636352 + (self.counter.count - 76) * 128 * 1024**2
        ):
            raise ValueError("phase reservation identity")
        value = self.requested_vbiasn_v
        if self.analysis == "dc":
            if self.spectrum or set(self.scalars) != {
                "Vop",
                "Vom",
                "Vp",
                "Vm",
                "VDD",
                "Vbiasn",
                "Vbiasp",
            }:
                raise ValueError("complete effective DC frame required")
            expected = {"Vp": 0.5, "Vm": 0.5, "VDD": 1, "Vbiasn": float(value), "Vbiasp": 0.702}
            if any(abs(self.scalars[n] - v) > 1e-9 for n, v in expected.items()):
                raise ValueError("effective DC grid input")
            specs = (
                ("vdd", "supply", 1),
                ("vss", "supply", 0),
                ("bias-n", "bias", float(value)),
                ("bias-p", "bias", 0.702),
                ("input-p", "stimulus", 0.5),
                ("input-m", "stimulus", 0.5),
            )
            if len(self.sources) != 6:
                raise ValueError("complete signed supply inventory")
            for source, (name, role, voltage) in zip(self.sources, specs, strict=True):
                if (
                    source.source_id != name
                    or source.role != role
                    or source.current_a is None
                    or source.voltage_v is None
                    or abs(source.voltage_v - voltage) > 1e-9
                ):
                    raise ValueError("source current/sign/effective voltage binding")
            delivered_power(self.sources)
        else:
            # AC scientific content is the identical qualified bounded reader.
            if self.scalars or self.sources:
                raise ValueError("AC frame cannot contain DC data")
            validate_grid_ac(self.spectrum)
        return self


class AmplifierTransport(Protocol):
    async def amplifier_reserve(
        self, child: UUID, mode: Mode, value: str, plan_hash: str
    ) -> None: ...
    async def amplifier_lookup_reservation(self, child: UUID) -> bool: ...
    async def amplifier_submit(self, child: UUID) -> JobStatus: ...
    async def amplifier_status(self, child: UUID) -> JobStatus: ...
    async def amplifier_result(self, child: UUID) -> AmplifierChild: ...
    async def amplifier_effective_values(self, child: UUID) -> dict[str, str]: ...


class AmplifierBackend:
    """Adapt scientific result to common lifecycle checks without a new ledger."""

    def __init__(self, transport: AmplifierTransport) -> None:
        self.transport = transport

    async def lookup_sweep_reservation(self, child: UUID) -> bool:
        return await self.transport.amplifier_lookup_reservation(child)

    async def status(self, child: UUID) -> JobStatus:
        return await self.transport.amplifier_status(child)

    async def cancel(self, child: UUID) -> JobStatus:
        # Native active cancellation is not qualified. Only observe it.
        return await self.status(child)

    async def effective_sweep_values(self, child: UUID) -> dict[str, str]:
        return await self.transport.amplifier_effective_values(child)

    async def result(self, child: UUID) -> JobResult:
        from cadence_mcp_bridge.models import JobState, JobSummary

        result = await self.transport.amplifier_result(child)
        if result.job_id != child:
            raise InvalidInputError("amplifier child result identity")
        return JobResult(
            job_id=child,
            state=JobState.SUCCEEDED,
            exit_code=0,
            summary=JobSummary(
                text="Qualified bounded amplifier point",
                errors=0,
                warnings=result.warnings,
                notices=0,
            ),
        )


class AmplifierLifecycle(SweepSupervisor):
    STORE_TYPE: ClassVar[type[SweepStore]] = AmplifierStore
    STATUS_MODEL: ClassVar[type[SweepStatus]] = AmplifierStatus
    RESULT_MODEL: ClassVar[type[SweepResult]] = AmplifierEngineResult
    STOP_ACTIVE_ON_CANCEL: ClassVar[bool] = False

    def __init__(self, transport: AmplifierTransport, journal: Path) -> None:
        self.adapter = AmplifierBackend(transport)
        super().__init__(cast(SweepBackend, self.adapter), journal)

    async def _reserve_child(self, child: UUID, plan: SweepPlan, point: dict[str, Any]) -> None:
        p = AmplifierEnginePlan.model_validate(plan)
        mode: Mode = "dc" if p.request.binding.analysis_id == "grid-dc-v1" else "ac"
        await self.adapter.transport.amplifier_reserve(
            child, mode, str(point["requested_value"]), p.plan_hash
        )

    async def _submit_child(self, child: UUID, plan: SweepPlan, point: dict[str, Any]) -> JobStatus:
        return await self.adapter.transport.amplifier_submit(child)

    async def submit(self, submission: SweepSubmission) -> SweepStatus:
        result = await super().submit(submission)
        document = self.store.get(result.sweep_id)
        if document["cancel_requested"] and any(
            p.get("phase") in ("sending", "running") for p in document["points"]
        ) and (result.sweep_id not in self.tasks or self.tasks[result.sweep_id].done()):
            self.tasks[result.sweep_id] = asyncio.create_task(self._run(result.sweep_id))
        return result

    async def cancel(self, sweep_id: UUID) -> SweepStatus:
        # Reuse durable cancellation checkpoint semantics, with no process control.
        lock = self.locks.setdefault(sweep_id, asyncio.Lock())
        async with lock:
            document = self.store.get(sweep_id)
            if all(p["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") for p in document["points"]):
                return self._status(document)
            document["cancel_requested"] = True
            for point in document["points"]:
                if point["state"] == "NOT_RUN" and point.get("phase") not in ("sending", "running"):
                    point.update(state="CANCELLED", phase="cancelled", quality="not_available")
            self.store.put(document)
        return self._status(self.store.get(sweep_id))

    @classmethod
    def _status(cls, document: dict[str, Any]) -> SweepStatus:
        result = super()._status(document)
        if document["cancel_requested"] and any(
            p.get("phase") in ("sending", "running") and p["state"] not in ("SUCCEEDED", "FAILED")
            for p in document["points"]
        ):
            return result.model_copy(update={"state": "RUNNING"})
        return result


class AmplifierPrepared(ContractModel):
    contract_version: Literal[1] = 1
    definition: AmplifierDefinition = Field(default_factory=AmplifierDefinition)
    definition_sha256: Digest = DEFINITION_SHA
    engine_plan: AmplifierEnginePlan
    execution_eligible: Literal[True] = True
    runtime_guards_required: Literal[True] = True
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class AmplifierSubmission(VariableModel):
    request: AmplifierSweepRequest
    expected_plan_hash: Digest
    experiment_key: UUID

    @field_validator("experiment_key", mode="before")
    @classmethod
    def uuid_string(cls, value: Any) -> UUID:
        if type(value) is str:
            parsed = UUID(value)
            if str(parsed) != value:
                raise ValueError("canonical experiment UUID")
            return parsed
        if isinstance(value, UUID):
            return value
        raise ValueError("experiment UUID required")


class AmplifierQuery(VariableModel):
    design_id: Literal["reference-differential-amplifier-tb2"]
    sweep_id: UUID

    @field_validator("sweep_id", mode="before")
    @classmethod
    def uuid_string(cls, value: Any) -> UUID:
        return AmplifierSubmission.uuid_string(value)


class AmplifierMetric(ContractModel):
    job_id: UUID
    requested_vbiasn_v: str
    measurement_id: Literal["dc-supply-power-grid-v2", "gain-10hz-grid-v1"]
    definition_sha256: Digest = DEFINITION_SHA
    status: Literal["QUALIFIED"] = "QUALIFIED"
    value: Finite
    unit: Literal["W", "dB"]
    bias_source_power_w: Finite | None = None
    input_source_power_w: Finite | None = None
    all_source_power_w: Finite | None = None
    signed_sources: tuple[SignedSource, ...] = ()
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    source_result_sha256: Digest
    counter: PowerCounter
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def source_derivation(self) -> Self:
        if self.definition_sha256 != DEFINITION_SHA or self.requested_vbiasn_v not in GRID:
            raise ValueError("compiled metric/grid binding")
        if self.measurement_id == "dc-supply-power-grid-v2":
            if self.unit != "W" or (
                self.value, self.bias_source_power_w, self.input_source_power_w,
                self.all_source_power_w
            ) != delivered_power(self.signed_sources):
                raise ValueError("qualified signed source power derivation required")
        elif (self.unit != "dB" or self.signed_sources or any(v is not None for v in (
            self.bias_source_power_w,self.input_source_power_w,self.all_source_power_w
        ))):
            raise ValueError("qualified differential AC gain shape")
        return self


class AmplifierSweepResult(ContractModel):
    contract_version: Literal[1] = 1
    definition: AmplifierDefinition = Field(default_factory=AmplifierDefinition)
    definition_sha256: Digest = DEFINITION_SHA
    engine: AmplifierEngineResult
    measurements: Annotated[tuple[AmplifierMetric, ...], Field(max_length=3)]
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class AmplifierSupervisor:
    def __init__(
        self,
        registry: RegistryBase,
        pdks: PdkRegistry,
        transport: AmplifierTransport,
        journal: Path,
    ) -> None:
        self.registry, self.pdks, self.transport = registry, pdks, transport
        self.engine = AmplifierLifecycle(transport, journal)

    def require_contract(self) -> None:
        if (
            not isinstance(self.registry, DesignContractRegistry)
            or canonical_digest(self.registry) != REGISTRY_SHA
            or self.pdks.find(reference_adapter().adapter_id) != reference_adapter()
        ):
            raise InvalidInputError("Reviewed amplifier finite-grid operator registry required")

    def prepare(self, request: AmplifierSweepRequest) -> AmplifierPrepared:
        self.require_contract()
        return AmplifierPrepared(engine_plan=make_amplifier_plan(request))

    async def submit(self, submission: AmplifierSubmission) -> AmplifierStatus:
        plan = self.prepare(submission.request).engine_plan
        if submission.expected_plan_hash != plan.plan_hash:
            raise InvalidInputError("Amplifier sweep plan changed")
        return AmplifierStatus.model_validate(
            await self.engine.submit(
                SweepSubmission(plan=plan, experiment_key=submission.experiment_key)
            )
        )

    async def status(self, query: AmplifierQuery) -> AmplifierStatus:
        self.require_contract()
        return AmplifierStatus.model_validate(await self.engine.status(query.sweep_id))

    async def cancel(self, query: AmplifierQuery) -> AmplifierStatus:
        self.require_contract()
        return AmplifierStatus.model_validate(await self.engine.cancel(query.sweep_id))

    async def result(self, query: AmplifierQuery) -> AmplifierSweepResult:
        self.require_contract()
        result = AmplifierEngineResult.model_validate(await self.engine.result(query.sweep_id))
        plan = AmplifierEnginePlan.model_validate(self.engine.store.get(query.sweep_id)["plan"])
        metrics = []
        for point in result.points:
            if point.state != "SUCCEEDED":
                continue
            child = await self.transport.amplifier_result(point.child_job_id)
            mode = "dc" if plan.request.binding.analysis_id == "grid-dc-v1" else "ac"
            if (
                child.job_id != point.child_job_id
                or child.plan_hash != plan.plan_hash
                or child.analysis != mode
                or child.requested_vbiasn_v != point.requested_value
            ):
                raise InvalidInputError("Point measurement/admission binding changed")
            common: dict[str, Any] = dict(
                job_id=child.job_id,
                requested_vbiasn_v=child.requested_vbiasn_v,
                input_sha256=child.input_sha256,
                psf_sha256=child.psf_sha256,
                frame_sha256=child.frame_sha256,
                source_result_sha256=canonical_digest(child),
                counter=child.counter,
            )
            if mode == "dc":
                rails, bias, stimulus, total = delivered_power(child.sources)
                metric = AmplifierMetric(
                    **common,
                    measurement_id="dc-supply-power-grid-v2",
                    value=rails,
                    unit="W",
                    bias_source_power_w=bias,
                    input_source_power_w=stimulus,
                    all_source_power_w=total,
                    signed_sources=child.sources,
                )
            else:
                gain = child.spectrum[0]
                if (
                    gain.frequency_hz != 10
                    or gain.gain_db is None
                    or not math.isfinite(gain.gain_db)
                ):
                    raise InvalidInputError("10Hz differential gain unavailable")
                metric = AmplifierMetric(
                    **common, measurement_id="gain-10hz-grid-v1", value=gain.gain_db, unit="dB"
                )
            metrics.append(metric)
        return AmplifierSweepResult(engine=result, measurements=tuple(metrics))
