"""Dedicated MCP ingress for host-enrolled analyses of a saved revision."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import Field, model_validator

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.amplifier_comparison_server import (
    load_retained_amp_comparison,
    register_retained_amp_comparison,
)
from cadence_mcp_bridge.candidate_cli import _PinnedComparisonFile, read_candidate_document
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeResult, _runtime_routes
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_service import (
    NativeOperationPlan,
    NativeOperationQuery,
    NativeOperationResult,
    NativeOperationService,
    NativeOperationStatus,
)
from cadence_mcp_bridge.operator_operations import OperationPlan
from cadence_mcp_bridge.runtime_context import ExecutionContext, select_context
from cadence_mcp_bridge.server import _stable_result
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)


class SavedAnalysisRevision(VariableModel):
    revision_sha256: Digest
    testbench_revision_sha256: Digest
    reconciled_netlist_sha256: Digest
    reconciliation_receipt_sha256: Digest
    registered_source_tree_sha256: Digest
    registered_ade_state_sha256: Digest


class _FixedAnalysis(VariableModel):
    identity: NativeOperationQuery
    plan: OperationPlan

    @model_validator(mode="after")
    def matches(self) -> _FixedAnalysis:
        if self.identity.expected_plan_sha256 != self.plan.plan_sha256:
            raise ValueError("fixed plan digest differs")
        return self


class FixedResearchAnalysisRegistration(VariableModel):
    schema_version: Literal[1]
    context_sha256: Digest
    revision: SavedAnalysisRevision
    saved_apply: _PinnedComparisonFile
    runtime_manifest: _PinnedComparisonFile
    runtime_registration: _PinnedComparisonFile
    analyses: Annotated[tuple[_FixedAnalysis, ...], Field(min_length=1, max_length=3)]
    comparison: _PinnedComparisonFile | None = None

    @model_validator(mode="after")
    def distinct(self) -> FixedResearchAnalysisRegistration:
        if len({entry.identity.operation_id for entry in self.analyses}) != len(self.analyses):
            raise ValueError("duplicate fixed operation")
        return self


class FixedResearchAnalysisPlan(ContractModel):
    operation: NativeOperationQuery
    plan: NativeOperationPlan
    revision: SavedAnalysisRevision


class FixedResearchAnalysisResult(ContractModel):
    revision: SavedAnalysisRevision
    result: NativeOperationResult


def _verified_runtime(
    context: ExecutionContext,
    registration: FixedResearchAnalysisRegistration,
) -> None:
    if context.context_sha256 != registration.context_sha256:
        raise ValueError("fixed analysis context differs")
    manifest = read_candidate_document(
        registration.runtime_manifest.path, expected_sha256=registration.runtime_manifest.sha256
    )
    compiled = read_candidate_document(
        registration.runtime_registration.path,
        expected_sha256=registration.runtime_registration.sha256,
    )
    revision = registration.revision
    saved = PmosDefaultChangeResult.model_validate_json(
        read_candidate_document(
            registration.saved_apply.path,
            expected_sha256=registration.saved_apply.sha256,
        )
    )
    if (
        saved.outcome != "VERIFIED"
        or saved.observed_revision_sha256 != revision.revision_sha256
        or saved.observed_testbench_revision_sha256 != revision.testbench_revision_sha256
        or saved.netlist_sha256 != revision.reconciled_netlist_sha256
        or saved.netlist_receipt_sha256 != revision.reconciliation_receipt_sha256
    ):
        raise ValueError("fixed analysis saved apply evidence differs")
    binding = context.binding
    for entry in registration.analyses:
        plan = entry.plan
        if (
            plan.resource_domain_sha256 != context.resource_domain_sha256
            or plan.runner_sha256 != binding.runner_sha256
            or plan.environment_sha256 != binding.environment_sha256
            or plan.design_sha256 != binding.design_sha256
            or plan.pdk_sha256 != binding.pdk_sha256
            or plan.ledger_ref != binding.ledger_ref
            or plan.grant_sha256 != binding.operator_grant_sha256
        ):
            raise ValueError("fixed analysis plan runtime differs")
        route = _runtime_routes(plan, manifest, compiled).get(
            (
                plan.request.design_id,
                plan.request.analysis_id,
            )
        )
        if route is None or route["analysis"] != plan.analysis:
            raise ValueError("fixed analysis route not registered")
        ade = route["ade"]
        if (
            ade["source_tree_sha256"] != revision.registered_source_tree_sha256
            or ade["ade_state_tree_sha256"] != revision.registered_ade_state_sha256
        ):
            raise ValueError("fixed analysis saved source or ADE state differs")


def create_fixed_research_analysis_server(
    config: BridgeConfig,
    path: Path,
    expected_sha256: str,
) -> MCPServer:
    try:
        context = select_context(config) if config.runtime_mode == "operator" else None
        if context is None:
            raise ValueError("fixed analysis needs a selected operator context")
        registration = FixedResearchAnalysisRegistration.model_validate_json(
            read_candidate_document(path, expected_sha256=expected_sha256)
        )
        _verified_runtime(context, registration)
        native = NativeOperationService(context)
        comparison_ref = registration.comparison
        comparison = (
            load_retained_amp_comparison(comparison_ref.path, comparison_ref.sha256)
            if comparison_ref is not None
            else None
        )
        enrolled = {item.identity.operation_id: item for item in registration.analyses}
        if comparison is not None:
            for mode, row in (("dc", comparison.dc), ("ac", comparison.ac)):
                identity = row.candidate.operation
                entry = enrolled.get(identity.operation_id)
                if entry is None or entry.identity != identity or entry.plan.analysis != mode:
                    raise ValueError("comparison does not bind the enrolled candidate analyses")
    except (KeyError, OSError, TypeError, ValueError, ConfigurationError):
        raise ConfigurationError("Fixed research analysis registration rejected") from None

    server = MCPServer(
        name="cadence-fixed-research-analysis", version=__version__, log_level="WARNING"
    )
    if comparison is not None:
        register_retained_amp_comparison(server, comparison)

    def select(request: NativeOperationQuery) -> _FixedAnalysis:
        entry = enrolled.get(request.operation_id)
        if entry is None or entry.identity != request:
            raise ToolError("fixed_research_analysis_identity_rejected")
        return entry

    async def checked_plan(request: NativeOperationQuery) -> FixedResearchAnalysisPlan:
        entry = select(request)
        planned = await native.plan(entry.plan.request)
        if planned.plan != entry.plan or planned.plan_sha256 != request.expected_plan_sha256:
            raise ConfigurationError("Fixed research analysis plan differs")
        return FixedResearchAnalysisPlan(
            operation=request, plan=planned, revision=registration.revision
        )

    @server.tool(annotations=_READ, structured_output=True)
    async def cadence_plan_fixed_research_analysis(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, FixedResearchAnalysisPlan]:
        select(request)
        return await _stable_result(checked_plan(request))

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        structured_output=True,
        description="Submit the host-enrolled analysis or look up an existing operation ID.",
    )
    async def cadence_submit_fixed_research_analysis(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        entry = select(request)
        return await _stable_result(native.observe(request, entry.plan.request))

    @server.tool(annotations=_READ, structured_output=True)
    async def cadence_fixed_research_analysis_status(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        select(request)
        return await _stable_result(native.observe(request))

    async def identified_result(request: NativeOperationQuery) -> FixedResearchAnalysisResult:
        result = await native.result(request)
        return FixedResearchAnalysisResult(revision=registration.revision, result=result)

    @server.tool(annotations=_READ, structured_output=True)
    async def cadence_fixed_research_analysis_result(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, FixedResearchAnalysisResult]:
        select(request)
        return await _stable_result(identified_result(request))

    return server
