"""Dedicated MCP ingress for host-enrolled analyses of a saved revision."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import Field, model_validator

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.amplifier_comparison_server import (
    RetainedAmpComparisonQuery,
    _RetainedReport,
    project_retained_amp_comparison,
    register_retained_amp_comparison,
    requires_amp_terminal_custody,
)
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.candidate_cli import (
    _PinnedComparisonFile,
    read_candidate_document,
    verify_fresh_amplifier_comparison,
)
from cadence_mcp_bridge.candidate_execution import (
    PmosDefaultChangeResult,
    _fresh_amplifier_metric,
    _runtime_routes,
)
from cadence_mcp_bridge.candidate_reports import candidate_metric_delta
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_service import (
    NativeOperationPlan,
    NativeOperationQuery,
    NativeOperationResult,
    NativeOperationService,
    NativeOperationStatus,
)
from cadence_mcp_bridge.operator_operations import OperationPlan
from cadence_mcp_bridge.result_reports import ReportConditions
from cadence_mcp_bridge.runtime_context import ExecutionContext, select_context
from cadence_mcp_bridge.server import _stable_result
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_READ_EXTERNAL = ToolAnnotations(read_only_hint=True, open_world_hint=True)


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
    source_observation: _PinnedComparisonFile
    export_receipt: _PinnedComparisonFile
    runtime_manifest: _PinnedComparisonFile
    runtime_registration: _PinnedComparisonFile
    analyses: Annotated[tuple[_FixedAnalysis, ...], Field(min_length=1, max_length=3)]
    comparison: _PinnedComparisonFile | None = None
    comparison_request: _PinnedComparisonFile | None = None

    @model_validator(mode="after")
    def distinct(self) -> FixedResearchAnalysisRegistration:
        if len({entry.identity.operation_id for entry in self.analyses}) != len(self.analyses):
            raise ValueError("duplicate fixed operation")
        if self.comparison is None and self.comparison_request is not None:
            raise ValueError("comparison request requires an enrolled comparison")
        return self


class FixedResearchAnalysisPlan(ContractModel):
    operation: NativeOperationQuery
    plan: NativeOperationPlan
    revision: SavedAnalysisRevision


class FixedResearchAnalysisResult(ContractModel):
    revision: SavedAnalysisRevision
    result: NativeOperationResult


class _ComparisonRow(VariableModel):
    unit: Literal["W", "dB"]
    baseline_operation: NativeOperationQuery
    baseline_value: float
    candidate_operation: NativeOperationQuery
    candidate_status: Literal["FAILED", "SUCCEEDED", "NOT_RUN"]
    candidate_value: float | None
    absolute_delta: float | None


class _PartialComparison(VariableModel):
    report_sha256: Digest
    dc: _ComparisonRow
    ac: _ComparisonRow
    selected_candidate_id: Literal[None] = None
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def _partial_projection(report: _RetainedReport, digest: str) -> _PartialComparison:
    rows = {}
    for row in (report.association.dc, report.association.ac):
        baseline, candidate = row.baseline, row.candidate
        if (
            baseline.status != "SUCCEEDED" or baseline.value is None
            or baseline.operation is None or candidate.operation is None
            or candidate.status not in ("SUCCEEDED", "FAILED", "NOT_RUN")
            or (candidate.value is None) != (candidate.status != "SUCCEEDED")
        ):
            raise ValueError("partial comparison requires terminal rows")
        delta, _, reason = candidate_metric_delta(
            candidate.value, baseline.value, baseline_present=True,
        )
        if report.deltas.get(row.analysis) != {
            "absolute_delta": delta,
            "reason": reason,
        }:
            raise ValueError("partial comparison delta mismatch")
        rows[row.analysis] = _ComparisonRow(
            unit=row.unit, baseline_operation=baseline.operation, baseline_value=baseline.value,
            candidate_operation=candidate.operation, candidate_status=candidate.status,
            candidate_value=candidate.value, absolute_delta=delta,
        )
    return _PartialComparison(report_sha256=digest, dc=rows["dc"], ac=rows["ac"])


def _verified_runtime(
    context: ExecutionContext,
    registration: FixedResearchAnalysisRegistration,
) -> tuple[PmosDefaultChangeResult, dict[tuple[str, str], dict[str, Any]]]:
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
    observation = json.loads(
        read_candidate_document(
            registration.source_observation.path,
            expected_sha256=registration.source_observation.sha256,
        )
    )
    export = json.loads(
        read_candidate_document(
            registration.export_receipt.path,
            expected_sha256=registration.export_receipt.sha256,
        )
    )
    source = observation["source"]
    if (
        observation["status"] != "RESEARCH_1124_LIVE_READ_ONLY"
        or source["view_tree"] != saved.observed_revision_sha256
        or source["input_sha256"] != saved.netlist_sha256
        or export["status"] != "RESEARCH_1124_INPUTS_EXPORTED"
        or export["preflight_sha256"] != registration.source_observation.sha256
        or export["saved_view_tree_sha256"] != source["view_tree"]
        or export["saved_view_content_sha256"] != source["view_content"]
        or export["copied_view_content_sha256"] != source["view_content"]
        or export["source_library_content_sha256"] != source["library_content"]
        or export["copied_library_content_sha256"] != source["library_content"]
        or any(
            type(export[key]) is not int or export[key] != 0
            for key in ("ocean_calls", "simulations", "reservations")
        )
    ):
        raise ValueError("fixed analysis export does not preserve the observed saved circuit")
    routes = _runtime_routes(registration.analyses[0].plan, manifest, compiled)
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
        route = routes.get(
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
            or (route["source_cell"], ade["source_tree_sha256"])
            != (export["source_cell"], export["source_cell_sha256"])
            or (route["source_state"], ade["ade_state_tree_sha256"])
            != (export["source_state"], export["source_state_sha256"])
        ):
            raise ValueError("fixed analysis saved source or ADE state differs")
    return saved, routes


def _check_comparison(
    context: ExecutionContext,
    document: _RetainedReport,
    saved: PmosDefaultChangeResult,
    enrolled: dict[str, _FixedAnalysis],
    routes: dict[tuple[str, str], dict[str, Any]],
) -> None:
    pair = document.association
    readback = pair.readback
    if (
        readback.status != "MATCHED"
        or pair.change_plan_sha256 != saved.plan_sha256
        or readback.plan_sha256 != saved.plan_sha256
        or readback.reopened is None
        or readback.netlist is None
        or readback.reopened.revision != saved.candidate_revision
        or readback.netlist.revision != saved.candidate_revision
        or readback.reopened.revision_sha256 != saved.observed_revision_sha256
        or readback.reopened.testbench_revision_sha256 != saved.observed_testbench_revision_sha256
        or readback.reopened.artifact_sha256 != saved.reopen_receipt_sha256
        or readback.netlist.revision_sha256 != saved.observed_revision_sha256
        or readback.netlist.testbench_revision_sha256 != saved.observed_testbench_revision_sha256
        or readback.netlist.artifact_sha256 != saved.netlist_sha256
    ):
        raise ValueError("comparison readback does not match the saved revision")
    journal = AnalysisStore(context.binding.analysis_journal)
    with journal.connection(create=False, read_only=True) as connection:
        for row in (pair.dc, pair.ac):
            candidate = row.candidate
            identity = candidate.operation
            report = candidate.report
            if identity is None:
                raise ValueError("comparison candidate evidence missing")
            # A failed predecessor DC has no input or result to publish. The
            # enrolled comparison request must also rederive this exact record.
            if (
                row.analysis == "dc" and candidate.status == "FAILED"
                and saved.candidate_revision.revision_id == "amp-pm0-user-mcp-1123-r1"
            ):
                record = AnalysisStore._read_operation(connection, identity.operation_id)
                if (
                    record.progress.phase != "FAILED" or record.plan.analysis != "dc"
                    or record.plan.request.design_id != "amp-pm0-auto120-5656"
                    or record.plan.plan_sha256 != identity.expected_plan_sha256
                    or candidate.terminal_sha256 is None or report is not None
                    or candidate.value is not None
                    or record.progress.provider_receipt_sha256 != candidate.terminal_sha256
                ):
                    raise ValueError("failed DC evidence differs")
                continue
            entry = enrolled.get(identity.operation_id)
            if entry is None or entry.identity != identity or entry.plan.analysis != row.analysis:
                raise ValueError("comparison candidate analysis differs")
            if (
                row.analysis == "ac" and candidate.status == "NOT_RUN"
                and pair.dc.candidate.status == "FAILED"
                and saved.candidate_revision.revision_id == "amp-pm0-user-mcp-1123-r1"
            ):
                admitted = connection.execute(
                    "SELECT 1 FROM admissions WHERE operation_id=?", (identity.operation_id,)
                ).fetchone()
                if (
                    admitted or report is not None or candidate.value is not None
                    or candidate.terminal_sha256 is not None
                ):
                    raise ValueError("unsubmitted AC differs from the enrolled journal")
                continue
            if report is None:
                raise ValueError("comparison candidate report missing")
            record = AnalysisStore._read_operation(connection, identity.operation_id)
            route = routes[(entry.plan.request.design_id, entry.plan.request.analysis_id)]
            ade = AdeExecutionRegistration.model_validate_json(json.dumps(route["ade"]))
            reader = GenericReaderRegistration.model_validate_json(json.dumps(route["reader"]))
            conditions = ReportConditions(
                analysis_inputs=ade.inputs,
                source_tree_sha256=ade.source_tree_sha256,
                ade_state_tree_sha256=ade.ade_state_tree_sha256,
                static_statements_sha256=ade.static_statements_sha256,
                model_file_sha256=tuple(model.file_sha256 for model in ade.model_includes),
                transfer=reader.transfer,
            )
            value = _fresh_amplifier_metric(report, reader, ade)
            if (
                record.plan != entry.plan
                or record.progress.phase != "SUCCEEDED"
                or candidate.terminal_sha256 is None
                or candidate.terminal_sha256 != record.progress.provider_receipt_sha256
                or report.operation_id != identity.operation_id
                or report.plan != entry.plan
                or report.reader_registration_sha256 != canonical_digest(reader)
                or report.measurement_id != reader.measurement_id
                or report.analysis_conditions != conditions
                or value is None
                or value != candidate.value
            ):
                raise ValueError("comparison terminal, native conditions or value differs")


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
        saved, routes = _verified_runtime(context, registration)
        comparison_ref = registration.comparison
        comparison = None
        partial = None
        enrolled = {item.identity.operation_id: item for item in registration.analyses}
        if comparison_ref is not None:
            raw = read_candidate_document(
                comparison_ref.path, expected_sha256=comparison_ref.sha256,
            )
            document = _RetainedReport.model_validate_json(raw)
            needs_custody = (
                saved.candidate_revision.revision_id == "amp-pm0-user-mcp-1123-r1"
                or requires_amp_terminal_custody(document.association)
            )
            if needs_custody != (registration.comparison_request is not None):
                raise ValueError("Fixed comparison terminal enrollment differs")
            _check_comparison(context, document, saved, enrolled, routes)
            if registration.comparison_request is not None:
                verify_fresh_amplifier_comparison(
                    registration.comparison_request, config.runtime_settings_path, context, raw,
                )
            if (
                registration.comparison_request is not None
                and document.association.dc.candidate.status == "FAILED"
            ):
                partial = _partial_projection(document, comparison_ref.sha256)
            else:
                comparison = project_retained_amp_comparison(document, comparison_ref.sha256)
        native = NativeOperationService(context)
    except (KeyError, OSError, TypeError, ValueError, ConfigurationError, InvalidInputError):
        raise ConfigurationError("Fixed research analysis registration rejected") from None

    server = MCPServer(
        name="cadence-fixed-research-analysis", version=__version__, log_level="WARNING"
    )
    if partial is not None:
        summary = partial

        @server.tool(
            name="cadence_retained_amplifier_comparison", annotations=_READ, structured_output=True,
            description="Read the enrolled AMP comparison including the retained failed DC.",
        )
        def retained_partial(request: RetainedAmpComparisonQuery) -> _PartialComparison:
            if request.expected_report_sha256 != summary.report_sha256:
                raise ToolError("Retained amplifier comparison digest differs")
            return summary

        return server
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
            read_only_hint=False, idempotent_hint=True, open_world_hint=True
        ),
        structured_output=True,
        description="Submit the host-enrolled analysis or look up an existing operation ID.",
    )
    async def cadence_submit_fixed_research_analysis(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        entry = select(request)
        # Under its resource lock, the stock lifecycle checks durable replay
        # first, then replans and verifies the expected SHA before fresh admit.
        return await _stable_result(native.observe(request, entry.plan.request))

    @server.tool(annotations=_READ_EXTERNAL, structured_output=True)
    async def cadence_fixed_research_analysis_status(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        select(request)
        return await _stable_result(native.observe(request))

    async def identified_result(request: NativeOperationQuery) -> FixedResearchAnalysisResult:
        result = await native.result(request)
        return FixedResearchAnalysisResult(revision=registration.revision, result=result)

    @server.tool(annotations=_READ_EXTERNAL, structured_output=True)
    async def cadence_fixed_research_analysis_result(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, FixedResearchAnalysisResult]:
        select(request)
        return await _stable_result(identified_result(request))

    return server
