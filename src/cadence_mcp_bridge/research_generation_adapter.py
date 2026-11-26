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
    _read_candidate_bytes,
    _reserved,
    read_candidate_document,
)
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError
from cadence_mcp_bridge.onboarding import _local_path
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
_RECOVERY_FILES = ("recovery_enrollment", "locked_witness", "nominal_input", "retained_input")
_COMPLETION_FILES = ("phase_record", "completion")
_RUNTIME_FILES = ("runtime_manifest", "runtime_registration")


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


def _registered_context(config: BridgeConfig, path: Path) -> tuple[ExecutionContext, Path]:
    context = select_context(config) if config.runtime_mode == "operator" else None
    if context is None:
        raise ValueError("a selected operator context is required")
    directory = _local_path(path).parent
    if any(
        protected.resolve().is_relative_to(directory)
        for protected in (
            context.binding.analysis_journal,
            context.binding.sweep_journal,
            context.lock_path,
        )
    ):
        raise ValueError("registered generation evidence directory collides with operator state")
    return context, directory


def _load(
    config: BridgeConfig,
    path: Path,
    digest: str,
) -> tuple[ExecutionContext, ResearchGenerationBinding, RegisteredResearchGeneration]:
    from cadence_mcp_bridge.research_generation_provider import registered_research_generation

    try:
        context, directory = _registered_context(config, path)
        raw = read_candidate_document(path, expected_sha256=digest)
        binding = ResearchGenerationBinding.model_validate_json(
            json.dumps(json.loads(raw)["binding"])
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


def _export_analysis_source(
    arguments: argparse.Namespace,
    registered: Path,
    registration_sha: Digest,
    request: ResearchGenerationQuery,
) -> dict[str, str | bool]:
    from cadence_mcp_bridge.research_generation_provider import (
        registered_generation_analysis_source,
    )

    recovery = arguments.recover_retained_source
    required, excluded = (
        (_RECOVERY_FILES, _COMPLETION_FILES) if recovery else (_COMPLETION_FILES, _RECOVERY_FILES)
    )
    evidence = {field: getattr(arguments, field) for field in (*_RUNTIME_FILES, *required)}
    settings = arguments.settings
    if (
        settings is None
        or arguments.context is None
        or any(item is None for item in evidence.values())
        or any(getattr(arguments, name) is not None for name in excluded)
    ):
        raise ValueError("analysis source export requires explicit operator settings and custody")
    paths = [Path(item[0]) for item in evidence.values()]
    if any(
        path.drive.startswith(("\\\\", "//"))
        for path in (settings, registered, arguments.output, *paths)
    ):
        raise ValueError("analysis source export requires local files")
    config = BridgeConfig(
        runtime_mode="operator",
        runtime_settings_path=settings,
        runtime_context_id=arguments.context,
    )
    context, directory = _registered_context(config, registered)
    protected = _reserved(settings, (context,))
    protected.update(_local_path(path) for path in (*paths, Path(arguments.request[0])))
    output = _output(arguments.output, protected)
    if output.is_relative_to(directory):
        raise ValueError("analysis source export must be outside the evidence directory")
    documents = {
        key: _read_candidate_bytes(Path(path), expected_sha256=sha)
        for key, (path, sha) in evidence.items()
    }
    registration_raw = read_candidate_document(registered, expected_sha256=registration_sha)
    if recovery:
        from cadence_mcp_bridge.research_generation_ota_recovery import (
            recover_ota_generation_analysis_source,
        )
        from cadence_mcp_bridge.research_generation_recovery import (
            recover_retained_generation_source,
        )

        version = json.loads(documents["recovery_enrollment"])["schema_version"]
        recover_source = (
            recover_ota_generation_analysis_source
            if type(version) is int and version == 2
            else recover_retained_generation_source
        )

        recovered = recover_source(
            context,
            registration_raw,
            directory,
            request,
            recovery_enrollment=documents["recovery_enrollment"],
            expected_recovery_enrollment_sha256=evidence["recovery_enrollment"][1],
            locked_witness=documents["locked_witness"],
            runtime_manifest=documents["runtime_manifest"],
            runtime_registration=documents["runtime_registration"],
            nominal_input=documents["nominal_input"],
            retained_input=documents["retained_input"],
        )
        digest = _export_research(output, recovered.model_dump_json().encode())
        return {
            "status": recovered.status,
            "generation_status": recovered.generation_status,
            "file_sha256": digest,
            "execution_authorized": recovered.execution_authorized,
        }
    source = registered_generation_analysis_source(
        context,
        registration_raw,
        directory,
        request,
        documents["phase_record"],
        documents["completion"],
        runtime_manifest=documents["runtime_manifest"],
        runtime_registration=documents["runtime_registration"],
        expected_registration_file_sha256=registration_sha,
        expected_phase_record_sha256=evidence["phase_record"][1],
        expected_completion_sha256=evidence["completion"][1],
    )
    digest = _export_research(output, source.model_dump_json().encode())
    return {
        "status": "RESEARCH_GENERATION_ANALYSIS_SOURCE_EXPORTED",
        "file_sha256": digest,
        "execution_authorized": source.execution_authorized,
    }


def run_registered_generation(arguments: argparse.Namespace) -> int:
    try:
        registered_path, registered_digest = arguments.registration
        request_path, request_digest = arguments.request
        action = arguments.generation_action
        if (
            action == "handoff"
            and (arguments.analysis_source or arguments.recover_retained_source)
            and Path(request_path).drive.startswith(("\\\\", "//"))
        ):
            raise ValueError("analysis source export requires local files")
        request = ResearchGenerationQuery.model_validate_json(
            read_candidate_document(Path(request_path), expected_sha256=request_digest)
        )
        if action == "handoff":
            if arguments.analysis_source or arguments.recover_retained_source:
                result = _export_analysis_source(
                    arguments, Path(registered_path), registered_digest, request
                )
                print(json.dumps(result, sort_keys=True))
                return 0
            if any(
                getattr(arguments, name) is not None
                for name in (
                    "settings",
                    "context",
                    *_COMPLETION_FILES,
                    *_RUNTIME_FILES,
                    *_RECOVERY_FILES,
                )
            ):
                raise ValueError("analysis source options require an explicit source mode")
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
    except (OSError, KeyError, TypeError, ValueError, BridgeError):
        print(json.dumps({"status": "RESEARCH_GENERATION_REJECTED"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0
