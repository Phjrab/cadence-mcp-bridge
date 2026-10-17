"""Synthetic sequential lifecycle and real disposable SQLite identity tests only."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_candidate_contracts import candidate_operator, operator
from test_operator_lifecycle import SyntheticProvider

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.candidate_batches import (
    CandidateBatchQuery,
    CandidateBatchStore,
    CandidateBatchSubmission,
    CandidateBatchSupervisor,
)
from cadence_mcp_bridge.candidate_contracts import prepare_candidate_plan
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.extraction_recovery import ExtractionRecoveryService, RecoveryPlan
from cadence_mcp_bridge.native_service import NativeOperationRequest, NativeOperationService
from cadence_mcp_bridge.native_sweeps import (
    NativeSweepPlan,
    NativeSweepQuery,
    NativeSweepRequest,
    NativeSweepStore,
)
from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle
from cadence_mcp_bridge.operator_operations import OperationRejected, prepare_plan
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["candidate_operator", "candidate_native", "operator"]


@pytest.fixture
def candidate_native(candidate_operator):
    context, grant, request, _ = candidate_operator

    class Provider(SyntheticProvider):
        async def result(self, operation_id, plan):
            return self.jobs[operation_id], {"synthetic_fixture_only": True}

    provider = Provider(context)
    provider.phase = "SUCCEEDED"

    def make_native():
        native = object.__new__(NativeOperationService)
        native.context, native.grant, native.grant_sha256 = context, grant, canonical_digest(grant)
        native.provider = provider
        native.current = lambda: None
        native.lifecycle = OperatorLifecycle(
            context, AnalysisStore(context.binding.analysis_journal), provider,
        )
        return native

    return make_native, provider, request


async def admitted(candidate_native):
    make_native, provider, request = candidate_native
    supervisor = CandidateBatchSupervisor(make_native())
    plan = await supervisor.plan(request)
    submission = CandidateBatchSubmission(
        batch_id=request.batch_id, expected_plan_sha256=plan.plan_sha256, request=request,
    )
    status = await supervisor.submit(submission)
    return supervisor, submission, plan, status, provider


@pytest.mark.asyncio
async def test_plan_manifest_retry_restart_and_one_child_per_advance(candidate_native):
    make_native, provider, request = candidate_native
    supervisor = CandidateBatchSupervisor(make_native())
    plan = await supervisor.plan(request)
    assert not supervisor.store.store.path.exists()
    assert not supervisor.native.context.lock_path.exists()
    supervisor, submission, plan, status, _ = await admitted(candidate_native)
    assert status.state == "PLANNED" and provider.calls == []
    identities = [candidate.operation_id for candidate in request.candidates]
    original = (provider.attempts, provider.reserved)
    for index in range(3):
        supervisor = CandidateBatchSupervisor(make_native())
        await supervisor.submit(submission)
        await supervisor.status(submission)
        assert provider.calls == identities[:index]
        await supervisor.advance(submission)
        assert provider.calls == identities[:index + 1]
    assert (await supervisor.status(submission)).state == "SUCCEEDED"
    result = await supervisor.result(submission)
    assert [item["operation_id"] for item in result.candidates] == identities
    assert result.new_simulations == 0 and result.new_extractions == 0
    await CandidateBatchSupervisor(make_native()).advance(submission)
    await CandidateBatchSupervisor(make_native()).submit(submission)
    assert provider.calls == identities
    assert (provider.attempts, provider.reserved) == (original[0] + 3, original[1] + 3 * 134217728)


@pytest.mark.asyncio
async def test_real_new_process_parent_retry_queries_same_ids_without_dispatch(
    candidate_native, candidate_operator, tmp_path,
):
    _, provider, _ = candidate_native
    supervisor, submission, _, _, _ = await admitted(candidate_native)
    await supervisor.advance(submission)
    settings = candidate_operator[3]
    query_path = tmp_path / "batch-query.json"
    query_path.write_text(submission.model_dump_json(), encoding="utf-8")
    script = '''
import asyncio, json, sys
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.candidate_batches import CandidateBatchSubmission, CandidateBatchSupervisor
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle
from cadence_mcp_bridge.runtime_context import load_runtime
class NoDispatch:
    async def lookup(self, *args):
        raise AssertionError("terminal replay cannot need remote lookup")
    async def authorize(self, *args):
        raise AssertionError("replay cannot authorize")
    async def accept(self, *args):
        raise AssertionError("replay cannot dispatch")
context = load_runtime(__import__("pathlib").Path(sys.argv[1]))[0]
native = object.__new__(NativeOperationService)
native.context = context
native.current = lambda: None
native.lifecycle = OperatorLifecycle(context, AnalysisStore(context.binding.analysis_journal),
                                     NoDispatch())
submission = CandidateBatchSubmission.model_validate_json(
    __import__("pathlib").Path(sys.argv[2]).read_bytes())
async def perform():
    supervisor = CandidateBatchSupervisor(native)
    first = await supervisor.submit(submission)
    second = await supervisor.status(submission)
    assert first == second
    print(json.dumps({"status": second.model_dump(mode="json"), "dispatches": 0}))
asyncio.run(perform())
'''
    before = (provider.attempts, provider.reserved, list(provider.calls))
    reply = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", script, str(settings), str(query_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    observed = json.loads(reply.stdout)
    assert observed["dispatches"] == 0
    assert [item["operation_id"] for item in observed["status"]["candidates"]] == [
        item.operation_id for item in submission.request.candidates
    ]
    assert observed["status"]["state"] == "PARTIAL"
    assert before == (provider.attempts, provider.reserved, provider.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["FAILED", "EXTRACTION_FAILED", "RUNNING", "RESERVED"])
async def test_halt_all_does_not_admit_later_children(candidate_native, phase):
    make_native, provider, _ = candidate_native
    provider.phase = phase
    supervisor, submission, _, _, _ = await admitted(candidate_native)
    observed = await supervisor.advance(submission)
    for _ in range(3):
        await CandidateBatchSupervisor(make_native()).advance(submission)
        await supervisor.submit(submission)
    assert len(provider.calls) == 1
    assert all(item["phase"] == "NOT_RUN" for item in observed.candidates[1:])
    results = await supervisor.result(submission)
    assert len(results.candidates) == 3
    assert results.candidates[0]["phase"] == phase
    assert all(item["phase"] == "NOT_RUN" and item["result"] is None
               for item in results.candidates[1:])
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_retained_result_read_failure_keeps_success_and_untouched_rows(
    candidate_native, monkeypatch,
):
    supervisor, submission, _, _, provider = await admitted(candidate_native)
    await supervisor.advance(submission)

    async def unavailable(query):
        raise InvalidInputError("synthetic retained reader unavailable")

    monkeypatch.setattr(supervisor.native, "result", unavailable)
    result = await supervisor.result(submission)
    assert len(result.candidates) == 3
    assert result.candidates[0]["phase"] == "SUCCEEDED"
    assert result.candidates[0]["result_unavailable_reason"] == "RETAINED_RESULT_UNAVAILABLE"
    assert all(item["result"] is None for item in result.candidates)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("loss", ["before", "after"])
async def test_transport_loss_restart_cannot_resend_or_skip_unknown(candidate_native, loss):
    make_native, provider, _ = candidate_native
    provider.phase = "RESERVED"
    provider.loss = loss
    supervisor, submission, _, _, _ = await admitted(candidate_native)
    with pytest.raises(ConnectionError):
        await supervisor.advance(submission)
    before = (provider.attempts, provider.reserved)
    for _ in range(2):
        restarted = CandidateBatchSupervisor(make_native())
        await restarted.submit(submission)
        await restarted.advance(submission)
    assert len(provider.calls) == 1
    assert (provider.attempts, provider.reserved) == before
    assert all(item["phase"] == "NOT_RUN"
               for item in (await supervisor.status(submission)).candidates[1:])


@pytest.mark.asyncio
async def test_changed_current_authority_and_wrong_parent_hash_reject(candidate_native):
    make_native, provider, _ = candidate_native
    supervisor, submission, _, _, _ = await admitted(candidate_native)
    await supervisor.advance(submission)
    changed = make_native()
    changed.grant = changed.grant.model_copy(update={"valid_until_unix": 2})
    changed.grant_sha256 = canonical_digest(changed.grant)
    with pytest.raises(OperationRejected):
        await CandidateBatchSupervisor(changed).advance(submission)
    wrong = CandidateBatchQuery(batch_id=submission.batch_id, expected_plan_sha256="f" * 64)
    with pytest.raises(InvalidInputError):
        await supervisor.status(wrong)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_admitted_manifest_reserves_parent_children_and_exact_owner(candidate_native):
    supervisor, submission, plan, _, provider = await admitted(candidate_native)
    store = AnalysisStore(supervisor.store.store.path)
    for identity in (submission.batch_id, plan.request.candidates[0].operation_id):
        with pytest.raises(InvalidInputError):
            store.admit(identity, "legacy", "example-dc", "a" * 64)
        with pytest.raises(InvalidInputError):
            store.admit_operation(identity, plan.plans[0], dispatch_intent=True)
        with pytest.raises(InvalidInputError):
            store.admit_operation(identity, plan.plans[0], candidate_batch_id=str(uuid4()))
    child = plan.request.candidates[0].operation_id
    with pytest.raises(InvalidInputError):
        store.admit_operation(child, plan.plans[1], candidate_batch_id=submission.batch_id)
    with pytest.raises(InvalidInputError):
        store.admit_operation(child, plan.plans[0], sweep_id=submission.batch_id)
    with pytest.raises(InvalidInputError):
        store.admit_operation(child, plan.plans[0], sweep_id=submission.batch_id,
                              candidate_batch_id=submission.batch_id)
    assert provider.calls == []


def test_atomic_manifest_competes_with_ordinary_admission_and_keeps_legacy(candidate_operator):
    context, grant, request, _ = candidate_operator
    plan = prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)
    store = AnalysisStore(context.binding.analysis_journal)
    legacy = str(uuid4())
    store.admit(legacy, "legacy", "dc", "a" * 64)
    query = CandidateBatchQuery(batch_id=request.batch_id, expected_plan_sha256=plan.plan_sha256)

    def competing(index):
        try:
            if index % 2:
                CandidateBatchStore(AnalysisStore(store.path)).admit(query, plan)
                return "parent"
            return "child" if AnalysisStore(store.path).admit(
                request.candidates[0].operation_id, "legacy", "dc", "b" * 64,
            ) else "child-replay"
        except InvalidInputError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(competing, range(8)))
    assert not ("parent" in results and "child" in results)
    assert "parent" in results or "child" in results
    store.require(legacy, "legacy", "dc", "a" * 64)


@pytest.mark.asyncio
async def test_native_sweep_parent_and_candidate_children_share_namespace(candidate_native):
    supervisor, submission, plan, _, provider = await admitted(candidate_native)
    sweep_request = NativeSweepRequest(
        template=NativeOperationRequest.model_validate_json(plan.plans[0].request.model_dump_json()),
        variable_id=plan.varied_variables[0].logical_id, values=("1", "1.1"),
    )
    sweep_plan = NativeSweepPlan(request=sweep_request, points=plan.plans[:2])
    for identity in (submission.batch_id, plan.request.candidates[0].operation_id):
        with pytest.raises(InvalidInputError):
            NativeSweepStore(supervisor.store.store).admit(
                NativeSweepQuery(sweep_id=identity, expected_plan_sha256=sweep_plan.plan_sha256),
                sweep_plan,
            )
    assert provider.calls == []


@pytest.mark.asyncio
async def test_duplicate_advance_calls_have_one_authoritative_child(candidate_native):
    import asyncio

    make_native, provider, _ = candidate_native
    provider.phase = "RUNNING"
    _, submission, _, _, _ = await admitted(candidate_native)
    # The real lifecycle resource lock and durable dispatch intent are retained.
    await asyncio.gather(*(CandidateBatchSupervisor(make_native()).advance(submission)
                           for _ in range(3)))
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_corrupt_manifest_cannot_be_recreated_or_dispatch(candidate_native):
    supervisor, submission, _, _, provider = await admitted(candidate_native)
    with supervisor.store.store.connection(create=False) as connection:
        connection.execute("UPDATE candidate_batches_v1 SET document='{}'")
    for action in (supervisor.submit, supervisor.advance, supervisor.status, supervisor.result):
        with pytest.raises(InvalidInputError):
            await action(submission)
    assert provider.calls == []


@pytest.mark.asyncio
async def test_recovery_and_manifest_reservation_cannot_steal_each_others_ids(candidate_native):
    make_native, provider, request = candidate_native
    native = make_native()
    supervisor = CandidateBatchSupervisor(native)
    plan = await supervisor.plan(request)
    operation_id = request.candidates[0].operation_id
    recovery_grant = native.grant.model_copy(update={"actions": ("recover_extraction",)})
    base = prepare_plan(native.context, recovery_grant, canonical_digest(recovery_grant),
                        plan.plans[0].request, int(time.time()), action="recover_extraction")
    recovery_plan = RecoveryPlan.model_validate_json(json.dumps({
        **base.model_dump(mode="json"), "recovery": {
            "original_operation_id": str(uuid4()), "original_plan_sha256": "a" * 64,
            "original_tree_fingerprint": "b" * 64,
        },
    }))
    query = CandidateBatchQuery(batch_id=request.batch_id, expected_plan_sha256=plan.plan_sha256)
    recovery_calls = []

    async def lookup(*args):
        return None

    async def authorize(*args):
        # Deliberately win the manifest transaction between recovery's early
        # availability read and its final atomic admission.
        supervisor.store.admit(query, plan)
        return SimpleNamespace(check=lambda *args: None)

    async def recover(*args):
        recovery_calls.append(args)
        raise AssertionError("The losing recovery must not contact the remote dispatcher")

    recovery = object.__new__(ExtractionRecoveryService)
    recovery.native = SimpleNamespace(
        context=native.context, grant=recovery_grant, grant_sha256=canonical_digest(recovery_grant),
        lifecycle=native.lifecycle, current=lambda: None,
        provider=SimpleNamespace(lookup=lookup, authorize=authorize, _observation=recover),
    )
    with pytest.raises(OperationRejected) as failure:
        await recovery.observe(operation_id, recovery_plan, submit=True)
    assert failure.value.reason == "recovery_local_identity_occupied"
    assert recovery_calls == [] and provider.calls == []


def test_recovery_marker_blocks_manifest_without_resetting_legacy_data(candidate_operator):
    context, grant, request, _ = candidate_operator
    plan = prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)
    store = AnalysisStore(context.binding.analysis_journal)
    child = request.candidates[0]
    assert store.admit(child.operation_id, child.design_id,
                       "extraction-recovery:" + child.analysis_id, "c" * 64)
    with pytest.raises(InvalidInputError):
        CandidateBatchStore(store).admit(CandidateBatchQuery(
            batch_id=request.batch_id, expected_plan_sha256=plan.plan_sha256,
        ), plan)
    store.require(child.operation_id, child.design_id,
                  "extraction-recovery:" + child.analysis_id, "c" * 64)
