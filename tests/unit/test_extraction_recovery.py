"""Recovery scope/replay and disposable POSIX extraction tests, never Cadence."""

import copy
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_native_gate import confirmed_domain, qualified, root
from test_operator_operations import operator as operator_fixture
from test_runtime_context import make_settings

from cadence_mcp_bridge import _native_copy as copying
from cadence_mcp_bridge import _native_eda_worker as eda
from cadence_mcp_bridge import _native_operations as operations
from cadence_mcp_bridge import _native_recovery as recovery
from cadence_mcp_bridge import _native_rendering as rendering
from cadence_mcp_bridge import _operator_confirmation as confirmation
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import _storage_worker as storage
from cadence_mcp_bridge.__main__ import build_parser, main
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.extraction_recovery import ExtractionRecoveryService, RecoveryPlan
from cadence_mcp_bridge.operator_lifecycle import ProviderObservation
from cadence_mcp_bridge.operator_operations import OperationRejected, prepare_plan
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["confirmed_domain", "qualified", "root", "operator_fixture"]


@pytest.fixture
def host_plan(operator_fixture):
    context, grant, request, _ = operator_fixture
    grant = grant.model_copy(update={"actions": ("recover_extraction",)})
    digest = canonical_digest(grant)
    normal = prepare_plan(context, grant, digest, request, int(time.time()),
                          action="recover_extraction")
    source = str(uuid4())
    plan = RecoveryPlan.model_validate_json(json.dumps({
        **normal.model_dump(mode="json"),
        "recovery": {"original_operation_id": source, "original_plan_sha256": "a" * 64,
                     "original_tree_fingerprint": "b" * 64},
    }))
    return context, grant, request, plan


def test_recovery_only_grant_does_not_authorize_simulation(host_plan):
    context, grant, request, plan = host_plan
    with pytest.raises(OperationRejected) as failure:
        prepare_plan(context, grant, canonical_digest(grant), request, int(time.time()))
    assert failure.value.reason == "authority_scope_denied"
    assert "recovery" not in prepare_plan(
        context, grant, canonical_digest(grant), request, int(time.time()),
        action="recover_extraction",
    ).model_dump(mode="json")
    assert plan.plan_sha256 != plan.recovery.original_plan_sha256


def service_with_provider(host_plan, provider):
    context, grant, _, _ = host_plan
    service = object.__new__(ExtractionRecoveryService)
    service.native = SimpleNamespace(
        context=context, grant=grant, grant_sha256=canonical_digest(grant), provider=provider,
        current=lambda: None,
        lifecycle=SimpleNamespace(store=AnalysisStore(context.binding.analysis_journal)),
    )
    return service


@pytest.mark.asyncio
async def test_repeated_recovery_lookup_never_authorizes_or_dispatches(host_plan):
    _, _, _, plan = host_plan
    op = str(uuid4())
    observed = ProviderObservation.model_validate_json(json.dumps({
        "operation_id": op, "plan_sha256": plan.plan_sha256,
        "resource_domain_sha256": plan.resource_domain_sha256, "ledger_ref": plan.ledger_ref,
        "progress": {"phase": "DISPATCHED", "remote_revision": 2,
                     "provider_receipt_sha256": "f" * 64},
    }))
    calls = []

    async def lookup(identity, actual):
        calls.append("lookup")
        assert identity == op and actual == plan
        return observed

    service = service_with_provider(host_plan, SimpleNamespace(lookup=lookup))
    # No authorize/accept methods exist: neither can be called on replay.
    for _ in range(3):
        assert await service.observe(op, plan, submit=True) == observed
    assert calls == ["lookup"] * 3
    with pytest.raises(OperationRejected) as failure:
        await service.observe(plan.recovery.original_operation_id, plan, submit=True)
    assert failure.value.reason == "recovery_identity_must_be_distinct"


@pytest.mark.asyncio
async def test_recovery_transport_uncertainty_is_not_resent(host_plan):
    _, _, _, plan = host_plan
    calls = []

    async def lookup(*args):
        calls.append("lookup")
        return None

    async def authorize(*args):
        calls.append("authorize")
        return SimpleNamespace(check=lambda *args: None)

    async def observe(*args):
        calls.append("recover")
        raise OperationRejected("native_provider_transport_unknown")

    provider = SimpleNamespace(lookup=lookup, authorize=authorize, _observation=observe)
    service = service_with_provider(host_plan, provider)
    operation_id = str(uuid4())
    with pytest.raises(OperationRejected) as failure:
        await service.observe(operation_id, plan, submit=True)
    assert failure.value.reason == "native_provider_transport_unknown"
    assert calls == ["lookup", "authorize", "recover"]
    # New-process retry must retain an absent remote outcome as unknown, rather
    # than sending recovery again or adopting this marker as a simulation.
    restarted = service_with_provider(host_plan, provider)
    for submit in (False, True):
        with pytest.raises(OperationRejected) as failure:
            await restarted.observe(operation_id, plan, submit=submit)
        assert failure.value.reason == "recovery_local_intent_unknown_no_resend"
    assert calls == ["lookup", "authorize", "recover", "lookup", "lookup"]
    with pytest.raises(InvalidInputError, match="not admitted"):
        restarted.native.lifecycle.store.admit_operation(operation_id, plan)


def test_submit_requires_explicit_experimental_switch():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["operator-recovery", "submit", "--settings", "s", "--context", "c",
                           "--plan", "p", "--expected-plan-sha256", "a" * 64,
                           "--operation-id", str(uuid4())])


@pytest.mark.parametrize("context_index", [0, 1])
@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize("reserved_name", [
    "analysis_journal", "sweep_journal", "analysis-wal", "analysis-shm", "analysis-journal",
    "sweep-wal", "sweep-shm", "sweep-journal", "lock", "settings", "design_registry",
])
def test_recovery_plan_reserves_all_context_state_before_provider_contact(
    tmp_path, monkeypatch, capsys, context_index, alias, reserved_name,
):
    settings = make_settings(tmp_path)
    if alias:
        runtime = json.loads(settings.read_bytes())
        for entry in runtime["contexts"]:
            for field in ("analysis_journal", "sweep_journal"):
                journal = Path(entry[field])
                intermediate = journal.parent / "alias"
                intermediate.mkdir(exist_ok=True)
                entry[field] = str(intermediate / ".." / journal.name)
        settings.write_text(json.dumps(runtime))
    contexts = load_runtime(settings)
    context = contexts[context_index]
    if reserved_name == "lock":
        output = context.lock_path
    elif reserved_name == "settings":
        output = settings
    elif "-" in reserved_name:
        journal, suffix = reserved_name.split("-", 1)
        output = Path(str(getattr(context.binding, journal + "_journal")) + "-" + suffix)
    else:
        output = getattr(context.binding, reserved_name)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    def no_provider(*args):
        raise AssertionError("reserved output must reject before constructing the provider")

    monkeypatch.setattr(
        "cadence_mcp_bridge.extraction_recovery.ExtractionRecoveryService", no_provider,
    )
    assert main([
        "operator-recovery", "plan", "--settings", str(settings), "--context", "context-1",
        "--request", str(tmp_path / "not-read.json"), "--original-operation-id", str(uuid4()),
        "--original-plan-sha256", "a" * 64, "--output", str(output),
    ]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "recovery_plan_output_reserved"
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_recovery_plan_export_preserves_inputs_and_rejects_existing_output_before_contact(
    operator_fixture, host_plan, tmp_path, monkeypatch, capsys,
):
    context, _, request, settings = operator_fixture
    plan = host_plan[3]
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json())
    output = tmp_path / "new-recovery-plan.json"
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    calls = []

    class SourceProvider:
        def __init__(self, selected):
            assert selected.binding.context_id == context.binding.context_id

        async def plan(self, requested, original_id, original_digest):
            calls.append("source_lookup")
            assert requested == request
            assert original_id == plan.recovery.original_operation_id
            assert original_digest == plan.recovery.original_plan_sha256
            return plan

    monkeypatch.setattr(
        "cadence_mcp_bridge.extraction_recovery.ExtractionRecoveryService", SourceProvider,
    )
    arguments = [
        "operator-recovery", "plan", "--settings", str(settings),
        "--context", context.binding.context_id, "--request", str(request_path),
        "--original-operation-id", plan.recovery.original_operation_id,
        "--original-plan-sha256", plan.recovery.original_plan_sha256, "--output", str(output),
    ]
    assert main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "RECOVERY_PLAN_PREPARED_NOT_SUBMITTED"
    assert report["new_reservations"] == 0
    assert RecoveryPlan.model_validate_json(output.read_bytes()) == plan
    assert {p: p.read_bytes() for p in before} == before
    assert main(arguments) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "recovery_plan_new_output_required"
    assert calls == ["source_lookup"]
    assert RecoveryPlan.model_validate_json(output.read_bytes()) == plan


@pytest.mark.asyncio
async def test_existing_local_operation_id_is_read_only_and_cannot_dispatch(host_plan):
    context, _, _, plan = host_plan
    op = str(uuid4())
    store = AnalysisStore(context.binding.analysis_journal)
    store.admit(op, "synthetic-other", "synthetic-analysis", "e" * 64)
    before = store.path.read_bytes()

    async def lookup(*args):
        return None

    service = service_with_provider(host_plan, SimpleNamespace(lookup=lookup))
    service.native.lifecycle.store = store
    with pytest.raises(OperationRejected) as failure:
        await service.observe(op, plan, submit=True)
    assert failure.value.reason == "recovery_local_identity_occupied"
    assert store.path.read_bytes() == before


@pytest.fixture
def failed_source(qualified, monkeypatch):
    if os.name != "posix":
        pytest.skip("real descriptor/scanner/accounting qualification requires POSIX")
    root, gate, plan, confirmation_request = qualified
    gate.storage = storage
    route = gate.route(plan)
    gate.profile["paths"]["job_root"] = str(root / accounting.JOBS)
    gate.profile["tools"] = {"ocean": {"path": "/synthetic/not-executed"},
                             "spectre": {"path": "/synthetic/not-executed"}}
    route["ade"].update(
        inputs={"analysis": "dc", "mode": "saved_operating_point",
                "statement_sha256": operations.digest(b"dc ")},
        static_statements_sha256=rendering.static_fingerprint(["R0 (in out) resistor r=1000"]),
    )
    route["reader"] = {"nodes": [{"logical_id": "out", "selector": "/out"}],
                       "sources": [], "maximum_samples": 16}
    op = str(uuid4())
    source = operations.OperationJournal(str(root), op, plan, accounting)
    native = eda.EdaWorker(gate, operations, rendering, copying, installer)
    data = b"simulator lang=spectre\nR0 (in out) resistor r=1000\ndc0 dc\n"
    effective = rendering.effective_input(data, {}, [], route["ade"]["inputs"],
                                         route["ade"]["static_statements_sha256"])
    with accounting.ReservationSession(str(root)) as session:
        binding, _ = gate.check(session, plan, "submit")
        source.create(binding)
        receipt = session.reserve(op, binding)
        source.append(session, "RESERVED", operations.digest(operations.canonical(receipt)))
        source.append(session, "DISPATCHED", "e" * 64)
        source.append(session, "RUNNING", "e" * 64)
        source.append(session, "EXTRACTING", operations.digest(operations.canonical(effective)))
        source.append(session, "EXTRACTION_FAILED", "f" * 64)
    native.write(source.work + "/input.scs", data)
    native.write(source.job + "/cds.lib", b"synthetic library, never Cadence input\n")
    accounting.write_new(source.work + "/effective-input.json", {
        "operation_id": op, "plan_sha256": source.plan_sha,
        "native_input_sha256": effective["input_sha256"],
        "planned_execution_input_sha256": binding["execution_input_sha256"],
    })
    Path(source.work + "/psf").mkdir(mode=0o700)
    Path(source.work + "/psf/synthetic-result").write_bytes(b"synthetic PSF, not native evidence")
    Path(source.work + "/psf/synthetic-result").chmod(0o600)
    recover = recovery.ExtractionRecovery(native)
    new_plan = copy.deepcopy(plan)
    grant = json.loads(confirmation_request["grant_json"])
    grant["actions"].append("recover_extraction")
    confirmation_request = dict(
        confirmation_request, grant_json=confirmation.canonical(grant).decode("ascii"),
        grant_sha256=confirmation.digest(confirmation.canonical(grant)),
    )
    confirmation.confirm(confirmation_request, "a" * 64)
    new_plan["grant_sha256"] = confirmation_request["grant_sha256"]
    new_plan["recovery"] = {"original_operation_id": op,
                            "original_plan_sha256": source.plan_sha,
                            "original_tree_fingerprint": "0" * 64}
    info = recover.source(new_plan, False)[1]
    new_plan["recovery"]["original_tree_fingerprint"] = info["original_tree_fingerprint"]
    return root, gate, native, recover, source, new_plan


def test_failed_psf_recovery_is_reader_only_preserves_original_and_replay(
    failed_source, monkeypatch,
):
    root, gate, native, recover, source, plan = failed_source
    unchanged = copying.dependency_snapshot(source.job)
    calls = []
    def program(session, journal, argv, label, seconds, limit):
        calls.append(label)
        assert label == "reader" and argv[0] == "/synthetic/not-executed"
        assert original_path_in_script(source, journal)
        header = "|".join(("MCP_GREL_FRAME", "1", journal.operation_id, journal.plan_sha,
                           operations.digest(Path(source.work + "/input.scs").read_bytes()),
                           operations.digest(operations.canonical(gate.route(plan)["reader"]))))
        native.write(journal.work + "/generic-frame.txt", (header + "\nV|out|0.5\nEND\n").encode())

    monkeypatch.setattr(native, "program", program)

    class Worker:
        def start(self, session, journal, plan):
            journal.append(session, "RUNNING", "e" * 64)
            recover.run(session, journal, plan)

    coordinator = operations.NativeCoordinator(str(root), accounting, gate, Worker(),
                                             "recover_extraction", recover.preflight)
    op = str(uuid4())
    result = coordinator.accept(op, plan)
    assert result["progress"]["phase"] == "SUCCEEDED"
    after = accounting.read(str(root / accounting.LEDGER))
    assert after["count"] == 84  # Seed82 + original1 + recovery1; no Spectre call.
    restarted = operations.NativeCoordinator(str(root), accounting, gate, Worker(),
                                            "recover_extraction", recover.preflight)
    assert restarted.accept(op, plan) == result
    payload = recover.result(restarted.journal(op, plan), plan)
    assert "V|out|0.5" in payload["frame"]
    assert calls == ["reader"]
    assert accounting.read(str(root / accounting.LEDGER)) == after
    assert copying.dependency_snapshot(source.job) == unchanged
    assert source.observation()["progress"]["phase"] == "EXTRACTION_FAILED"


def test_recovery_fork_uncertainty_keeps_admission_and_blocks_restart_dispatch(failed_source):
    root, gate, _, recover, source, plan = failed_source
    unchanged = copying.dependency_snapshot(source.job)
    calls = []

    class Worker:
        def start(self, *args):
            calls.append("fork")
            raise OSError("synthetic fork/lost acknowledgement")

    coordinator = operations.NativeCoordinator(str(root), accounting, gate, Worker(),
                                             "recover_extraction", recover.preflight)
    op = str(uuid4())
    with pytest.raises(OSError):
        coordinator.accept(op, plan)
    ledger = Path(root / accounting.LEDGER).read_bytes()
    restarted = operations.NativeCoordinator(str(root), accounting, gate, Worker(),
                                            "recover_extraction", recover.preflight)
    assert restarted.accept(op, plan)["progress"]["phase"] == "DISPATCHED"
    assert restarted.lookup(op, plan)["progress"]["phase"] == "DISPATCHED"
    assert calls == ["fork"] and Path(root / accounting.LEDGER).read_bytes() == ledger
    assert copying.dependency_snapshot(source.job) == unchanged


def original_path_in_script(source, journal):
    text = Path(journal.work + "/reader.ocn").read_text()
    return source.work + "/psf" in text and journal.work + "/generic-frame.txt" in text


@pytest.mark.parametrize("tamper", ["psf", "input", "identity", "conditions"])
def test_source_drift_and_scope_reject_without_new_spend(failed_source, tamper):
    root, _, _, recover, source, plan = failed_source
    before = Path(root / accounting.LEDGER).read_bytes()
    if tamper == "psf":
        leaf = Path(source.work + "/psf/synthetic-result")
        info = leaf.stat()
        leaf.write_bytes(b"X" * info.st_size)
        os.utime(leaf, ns=(info.st_atime_ns, info.st_mtime_ns))
    elif tamper == "input":
        Path(source.work + "/input.scs").write_bytes(b"invalid input")
    elif tamper == "identity":
        plan["recovery"]["original_plan_sha256"] = "b" * 64
    else:
        plan["request"]["analysis_id"] = "different-analysis"
    with pytest.raises(ValueError):
        recover.preflight(plan)
    assert Path(root / accounting.LEDGER).read_bytes() == before


def test_gate_requires_recovery_action_and_ordinary_submit_stays_denied(qualified):
    root, gate, plan, _ = qualified
    plan["recovery"] = {"original_operation_id": str(uuid4()),
                        "original_plan_sha256": "a" * 64,
                        "original_tree_fingerprint": "b" * 64}
    with accounting.ReservationSession(str(root)) as session:
        with pytest.raises(ValueError, match="action_mismatch"):
            gate.check(session, plan, "submit")
        with pytest.raises(ValueError, match="action_denied"):
            gate.check(session, plan, "recover_extraction")
