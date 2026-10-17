"""Explicit sequential candidates over the retained native lifecycle and journal.

Submission fixes a manifest only. Advance submits at most one untouched child;
status, results and retries cannot create a simulation or another accounting domain.
The explicit experimental operator workflow is the only caller; no public MCP tool
installs this coordinator.
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from cadence_mcp_bridge.analysis_store import MAX_RECORDS, AnalysisStore
from cadence_mcp_bridge.candidate_contracts import (
    CandidateBatchPlan,
    CandidateBatchRequest,
    prepare_candidate_plan,
)
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError, InvalidInputError
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel


class CandidateBatchQuery(VariableModel):
    batch_id: OperationId
    expected_plan_sha256: Digest


class CandidateBatchSubmission(CandidateBatchQuery):
    request: CandidateBatchRequest


class CandidateBatchStatus(VariableModel):
    batch_id: OperationId
    plan_sha256: Digest
    state: Literal["PLANNED", "PARTIAL", "RUNNING", "STOPPED", "SUCCEEDED"]
    candidates: tuple[dict[str, Any], ...]
    simulation_retry: Literal[False] = False
    budget_reset_or_refund: Literal[False] = False


class CandidateBatchResult(VariableModel):
    batch_id: OperationId
    plan_sha256: Digest
    state: Literal["PLANNED", "PARTIAL", "RUNNING", "STOPPED", "SUCCEEDED"]
    candidates: tuple[dict[str, Any], ...]
    qualification: Literal["REGISTERED_CHILD_RESULTS_NOT_GENERIC_CANDIDATE_QUALIFICATION"] = (
        "REGISTERED_CHILD_RESULTS_NOT_GENERIC_CANDIDATE_QUALIFICATION"
    )
    new_simulations: Literal[0] = 0
    new_extractions: Literal[0] = 0


class CandidateBatchStore:
    """Additive manifest in the existing AnalysisStore; no second job database."""

    def __init__(self, store: AnalysisStore) -> None:
        self.store = store

    @staticmethod
    def _parse(raw: str, query: CandidateBatchQuery) -> CandidateBatchPlan:
        try:
            if not isinstance(raw, str) or len(raw) > 524288:
                raise ValueError("size")
            plan = CandidateBatchPlan.model_validate_json(raw)
            if (plan.request.batch_id, plan.plan_sha256) != (
                query.batch_id, query.expected_plan_sha256,
            ):
                raise ValueError("identity")
            return plan
        except ValueError:
            raise InvalidInputError("Candidate batch checkpoint identity is invalid") from None

    def admit(self, query: CandidateBatchQuery, plan: CandidateBatchPlan) -> CandidateBatchPlan:
        plan = CandidateBatchPlan.model_validate_json(plan.model_dump_json())
        if (query.batch_id, query.expected_plan_sha256) != (
            plan.request.batch_id, plan.plan_sha256,
        ):
            raise InvalidInputError("Candidate batch differs from the reviewed plan")
        raw = plan.model_dump_json()
        if len(raw) > 524288:
            raise ConfigurationError("Candidate batch plan exceeds journal capacity")
        with self.store.connection(create=True) as connection:
            self.store._lifecycle_capacity(connection)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS candidate_batches_v1 "
                "(batch_id TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT document FROM candidate_batches_v1 WHERE batch_id=?", (query.batch_id,)
            ).fetchone()
            if row is not None:
                existing = self._parse(row[0], query)
                if existing != plan:
                    raise InvalidInputError("Candidate batch immutable plan conflicts")
                return existing
            if connection.execute("SELECT COUNT(*) FROM candidate_batches_v1").fetchone()[0] >= (
                MAX_RECORDS
            ):
                raise ConfigurationError("Candidate batch journal capacity reached")
            identities = (query.batch_id, *(c.operation_id for c in plan.request.candidates))
            if any(not self.store.native_sweep_identity_available(connection, identity)
                   for identity in identities):
                raise InvalidInputError("Candidate batch identity conflicts with a reserved ID")
            connection.execute(
                "INSERT INTO candidate_batches_v1 VALUES (?,?)", (query.batch_id, raw)
            )
            return plan

    def read(self, query: CandidateBatchQuery) -> CandidateBatchPlan:
        with self.store.connection(create=False) as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_batches_v1'"
            ).fetchone() is None:
                raise InvalidInputError("Candidate batch has not been admitted")
            row = connection.execute(
                "SELECT document FROM candidate_batches_v1 WHERE batch_id=?", (query.batch_id,)
            ).fetchone()
            if row is None:
                raise InvalidInputError("Candidate batch has not been admitted")
            return self._parse(row[0], query)

    def admitted(self, operation_id: str) -> bool:
        with self.store.connection(create=False) as connection:
            return connection.execute(
                "SELECT 1 FROM admissions WHERE operation_id=?", (operation_id,)
            ).fetchone() is not None


class CandidateBatchSupervisor:
    def __init__(self, native: NativeOperationService) -> None:
        self.native = native
        self.store = CandidateBatchStore(native.lifecycle.store)

    async def plan(self, request: CandidateBatchRequest) -> CandidateBatchPlan:
        self.native.current()
        return prepare_candidate_plan(
            self.native.context, self.native.grant, self.native.grant_sha256,
            request, int(time.time()),
        )

    async def submit(self, submission: CandidateBatchSubmission) -> CandidateBatchStatus:
        self.native.current()
        try:
            plan = self.store.read(submission)
        except InvalidInputError:
            plan = self.store.admit(submission, await self.plan(submission.request))
        if plan.request != submission.request:
            raise InvalidInputError("Candidate batch request identity conflicts")
        return await self.status(submission)

    def _bound(self, query: CandidateBatchQuery) -> CandidateBatchPlan:
        self.native.current()
        plan = self.store.read(query)
        first = plan.plans[0]
        if (first.resource_domain_sha256, first.ledger_ref) != (
            self.native.context.resource_domain_sha256, self.native.context.binding.ledger_ref,
        ):
            raise InvalidInputError("Candidate batch belongs to another resource domain")
        return plan

    async def status(self, query: CandidateBatchQuery) -> CandidateBatchStatus:
        plan = self._bound(query)
        candidates = []
        for candidate, point in zip(plan.request.candidates, plan.plans, strict=True):
            phase = "NOT_RUN"
            if self.store.admitted(candidate.operation_id):
                observed = await self.native.observe(NativeOperationQuery(
                    operation_id=candidate.operation_id, expected_plan_sha256=point.plan_sha256,
                ))
                phase = observed.progress.phase
            candidates.append({
                "candidate_id": candidate.candidate_id, "label": candidate.label,
                "operation_id": candidate.operation_id, "plan_sha256": point.plan_sha256,
                "phase": phase,
            })
        phases = [candidate["phase"] for candidate in candidates]
        state: Literal["PLANNED", "PARTIAL", "RUNNING", "STOPPED", "SUCCEEDED"] = "PARTIAL"
        if all(phase == "SUCCEEDED" for phase in phases):
            state = "SUCCEEDED"
        elif any(phase in ("UNKNOWN_OUTCOME", "FAILED", "EXTRACTION_FAILED", "CANCELLED")
                 for phase in phases):
            state = "STOPPED"
        elif any(phase not in ("NOT_RUN", "SUCCEEDED") for phase in phases):
            state = "RUNNING"
        elif all(phase == "NOT_RUN" for phase in phases):
            state = "PLANNED"
        return CandidateBatchStatus(
            batch_id=query.batch_id, plan_sha256=plan.plan_sha256,
            state=state, candidates=tuple(candidates),
        )

    async def advance(self, query: CandidateBatchQuery) -> CandidateBatchStatus:
        plan = self._bound(query)
        status = await self.status(query)
        if status.state not in ("PLANNED", "PARTIAL"):
            return status
        for candidate, point, observed in zip(
            plan.request.candidates, plan.plans, status.candidates, strict=True,
        ):
            if observed["phase"] == "SUCCEEDED":
                continue
            if observed["phase"] != "NOT_RUN":
                return status
            fresh = await self.plan(plan.request)
            if fresh != plan:
                raise InvalidInputError("Candidate batch policy changed; new admission denied")
            await self.native.observe(
                NativeOperationQuery(
                    operation_id=candidate.operation_id, expected_plan_sha256=point.plan_sha256,
                ), point.request, candidate_batch_id=query.batch_id,
            )
            break
        return await self.status(query)

    async def result(self, query: CandidateBatchQuery) -> CandidateBatchResult:
        plan = self._bound(query)
        status = await self.status(query)
        candidates = []
        for candidate, point, observed in zip(
            plan.request.candidates, plan.plans, status.candidates, strict=True,
        ):
            result = None
            reason = observed["phase"]
            if observed["phase"] == "SUCCEEDED":
                try:
                    result = (await self.native.result(NativeOperationQuery(
                        operation_id=candidate.operation_id,
                        expected_plan_sha256=point.plan_sha256,
                    ))).model_dump(mode="json")
                    reason = None
                except BridgeError:
                    # A missing/unavailable retained result does not erase this
                    # candidate or authorize extraction, replacement or retry.
                    reason = "RETAINED_RESULT_UNAVAILABLE"
            candidates.append({
                "candidate_id": candidate.candidate_id, "label": candidate.label,
                "operation_id": candidate.operation_id, "plan_sha256": point.plan_sha256,
                "phase": observed["phase"], "result": result,
                "result_unavailable_reason": reason,
            })
        output = {"batch_id": query.batch_id, "plan_sha256": plan.plan_sha256,
                  "state": status.state, "candidates": candidates}
        if len(json.dumps(output, allow_nan=False).encode()) > 1048576:
            raise InvalidInputError("Candidate aggregate exceeds bounded output; query children")
        return CandidateBatchResult.model_validate_json(json.dumps(output))
