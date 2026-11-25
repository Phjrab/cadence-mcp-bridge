"""Exercise normal registration and durable phase transport with an isolated fake guest."""

import base64
import json
import time
from hashlib import sha256
from importlib.resources import files
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_registered_mos_sizing import _fixture

from cadence_mcp_bridge import _amp_pm0_default_phase as guest_support
from cadence_mcp_bridge import _registered_mos_edit_phase as guest_contract
from cadence_mcp_bridge import m2_cdf, registered_mos_edit_server, registered_mos_transport
from cadence_mcp_bridge import registered_mos_sizing_transport as sizing
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.registered_mos_edit import NativeMosEditSave
from cadence_mcp_bridge.server import create_default_server


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    route, child, requested, _, binding, before, capture = _fixture()
    package = files("cadence_mcp_bridge")
    guest = package.joinpath("_registered_mos_edit_phase.py").read_bytes()
    support = package.joinpath("_amp_pm0_default_phase.py").read_bytes()
    renderer = package.joinpath("mos_wl_skill.py").read_bytes()
    collector = m2_cdf.render_reopened_mos_cdf()
    constraints = b"bounded CDF fixture"
    hash_child = package.joinpath("_mos_cdf_call_contract.py").read_bytes()
    safety = _canonical({"fixture": "native safety"})
    directory = tmp_path / "evidence"
    slots = directory / binding.operation_id
    slots.mkdir(parents=True)
    (slots / "native-safety.private.json").write_bytes(safety)
    (directory / "baseline-input.private.scs").write_bytes(before)
    (directory / "cdf-constraints.private.txt").write_bytes(constraints)
    policy = route.model_dump(mode="json")
    policy["support"]["pdk_identity_sha256"] = guest_contract.SIZING_PDK_TREE_SHA256
    policy["support"]["adapter_sha256"] = _sha(renderer)
    policy["support"]["cdf_constraints_sha256"] = _sha(constraints)
    enrollment = _canonical(
        {
            "schema_version": 4,
            "route": "registered_mos_sizing",
            "owner": "C0",
            "context_id": "owned-sizing",
            "resource_domain_sha256": "1" * 64,
            "environment_sha256": "2" * 64,
            "native_manifest_sha256": "3" * 64,
            "evidence_directory": str(directory),
            "route_qualification": policy,
            "guest_sha256": _sha(guest),
            "support_sha256": _sha(support),
            "collector_sha256": _sha(collector),
            "renderer_sha256": _sha(renderer),
            "hash_child_sha256": _sha(hash_child),
            "valid_until_unix": int(time.time()) + 1_000,
            "admitted_l": {
                "minimum": {"unit": "nm", "value": "200"},
                "maximum": {"unit": "nm", "value": "250"},
            },
            "slots": [
                {
                    "operation_id": binding.operation_id,
                    "owned_copy_operation_id": binding.owned_copy_operation_id,
                    "child": child.model_dump(mode="json"),
                    "owned_library": "CmosLongMosSizingFixture",
                    "owned_before_view_tree_sha256": binding.owned_before_view_tree_sha256,
                    "owned_before_testbench_tree_sha256": (
                        binding.owned_before_testbench_tree_sha256
                    ),
                    "source_preservation_sha256": binding.source_preservation_sha256,
                    "native_safety_sha256": _sha(safety),
                }
            ],
        }
    )
    path = tmp_path / "registration.json"
    path.write_bytes(enrollment)
    context = SimpleNamespace(
        context_sha256="4" * 64,
        resource_domain_sha256="1" * 64,
        binding=SimpleNamespace(
            context_id="owned-sizing",
            environment_sha256="2" * 64,
            runner_sha256="3" * 64,
            pmos_default_change_binding=path,
            pmos_default_change_sha256=_sha(enrollment),
            analysis_journal=tmp_path / "analysis.db",
            sweep_journal=tmp_path / "sweep.db",
        ),
        lock_path=tmp_path / "resource.lock",
        contracts=SimpleNamespace(
            environment=SimpleNamespace(
                paths=SimpleNamespace(managed_root="/fixture/managed"),
            )
        ),
    )
    monkeypatch.setattr(registered_mos_edit_server, "select_context", lambda _: context)
    monkeypatch.setattr(sizing, "_ssh", lambda _: ["fixture"])
    phases = []
    captures = []

    def run_fixed(argv, payload, _, **bounds):
        assert payload.startswith(guest) and bounds == {"timeout": 60, "limit": 524_288}
        envelope = json.loads(payload[len(guest) :])
        scope_raw = base64.b64decode(envelope["scope_base64"], validate=True)
        scope = json.loads(scope_raw)
        ack = json.loads(base64.b64decode(envelope["authority_base64"], validate=True))
        bundle = base64.b64decode(envelope["sizing_base64"], validate=True)
        program = json.loads(bundle)
        assert _sha(bundle) == scope["sizing_sha256"]
        rendered, child_asset = guest_contract.read_sizing_assets(guest_support, envelope, scope)
        assert b'"250n"' in rendered and child_asset == hash_child
        assert _sha(rendered) == program["adapter_sha256"] != _sha(renderer)
        assert scope["route_qualification"]["support"]["adapter_sha256"] == _sha(renderer)
        assert _sha(scope_raw) == argv[-2] == ack["scope_sha256"]
        assert scope["candidate_request"] == {"l": {"value": "250", "unit": "nm"}, "w": None}
        assert ack["owner"] == "C0" and ack["operation_id"] == binding.operation_id
        assert base64.b64decode(envelope["native_safety_base64"], validate=True) == safety
        readback = capture.readback.model_copy(
            update={
                "plan_sha256": scope["subject"]["plan_sha256"],
                "scope_sha256": argv[-2],
            }
        )
        phase = argv[-1]
        if phase == "EDIT_SAVE":
            assert not phases and envelope["previous_receipt_sha256"] is None
            wire = readback.model_dump(mode="json", include=set(NativeMosEditSave.model_fields))
        else:
            assert phases == ["EDIT_SAVE"] and phase == "INDEPENDENT_REOPEN_NETLIST"
            assert envelope["previous_receipt_sha256"] == _sha(captures[0])
            wire = {
                "readback": readback.model_dump(mode="json"),
                "input_base64": base64.b64encode(capture.netlist).decode("ascii"),
                "cdf_frame_base64": base64.b64encode(capture.cdf_frame).decode("ascii"),
            }
        phases.append(phase)
        raw = _canonical(wire)
        captures.append(raw)
        return 0, raw, b""

    monkeypatch.setattr(registered_mos_transport, "run_fixed", run_fixed)
    candidate = {
        "operation_id": binding.operation_id,
        "expected_enrollment_sha256": _sha(enrollment),
        "expected_baseline_sha256": route.baseline.revision_sha256,
        "values": requested.model_dump(mode="json"),
    }
    return context, candidate, slots, phases


@pytest.mark.asyncio
async def test_enrolled_sizing_previews_then_dispatches_once_and_reads_after_restart(enrolled):
    context, candidate, slots, phases = enrolled
    server = create_default_server(operator_mode=True, registered_mos_edit=True)
    inspect = "cadence_inspect_registered_mos_sizing"
    plan = "cadence_plan_registered_mos_sizing"
    apply = "cadence_apply_registered_mos_sizing"
    lookup = "cadence_lookup_registered_mos_sizing"
    assert {tool.name for tool in await server.list_tools()} == {inspect, plan, apply, lookup}
    info = (await server.call_tool(inspect, {})).structured_content
    assert info["current"]["l"] == {"unit": "nm", "value": "100"}
    assert info["support"]["l"]["maximum"] is None
    assert info["admission_l"]["maximum"]["value"] == "250"
    preview = (await server.call_tool(plan, {"request": candidate})).structured_content
    conflict = {**candidate, "values": {"l": {"unit": "nm", "value": "200"}}}
    new_plan = (await server.call_tool(plan, {"request": conflict})).structured_content
    assert new_plan["plan"]["expected"]["l"] == {"unit": "nm", "value": "200"}
    assert (
        new_plan["identity"]["expected_scope_sha256"]
        != preview["identity"]["expected_scope_sha256"]
    )
    assert preview["execution_authorized"] is False
    assert preview["plan"]["expected"]["l"] == {"unit": "nm", "value": "250"}
    request = {"identity": preview["identity"], "candidate": candidate}
    assert (await server.call_tool(lookup, {"request": request["identity"]})).structured_content[
        "outcome"
    ] == "NOT_FOUND"
    assert not (slots / "registered-mos-intent.private.json").exists() and not phases

    outside = {**candidate, "values": {"l": {"unit": "nm", "value": "251"}}}
    wrong_unit = {**candidate, "values": {"l": {"unit": "m", "value": "0.000001"}}}
    for bad in (outside, wrong_unit, {**candidate, "path": "caller-owned"}):
        with pytest.raises(ToolError):
            await server.call_tool(plan, {"request": bad})
    bad_scope = {**request["identity"], "expected_scope_sha256": "0" * 64}
    with pytest.raises(ToolError):
        await server.call_tool(apply, {"request": {**request, "identity": bad_scope}})
    context.context_sha256 = "5" * 64
    with pytest.raises(ToolError):
        await server.call_tool(apply, {"request": request})
    context.context_sha256 = "4" * 64
    assert not phases

    result = (await server.call_tool(apply, {"request": request})).structured_content
    assert result["outcome"] == "VERIFIED"
    assert result["observed"]["l"] == result["expected"]["l"]
    assert not result["analysis_execution_authorized"]
    after = {path: path.read_bytes() for path in slots.iterdir()}
    restarted = create_default_server(operator_mode=True, registered_mos_edit=True)
    equivalent = {**candidate, "values": {"l": {"unit": "um", "value": "0.25"}}}
    replay = (
        await restarted.call_tool(apply, {"request": {**request, "candidate": equivalent}})
    ).structured_content
    assert replay == {**result, "replayed": True, "dispatched_this_call": False}
    retained = (
        await restarted.call_tool(lookup, {"request": request["identity"]})
    ).structured_content
    assert retained["result"] == replay
    with pytest.raises(ToolError):
        await restarted.call_tool(
            apply,
            {"request": {"candidate": conflict, "identity": new_plan["identity"]}},
        )
    assert phases == ["EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST"]
    assert {path: path.read_bytes() for path in slots.iterdir()} == after


def test_sizing_cli_uses_same_enrollment_and_fails_closed(enrolled, capsys, tmp_path):
    context, candidate, _, phases = enrolled
    base = [
        "operator-mos-edit",
        "--settings",
        str(tmp_path / "settings.json"),
        "--context",
        "owned-sizing",
    ]
    assert main([*base, "inspect-sizing"]) == 0
    assert json.loads(capsys.readouterr().out)["operation_ids"] == [candidate["operation_id"]]
    query = tmp_path / "sizing-request.json"
    raw = _canonical(candidate)
    query.write_bytes(raw)
    assert main([*base, "plan-sizing", "--request", str(query), _sha(raw)]) == 0
    assert json.loads(capsys.readouterr().out)["plan"]["requested"]["l"]["value"] == "250"
    assert main([*base, "plan-sizing", "--request", str(query), "0" * 64]) == 2
    assert not phases
    context.binding.pmos_default_change_sha256 = "0" * 64
    with pytest.raises(ConfigurationError):
        create_default_server(operator_mode=True, registered_mos_edit=True)
    context.binding.pmos_default_change_binding = context.binding.pmos_default_change_sha256 = None
    with pytest.raises(ConfigurationError):
        create_default_server(operator_mode=True, registered_mos_edit=True)
