"""Project a host-pinned AMP v2 writer and its independent readback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cadence_mcp_bridge.amplifier_pm0_default import (
    AmplifierPm0DispatchBinding,
    _pm0_frame,
    plan_amplifier_pm0_default_change,
    verify_amplifier_pm0_save_metadata,
)
from cadence_mcp_bridge.amplifier_pm0_service import (
    _LIMIT,
    _decode,
    _EditResponse,
    _FixedAmplifierPm0Provider,
    _Response,
    _Scope,
)
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest, PmosDefaultChangeResult
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeValue,
    NetlistProjection,
    project_netlist_change,
)
from cadence_mcp_bridge.pmos_default_service import _document, _require, _sha
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest


@dataclass(frozen=True)
class AmplifierPm0V2Evidence:
    """Exact raw bytes. The trusted host must verify every file pin before constructing this."""

    scope: bytes
    baseline_input: bytes
    writer_intent: bytes
    edit_intent: bytes
    edit_stdout: bytes
    edit_stderr: bytes
    edit_transport: bytes
    original_apply: bytes
    replay: bytes
    replay_transport: bytes
    readback_scope: bytes
    readback_intent: bytes
    readback_stdout: bytes
    readback_transport: bytes
    terminal_audit: bytes


class AmplifierPm0V2SavedRevision(VariableModel):
    status: Literal["VERIFIED"] = "VERIFIED"
    provenance: Literal["INDEPENDENT_V2_READBACK"] = "INDEPENDENT_V2_READBACK"
    schematic_revision_sha256: Digest
    testbench_revision_sha256: Digest
    library_tree_sha256: Digest
    source_preservation_sha256: Digest
    edit_receipt_sha256: Digest
    reopen_receipt_sha256: Digest
    netlist_receipt_sha256: Digest
    receipt_sha256: Digest
    terminal_audit_sha256: Digest
    reopened_signature_sha256: Digest
    oa_width: ChangeValue
    oa_readback: tuple[str, ...]
    saved_geometry_counter_before: int
    saved_geometry_counter_after: int
    netlist: NetlistProjection


class AmplifierPm0V2Projection(VariableModel):
    identity: PmosDefaultChangeRequest
    plan: ChangePlan
    writer: PmosDefaultChangeResult
    saved_revision: AmplifierPm0V2SavedRevision
    execution_authorized: Literal[False] = False


class _StockResult(PmosDefaultChangeResult):
    remote_contact: Literal[False] | None
    budget_reset_or_refund: Literal[False]


class _ReadbackScope(VariableModel):
    action: Literal["AMP_EXISTING_SAVED_READBACK_ONLY"]
    scope: Digest
    operation: OperationId
    exact_saved: Digest
    actual_safety_proof: Digest
    stock_unknown: Digest
    replay: Digest
    host: Digest
    payload: Digest
    old_claim: Digest
    existing_ocean: Literal[1]
    remaining_ocean: Literal[1]
    write_target: Literal["readback-netlist evidence only"]
    spectre: Literal[0]
    reservations: Literal[0]


def _stock_result(
    raw: bytes, request: PmosDefaultChangeRequest, plan: ChangePlan, *, replay: bool
) -> PmosDefaultChangeResult:
    _closed_document(raw, max_bytes=4096)
    result = _StockResult.model_validate_json(raw)
    result.check_registered_scope(
        request, registered_plan=plan, registered_scope_sha256=request.expected_scope_sha256
    )
    # The CLI keeps the historical outcome. No fields from readback belong in it.
    _require(
        result.outcome == "OUTCOME_UNKNOWN"
        and result.replayed is replay
        and result.dispatched_this_call is (False if replay else None)
        and result.remote_contact is result.dispatched_this_call
        and all(
            value is None
            for value in (
                result.observed_revision_sha256,
                result.observed_testbench_revision_sha256,
                result.source_preservation_sha256,
                result.reopen_receipt_sha256,
                result.netlist_receipt_sha256,
                result.netlist_sha256,
            )
        ),
        "amp_v2_original_writer_outcome",
    )
    return PmosDefaultChangeResult.model_validate(
        result.model_dump(exclude={"remote_contact", "budget_reset_or_refund"})
    )


def _capture_index(inventory: object, captured: dict[str, bytes], *, replay: bool) -> None:
    reason = "amp_v2_capture_inventory"
    if not isinstance(inventory, dict):
        raise ValueError(reason)
    _require(set(inventory) == set(captured), reason)
    for name, payload in captured.items():
        row = inventory[name]
        if not isinstance(row, list) or len(row) != (3 if replay else 2):
            raise ValueError(reason)
        _require(
            row[-1] == _sha(payload)
            and type(row[-2]) is int
            and row[-2] > 0
            and (not replay or row[0] == len(payload)),
            reason,
        )


def project_retained_amplifier_pm0_v2(
    request: PmosDefaultChangeRequest, evidence: AmplifierPm0V2Evidence
) -> AmplifierPm0V2Projection:
    """Read both linked outcomes without consulting runtime settings or launching a job."""
    _document(evidence.scope)
    scope = _Scope.model_validate_json(evidence.scope)
    plan = scope.plan
    scope_sha = _sha(evidence.scope)
    _require(
        request.operation_id == scope.operation_id
        and request.expected_plan_sha256 == scope.plan_sha256 == plan.plan_sha256
        and request.expected_scope_sha256 == scope_sha
        and plan
        == plan_amplifier_pm0_default_change(
            scope.qualification, plan.candidate_id, plan.candidate_revision, plan.requested
        )
        and 0 < len(evidence.baseline_input) <= 32768
        and _sha(evidence.baseline_input) == plan.baseline.netlist_sha256,
        "amp_v2_registered_identity",
    )
    binding = AmplifierPm0DispatchBinding(
        operation_id=scope.operation_id,
        scope_sha256=scope_sha,
        plan_sha256=plan.plan_sha256,
        owned_library=scope.owned_library,
        owned_cell=scope.owned_cell,
        owned_view=scope.owned_view,
        owned_before_view_tree_sha256=scope.owned_before_view_tree_sha256,
    )
    claim_sha = _sha(evidence.writer_intent)
    edit_intent = _document(evidence.edit_intent)
    _require(
        _document(evidence.writer_intent)
        == dict(
            operation_id=binding.operation_id,
            scope_sha256=scope_sha,
            plan_sha256=binding.plan_sha256,
            dispatch_binding_sha256=canonical_digest(binding),
            retry=False,
        )
        and set(edit_intent) == {"claim_sha256", "prior_receipt_sha256", "request_sha256", "retry"}
        and edit_intent["claim_sha256"] == claim_sha
        and edit_intent["prior_receipt_sha256"] == "none"
        and edit_intent["retry"] is False
        and 0 < len(evidence.edit_stderr) <= _LIMIT
        and _document(evidence.edit_transport)
        == _FixedAmplifierPm0Provider._transport_record(
            0, evidence.edit_stdout, evidence.edit_stderr
        ),
        "amp_v2_writer_capture",
    )
    _document(evidence.edit_stdout)
    edit = _EditResponse.model_validate_json(evidence.edit_stdout)
    saved = edit.receipt
    _require(
        canonical_digest(saved) == edit.receipt_sha256
        and (saved.operation_id, saved.scope_sha256) == (scope.operation_id, scope_sha)
        and saved.source_preservation_sha256 == scope.source_preservation_sha256
        and saved.saved_view_tree_sha256
        not in (scope.owned_before_view_tree_sha256, plan.baseline.revision_sha256),
        "amp_v2_saved_receipt",
    )
    _stock_result(evidence.original_apply, request, plan, replay=False)
    writer = _stock_result(evidence.replay, request, plan, replay=True)
    captured = {
        "amp-edit-intent.private.json": evidence.edit_intent,
        "amp-edit-stderr.private.txt": evidence.edit_stderr,
        "amp-edit-stdout.private.json": evidence.edit_stdout,
        "amp-edit-transport.private.json": evidence.edit_transport,
        "amp-writer-intent.private.json": evidence.writer_intent,
    }
    replay = _document(evidence.replay_transport)
    _require(
        replay.get("exit") == 0
        and replay.get("err") == _sha(b"")
        and replay.get("out") == _sha(evidence.replay),
        "amp_v2_replay_transport",
    )
    _capture_index(replay.get("retained_after"), captured, replay=True)

    _document(evidence.readback_scope)
    observer = _ReadbackScope.model_validate_json(evidence.readback_scope)
    intent = _document(evidence.readback_intent)
    transport = _document(evidence.readback_transport)
    _require(
        (observer.operation, observer.scope, observer.exact_saved)
        == (scope.operation_id, scope_sha, edit.receipt_sha256)
        and observer.payload == edit_intent["request_sha256"]
        and observer.old_claim == claim_sha
        and observer.stock_unknown == _sha(evidence.original_apply)
        and observer.replay == _sha(evidence.replay)
        and intent.get("scope") == _sha(evidence.readback_scope)
        and intent.get("retry") is False
        and transport.get("captured_unchanged") is True
        and transport.get("exit") == 0
        and transport.get("stderr") == _sha(b"")
        and transport.get("stdout") == _sha(evidence.readback_stdout),
        "amp_v2_independent_readback_capture",
    )
    _capture_index(
        intent.get("captured"),
        captured
        | {
            "apply-cli.stdout.private.json": evidence.original_apply,
            "replay-cli.stdout.private.json": evidence.replay,
        },
        replay=False,
    )
    _closed_document(evidence.readback_stdout, max_bytes=_LIMIT)
    response = _Response.model_validate_json(evidence.readback_stdout)
    receipt = response.receipt
    frame, values = _pm0_frame(baseline=False)
    _require(
        _canonical(response.model_dump(mode="json")) == evidence.readback_stdout
        and canonical_digest(receipt) == response.receipt_sha256
        and (receipt.operation_id, receipt.scope_sha256, receipt.plan_sha256)
        == (scope.operation_id, scope_sha, plan.plan_sha256)
        and receipt.owned_before_view_tree_sha256 == scope.owned_before_view_tree_sha256
        and receipt.source_preservation_sha256 == saved.source_preservation_sha256
        and receipt.saved_view_tree_sha256
        == receipt.reopened_view_tree_sha256
        == receipt.netlisted_view_tree_sha256
        == saved.saved_view_tree_sha256
        and receipt.presave_signature_sha256 == saved.presave_signature_sha256
        and receipt.reopened_signature_sha256 == saved.reopened_signature_sha256
        and receipt.edit_live_counter == saved.edit_live_counter
        and tuple(frame) == receipt.reopen_frame,
        "amp_v2_independent_receipt",
    )
    audit = _document(evidence.terminal_audit)
    inventory = audit.get("evidence")
    _require(
        audit.get("status") == "AMP_PRODUCT_VERIFIED_DURABLE"
        and audit.get("scope_sha256") == scope_sha
        and audit.get("receipt") == receipt.model_dump(mode="json")
        and audit.get("view_sha256") == receipt.saved_view_tree_sha256
        and audit.get("library_sha256") == saved.saved_library_tree_sha256
        and audit.get("reservations_in_call") == audit.get("simulations_in_call") == 0
        and isinstance(inventory, dict)
        and inventory.get("edit") == edit.receipt_sha256
        and inventory.get("readback-netlist") == response.receipt_sha256
        and inventory.get("reopen-receipt.json") == receipt.reopen_receipt_sha256
        and inventory.get("netlist-receipt.json") == receipt.netlist_receipt_sha256
        and inventory.get("effective-input.scs") == receipt.netlist_sha256,
        "amp_v2_durable_terminal_audit",
    )
    before, after = verify_amplifier_pm0_save_metadata(
        _decode(response.presave_base64, 65536, receipt.presave_signature_sha256),
        _decode(response.reopened_base64, 65536, receipt.reopened_signature_sha256),
        live_counter=receipt.edit_live_counter,
    )
    netlist = project_netlist_change(
        plan,
        evidence.baseline_input,
        _decode(response.input_base64, 32768, receipt.netlist_sha256),
    )
    return AmplifierPm0V2Projection(
        identity=request,
        plan=plan,
        writer=writer,
        saved_revision=AmplifierPm0V2SavedRevision(
            schematic_revision_sha256=receipt.reopened_view_tree_sha256,
            testbench_revision_sha256=receipt.netlisted_view_tree_sha256,
            library_tree_sha256=saved.saved_library_tree_sha256,
            source_preservation_sha256=receipt.source_preservation_sha256,
            edit_receipt_sha256=edit.receipt_sha256,
            reopen_receipt_sha256=receipt.reopen_receipt_sha256,
            netlist_receipt_sha256=receipt.netlist_receipt_sha256,
            receipt_sha256=response.receipt_sha256,
            terminal_audit_sha256=_sha(evidence.terminal_audit),
            reopened_signature_sha256=receipt.reopened_signature_sha256,
            oa_width=ChangeValue(value=values["w"][:-1], unit="nm"),
            oa_readback=receipt.reopen_frame,
            saved_geometry_counter_before=before,
            saved_geometry_counter_after=after,
            netlist=netlist,
        ),
    )
