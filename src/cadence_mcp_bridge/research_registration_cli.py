"""Local assembly over the operator's pinned research registration evidence."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal

from cadence_mcp_bridge.candidate_cli import (
    _export_research,
    _output,
    _PinnedComparisonFile,
    _read_candidate_bytes,
    _reserved,
    read_candidate_document,
)
from cadence_mcp_bridge.generic_ade import LIMIT as BASELINE_LIMIT
from cadence_mcp_bridge.native_registration import (
    ReaderDefinition,
    RegistrationObservation,
    RegistrationProbeRequest,
    assemble,
)
from cadence_mcp_bridge.native_runtime import NativeRegistration
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_circuit import (
    MosBlockRegistrationHandoff,
    verify_mos_block_registration_source,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest


class ResearchRegistrationRequest(VariableModel):
    schema_version: Literal[1]
    expected_context_sha256: Digest
    expected_handoff_sha256: Digest
    identity_manifest_sha256: Digest
    probe: _PinnedComparisonFile
    observation: _PinnedComparisonFile
    reader_definition: _PinnedComparisonFile
    handoff: _PinnedComparisonFile


def assemble_research(
    arguments: Namespace, context: ExecutionContext, contexts: tuple[ExecutionContext, ...]
) -> dict[str, object]:
    request_path, request_sha = arguments.request
    path = Path(request_path)
    request = ResearchRegistrationRequest.model_validate_json(
        read_candidate_document(path, expected_sha256=request_sha)
    )
    if request.expected_context_sha256 != context.context_sha256:
        raise OperationRejected("research_registration_context_mismatch")
    probe = RegistrationProbeRequest.model_validate_json(_read(request.probe))
    observation = RegistrationObservation.model_validate_json(_read(request.observation))
    reader = ReaderDefinition.model_validate_json(_read(request.reader_definition))
    handoff = MosBlockRegistrationHandoff.model_validate_json(_read(request.handoff))
    protected = _reserved(arguments.settings, contexts) | {
        _local_path(item)
        for item in (
            path,
            request.probe.path,
            request.observation.path,
            request.reader_definition.path,
            request.handoff.path,
            probe.baseline_netlist,
        )
    }
    output = _output(arguments.output, protected)

    profile = context.contracts.designs.profile(probe.validation_request.design_id)
    workspace = PurePosixPath(context.contracts.environment.paths.workspace_root)
    library = PurePosixPath(handoff.library.path)
    if (
        handoff.binding.design_id != profile.design_id
        or handoff.library.name != profile.binding.library
        or not library.is_relative_to(workspace)
        or library == workspace
        or probe.source_cell != observation.source_cell
        or probe.source_state != observation.source_state
    ):
        raise OperationRejected("research_registration_source_binding_mismatch")
    verify_mos_block_registration_source(
        handoff,
        observation,
        expected_handoff_sha256=request.expected_handoff_sha256,
        expected_observation_sha256=canonical_digest(observation),
    )
    _read_candidate_bytes(
        probe.baseline_netlist,
        expected_sha256=observation.baseline_input_sha256,
        limit=BASELINE_LIMIT,
    )

    # Keep the stock assembler's output private until its one route agrees with the
    # checked inputs. Publish only an exclusive operator-local registration file.
    with TemporaryDirectory(prefix=".research-registration-", dir=output.parent) as staging:
        target = Path(staging) / "registration.json"
        assemble(
            context,
            [request.probe.path],
            [request.observation.path],
            [request.reader_definition.path],
            request.identity_manifest_sha256,
            target,
        )
        raw = read_candidate_document(target)
        registration = NativeRegistration.model_validate_json(raw)
        (route,) = registration.routes
        reader_fields = set(ReaderDefinition.model_fields)
        if (
            registration.identity_manifest_sha256 != request.identity_manifest_sha256
            or route.validation_request != probe.validation_request
            or route.ade != observation.ade
            or route.source_cell != observation.source_cell
            or route.source_state != observation.source_state
            or route.libraries != observation.libraries
            or route.model_files != observation.model_files
            or route.reader.model_dump(include=reader_fields) != reader.model_dump()
        ):
            raise OperationRejected("research_registration_assembled_route_mismatch")
        for ref in (request.probe, request.observation, request.reader_definition, request.handoff):
            _read(ref)
        _read_candidate_bytes(
            probe.baseline_netlist,
            expected_sha256=observation.baseline_input_sha256,
            limit=BASELINE_LIMIT,
        )
        registration_sha = _export_research(output, raw)

    return {
        "status": "RESEARCH_NATIVE_REGISTRATION_ASSEMBLED_NOT_AUTHORIZED",
        "provenance": "OPERATOR_PINNED_HANDOFF_AND_OBSERVATION",
        "registration_sha256": registration_sha,
        "handoff_sha256": handoff.handoff_sha256,
        "baseline_input_sha256": observation.baseline_input_sha256,
        "dut_netlist_sha256": handoff.pins.raw_netlist_sha256,
        "routes": 1,
        "remote_contact": False,
        "execution_authorized": False,
        "new_simulations": 0,
        "new_reservations": 0,
    }


def _read(ref: _PinnedComparisonFile) -> bytes:
    return read_candidate_document(ref.path, expected_sha256=ref.sha256)
