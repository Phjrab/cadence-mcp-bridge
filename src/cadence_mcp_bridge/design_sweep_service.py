"""Registered contracts wrapping the existing durable sweep engine, not a new engine."""

import sqlite3
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import field_validator

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.fixture_contracts import CompletionDefinition, FixtureAnalysis
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.pdk_adapters import PdkAdapter, PdkRegistry
from cadence_mcp_bridge.registered_sweeps import (
    DesignSweepPlan,
    DesignSweepRequest,
    RegisteredSweepPlanner,
)
from cadence_mcp_bridge.sweep_registry import BINDINGS, FIXTURE_PDK
from cadence_mcp_bridge.sweep_service import SweepSupervisor
from cadence_mcp_bridge.sweeps import (
    PointState,
    SweepPlan,
    SweepRequest,
    SweepResult,
    SweepStatus,
    SweepSubmission,
    make_plan,
    sweep_id,
)
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


def fixture_pdk_adapter() -> PdkAdapter:
    """Explicit no-PDK applicability, never a qualified device/model adapter."""
    return PdkAdapter(
        schema_version=2,
        adapter_id=FIXTURE_PDK,
        technology_id="passive-template",
        role="regression_reference",
        environment_ids=("cadence-vm",),
        process_corner_ids=("nominal",),
        rc_corner_ids=(),
        binding_kind="unqualified",
        binding_ref=None,
        binding_sha256=None,
        capabilities=(),
    )


class DesignSweepExecutionPlan(ContractModel):
    contract_version: Literal[2] = 2
    plan_hash: Digest
    request: DesignSweepRequest
    local_plan: DesignSweepPlan
    execution_eligible: bool
    qualification_scope: Literal["compiled_rc_fixture", "unqualified"]
    blocking_reason: (
        Literal["numeric_contract_denied", "adapter_unqualified", "pdk_mismatch"] | None
    )
    engine_plan: SweepPlan | None
    definition: CompletionDefinition | None
    runtime_verification: Literal["existing_sweep_guards_required"] = (
        "existing_sweep_guards_required"
    )
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class SweepIdentityModel(VariableModel):
    @field_validator("experiment_key", "sweep_id", mode="before", check_fields=False)
    @classmethod
    def canonical_uuid(cls, value: Any) -> UUID:
        if isinstance(value, UUID):
            return value
        if type(value) is not str:
            raise ValueError("canonical UUID string required")
        parsed = UUID(value)
        if str(parsed) != value:
            raise ValueError("canonical UUID string required")
        return parsed


class DesignSweepSubmission(SweepIdentityModel):
    request: DesignSweepRequest
    expected_plan_hash: Digest
    experiment_key: UUID


class DesignSweepQuery(SweepIdentityModel):
    design_id: LogicalId
    sweep_id: UUID


class DesignSweepExecutionResult(ContractModel):
    contract_version: Literal[2] = 2
    design_id: LogicalId
    analysis_id: LogicalId
    variable_id: LogicalId
    measurement_ids: tuple[LogicalId, ...]
    plan_hash: Digest
    contract_sha256: Digest
    definition: CompletionDefinition
    engine: SweepStatus | SweepResult
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class DesignSweepSupervisor:
    def __init__(
        self,
        planner: RegisteredSweepPlanner,
        engine: SweepSupervisor,
        pdks: PdkRegistry,
    ) -> None:
        self.planner, self.engine, self.pdks = planner, engine, pdks

    def prepare(self, request: DesignSweepRequest) -> DesignSweepExecutionPlan:
        local = self.planner.plan(request)
        analysis = next(
            c
            for c in self.planner.registry.analyses_for(request.design_id)
            if c.analysis_id == request.analysis_id
        )
        engine_plan = None
        reason: Literal["numeric_contract_denied", "adapter_unqualified", "pdk_mismatch"] | None
        if not local.locally_admissible:
            reason = "numeric_contract_denied"
        elif not isinstance(analysis, FixtureAnalysis) or request.measurement_ids != (
            "completion",
        ):
            reason = "adapter_unqualified"
        elif self.pdks.find(FIXTURE_PDK) != fixture_pdk_adapter():
            reason = "pdk_mismatch"
        else:
            # Registry v5 pins design, variables, analysis and reader to this one compiled route.
            engine_plan = make_plan(
                SweepRequest(
                    profile_id="fixture-rc-transient",
                    axis=BINDINGS[request.variable_id],
                    unit=cast(Literal["ohm", "F", "s"], request.unit),
                    values=local.canonical_values,
                    fixed={BINDINGS[n]: v.value for n, v in local.canonical_fixed.items()},
                )
            )
            reason = None
        unsigned = DesignSweepExecutionPlan(
            plan_hash="0" * 64,
            request=request.model_copy(
                update={
                    "values": local.canonical_values,
                    "linear": None,
                    "fixed": local.canonical_fixed,
                    "measurement_ids": local.contract.measurement_ids,
                }
            ),
            local_plan=local,
            execution_eligible=reason is None,
            qualification_scope="compiled_rc_fixture" if reason is None else "unqualified",
            blocking_reason=reason,
            engine_plan=engine_plan,
            definition=CompletionDefinition() if reason is None else None,
        )
        # Include the entire immutable PDK snapshot, including negative applicability.
        digest = canonical_digest(
            unsigned.model_copy(
                update={
                    "plan_hash": canonical_digest(self.pdks),
                }
            )
        )
        return unsigned.model_copy(update={"plan_hash": digest})

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.engine.store.path, timeout=10)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    async def submit(self, submission: DesignSweepSubmission) -> DesignSweepExecutionResult:
        plan = self.prepare(submission.request)
        if not plan.execution_eligible or plan.engine_plan is None:
            raise InvalidInputError("Registered sweep execution is unqualified")
        if submission.expected_plan_hash != plan.plan_hash:
            raise InvalidInputError("Registered sweep execution plan changed")
        parent = sweep_id(plan.engine_plan.plan_hash, submission.experiment_key)
        raw = plan.model_dump_json()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS registered_sweep_admissions "
                "(id TEXT PRIMARY KEY, experiment_key TEXT UNIQUE NOT NULL, plan TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT id,plan FROM registered_sweep_admissions WHERE experiment_key=?",
                (str(submission.experiment_key),),
            ).fetchone()
            if row is not None:
                if row[0] != str(parent) or self._validate(row[1]) != plan:
                    raise InvalidInputError("Experiment key belongs to another registered contract")
            else:
                connection.execute(
                    "INSERT INTO registered_sweep_admissions VALUES (?,?,?)",
                    (str(parent), str(submission.experiment_key), raw),
                )
        # Engine owns the journal phases/reservations/children, including crash recovery.
        status = await self.engine.submit(
            SweepSubmission(
                plan=plan.engine_plan,
                experiment_key=submission.experiment_key,
            )
        )
        return self._envelope(plan, status)

    def _validate(self, raw: str) -> DesignSweepExecutionPlan:
        try:
            if len(raw) > 65536:
                raise ValueError("admission bound")
            plan = DesignSweepExecutionPlan.model_validate_json(raw)
            current = self.prepare(plan.request)
            if plan != current or not current.execution_eligible:
                raise ValueError("admission drift")
        except (ValueError, KeyError):
            raise InvalidInputError(
                "Registered sweep admission corrupt or contract changed"
            ) from None
        return plan

    def admitted(self, query: DesignSweepQuery) -> DesignSweepExecutionPlan:
        with self._connect() as connection:
            if (
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='registered_sweep_admissions'"
                ).fetchone()
                is None
            ):
                raise InvalidInputError("Unknown registered sweep admission")
            row = connection.execute(
                "SELECT experiment_key,plan FROM registered_sweep_admissions WHERE id=?",
                (str(query.sweep_id),),
            ).fetchone()
        if row is None:
            raise InvalidInputError("Unknown registered sweep admission")
        plan = self._validate(row[1])
        if (
            plan.request.design_id != query.design_id
            or plan.engine_plan is None
            or sweep_id(plan.engine_plan.plan_hash, UUID(row[0])) != query.sweep_id
        ):
            raise InvalidInputError("Registered sweep identity mismatch")
        return plan

    async def status(self, query: DesignSweepQuery) -> DesignSweepExecutionResult:
        plan = self.admitted(query)
        return self._envelope(plan, await self.engine.status(query.sweep_id))

    async def result(self, query: DesignSweepQuery) -> DesignSweepExecutionResult:
        plan = self.admitted(query)
        return self._envelope(plan, await self.engine.result(query.sweep_id))

    async def cancel(self, query: DesignSweepQuery) -> DesignSweepExecutionResult:
        plan = self.admitted(query)
        status = await self.engine.status(query.sweep_id)
        if all(
            p.state in (PointState.SUCCEEDED, PointState.FAILED, PointState.CANCELLED)
            for p in status.points
        ):
            return self._envelope(plan, status)
        return self._envelope(plan, await self.engine.cancel(query.sweep_id))

    @staticmethod
    def _envelope(
        plan: DesignSweepExecutionPlan,
        status: SweepStatus | SweepResult,
    ) -> DesignSweepExecutionResult:
        assert plan.definition is not None and plan.engine_plan is not None
        if status.plan_hash != plan.engine_plan.plan_hash:
            raise InvalidInputError("Registered engine plan identity mismatch")
        return DesignSweepExecutionResult(
            design_id=plan.request.design_id,
            analysis_id=plan.request.analysis_id,
            variable_id=plan.request.variable_id,
            measurement_ids=plan.request.measurement_ids,
            plan_hash=plan.plan_hash,
            contract_sha256=plan.request.expected_contract_sha256,
            definition=plan.definition,
            engine=status,
        )
