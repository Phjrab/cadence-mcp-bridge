"""Concrete host custody with a bounded fixture transport, no native execution."""

import base64
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_research_bench import _declarative_fixture

from cadence_mcp_bridge import research_generation_provider as host
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.native_runtime import NativeLibrary
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_bench import render_research_bench
from cadence_mcp_bridge.research_circuit import MosBlockStageReceipt
from cadence_mcp_bridge.research_generation_service import (
    ResearchGenerationBinding,
    ResearchGenerationQuery,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


@pytest.fixture
def packet(tmp_path, monkeypatch):
    bench, plan, frames, conditions, dut, full = _declarative_fixture()
    library_path = f"/owned/{plan.output_library}"
    scripts = render_research_bench(
        bench,
        plan,
        frames,
        expected_plan_sha256=canonical_digest(bench),
        owned_library_path=library_path,
    )
    programs = {
        "save": scripts.generate.encode("ascii"),
        "reopen": scripts.reopen.encode("ascii"),
        "netlist": b"reviewed fixed netlist fixture\n",
    }
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    guest = b"reviewed fixed guest fixture\n"
    (tmp_path / host._GUEST_ASSET).write_bytes(guest)
    monkeypatch.setattr(host, "files", lambda name: tmp_path)
    scope = b'{"kind":"generation-fixture"}'
    binding = ResearchGenerationBinding(
        operation_id="11111111-2222-4333-8444-555555555555",
        context_id="registered-research",
        resource_domain_sha256="e" * 64,
        native_manifest_sha256="d" * 64,
        scope_sha256=host._sha(scope),
        plan_sha256=canonical_digest(plan),
        bench_plan_sha256=canonical_digest(bench),
        conditions_sha256=canonical_digest(conditions),
        output_library=plan.output_library,
        owned_library_path=library_path,
        save_program_sha256=host._sha(programs["save"]),
        reopen_program_sha256=host._sha(programs["reopen"]),
        netlist_program_sha256=host._sha(programs["netlist"]),
    )
    pin = canonical_digest(binding)
    authority = _canonical(
        {
            "operation_id": binding.operation_id,
            "binding_sha256": pin,
            "scope_sha256": binding.scope_sha256,
            "approved_phases": list(programs),
            "valid_until_unix": 100,
        }
    )
    for leaf, raw in {
        "plan.private.json": _canonical(plan.model_dump(mode="json")),
        "bench-plan.private.json": _canonical(bench.model_dump(mode="json")),
        "conditions.private.json": _canonical(conditions.model_dump(mode="json")),
        "execution-scope.private.json": scope,
        "c0-exact-ack.private.json": authority,
        **{f"cdf-{pin}.private": raw for pin, raw in frames.items()},
        **{f"{phase}-program.private": raw for phase, raw in programs.items()},
    }.items():
        (evidence / leaf).write_bytes(raw)
    registration = _canonical(
        {
            "schema_version": 1,
            "binding": binding.model_dump(mode="json"),
            "binding_sha256": pin,
            "authority_sha256": host._sha(authority),
            "guest_sha256": host._sha(guest),
            "cdf_sha256": list(frames),
        }
    )
    env = SimpleNamespace(
        paths=SimpleNamespace(workspace_root="/owned", managed_root="/owned/.mcp")
    )
    ctx = SimpleNamespace(
        contracts=SimpleNamespace(environment=env),
        binding=SimpleNamespace(
            context_id=binding.context_id, runner_sha256=binding.native_manifest_sha256
        ),
        resource_domain_sha256=binding.resource_domain_sha256,
    )
    calls, clock = [], [10]
    locked = False

    @contextmanager
    def lock(context):
        nonlocal locked
        assert context is ctx and not locked
        locked = True
        try:
            yield
        finally:
            locked = False

    monkeypatch.setattr(host, "resource_lock", lock)
    monkeypatch.setattr(host, "_ssh", lambda environment: ["fixture"])
    monkeypatch.setattr(host.time, "time", lambda: clock[0])
    library = NativeLibrary(name=plan.output_library, path=library_path, tree_sha256="c" * 64)
    predecessor = None

    def transport(argv, payload, environment, *, timeout, limit):
        nonlocal predecessor
        assert locked and timeout == 60 and limit == 1_048_576
        assert argv[-3] == binding.scope_sha256 and argv[-1] == (predecessor or "''")
        phase = argv[-2]
        calls.append(phase)
        assert payload.startswith(guest)
        envelope = json.loads(payload[len(guest) :])
        assert envelope["binding"] == binding.model_dump(mode="json")
        assert base64.b64decode(envelope["scope_base64"]) == scope
        assert base64.b64decode(envelope["authority_base64"]) == authority
        assert base64.b64decode(envelope["program_base64"]) == programs[phase]
        markers = scripts.save_markers if phase == "save" else scripts.reopen_markers
        stdout = b"" if phase == "netlist" else ("\n".join(markers) + "\n").encode("ascii")
        program = host._sha(programs[phase])
        receipt = MosBlockStageReceipt(
            phase=phase,
            operation_id=binding.operation_id,
            plan_sha256=binding.plan_sha256,
            library=library,
            source_cell=f"{library_path}/{plan.root}",
            source_tree_sha256="b" * 64,
            bench_cell=f"{library_path}/{bench.bench.name}",
            bench_tree_sha256="9" * 64,
            artifact_sha256=host._sha(full if phase == "netlist" else stdout),
            script_sha256=None if phase == "netlist" else program,
        )
        response = _canonical(
            {
                "binding_sha256": pin,
                "scope_sha256": binding.scope_sha256,
                "program_sha256": program,
                "previous_receipt_sha256": predecessor,
                "receipt": receipt.model_dump(mode="json"),
                "stdout_base64": base64.b64encode(stdout).decode("ascii"),
                "dut_netlist_base64": base64.b64encode(dut if phase == "netlist" else b"").decode(
                    "ascii"
                ),
                "full_netlist_base64": base64.b64encode(full if phase == "netlist" else b"").decode(
                    "ascii"
                ),
            }
        )
        predecessor = canonical_digest(receipt)
        return 0, response + b"\n", b""

    monkeypatch.setattr(host, "run_fixed", transport)
    query = ResearchGenerationQuery(operation_id=binding.operation_id, expected_binding_sha256=pin)
    return ctx, registration, evidence, query, calls, clock, transport


def test_concrete_host_dispatch_and_restart_replay(packet):
    ctx, registration, evidence, query, calls, clock, _ = packet
    service = host.registered_research_generation(ctx, registration, evidence)
    assert service.status(query).status == "NOT_SUBMITTED"
    result = service.submit(query)
    assert result.status == "VERIFIED" and not result.replayed
    assert calls == ["save", "reopen", "netlist"]
    before = {p.name: p.read_bytes() for p in evidence.iterdir()}
    clock[0] = 101
    restarted = host.registered_research_generation(ctx, registration, evidence)
    assert restarted.submit(query).replayed
    assert restarted.registration_handoff(query).handoff_sha256 == result.handoff_sha256
    assert calls == ["save", "reopen", "netlist"]
    assert before == {p.name: p.read_bytes() for p in evidence.iterdir()}


@pytest.mark.parametrize("fault", ["timeout", "foreign_predecessor", "wrong_program"])
def test_concrete_host_fails_closed_on_partial_or_foreign_capture(packet, monkeypatch, fault):
    ctx, registration, evidence, query, calls, _, original = packet

    def transport(argv, payload, environment, **kwargs):
        if argv[-2] == "reopen" and fault == "timeout":
            calls.append("reopen")
            raise ValueError("fixture transport timeout")
        exit_code, stdout, stderr = original(argv, payload, environment, **kwargs)
        if argv[-2] == "reopen":
            row = json.loads(stdout)
            key = "previous_receipt_sha256" if fault == "foreign_predecessor" else "program_sha256"
            row[key] = "0" * 64
            stdout = _canonical(row)
        return exit_code, stdout, stderr

    monkeypatch.setattr(host, "run_fixed", transport)
    service = host.registered_research_generation(ctx, registration, evidence)
    result = service.submit(query)
    assert result.status == "OUTCOME_UNKNOWN" and result.completed_phases == ("save",)
    restarted = host.registered_research_generation(ctx, registration, evidence)
    assert restarted.submit(query).status == "OUTCOME_UNKNOWN"
    assert calls == ["save", "reopen"]


def test_concrete_host_never_claims_stale_program_or_orphaned_phase(packet):
    ctx, registration, evidence, query, calls, _, _ = packet
    service = host.registered_research_generation(ctx, registration, evidence)
    path: Path = evidence / "save-program.private"
    path.write_bytes(b"modified")
    with pytest.raises(OperationRejected):
        service.submit(query)
    assert not (evidence / host._CLAIM).exists()
    (evidence / "generation-save-intent.private.json").write_bytes(b"{}")
    with pytest.raises(OperationRejected) as error:
        service.submit(query)
    assert error.value.reason == "research_generation_orphan_capture"
    assert calls == []
