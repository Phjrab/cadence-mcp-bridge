"""Bounded authenticated retrieval with mathematical fixtures; no native EDA."""

import hashlib
from copy import deepcopy

import pytest
from test_generic_measurements import frame_for, operator, operator_base, reader_for

from cadence_mcp_bridge import authenticated_provider as wire
from cadence_mcp_bridge.generic_measurements import render_reader
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["operator", "operator_base"]


@pytest.fixture
def retrieval(operator, monkeypatch):
    context, plan, ade, reader, op, native_input = args = reader_for(operator)
    frame = frame_for(args, "V|input|1\nV|output|0.5\nI|rail|-0.002")
    script = render_reader(context, plan, ade, reader, op, native_input)
    receipt = {
        "schema_version": 1,
        "operation_id": op,
        "plan_sha256": plan.plan_sha256,
        "native_input_sha256": native_input,
        "reader_registration_sha256": canonical_digest(reader),
        "reader_script_sha256": hashlib.sha256(script).hexdigest(),
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
        "psf_tree_fingerprint": "a" * 64,
        "pre_receipt_tree_fingerprint": "b" * 64,
        "logical_bytes": 100,
        "allocated_bytes": 4096,
        "originals_preserved": True,
    }
    event = {
        "schema_version": 1,
        "operation_id": op,
        "plan_sha256": plan.plan_sha256,
        "revision": 5,
        "previous_sha256": "c" * 64,
        "phase": "SUCCEEDED",
        "evidence_sha256": hashlib.sha256(wire._canonical(receipt)).hexdigest(),
    }
    observation = {
        "operation_id": op,
        "plan_sha256": plan.plan_sha256,
        "resource_domain_sha256": plan.resource_domain_sha256,
        "ledger_ref": plan.ledger_ref,
        "progress": {
            "phase": "SUCCEEDED",
            "remote_revision": 5,
            "provider_receipt_sha256": hashlib.sha256(wire._canonical(event)).hexdigest(),
        },
    }
    payload = dict(
        observation=observation,
        terminal_event=event,
        receipt=receipt,
        ade=ade.model_dump(mode="json"),
        reader=reader.model_dump(mode="json"),
        frame=frame.decode("ascii"),
    )
    provider = wire.AuthenticatedOperatorProvider(
        context,
        wire.NativeProviderBinding(
            schema_version=1,
            identity_manifest_sha256="a" * 64,
            runtime_manifest_sha256=context.binding.runner_sha256,
        ),
    )
    calls = []

    def transport(argv, raw, env, **bounds):
        calls.append(__import__("json").loads(raw)["action"])
        return (
            0,
            wire._canonical(
                dict(
                    schema_version=1,
                    action="result",
                    payload=payload,
                    runtime_manifest_sha256=provider.binding.runtime_manifest_sha256,
                    identity_manifest_sha256=provider.binding.identity_manifest_sha256,
                )
            ),
            b"",
        )

    monkeypatch.setattr(wire, "_ssh", lambda _: ["fixed-synthetic-ssh", "python", "-B"])
    monkeypatch.setattr(wire, "run_fixed", transport)
    return provider, plan, op, payload, calls


@pytest.mark.asyncio
async def test_verified_result_projects_only_registered_measurements_without_writes(retrieval):
    provider, plan, op, payload, calls = retrieval
    before = deepcopy(payload)
    observed, result = await provider.result(op, plan)
    assert calls == ["result"] and payload == before
    assert observed.progress.phase == "SUCCEEDED"
    assert result["status"] == "NATIVE_RESULT_RETRIEVED"
    assert result["nodes"][1] == dict(logical_id="output", value=0.5, unit="V")
    assert result["power"]["supply_w"] == 0.001
    assert result["spec_evaluation"] == "not_evaluated"
    assert not provider.context.binding.analysis_journal.exists()
    assert not provider.context.lock_path.exists()
    assert not set(result) & {"frame", "ade", "reader", "source_cell", "source_state"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "job",
        "plan",
        "event",
        "receipt",
        "frame",
        "reader",
        "oversize",
        "nonsuccess",
        "extra",
        "script",
    ],
)
async def test_result_substitution_and_partial_or_unbound_frames_fail_closed(retrieval, failure):
    provider, plan, op, data, calls = retrieval
    if failure == "job":
        data["receipt"]["operation_id"] = "different"
    elif failure == "plan":
        data["observation"]["plan_sha256"] = "9" * 64
    elif failure == "event":
        data["terminal_event"]["previous_sha256"] = "9" * 64
    elif failure == "receipt":
        data["receipt"]["frame_sha256"] = "9" * 64
    elif failure == "frame":
        data["frame"] = data["frame"].replace("V|output|0.5", "V|output|999")
    elif failure == "reader":
        data["reader"]["nodes"][1]["selector"] = "/wrong"
    elif failure == "oversize":
        data["frame"] = "A" * 65537
    elif failure == "nonsuccess":
        data["observation"]["progress"]["phase"] = "EXTRACTING"
    elif failure == "extra":
        data["raw_path"] = "/not-an-interface"
    else:
        data["receipt"]["reader_script_sha256"] = "9" * 64
        data["terminal_event"]["evidence_sha256"] = hashlib.sha256(
            wire._canonical(data["receipt"])
        ).hexdigest()
        data["observation"]["progress"]["provider_receipt_sha256"] = hashlib.sha256(
            wire._canonical(data["terminal_event"])
        ).hexdigest()
    with pytest.raises(OperationRejected):
        await provider.result(op, plan)
    assert calls == ["result"]
