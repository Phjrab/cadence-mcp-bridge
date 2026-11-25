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
from cadence_mcp_bridge._mos_sizing_slot import (
    sizing_scope_template_sha256,
    verify_sizing_slot,
)
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.mos_wl_skill import render_mos_wl_skill
from cadence_mcp_bridge.operator_operations import OperationRejected
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
    policy["support"]["adapter_sha256"] = _sha(renderer)
    policy["support"]["pdk_identity_sha256"] = guest_contract.SIZING_PDK_TREE_SHA256
    policy["support"]["cdf_constraints_sha256"] = _sha(constraints)
    policy["support"]["pdk_identity_sha256"] = guest_contract.SIZING_PDK_TREE_SHA256
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
            mos_dc_evaluation_binding=None,
            mos_dc_evaluation_sha256=None,
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
        assert set(envelope) == {
            "managed_root",
            "scope_base64",
            "authority_base64",
            "baseline_base64",
            "native_safety_base64",
            "support_base64",
            "cdf_collector_base64",
            "sizing_base64",
            "previous_receipt_sha256",
        }
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
        assert "slot_manifest_sha256" not in scope
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
    compare = "cadence_compare_registered_mos_sizing"
    tool_names = {tool.name for tool in await server.list_tools()}
    assert tool_names == {inspect, plan, apply, lookup, compare}
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
    comparison = {"request": {"edits": [request["identity"]]}}
    pending = (await server.call_tool(compare, comparison)).structured_content["rows"][0]
    assert pending["edit_outcome"] == "NOT_FOUND" and pending["analysis_status"] == "NOT_RUN"
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
    compared = (await restarted.call_tool(compare, comparison)).structured_content["rows"][0]
    assert compared["edit_outcome"] == "VERIFIED" and compared["analysis_status"] == "NOT_RUN"
    assert compared["evaluation"]["edit"] == replay and compared["evaluation"]["report"] is None
    for bad_request in (
        {"edits": [request["identity"]] * 2},
        {**comparison["request"], "export": "caller-owned"},
        {"edits": [{**request["identity"], "expected_plan_sha256": "0" * 64}]},
    ):
        with pytest.raises(ToolError):
            await restarted.call_tool(compare, {"request": bad_request})
    with pytest.raises(ToolError):
        await restarted.call_tool(
            apply,
            {"request": {"candidate": conflict, "identity": new_plan["identity"]}},
        )
    assert phases == ["EDIT_SAVE", "INDEPENDENT_REOPEN_NETLIST"]
    assert {path: path.read_bytes() for path in slots.iterdir()} == after


def test_host_envelope_matches_one_immutable_native_slot_for_two_lengths(enrolled, monkeypatch):
    context, candidate, directory, phases = enrolled
    registration_path = context.binding.pmos_default_change_binding
    original = json.loads(registration_path.read_bytes())

    def packet(values, phase="EDIT_SAVE", previous=None):
        service = sizing.selected_mos_sizing(context)
        request = sizing.MosSizingCandidate.model_validate({**candidate, "values": values})
        exact = service._service(request)
        _, payload = exact._provider._prepare(exact._binding, phase, previous)
        guest = files("cadence_mcp_bridge").joinpath("_registered_mos_edit_phase.py").read_bytes()
        envelope = json.loads(payload[len(guest) :])
        scope = json.loads(base64.b64decode(envelope["scope_base64"], validate=True))
        assets = base64.b64decode(envelope["sizing_base64"], validate=True)
        assert envelope["previous_receipt_sha256"] == previous
        return scope, assets, envelope

    values250 = {"l": {"unit": "um", "value": "0.25"}}
    scope, _, exact_packet = packet(values250)
    assert "slot_manifest_sha256" not in scope
    assert "slot_verifier_base64" not in exact_packet
    template = render_mos_wl_skill("nmos1v", length_nm="250").replace(
        b'"250n"', b'"@LENGTH_NM@"'
    )
    manifest = _canonical(
        {
            "schema_version": 1,
            "owner": "C0",
            "route": "registered_mos_sizing",
            "operation_id": candidate["operation_id"],
            "valid_until_unix": original["valid_until_unix"],
            "scope_template_sha256": sizing_scope_template_sha256(scope),
            "length_nm_min": "200",
            "length_nm_max": "250",
            "renderer_template_sha256": _sha(template),
            "adapter_template": template.decode("ascii"),
            "hash_child_sha256": original["hash_child_sha256"],
        }
    )
    original["slots"][0]["slot_manifest_sha256"] = _sha(manifest)
    updated = _canonical(original)
    registration_path.write_bytes(updated)
    context.binding.pmos_default_change_sha256 = _sha(updated)
    candidate["expected_enrollment_sha256"] = _sha(updated)
    scope200, assets200, packet200 = packet({"l": {"unit": "nm", "value": "200"}})
    scope250, assets250, packet250 = packet(values250)
    reopen_scope, reopen_assets, reopen = packet(values250, "INDEPENDENT_REOPEN_NETLIST", "a" * 64)
    assert _sha(manifest) == scope200["slot_manifest_sha256"] == scope250["slot_manifest_sha256"]
    assert scope200["subject"]["plan_sha256"] != scope250["subject"]["plan_sha256"]
    assert assets200 != assets250
    assert (reopen_scope, reopen_assets) == (scope250, assets250)
    verifier = files("cadence_mcp_bridge").joinpath("_mos_sizing_slot.py").read_bytes()
    for envelope in (packet200, packet250, reopen):
        assert set(envelope) == {*exact_packet, "slot_verifier_base64"}
        assert guest_contract.read_encoded(envelope, "slot_verifier", 16384) == verifier
    assert _sha(verifier) == guest_contract.SIZING_SLOT_VERIFIER_SHA256
    for scope, assets in ((scope200, assets200), (scope250, assets250)):
        length = scope["candidate_request"]["l"]["value"]
        assert verify_sizing_slot(manifest, scope, assets, time.time()) == length
    with pytest.raises(ValueError):
        verify_sizing_slot(manifest, scope250, assets200, time.time())
    with monkeypatch.context() as patch:
        patch.setattr(guest_contract, "SIZING_SLOT_VERIFIER_SHA256", "0" * 64)
        with pytest.raises(OperationRejected) as mismatch:
            packet(values250)
        assert mismatch.value.reason == "registered_mos_sizing_asset"
        patch.delattr(guest_contract, "SIZING_SLOT_VERIFIER_SHA256")
        with pytest.raises(ValueError, match="does not support finite slot verification"):
            packet(values250)
    assert not phases and not (directory / "registered-mos-intent.private.json").exists()


def test_pmos_total_width_uses_distinct_fixed_callback_child(enrolled):
    context, candidate, directory, phases = enrolled
    path = context.binding.pmos_default_change_binding
    enrollment = json.loads(path.read_bytes())
    route = enrollment["route_qualification"]
    target = route["target"]
    target["instance"].update(instance_path="DUT/MP", master_cell="pmos1v", property_name="w")
    target.update(
        netlist_path="DUT/MP",
        netlist_model="gpdk090_pmos1v",
        netlist_terminals=["vout", "vin", "vdd", "vdd"],
    )
    for key, value in (("w", "350n"), ("fw", "350n"), ("model", "gpdk090_pmos1v")):
        route["before"][key].update(oa_value=value, cdf_value=value)
    route["support"].update(w={}, l=None)

    baseline_path = directory.parent / "baseline-input.private.scs"
    baseline = baseline_path.read_bytes().replace(
        b"MN (vout vin vss vss) gpdk090_nmos1v w=(120n)",
        b"MP (vout vin vdd vdd) gpdk090_pmos1v w=(350n)",
    )
    baseline_path.write_bytes(baseline)
    route["baseline"]["netlist_sha256"] = _sha(baseline)

    package = files("cadence_mcp_bridge")
    guest = package.joinpath("_registered_mos_edit_phase.py").read_bytes()
    width_child = package.joinpath("_mos_pmos_width_callback.py").read_bytes()
    original_child_pin = enrollment["hash_child_sha256"]
    width = {"value": "3000", "unit": "nm"}
    enrollment.update(
        admitted_l=None,
        admitted_w={"minimum": width, "maximum": width},
        width_field="w",
        hash_child_sha256=_sha(width_child),
    )

    def resolve(document):
        raw = _canonical(document)
        path.write_bytes(raw)
        context.binding.pmos_default_change_sha256 = _sha(raw)
        return sizing.selected_mos_sizing(context)

    registered = resolve(enrollment)
    request = sizing.MosSizingCandidate.model_validate({
        **candidate,
        "expected_enrollment_sha256": registered.enrollment_sha256,
        "values": {"w": width},
    })
    service = registered._service(request)
    assert service.plan.current.w.value == "350"
    assert service.plan.expected.model_dump(mode="json") == {
        "w": width, "l": {"value": "100", "unit": "nm"},
    }
    assert service.plan.changed == ("w",)
    equivalent = sizing.MosSizingCandidate.model_validate({
        **request.model_dump(mode="json"), "values": {"w": {"value": "3", "unit": "um"}},
    })
    assert registered.plan(equivalent).identity == service.identity
    for phase, prior in (("EDIT_SAVE", None), ("INDEPENDENT_REOPEN_NETLIST", "a" * 64)):
        _, payload = service._provider._prepare(service._binding, phase, prior)
        envelope = json.loads(payload[len(guest) :])
        scope = json.loads(base64.b64decode(envelope["scope_base64"], validate=True))
        adapter, child = guest_contract.read_sizing_assets(guest_support, envelope, scope)
        assert child == width_child and _sha(child) != original_child_pin
        assert adapter == render_mos_wl_skill("pmos1v", width_nm="3000", width_field="w")
        assert 'slot_verifier_base64' not in envelope and "slot_manifest_sha256" not in scope
        assert envelope["previous_receipt_sha256"] == prior
    with pytest.raises(OperationRejected) as mismatch:
        resolve({**enrollment, "hash_child_sha256": original_child_pin})
    assert mismatch.value.reason == "registered_mos_sizing_guest_contract"
    with pytest.raises(OperationRejected) as wrong_axis:
        resolve({**enrollment, "width_field": "fw"})
    assert wrong_axis.value.reason == "registered_mos_sizing_pmos_width_enrollment"
    with pytest.raises(OperationRejected) as wrong_mode:
        resolve({
            **enrollment,
            "slots": [{**enrollment["slots"][0], "slot_manifest_sha256": "a" * 64}],
        })
    assert wrong_mode.value.reason == "registered_mos_sizing_pmos_width_enrollment"
    assert not phases and not (directory / "registered-mos-intent.private.json").exists()


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
    preview = json.loads(capsys.readouterr().out)
    assert preview["plan"]["requested"]["l"]["value"] == "250"
    compare = tmp_path / "compare-request.json"
    comparison = _canonical({"edits": [preview["identity"]]})
    compare.write_bytes(comparison)
    assert main([*base, "compare-sizing", "--request", str(compare), _sha(comparison)]) == 0
    retained = json.loads(capsys.readouterr().out)["rows"][0]
    assert retained["edit_outcome"] == "NOT_FOUND" and retained["analysis_status"] == "NOT_RUN"
    assert main([*base, "plan-sizing", "--request", str(query), "0" * 64]) == 2
    assert not phases
    context.binding.pmos_default_change_sha256 = "0" * 64
    with pytest.raises(ConfigurationError):
        create_default_server(operator_mode=True, registered_mos_edit=True)
    context.binding.pmos_default_change_binding = context.binding.pmos_default_change_sha256 = None
    with pytest.raises(ConfigurationError):
        create_default_server(operator_mode=True, registered_mos_edit=True)
