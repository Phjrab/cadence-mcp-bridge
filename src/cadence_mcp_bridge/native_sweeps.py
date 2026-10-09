"""Bounded 1D coordination over the existing native lifecycle and analysis journal.

No worker, budget, remote runner or parallel accounting is created. Planning is
read-only. Parent retries are lookup-only; advance explicitly admits at most one
untouched point after every preceding point has succeeded.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.analysis_store import MAX_RECORDS, AnalysisStore
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import (
    NativeOperationQuery,
    NativeOperationRequest,
    NativeOperationService,
)
from cadence_mcp_bridge.operator_operations import ExplicitValue, OperationPlan, OperationRequest
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)


class NativeSweepRequest(VariableModel):
    template: NativeOperationRequest
    variable_id: LogicalId
    values: Annotated[tuple[NumberText, ...], Field(min_length=1, max_length=16)]

    @field_validator("values", mode="before")
    @classmethod
    def numbers(cls, values: Any) -> tuple[str, ...]:
        if type(values) not in (list, tuple):
            raise ValueError("bounded explicit numeric array required")
        return tuple(number_text(value) for value in values)

    @field_validator("template", mode="before")
    @classmethod
    def json_template(cls, value: Any) -> Any:
        if type(value) is dict:
            return NativeOperationRequest.model_validate_json(json.dumps(value))
        return value

    @model_validator(mode="after")
    def axis(self) -> Self:
        if len(set(self.values)) != len(self.values):
            raise ValueError("distinct canonical axis values required")
        if self.variable_id not in {v.logical_id for v in self.template.values}:
            raise ValueError("axis must be one explicit registered variable")
        return self

    def point_request(self, index: int) -> NativeOperationRequest:
        return self.template.model_copy(
            update={
                "values": tuple(
                    ExplicitValue(
                        logical_id=v.logical_id,
                        unit=v.unit,
                        value=self.values[index] if v.logical_id == self.variable_id else v.value,
                    )
                    for v in self.template.values
                )
            }
        )


class NativeSweepPlan(VariableModel):
    schema_version: Literal[1] = 1
    request: NativeSweepRequest
    points: Annotated[tuple[OperationPlan, ...], Field(min_length=1, max_length=16)]
    initial_condition: Literal["independent"] = "independent"
    accounting: Literal["existing_native_operations_no_additional_ledger"] = (
        "existing_native_operations_no_additional_ledger"
    )

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(self.points) != len(self.request.values):
            raise ValueError("point count differs")
        for i, point in enumerate(self.points):
            expected = OperationRequest.model_validate_json(
                self.request.point_request(i).model_dump_json()
            )
            expected = expected.model_copy(
                update={"values": tuple(sorted(expected.values, key=lambda v: v.logical_id))}
            )
            if point.request != expected:
                raise ValueError("point axis or fixed inputs differ")
            if point.model_copy(update={"request": self.points[0].request}) != self.points[0]:
                raise ValueError("point authority/runtime identity differs")
        return self

    @property
    def plan_sha256(self) -> str:
        return canonical_digest(self)


class NativeSweepQuery(VariableModel):
    sweep_id: OperationId
    expected_plan_sha256: Digest


class NativeSweepSubmission(NativeSweepQuery):
    request: NativeSweepRequest

    @field_validator("request", mode="before")
    @classmethod
    def json_request(cls, value: Any) -> Any:
        if type(value) is dict:
            return NativeSweepRequest.model_validate_json(json.dumps(value))
        return value


class NativeSweepRecord(VariableModel):
    sweep_id: OperationId
    plan: NativeSweepPlan
    operation_ids: Annotated[tuple[OperationId, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if (
            len(self.operation_ids) != len(self.plan.points)
            or len(set(self.operation_ids)) != len(self.operation_ids)
            or self.sweep_id in self.operation_ids
        ):
            raise ValueError("distinct immutable child identities required")
        return self


class NativeSweepPlanned(ContractModel):
    plan: NativeSweepPlan
    plan_sha256: Digest
    point_count: int
    result_reservation_bytes: int
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False

    @field_validator("plan", mode="before")
    @classmethod
    def json_plan(cls, value: Any) -> Any:
        if type(value) is dict:
            return NativeSweepPlan.model_validate_json(json.dumps(value))
        return value


class NativeSweepStatus(ContractModel):
    sweep_id: OperationId
    plan_sha256: Digest
    state: Literal["PLANNED", "PARTIAL", "RUNNING", "STOPPED", "SUCCEEDED"]
    points: tuple[dict[str, Any], ...]
    simulation_retry: Literal[False] = False
    budget_reset_or_refund: Literal[False] = False


class NativeSweepResult(ContractModel):
    sweep_id: OperationId
    plan_sha256: Digest
    variable_id: LogicalId
    requested_values: tuple[str, ...]
    points: tuple[dict[str, Any], ...]
    execution_authorized: Literal[False] = False
    budget_reset_or_refund: Literal[False] = False


class NativeSweepStore:
    """Additive parent identities in the existing guarded AnalysisStore.

    The legacy SweepStore's deterministic reference UUID5 codec is preserved;
    native children require UUID4. This table coordinates those native operations
    rather than interpreting or resetting the legacy sweep database.
    """

    def __init__(self, store: AnalysisStore) -> None:
        self.store = store

    @staticmethod
    def _parse(raw: str, query: NativeSweepQuery) -> NativeSweepRecord:
        try:
            if len(raw) > 524288:
                raise ValueError("size")
            record = NativeSweepRecord.model_validate_json(raw)
            if (record.sweep_id, record.plan.plan_sha256) != (
                query.sweep_id,
                query.expected_plan_sha256,
            ):
                raise ValueError("identity")
            return record
        except ValueError:
            raise InvalidInputError("Native sweep checkpoint identity is invalid") from None

    def admit(self, query: NativeSweepQuery, plan: NativeSweepPlan) -> NativeSweepRecord:
        if query.expected_plan_sha256 != plan.plan_sha256:
            raise InvalidInputError("Native sweep plan differs from the reviewed plan")
        with self.store.connection(create=True) as connection:
            self.store._lifecycle_capacity(connection)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS native_sweeps_v1 "
                "(sweep_id TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT document FROM native_sweeps_v1 WHERE sweep_id=?", (query.sweep_id,)
            ).fetchone()
            if row is not None:
                return self._parse(row[0], query)
            if (
                connection.execute("SELECT COUNT(*) FROM native_sweeps_v1").fetchone()[0]
                >= MAX_RECORDS
            ):
                raise ConfigurationError("Native sweep journal capacity reached")
            # Parent and child IDs share one namespace with every admission and
            # prior sweep claim, even before any child is dispatched.
            if not self.store.native_sweep_identity_available(connection, query.sweep_id):
                raise InvalidInputError("Native sweep ID conflicts with a reserved operation")
            record = NativeSweepRecord(
                sweep_id=query.sweep_id,
                plan=plan,
                operation_ids=tuple(str(uuid4()) for _ in plan.points),
            )
            if any(
                not self.store.native_sweep_identity_available(connection, identity)
                for identity in record.operation_ids
            ):
                raise InvalidInputError("Native sweep child ID conflicts with a reserved operation")
            raw = record.model_dump_json()
            if len(raw) > 524288:
                raise ConfigurationError("Native sweep plan exceeds journal capacity")
            connection.execute("INSERT INTO native_sweeps_v1 VALUES (?,?)", (query.sweep_id, raw))
            return record

    def read(self, query: NativeSweepQuery) -> NativeSweepRecord:
        with self.store.connection(create=False) as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_sweeps_v1'"
                ).fetchone()
                is None
            ):
                raise InvalidInputError("Native sweep has not been admitted")
            row = connection.execute(
                "SELECT document FROM native_sweeps_v1 WHERE sweep_id=?", (query.sweep_id,)
            ).fetchone()
            if row is None:
                raise InvalidInputError("Native sweep has not been admitted")
            return self._parse(row[0], query)

    def admitted(self, operation_id: str) -> bool:
        with self.store.connection(create=False) as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM admissions WHERE operation_id=?", (operation_id,)
                ).fetchone()
                is not None
            )


class NativeSweepSupervisor:
    def __init__(self, native: NativeOperationService) -> None:
        self.native = native
        self.store = NativeSweepStore(native.lifecycle.store)

    async def plan(self, request: NativeSweepRequest) -> NativeSweepPlanned:
        self.native.current()
        axis = next(
            (
                v
                for v in self.native.context.contracts.designs.variables(
                    request.template.design_id
                ).variables
                if v.logical_id == request.variable_id
            ),
            None,
        )
        if (
            axis is None
            or axis.mutation_policy != "owned_copy_only"
            or axis.range_status != "qualified"
        ):
            raise InvalidInputError("Native sweep axis requires a qualified mutable region")
        points = tuple(
            [
                (await self.native.plan(request.point_request(i))).plan
                for i in range(len(request.values))
            ]
        )
        plan = NativeSweepPlan(request=request, points=points)
        total = sum(p.request.result_reservation_bytes for p in points)
        if (
            len(points) > self.native.grant.attempt_limit
            or total > self.native.grant.result_reserved_bytes_limit
        ):
            raise InvalidInputError("Native sweep exceeds the operator scope")
        return NativeSweepPlanned(
            plan=plan,
            plan_sha256=plan.plan_sha256,
            point_count=len(points),
            result_reservation_bytes=total,
        )

    async def submit(self, submission: NativeSweepSubmission) -> NativeSweepStatus:
        self.native.current()
        # Admission fixes all child UUIDs before any dispatch. Submit never advances.
        try:
            record = self.store.read(submission)
        except InvalidInputError:
            planned = await self.plan(submission.request)
            record = self.store.admit(submission, planned.plan)
        if record.plan.request != submission.request:
            raise InvalidInputError("Native sweep request identity conflicts")
        return await self.status(submission)

    def _bound(self, query: NativeSweepQuery) -> NativeSweepRecord:
        self.native.current()
        record = self.store.read(query)
        plan = record.plan.points[0]
        context = self.native.context
        if (plan.resource_domain_sha256, plan.ledger_ref) != (
            context.resource_domain_sha256,
            context.binding.ledger_ref,
        ):
            raise InvalidInputError("Native sweep belongs to another resource domain")
        return record

    async def status(self, query: NativeSweepQuery) -> NativeSweepStatus:
        record = self._bound(query)
        points = []
        for i, (operation_id, plan) in enumerate(
            zip(record.operation_ids, record.plan.points, strict=True)
        ):
            phase = "NOT_RUN"
            if self.store.admitted(operation_id):
                observed = await self.native.observe(
                    NativeOperationQuery(
                        operation_id=operation_id, expected_plan_sha256=plan.plan_sha256
                    )
                )
                phase = observed.progress.phase
            points.append(
                dict(
                    index=i,
                    requested_value=record.plan.request.values[i],
                    operation_id=operation_id,
                    plan_sha256=plan.plan_sha256,
                    phase=phase,
                )
            )
        phases = [point["phase"] for point in points]
        state: Literal["PLANNED", "PARTIAL", "RUNNING", "STOPPED", "SUCCEEDED"] = "PARTIAL"
        if all(p == "SUCCEEDED" for p in phases):
            state = "SUCCEEDED"
        elif any(
            p in ("UNKNOWN_OUTCOME", "FAILED", "EXTRACTION_FAILED", "CANCELLED") for p in phases
        ):
            state = "STOPPED"
        elif any(p != "NOT_RUN" and p != "SUCCEEDED" for p in phases):
            state = "RUNNING"
        elif all(p == "NOT_RUN" for p in phases):
            state = "PLANNED"
        return NativeSweepStatus(
            sweep_id=record.sweep_id,
            plan_sha256=record.plan.plan_sha256,
            state=state,
            points=tuple(points),
        )

    async def advance(self, query: NativeSweepQuery) -> NativeSweepStatus:
        record = self._bound(query)
        status = await self.status(query)
        if status.state not in ("PLANNED", "PARTIAL"):
            return status
        for i, point in enumerate(status.points):
            if point["phase"] == "SUCCEEDED":
                continue
            if point["phase"] != "NOT_RUN":
                return status
            plan = record.plan.points[i]
            # Current authority must reproduce the exact saved plan; never adopt new
            # policy, grant, runner or input values on a partially completed sweep.
            fresh = await self.native.plan(plan.request)
            if fresh.plan != plan:
                raise InvalidInputError("Native sweep policy changed; new point admission denied")
            await self.native.observe(
                NativeOperationQuery(
                    operation_id=record.operation_ids[i], expected_plan_sha256=plan.plan_sha256
                ),
                plan.request,
                sweep_id=record.sweep_id,
            )
            break
        return await self.status(query)

    async def result(self, query: NativeSweepQuery) -> NativeSweepResult:
        record = self._bound(query)
        status = await self.status(query)
        if status.state != "SUCCEEDED":
            raise InvalidInputError("Native sweep results require all points to succeed")
        values = []
        for operation_id, plan in zip(record.operation_ids, record.plan.points, strict=True):
            result = await self.native.result(
                NativeOperationQuery(
                    operation_id=operation_id, expected_plan_sha256=plan.plan_sha256
                )
            )
            values.append(result.model_dump(mode="json"))
        output = dict(
            sweep_id=record.sweep_id,
            plan_sha256=record.plan.plan_sha256,
            variable_id=record.plan.request.variable_id,
            requested_values=list(record.plan.request.values),
            points=values,
            execution_authorized=False,
            budget_reset_or_refund=False,
        )
        if len(json.dumps(output, allow_nan=False).encode()) > 1048576:
            raise InvalidInputError(
                "Sweep aggregate exceeds bounded output; query individual points"
            )
        return NativeSweepResult.model_validate(output)
