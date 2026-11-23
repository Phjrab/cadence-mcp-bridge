"""Verify v2 retained evidence joins without file access during projection."""

import base64
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_amplifier_pm0_default import _registered_provider_fixture
from test_amplifier_pm0_default import operation as operation

from cadence_mcp_bridge.amplifier_pm0_default import (
    AmplifierPm0DispatchBinding,
    RetainedAmplifierPm0DefaultChange,
    _pm0_frame,
)
from cadence_mcp_bridge.amplifier_pm0_retained_v2 import (
    AmplifierPm0V2Evidence,
    project_retained_amplifier_pm0_v2,
)
from cadence_mcp_bridge.amplifier_pm0_service import _FixedAmplifierPm0Provider
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest, PmosDefaultChangeResult
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.pmos_default_service import _sha
from cadence_mcp_bridge.variable_contracts import canonical_digest


@pytest.fixture
def v2(
    operation: tuple[RetainedAmplifierPm0DefaultChange, PmosDefaultChangeRequest],
    tmp_path: Path,
) -> tuple[PmosDefaultChangeRequest, AmplifierPm0V2Evidence]:
    _, directory, request, scope, _ = _registered_provider_fixture(operation, tmp_path)
    reconciliation = operation[0].journal.reconciliation
    assert reconciliation is not None
    binding = AmplifierPm0DispatchBinding(
        operation_id=scope.operation_id,
        scope_sha256=request.expected_scope_sha256,
        plan_sha256=scope.plan_sha256,
        owned_library=scope.owned_library,
        owned_cell=scope.owned_cell,
        owned_view=scope.owned_view,
        owned_before_view_tree_sha256=scope.owned_before_view_tree_sha256,
    )
    # The original apply and same-ID lookup record stock UNKNOWN.
    identity = dict(
        operation_id=binding.operation_id,
        scope_sha256=binding.scope_sha256,
        plan_sha256=binding.plan_sha256,
    )
    stock = PmosDefaultChangeResult(
        **identity,
        candidate_revision=scope.plan.candidate_revision,
        outcome="OUTCOME_UNKNOWN",
        replayed=False,
        dispatched_this_call=None,
    ).model_dump(mode="json")
    apply = _canonical(stock | {"remote_contact": None, "budget_reset_or_refund": False})
    replay = _canonical(
        stock
        | {
            "replayed": True,
            "dispatched_this_call": False,
            "remote_contact": False,
            "budget_reset_or_refund": False,
        }
    )
    writer = _canonical(
        identity
        | {
            "dispatch_binding_sha256": canonical_digest(binding),
            "retry": False,
        }
    )
    payload = "1" * 64
    edit_intent = _canonical(
        {
            "claim_sha256": _sha(writer),
            "request_sha256": payload,
            "prior_receipt_sha256": "none",
            "retry": False,
        }
    )
    edit_receipt = {
        "operation_id": binding.operation_id,
        "scope_sha256": binding.scope_sha256,
        "saved_view_tree_sha256": "2" * 64,
        "saved_library_tree_sha256": "3" * 64,
        "presave_signature_sha256": _sha(reconciliation.presave),
        "reopened_signature_sha256": _sha(reconciliation.reopened),
        "edit_live_counter": 35,
        "source_preservation_sha256": scope.source_preservation_sha256,
        "status": "SAVED",
    }
    edit_pin = _sha(_canonical(edit_receipt))
    edit = _canonical({"receipt": edit_receipt, "receipt_sha256": edit_pin})
    edit_stderr = b"UnicodeWarning from guest comparison"
    edit_transport = _canonical(_FixedAmplifierPm0Provider._transport_record(0, edit, edit_stderr))
    captured = {
        "amp-edit-intent.private.json": edit_intent,
        "amp-edit-stdout.private.json": edit,
        "amp-edit-stderr.private.txt": edit_stderr,
        "amp-edit-transport.private.json": edit_transport,
        "amp-writer-intent.private.json": writer,
    }
    readback_scope = _canonical(
        {
            "action": "AMP_EXISTING_SAVED_READBACK_ONLY",
            "scope": binding.scope_sha256,
            "operation": binding.operation_id,
            "exact_saved": edit_pin,
            "actual_safety_proof": "4" * 64,
            "stock_unknown": _sha(apply),
            "replay": _sha(replay),
            "host": "5" * 64,
            "payload": payload,
            "old_claim": _sha(writer),
            "existing_ocean": 1,
            "remaining_ocean": 1,
            "write_target": "readback-netlist evidence only",
            "spectre": 0,
            "reservations": 0,
        }
    )
    readback_intent = _canonical(
        {
            "scope": _sha(readback_scope),
            "retry": False,
            "captured": {
                name: [1, _sha(raw)]
                for name, raw in (
                    captured
                    | {
                        "apply-cli.stdout.private.json": apply,
                        "replay-cli.stdout.private.json": replay,
                    }
                ).items()
            },
        }
    )
    final = edit_receipt.copy()
    del final["saved_library_tree_sha256"]
    final.update(
        status="VERIFIED",
        plan_sha256=binding.plan_sha256,
        owned_before_view_tree_sha256=scope.owned_before_view_tree_sha256,
        reopened_view_tree_sha256=final["saved_view_tree_sha256"],
        netlisted_view_tree_sha256=final["saved_view_tree_sha256"],
        reopen_receipt_sha256="6" * 64,
        netlist_receipt_sha256="7" * 64,
        netlist_sha256=_sha(reconciliation.netlist),
        reopen_frame=_pm0_frame(baseline=False)[0],
        ocean_calls=2,
        simulations=0,
        reservations=0,
    )
    final_pin = _sha(_canonical(final))
    readback = _canonical(
        {
            "receipt": final,
            "receipt_sha256": final_pin,
            "presave_base64": base64.b64encode(reconciliation.presave).decode("ascii"),
            "reopened_base64": base64.b64encode(reconciliation.reopened).decode("ascii"),
            "input_base64": base64.b64encode(reconciliation.netlist).decode("ascii"),
        }
    )
    audit = _canonical(
        {
            "status": "AMP_PRODUCT_VERIFIED_DURABLE",
            "scope_sha256": binding.scope_sha256,
            "receipt": final,
            "view_sha256": final["saved_view_tree_sha256"],
            "library_sha256": edit_receipt["saved_library_tree_sha256"],
            "reservations_in_call": 0,
            "simulations_in_call": 0,
            "evidence": {
                "edit": edit_pin,
                "readback-netlist": final_pin,
                "reopen-receipt.json": final["reopen_receipt_sha256"],
                "netlist-receipt.json": final["netlist_receipt_sha256"],
                "effective-input.scs": final["netlist_sha256"],
            },
        }
    )
    return request, AmplifierPm0V2Evidence(
        scope=(directory / "execution-scope.private.json").read_bytes(),
        baseline_input=operation[0].baseline_input,
        writer_intent=writer,
        edit_intent=edit_intent,
        edit_stdout=edit,
        edit_stderr=edit_stderr,
        edit_transport=edit_transport,
        original_apply=apply,
        replay=replay,
        replay_transport=_canonical(
            {
                "exit": 0,
                "err": _sha(b""),
                "out": _sha(replay),
                "retained_after": {
                    name: [len(raw), 1, _sha(raw)] for name, raw in captured.items()
                },
            }
        ),
        readback_scope=readback_scope,
        readback_intent=readback_intent,
        readback_stdout=readback,
        readback_transport=_canonical(
            {
                "captured_unchanged": True,
                "exit": 0,
                "stderr": _sha(b""),
                "stdout": _sha(readback),
            }
        ),
        terminal_audit=audit,
    )


def test_retained_v2_preserves_writer_and_projects_independent_revision(
    v2: tuple[PmosDefaultChangeRequest, AmplifierPm0V2Evidence],
) -> None:
    request, evidence = v2
    result = project_retained_amplifier_pm0_v2(request, evidence)
    assert result.identity == request and not result.execution_authorized
    assert result.writer.outcome == "OUTCOME_UNKNOWN"
    assert result.writer.replayed and not result.writer.dispatched_this_call
    assert result.writer.netlist_sha256 is None
    observation = result.saved_revision
    assert observation.status == "VERIFIED" and observation.provenance == "INDEPENDENT_V2_READBACK"
    assert observation.schematic_revision_sha256 == observation.testbench_revision_sha256
    assert observation.oa_width.normalized == observation.netlist.value.normalized
    assert observation.oa_width.value == "120"
    assert (
        observation.saved_geometry_counter_before,
        observation.saved_geometry_counter_after,
    ) == (
        12,
        35,
    )
    with pytest.raises(ValueError):
        project_retained_amplifier_pm0_v2(
            request.model_copy(update={"expected_scope_sha256": "a" * 64}), evidence
        )


@pytest.mark.parametrize(
    "field,key,substitute",
    [
        ("writer_intent", "retry", True),
        ("replay", "remote_contact", True),
        ("readback_scope", "exact_saved", "a" * 64),
        ("readback_transport", "captured_unchanged", False),
        ("terminal_audit", "view_sha256", "b" * 64),
    ],
)
def test_retained_v2_rejects_rebound_or_promoted_evidence(
    v2: tuple[PmosDefaultChangeRequest, AmplifierPm0V2Evidence],
    field: str,
    key: str,
    substitute: object,
) -> None:
    request, evidence = v2
    raw = json.loads(getattr(evidence, field))
    raw[key] = substitute
    with pytest.raises(ValueError):
        project_retained_amplifier_pm0_v2(request, replace(evidence, **{field: _canonical(raw)}))


def test_readback_capture_hash_does_not_replace_netlist_evidence(
    v2: tuple[PmosDefaultChangeRequest, AmplifierPm0V2Evidence],
) -> None:
    request, evidence = v2
    envelope = json.loads(evidence.readback_stdout)
    envelope["input_base64"] = base64.b64encode(b"changed netlist").decode("ascii")
    stdout = _canonical(envelope)
    transport = json.loads(evidence.readback_transport)
    transport["stdout"] = _sha(stdout)
    with pytest.raises(ValueError):
        project_retained_amplifier_pm0_v2(
            request,
            replace(evidence, readback_stdout=stdout, readback_transport=_canonical(transport)),
        )
