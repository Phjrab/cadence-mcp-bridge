"""Read-only transport for a host-registered retained AMP PM0 operation."""

from __future__ import annotations

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


def _read(source: _PinnedComparisonFile) -> bytes:
    return _read_candidate_bytes(source.path, expected_sha256=source.sha256)


def register_retained_pm0(server: MCPServer, path: Path, digest: str) -> None:
    try:
        files = _HostRegistration.model_validate_json(
            read_candidate_document(path, expected_sha256=digest)
        )
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
        checked_plan = RetainedPm0Plan(identity=identity, plan=plan)
        checked_apply = RetainedPm0Apply(writer=observed.writer)
        checked_observation = RetainedPm0Observation(
            writer=observed.writer, saved_revision=observed.saved_revision,
        )
    except (InvalidInputError, OSError, ValueError):
        raise ConfigurationError("Configured retained PM0 registration is invalid") from None

    def check(request: PmosDefaultChangeRequest) -> None:
        if request != identity:
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

    @server.tool(
        name="cadence_observe_retained_amp_pm0",
        annotations=_READ_ONLY, structured_output=True,
        description="Read the independently reconciled saved PM0 revision and historical outcome.",
    )
    def retained_observation(request: PmosDefaultChangeRequest) -> RetainedPm0Observation:
        check(request)
        return checked_observation
