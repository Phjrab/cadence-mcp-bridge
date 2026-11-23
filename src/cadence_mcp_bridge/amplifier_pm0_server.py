"""Read-only transport for a host-registered retained AMP PM0 operation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cadence_mcp_bridge.amplifier_pm0_default import (
    AmplifierPm0DefaultObservation,
    AmplifierPm0Journal,
    AmplifierPm0JournalPins,
    AmplifierPm0Reconciliation,
    RetainedAmplifierPm0DefaultChange,
)
from cadence_mcp_bridge.amplifier_pm0_retained_v2 import (
    AmplifierPm0V2Evidence,
    AmplifierPm0V2SavedRevision,
    project_retained_amplifier_pm0_v2,
)
from cadence_mcp_bridge.candidate_cli import (
    _PinnedComparisonFile,
    _read_candidate_bytes,
    read_candidate_document,
)
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest, PmosDefaultChangeResult
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.parameter_changes import ChangePlan
from cadence_mcp_bridge.variable_contracts import VariableModel

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


class _ObserverFiles(VariableModel):
    receipt: _PinnedComparisonFile
    replay: _PinnedComparisonFile
    presave: _PinnedComparisonFile
    reopened: _PinnedComparisonFile
    netlist: _PinnedComparisonFile


class _HostRegistration(VariableModel):
    plan: _PinnedComparisonFile
    baseline_input: _PinnedComparisonFile
    pins: AmplifierPm0JournalPins
    scope: _PinnedComparisonFile
    intent: _PinnedComparisonFile
    baseline_receipt: _PinnedComparisonFile
    writer_capture: _PinnedComparisonFile
    reconciliation: _ObserverFiles


class _V2EvidenceFiles(VariableModel):
    scope: _PinnedComparisonFile
    baseline_input: _PinnedComparisonFile
    writer_intent: _PinnedComparisonFile
    edit_intent: _PinnedComparisonFile
    edit_stdout: _PinnedComparisonFile
    edit_stderr: _PinnedComparisonFile
    edit_transport: _PinnedComparisonFile
    original_apply: _PinnedComparisonFile
    replay: _PinnedComparisonFile
    replay_transport: _PinnedComparisonFile
    readback_scope: _PinnedComparisonFile
    readback_intent: _PinnedComparisonFile
    readback_stdout: _PinnedComparisonFile
    readback_transport: _PinnedComparisonFile
    terminal_audit: _PinnedComparisonFile


class _V2HostRegistration(VariableModel):
    schema_version: Literal[2]
    identity: PmosDefaultChangeRequest
    evidence: _V2EvidenceFiles


class RetainedPm0Plan(VariableModel):
    identity: PmosDefaultChangeRequest
    plan: ChangePlan
    mode: Literal["RETAINED_PLAN"] = "RETAINED_PLAN"
    execution_authorized: Literal[False] = False


class RetainedPm0Apply(VariableModel):
    writer: PmosDefaultChangeResult
    mode: Literal["RETAINED_APPLY_LOOKUP"] = "RETAINED_APPLY_LOOKUP"
    execution_authorized: Literal[False] = False


class RetainedPm0Observation(AmplifierPm0DefaultObservation):
    mode: Literal["RETAINED_READ_ONLY_OBSERVATION"] = "RETAINED_READ_ONLY_OBSERVATION"


class RetainedPm0V2Observation(VariableModel):
    writer: PmosDefaultChangeResult
    saved_revision: AmplifierPm0V2SavedRevision
    mode: Literal["RETAINED_READ_ONLY_OBSERVATION"] = "RETAINED_READ_ONLY_OBSERVATION"
    execution_authorized: Literal[False] = False


def _read(source: _PinnedComparisonFile) -> bytes:
    return _read_candidate_bytes(source.path, expected_sha256=source.sha256)


def _load_legacy(raw: bytes) -> tuple[RetainedPm0Plan, RetainedPm0Observation]:
    files = _HostRegistration.model_validate_json(raw)
    plan = ChangePlan.model_validate_json(_read(files.plan))
    observer = files.reconciliation
    journal = AmplifierPm0Journal(
        scope=_read(files.scope), intent=_read(files.intent),
        baseline_receipt=_read(files.baseline_receipt),
        writer_capture=_read(files.writer_capture),
        reconciliation=AmplifierPm0Reconciliation(
            receipt=_read(observer.receipt), replay=_read(observer.replay),
            presave=_read(observer.presave), reopened=_read(observer.reopened),
            netlist=_read(observer.netlist),
        ),
    )
    identity = PmosDefaultChangeRequest(
        operation_id=files.pins.writer_operation_id,
        expected_plan_sha256=files.pins.plan_sha256,
        expected_scope_sha256=files.pins.writer_scope_sha256,
    )
    service = RetainedAmplifierPm0DefaultChange(
        plan, journal, files.pins, _read(files.baseline_input),
    )
    observed = service.observe(identity)
    if observed.saved_revision is None:
        raise ValueError("registered PM0 observation missing")
    return RetainedPm0Plan(identity=identity, plan=plan), RetainedPm0Observation(
        writer=observed.writer, saved_revision=observed.saved_revision,
    )


def _load_v2(raw: bytes) -> tuple[RetainedPm0Plan, RetainedPm0V2Observation]:
    registration = _V2HostRegistration.model_validate_json(raw)
    files = registration.evidence
    evidence = AmplifierPm0V2Evidence(**{
        field: _read(getattr(files, field)) for field in _V2EvidenceFiles.model_fields
    })
    result = project_retained_amplifier_pm0_v2(registration.identity, evidence)
    return RetainedPm0Plan(identity=result.identity, plan=result.plan), RetainedPm0V2Observation(
        writer=result.writer, saved_revision=result.saved_revision,
    )


def register_retained_pm0(server: MCPServer, path: Path, digest: str) -> None:
    try:
        raw = read_candidate_document(path, expected_sha256=digest)
        registration = json.loads(raw)
        if not isinstance(registration, dict):
            raise ValueError("retained PM0 registration must be an object")
        checked_plan, checked_observation = (
            _load_v2(raw) if "schema_version" in registration else _load_legacy(raw)
        )
        checked_apply = RetainedPm0Apply(writer=checked_observation.writer)
    except (InvalidInputError, OSError, ValueError):
        raise ConfigurationError("Configured retained PM0 registration is invalid") from None

    def check(request: PmosDefaultChangeRequest) -> None:
        if request != checked_plan.identity:
            raise ToolError("Retained PM0 operation, plan or scope differs")

    @server.tool(
        name="cadence_get_retained_amp_pm0_plan",
        annotations=_READ_ONLY, structured_output=True,
        description="Read the fixed PM0 width plan for the registered historical operation.",
    )
    def retained_plan(request: PmosDefaultChangeRequest) -> RetainedPm0Plan:
        check(request)
        return checked_plan

    @server.tool(
        name="cadence_get_retained_amp_pm0_apply",
        annotations=_READ_ONLY, structured_output=True,
        description="Read the original PM0 apply outcome. This lookup cannot dispatch an edit.",
    )
    def retained_apply(request: PmosDefaultChangeRequest) -> RetainedPm0Apply:
        check(request)
        return checked_apply

    description = "Read the independently reconciled saved PM0 revision and historical outcome."
    if isinstance(checked_observation, RetainedPm0V2Observation):
        v2 = checked_observation

        @server.tool(
            name="cadence_observe_retained_amp_pm0",
            annotations=_READ_ONLY, structured_output=True, description=description,
        )
        def retained_v2_observation(request: PmosDefaultChangeRequest) -> RetainedPm0V2Observation:
            check(request)
            return v2
    else:
        legacy = checked_observation

        @server.tool(
            name="cadence_observe_retained_amp_pm0",
            annotations=_READ_ONLY, structured_output=True, description=description,
        )
        def retained_observation(request: PmosDefaultChangeRequest) -> RetainedPm0Observation:
            check(request)
            return legacy
