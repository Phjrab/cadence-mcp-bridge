"""MCP and operator CLI over one host-registered research generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.candidate_cli import (
    _export_research,
    _output,
    _reserved,
    read_candidate_document,
)
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_circuit import MosBlockHandoffPins, MosBlockRegistrationHandoff
from cadence_mcp_bridge.research_generation_service import (
    RegisteredResearchGeneration,
    ResearchGenerationBinding,
    ResearchGenerationQuery,
    ResearchGenerationStatus,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext, select_context
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
)

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_REJECTED = "registered_research_generation_rejected"


class RegisteredGenerationPlan(VariableModel):
    identity: ResearchGenerationQuery
    plan_sha256: Digest
    bench_plan_sha256: Digest
    conditions_sha256: Digest
    scope_sha256: Digest
    output_library: BindingName
    execution_authorized: Literal[False] = False


class RegisteredGenerationHandoff(VariableModel):
    identity: ResearchGenerationQuery
    binding: RevisionBinding
    source_tree_sha256: Digest
    bench_tree_sha256: Digest
    static_statements_sha256: Digest
    handoff_sha256: Digest
    pins: MosBlockHandoffPins
    provenance: Literal["OPERATOR_AUTHENTICATION_REQUIRED"] = "OPERATOR_AUTHENTICATION_REQUIRED"
    execution_authorized: Literal[False] = False


def _load(
    config: BridgeConfig,
    path: Path,
    digest: str,
) -> tuple[ExecutionContext, ResearchGenerationBinding, RegisteredResearchGeneration]:
    from cadence_mcp_bridge.research_generation_provider import registered_research_generation

    try:
        context = select_context(config) if config.runtime_mode == "operator" else None
        if context is None:
            raise ValueError("a selected operator context is required")
        raw = read_candidate_document(path, expected_sha256=digest)
        binding = ResearchGenerationBinding.model_validate_json(
            json.dumps(json.loads(raw)["binding"])
        )
        directory = path.resolve(strict=True).parent
        if any(
            protected.resolve().is_relative_to(directory)
            for protected in (
                context.binding.analysis_journal,
                context.binding.sweep_journal,
                context.lock_path,
            )
        ):
            raise ValueError(
                "registered generation evidence directory collides with operator state"
            )
        return context, binding, registered_research_generation(context, raw, directory)
    except (OSError, KeyError, TypeError, ValueError, BridgeError):
        raise ConfigurationError("Registered research generation is unavailable") from None


def _plan(
    binding: ResearchGenerationBinding,
    request: ResearchGenerationQuery,
) -> RegisteredGenerationPlan:
    if (
        request.operation_id != binding.operation_id
        or request.expected_binding_sha256 != canonical_digest(binding)
    ):
        raise OperationRejected("research_generation_query_mismatch")
    return RegisteredGenerationPlan(
        identity=request,
        plan_sha256=binding.plan_sha256,
        bench_plan_sha256=binding.bench_plan_sha256,
        conditions_sha256=binding.conditions_sha256,
        scope_sha256=binding.scope_sha256,
        output_library=binding.output_library,
    )


def _handoff_summary(
    request: ResearchGenerationQuery,
    handoff: MosBlockRegistrationHandoff,
) -> RegisteredGenerationHandoff:
    return RegisteredGenerationHandoff(
        identity=request,
        binding=handoff.binding,
        source_tree_sha256=handoff.source_tree_sha256,
        bench_tree_sha256=handoff.bench_tree_sha256,
        static_statements_sha256=handoff.static_statements_sha256,
        handoff_sha256=handoff.handoff_sha256,
        pins=handoff.pins,
    )


def register_research_generation_tools(
    server: MCPServer,
    binding: ResearchGenerationBinding,
    service: RegisteredResearchGeneration,
) -> None:
    @server.tool(
        annotations=_READ,
        structured_output=True,
        description="Read exact registered generation plan, bench and scope identities.",
    )
    def cadence_plan_registered_research_generation(
        request: ResearchGenerationQuery,
    ) -> RegisteredGenerationPlan:
        try:
            return _plan(binding, request)
        except OperationRejected:
            raise ToolError(_REJECTED) from None

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=True,
        ),
        structured_output=True,
        description="Apply one operator-registered research generation or replay its existing ID.",
    )
    def cadence_apply_registered_research_generation(
        request: ResearchGenerationQuery,
    ) -> ResearchGenerationStatus:
        try:
            return service.submit(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_registered_research_generation_status(
        request: ResearchGenerationQuery,
    ) -> ResearchGenerationStatus:
        try:
            return service.status(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(
        annotations=_READ,
        structured_output=True,
        description="Read verified generation handoff digests for operator registration.",
    )
    def cadence_registered_research_generation_handoff(
        request: ResearchGenerationQuery,
    ) -> RegisteredGenerationHandoff:
        try:
            return _handoff_summary(request, service.registration_handoff(request))
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None


def create_research_generation_server(config: BridgeConfig, path: Path, digest: str) -> MCPServer:
    _, binding, service = _load(config, path, digest)
    server = MCPServer(
        name="cadence-registered-research-generation",
        version=__version__,
        log_level="WARNING",
    )
    register_research_generation_tools(server, binding, service)
    return server


def run_registered_generation(arguments: argparse.Namespace) -> int:
    try:
        registered_path, registered_digest = arguments.registration
        request_path, request_digest = arguments.request
        action = arguments.generation_action
        request = ResearchGenerationQuery.model_validate_json(
            read_candidate_document(Path(request_path), expected_sha256=request_digest)
        )
        config = BridgeConfig(runtime_mode="operator")
        context, binding, service = _load(config, Path(registered_path), registered_digest)
        if action == "plan":
            result = _plan(binding, request).model_dump(mode="json")
        elif action == "apply":
            result = service.submit(request).model_dump(mode="json")
        elif action == "status":
            result = service.status(request).model_dump(mode="json")
        else:
            handoff = service.registration_handoff(request)
            output = arguments.output.resolve()
            if output.is_relative_to(Path(registered_path).resolve().parent):
                raise ValueError("handoff export must be outside the evidence directory")
            settings = config.runtime_settings_path
            if settings is None:
                raise ConfigurationError("Operator settings are required for handoff export")
            _output(arguments.output, _reserved(settings, (context,)))
            digest = _export_research(arguments.output, handoff.model_dump_json().encode())
            result = _handoff_summary(request, handoff).model_dump(mode="json")
            result["file_sha256"] = digest
    except (OSError, ValueError, BridgeError):
        print(json.dumps({"status": "RESEARCH_GENERATION_REJECTED"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0
