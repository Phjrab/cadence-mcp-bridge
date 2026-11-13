"""Exercise the registered service and evidence chain without contacting a VM."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from test_runtime_context import make_settings

from cadence_mcp_bridge import pmos_default_service as service
from cadence_mcp_bridge._pmos_default_phase import BASELINE, DEFAULTS, netlist_marker
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    MosWidthQualification,
    plan_mos_width_change,
)
from cadence_mcp_bridge.runtime_context import RuntimeRejected, load_runtime, resource_lock

BASELINE_INPUT = b"""simulator lang=spectre
global 0
parameters m2_vin=0
subckt InvLong vdd vin vout vss
MP (vout vin vdd vdd) gpdk090_pmos1v w=(350n) l=100n as=98f ad=98f ps=1.26u pd=1.26u \\
    m=(1)*(1) simM=(1)*(1)
ends InvLong
DUT (vdd vin vout 0) InvLong
"""
CHILD_LIBRARY = "CmosLongPDefaultFixture1"


def frame() -> bytes:
    lines = [
        "C1_PMOS_OVERRIDE_REVERSION|1",
        f"TB|REOPENED|{CHILD_LIBRARY}|InvLong|symbol",
        "COPY|SOURCE_AND_CHILD|TOPOLOGY_AND_PROPERTIES_EQUAL",
    ]
    for stage in ("BASE", "COPY_BASELINE", "BEFORE_SAVE", "REOPENED"):
        for name, units, default in DEFAULTS:
            old = "350n" if name == "fw" else BASELINE.get(name, default)
            value = old if stage == "COPY_BASELINE" else default
            kind = "baseCellData" if stage == "BASE" else "instData"
            lines.append(f"CDF|{stage}|{name}|{kind}|{units}|{value}")
            removed = name in service._OVERRIDES
            if stage == "COPY_BASELINE" and removed:
                lines.append(f"DEFAULT|COPY_BASELINE|{name}|{default}")
            if stage != "BASE":
                oa = (
                    "ABSENT|-|-"
                    if removed and stage != "COPY_BASELINE"
                    else f"EXPLICIT|string|{value}"
                )
                lines.append(f"OA|{stage}|{name}|{oa}")
    lines += ["COPY|REOPENED|FIXED_TOPOLOGY_AND_PROPERTIES_EQUAL", "COMPLETE"]
    return ("\n".join(lines) + "\n").encode("ascii")


def test_netlist_marker_matches_byte_lines_amid_non_ascii_ocean_output():
    scope = "a" * 64
    diagnostic = "74b1b7fd-b977-4a46-8bdd-24929835ecf9"
    marker = netlist_marker(scope, diagnostic)
    assert isinstance(marker, bytes)
    output = (
        b"\xff Cadence banner\nMCP_GENERIC_ADE_NETLIST|"
        + scope.encode("ascii")
        + b"|"
        + diagnostic.encode("ascii")
        + b"\n\xa9"
    )
    assert output.splitlines().count(marker) == 1


def write(path: Path, value: object) -> str:
    raw = service._canonical(value)
    path.write_bytes(raw)
    return service._sha(raw)


@pytest.fixture
def packet(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    context = load_runtime(settings)[0]
    directory = tmp_path / "private"
    directory.mkdir()
    monkeypatch.setattr(service, "_BASELINE_NETLIST", service._sha(BASELINE_INPUT))
    source = dict(
        workspace_id="layout-mvp",
        design_id="cmos-long-inverter",
        revision_id="long-r1",
        source_baseline_sha256=service._BASELINE_REVISION,
    )
    old, new = (dict(value=value, unit="nm") for value in ("350", "120"))
    derived = [
        dict(
            before=dict(property_name=name, value=before),
            after=dict(property_name=name, value=after),
        )
        for name, before, after in (
            ("fw", "350n", "120n"),
            ("as", "98f", "69.6f"),
            ("ad", "98f", "69.6f"),
            ("ps", "1.26u", "1.16u"),
            ("pd", "1.26u", "1.16u"),
        )
    ]
    pins = {
        "cdf": b"synthetic accepted CDF frame",
        "legal-value": b"synthetic accepted CDF frame",
        "update-route": b"synthetic accepted receipt envelope",
    }
    for name, raw in pins.items():
        (directory / f"{name}-evidence.private").write_bytes(raw)
    monkeypatch.setattr(service, "_SOURCE9_CDF_FRAME", service._sha(pins["cdf"]))
    monkeypatch.setattr(service, "_SOURCE9_REOPEN_ENVELOPE", service._sha(pins["update-route"]))
    pins = {name: service._sha(raw) for name, raw in pins.items()}
    qualification = MosWidthQualification.model_validate_json(
        service._canonical(
            dict(
                baseline=dict(
                    revision=source,
                    revision_sha256=service._BASELINE_LIBRARY,
                    testbench_revision_sha256=service._BASELINE_TB,
                    fixed_conditions_sha256=service._BASELINE_CONDITIONS,
                    netlist_sha256=service._BASELINE_NETLIST,
                ),
                target=dict(
                    instance=dict(
                        instance_path="DUT/MP",
                        master_library="gpdk090",
                        master_cell="pmos1v",
                        master_view="symbol",
                        property_name="w",
                    )
                ),
                old=old,
                expected=new,
                fingers=1,
                multiplicity=1,
                derived=derived,
                cdf_evidence_sha256=pins["cdf"],
                legal_value_evidence_sha256=pins["legal-value"],
                update_route_evidence_sha256=pins["update-route"],
            )
        )
    )
    revision = qualification.baseline.revision.model_copy(
        update=dict(
            revision_id="fixture-child",
            parent_revision_id="long-r1",
            parent_revision_sha256=service._BASELINE_LIBRARY,
        )
    )
    plan = plan_mos_width_change(qualification, "fixture-child", revision, qualification.expected)
    package = Path(service.__file__).parent
    scope = dict(
        schema_version=1,
        operation_id=str(uuid4()),
        diagnostic_netlist_id=str(uuid4()),
        context_id=context.binding.context_id,
        resource_domain_sha256=context.resource_domain_sha256,
        environment_sha256=context.binding.environment_sha256,
        native_manifest_sha256=context.binding.runner_sha256,
        layout_manifest_sha256="1" * 64,
        worker_sha256="2" * 64,
        valid_until_unix=int(time.time()) + 120,
        phase_sha256=service._sha((package / "_pmos_default_phase.py").read_bytes()),
        skill_sha256=service._sha((package / "_pmos_default_reopen.ocn").read_bytes()),
        service_sha256=service._sha(Path(service.__file__).read_bytes()),
        qualification=qualification.model_dump(mode="json"),
        plan=plan.model_dump(mode="json"),
        plan_sha256=plan.plan_sha256,
        phases=list(service._PHASES),
        only_override_names=list(service._OVERRIDES),
        old_jobs=113,
        old_jobs_sha256="3" * 64,
        counter=dict(campaign_id="fixture", count=132, result_reserved_bytes=16258170880),
        counter_sha256="4" * 64,
        protected_sha256="5" * 64,
        candidate_library=CHILD_LIBRARY,
    )
    scope_sha = write(directory / "execution-scope.private.json", scope)
    registration = tmp_path / "registration.json"
    registration_sha = write(
        registration,
        dict(
            schema_version=1,
            context_id=context.binding.context_id,
            resource_domain_sha256=context.resource_domain_sha256,
            scope_sha256=scope_sha,
            evidence_directory=str(directory),
        ),
    )
    doc = json.loads(settings.read_bytes())
    doc["contexts"][0].update(
        pmos_default_change_binding=str(registration), pmos_default_change_sha256=registration_sha
    )
    write(settings, doc)
    (directory / "baseline-input.private.scs").write_bytes(BASELINE_INPUT)
    write(
        directory / "c0-exact-ack.private.json",
        dict(
            owner="C0",
            scope_sha256=scope_sha,
            approved_actions=list(service._PHASES),
            valid_until_unix=scope["valid_until_unix"],
        ),
    )
    request = PmosDefaultChangeRequest(
        operation_id=scope["operation_id"],
        expected_plan_sha256=plan.plan_sha256,
        expected_scope_sha256=scope_sha,
    )
    monkeypatch.setattr(service, "_ssh", lambda _environment: ["ssh.exe"])
    return directory, settings, scope, request


def fake_transport(monkeypatch, packet, *, broken: str | None = None):
    directory, _, scope, request = packet
    calls = []
    last = {}

    def run(argv, payload, environment, *, timeout, limit):
        assert argv[-1] == request.expected_scope_sha256 and timeout == 60 and limit == 131072
        assert (directory / "execution-intent.private.json").is_file()
        envelope = json.loads(payload)
        phase = envelope["phase"]
        assert envelope["previous"] == last
        assert (directory / f"{phase}-intent.private.json").is_file()
        calls.append(phase)
        if broken == phase:
            return 1, b"", b"fixture failure"
        if broken == "oversize":
            return 1, b"x" * 65537, b""
        row = dict(
            status="VERIFIED",
            phase=phase,
            operation_id=request.operation_id,
            scope_sha256=request.expected_scope_sha256,
            old_jobs=113,
            current_jobs=114,
            ledger=scope["counter"],
            source_preservation_sha256="6" * 64,
            owned_tree_sha256="7" * 64,
            view_tree_sha256=dict(dut="8" * 64, symbol="9" * 64, tb="a" * 64),
            job_logical_bytes=4096,
            job_allocated_bytes=8192,
            callback_executions=0,
            spectre_calls=0,
            simulations=0,
            reservations=0,
        )
        if phase == "revert":
            raw = frame()
            if broken == "frame":
                raw = raw.replace(
                    b"OA|REOPENED|w|ABSENT|-|-", b"OA|REOPENED|w|EXPLICIT|string|120n"
                )
            row["frame_sha256"] = service._sha(raw)
            row["frame_base64"] = base64.b64encode(raw).decode("ascii")
        else:
            child = "Grel_" + scope["diagnostic_netlist_id"].replace("-", "_")
            headers = (
                f"// Design library name: MCP_GREL_Work\n// Design cell name: {child}\n"
                f"// Library name: {CHILD_LIBRARY}\n"
            )
            raw = headers.encode() + BASELINE_INPUT
            for old, new in ((b"350n", b"120n"), (b"98f", b"69.6f"), (b"1.26u", b"1.16u")):
                raw = raw.replace(old, new)
            if broken == "revision":
                row["view_tree_sha256"]["tb"] = "b" * 64
            if broken == "topology":
                raw = raw.replace(b"(vout vin vdd vdd)", b"(vout vin vdd vss)")
            row.update(
                netlist_sha256=service._sha(raw),
                effective_input_base64=base64.b64encode(raw).decode("ascii"),
                diagnostic_netlist_id=scope["diagnostic_netlist_id"],
            )
        body = {key: value for key, value in row.items() if not key.endswith("_base64")}
        row["receipt_sha256"] = service._sha(service._canonical(body))
        last[phase] = row["receipt_sha256"]
        return 0, service._canonical(row), b""

    monkeypatch.setattr(service, "run_fixed", run)
    return calls


def test_verified_once_and_replayed_without_authority(packet, monkeypatch):
    directory, settings, _, request = packet
    calls = fake_transport(monkeypatch, packet)
    first = service.registered_pmos_default_change(load_runtime(settings)[0]).apply(request)
    assert first.outcome == "VERIFIED" and first.dispatched_this_call is True
    assert first.reopen_receipt_sha256 and first.netlist_receipt_sha256 and first.netlist_sha256
    (directory / "c0-exact-ack.private.json").unlink()
    (directory / "cdf-evidence.private").unlink()
    snapshot = {p.name: p.read_bytes() for p in directory.iterdir()}
    replay = service.registered_pmos_default_change(load_runtime(settings)[0]).apply(request)
    assert replay == first.model_copy(update=dict(replayed=True, dispatched_this_call=False))
    assert calls == ["revert", "netlist"]
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == snapshot


@pytest.mark.parametrize(
    ("broken", "expected_calls", "reopened"),
    [
        ("revert", ["revert"], False),
        ("frame", ["revert"], False),
        ("netlist", ["revert", "netlist"], True),
        ("revision", ["revert", "netlist"], True),
        ("topology", ["revert", "netlist"], True),
    ],
)
def test_unverified_phase_retains_only_verified_evidence(
    packet, monkeypatch, broken, expected_calls, reopened
):
    directory, settings, _, request = packet
    calls = fake_transport(monkeypatch, packet, broken=broken)
    context = load_runtime(settings)[0]
    for replayed in (False, True):
        result = service.registered_pmos_default_change(context).apply(request)
        assert result.outcome == "OUTCOME_UNKNOWN" and result.replayed is replayed
        assert bool(result.reopen_receipt_sha256) is reopened
        assert result.netlist_receipt_sha256 is None and result.netlist_sha256 is None
    assert not (directory / "verified.private.json").exists() and calls == expected_calls


@pytest.mark.parametrize("state", ["wrong_id", "expired", "corrupt", "orphan", "busy"])
def test_no_dispatch_before_claim(packet, monkeypatch, state):
    directory, settings, _, request = packet
    calls = fake_transport(monkeypatch, packet)
    context = load_runtime(settings)[0]
    native = service.registered_pmos_default_change(context)
    intent = directory / "execution-intent.private.json"
    if state == "wrong_id":
        with pytest.raises(OperationRejected) as error:
            native.apply(request.model_copy(update=dict(operation_id=str(uuid4()))))
        assert error.value.reason == "pmos_default_change_identity_mismatch"
    elif state == "expired":
        ack = directory / "c0-exact-ack.private.json"
        value = json.loads(ack.read_bytes())
        write(ack, {**value, "valid_until_unix": 1})
        with pytest.raises(OperationRejected) as error:
            native.apply(request)
        assert error.value.reason == "pmos_default_change_authority"
    elif state == "busy":
        with resource_lock(context), pytest.raises(RuntimeRejected):
            native.apply(request)
    elif state == "corrupt":
        intent.write_bytes(b"{")
        assert native.apply(request).outcome == "OUTCOME_UNKNOWN"
        assert intent.read_bytes() == b"{"
    else:
        orphan = directory / "netlist-intent.private.json"
        orphan.write_bytes(b"{}")
        assert native.apply(request).outcome == "OUTCOME_UNKNOWN"
        assert orphan.read_bytes() == b"{}"
    assert not calls
    if state != "corrupt":
        assert not intent.exists()


def test_response_above_capture_cap_retains_scalar_failure(packet, monkeypatch):
    directory, settings, _, request = packet
    calls = fake_transport(monkeypatch, packet, broken="oversize")
    context = load_runtime(settings)[0]
    result = service.registered_pmos_default_change(context).apply(request)
    assert result.outcome == "OUTCOME_UNKNOWN"
    evidence = json.loads((directory / "revert-execution.private.json").read_bytes())
    assert evidence == dict(
        status="RESPONSE_LIMIT_EXCEEDED",
        exit_code=1,
        stdout_bytes=65537,
        stdout_sha256=service._sha(b"x" * 65537),
        stderr_bytes=0,
        stderr_sha256=service._sha(b""),
    )
    assert not (directory / "revert-stdout.private.json").exists()
    replay = service.registered_pmos_default_change(context).apply(request)
    assert replay.replayed and replay.dispatched_this_call is False and calls == ["revert"]


def test_scope_rebuild_rejects_forged_qualification(packet):
    directory, settings, scope, _ = packet
    changed = dict(scope["plan"], qualification_sha256="f" * 64)
    scope.update(
        plan=changed,
        plan_sha256=ChangePlan.model_validate_json(service._canonical(changed)).plan_sha256,
    )
    raw = service._canonical(scope)
    with pytest.raises(ValueError, match="exact Source9"):
        service._Scope.model_validate_json(raw)
    (directory / "execution-scope.private.json").write_bytes(raw)
    with pytest.raises(OperationRejected):
        service.registered_pmos_default_change(load_runtime(settings)[0])


def test_scope_rejects_self_consistent_unanchored_route_evidence(packet):
    _, _, scope, _ = packet
    original = service._Scope.model_validate_json(service._canonical(scope))
    altered = original.qualification.model_copy(update={"update_route_evidence_sha256": "f" * 64})
    revised = plan_mos_width_change(
        altered,
        original.plan.candidate_id,
        original.plan.candidate_revision,
        original.plan.requested,
    )
    scope.update(
        qualification=altered.model_dump(mode="json"),
        plan=revised.model_dump(mode="json"),
        plan_sha256=revised.plan_sha256,
    )
    with pytest.raises(ValueError, match="exact Source9"):
        service._Scope.model_validate_json(service._canonical(scope))


def test_legacy_context_hash_and_registration_input_guards(tmp_path):
    settings = make_settings(tmp_path)
    old = load_runtime(settings)[0]
    document = json.loads(settings.read_bytes())
    binding = document["contexts"][0]
    for name in (
        "native_provider_binding",
        "native_provider_sha256",
        "operator_grant",
        "operator_grant_sha256",
        "native_specifications",
        "native_specifications_sha256",
        "layout_provider_binding",
        "layout_provider_sha256",
    ):
        binding[name] = None
    encoded = json.dumps(
        dict(binding=binding, resource_domain=old.resource_domain_sha256),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert old.context_sha256 == hashlib.sha256(encoded).hexdigest()
    with pytest.raises(OperationRejected) as missing:
        service.registered_pmos_default_change(old)
    assert missing.value.reason == "pmos_default_change_not_registered"
    registration = tmp_path / "operator.json"
    digest = write(registration, {})
    binding.update(pmos_default_change_binding=str(registration), pmos_default_change_sha256=digest)
    write(settings, document)
    updated = load_runtime(settings)[0]
    assert updated.context_sha256 != old.context_sha256
    assert (
        updated.resource_domain_sha256 == old.resource_domain_sha256
        and updated.lock_path == old.lock_path
    )
    binding["analysis_journal"] = str(registration)
    write(settings, document)
    with pytest.raises(RuntimeRejected) as collision:
        load_runtime(settings)
    assert collision.value.reason == "journal_contract_collision"
    binding["analysis_journal"] = str(old.binding.analysis_journal)
    binding["pmos_default_change_binding"] = registration.name
    write(settings, document)
    with pytest.raises(RuntimeRejected) as relative:
        load_runtime(settings)
    assert relative.value.reason == "absolute_pmos_default_change_binding_required"
    binding["pmos_default_change_binding"] = str(registration)
    write(settings, document)
    registration.write_bytes(b'{"v":1,"v":2}')
    with pytest.raises(RuntimeRejected) as drift:
        load_runtime(settings)
    assert drift.value.reason == "stale_pmos_default_change_binding_digest"
    binding["pmos_default_change_sha256"] = service._sha(registration.read_bytes())
    write(settings, document)
    with pytest.raises(RuntimeRejected):
        load_runtime(settings)
    del binding["pmos_default_change_sha256"]
    write(settings, document)
    with pytest.raises(RuntimeRejected):
        load_runtime(settings)
