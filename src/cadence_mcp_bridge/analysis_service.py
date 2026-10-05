"""Registered lifecycle adapter around the existing fixed native guard boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Protocol

from cadence_mcp_bridge.analyses import (
    AnalysisCancellation,
    AnalysisJobQuery,
    AnalysisList,
    AnalysisPlan,
    AnalysisResult,
    AnalysisSelection,
    AnalysisStatus,
    AnalysisSubmission,
)
from cadence_mcp_bridge.analysis_store import AnalysisStore, default_analysis_journal
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.models import JobState
from cadence_mcp_bridge.native_diagnostics import (
    OPERATING_POINT,
    REVISION,
    NativeDiagnosticRequest,
    NativeDiagnosticResult,
    NativeDiagnosticStatus,
    NativeSettings,
)


class NativeOperations(Protocol):
    async def submit_native_diagnostic(
        self, request: NativeDiagnosticRequest
    ) -> NativeDiagnosticStatus: ...
    async def native_diagnostic_status(
        self, job_id: str, analysis: str
    ) -> NativeDiagnosticStatus: ...
    async def native_diagnostic_result(
        self, job_id: str, analysis: str
    ) -> NativeDiagnosticResult: ...


class AnalysisSupervisor:
    def __init__(
        self, operations: NativeOperations, registry: RegistryBase, journal: Path | None
    ) -> None:
        self.operations = operations
        self.registry = registry
        self.store = AnalysisStore(default_analysis_journal() if journal is None else journal)

    def plan(self, selection: AnalysisSelection) -> AnalysisPlan:
        contracts = self.registry.analyses_for(selection.design_id)
        contract = next((c for c in contracts if c.analysis_id == selection.analysis_id), None)
        if contract is None:
            raise InvalidInputError("Analysis ID is not registered for this design")
        data = {
            "protocol": "registered-native-admission-v1",
            "contract": contract.model_dump(mode="json"),
        }
        plan_hash = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        eligible = contract.adapter_kind == "native-fixed-reference-v1"
        return AnalysisPlan(
            design_id=selection.design_id,
            analysis_id=selection.analysis_id,
            analysis=contract.analysis,
            plan_hash=plan_hash,
            dispatch_eligible=eligible,
            qualification_scope="fixed_native_compatibility" if eligible else "unqualified",
            blocking_reason=None if eligible else "adapter_unqualified",
            input_policy=contract.input_policy,
            fixed_settings=NativeSettings() if eligible else None,
        )

    def listing(self, design_id: str) -> AnalysisList:
        profile = self.registry.profile(design_id)
        return AnalysisList(
            design_id=design_id,
            declared_analyses=profile.allowed_analyses,
            analyses=tuple(
                self.plan(AnalysisSelection(design_id=design_id, analysis_id=c.analysis_id))
                for c in self.registry.analyses_for(design_id)
            ),
        )

    def executable(self, query: AnalysisJobQuery) -> AnalysisPlan:
        plan = self.plan(
            AnalysisSelection(design_id=query.design_id, analysis_id=query.analysis_id)
        )
        if not plan.dispatch_eligible:
            raise InvalidInputError("Registered analysis adapter is unqualified")
        return plan

    async def submit(self, submission: AnalysisSubmission) -> AnalysisStatus:
        plan = self.executable(submission)
        if submission.expected_plan_hash != plan.plan_hash:
            raise InvalidInputError("Analysis plan does not match the current registered contract")
        first = await asyncio.to_thread(
            self.store.admit,
            submission.operation_id,
            submission.design_id,
            submission.analysis_id,
            plan.plan_hash,
        )
        if first:
            native = await self.operations.submit_native_diagnostic(
                NativeDiagnosticRequest(
                    operation_id=submission.operation_id,
                    revision_id=REVISION,
                    operating_point_id=OPERATING_POINT,
                    analysis=plan.analysis,
                )
            )
        else:
            # A crash/timeout/cancelled coroutine may have sent. Lookup only, even if absent.
            native = await self.operations.native_diagnostic_status(
                submission.operation_id, plan.analysis
            )
        return self.status_envelope(submission, plan, native)

    async def admitted(self, query: AnalysisJobQuery) -> AnalysisPlan:
        plan = self.executable(query)
        await asyncio.to_thread(
            self.store.require,
            query.operation_id,
            query.design_id,
            query.analysis_id,
            plan.plan_hash,
        )
        return plan

    @staticmethod
    def status_envelope(
        query: AnalysisJobQuery, plan: AnalysisPlan, native: NativeDiagnosticStatus
    ) -> AnalysisStatus:
        if str(native.job_id) != query.operation_id or native.analysis != plan.analysis:
            raise RemoteFailureError("Registered analysis status identity mismatch")
        return AnalysisStatus(
            design_id=query.design_id,
            analysis_id=query.analysis_id,
            operation_id=query.operation_id,
            plan_hash=plan.plan_hash,
            native=native,
        )

    async def status(self, query: AnalysisJobQuery) -> AnalysisStatus:
        plan = await self.admitted(query)
        native = await self.operations.native_diagnostic_status(query.operation_id, plan.analysis)
        return self.status_envelope(query, plan, native)

    async def result(self, query: AnalysisJobQuery) -> AnalysisResult:
        plan = await self.admitted(query)
        native = await self.operations.native_diagnostic_result(query.operation_id, plan.analysis)
        if str(native.job_id) != query.operation_id or native.analysis != plan.analysis:
            raise RemoteFailureError("Registered analysis result identity mismatch")
        return AnalysisResult(
            design_id=query.design_id,
            analysis_id=query.analysis_id,
            operation_id=query.operation_id,
            plan_hash=plan.plan_hash,
            native=native,
        )

    async def cancel(self, query: AnalysisJobQuery) -> AnalysisCancellation:
        status = await self.status(query)
        terminal = status.native.state in (JobState.SUCCEEDED, JobState.FAILED)
        # There is no qualified native process-cancellation route. Never call generic kill/cancel.
        return AnalysisCancellation(
            status=status,
            outcome="terminal_noop" if terminal else "unsupported_active_cancellation",
        )
