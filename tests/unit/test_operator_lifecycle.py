"""Synthetic provider/ledger fault tests; no remote writes, approval or simulation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_operator_operations import operator as operator_fixture

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.operator_lifecycle import (
    OperatorLifecycle,
    ProviderAccounting,
    ProviderObservation,
)
from cadence_mcp_bridge.operator_operations import (
    OperationProgress,
    OperationRejected,
    prepare_plan,
)

operator = operator_fixture


class SyntheticProvider:
    """Only this test double owns fake accounting; production coordinator does not."""

    def __init__(self, context):
        self.context = context
        self.jobs = {}
        self.attempts = 82
        self.reserved = 9798942720
        self.grant_used = 0
        self.calls = []
        self.loss = None
        self.phase = "RESERVED"
        self.gate_changes = {}
        self.wrong_reply = {}
        self.authorizations = 0
        self.cancellations = 0

    async def authorize(self, plan, grant):
        self.authorizations += 1
        payload = dict(
            resource_domain_sha256=plan.resource_domain_sha256,
            ledger_ref=plan.ledger_ref,
            runner_sha256=plan.runner_sha256,
            grant_sha256=plan.grant_sha256,
            cumulative_attempts=self.attempts,
            cumulative_reserved_bytes=self.reserved,
            grant_attempts=self.grant_used,
            grant_reserved_bytes=self.grant_used * 134217728,
            attempt_ceiling=500,
            result_ceiling_bytes=10737418240,
            in_flight_reserved_bytes=0,
            logical_bytes=18030073,
            allocated_bytes=48308224,
            filesystem_free_bytes=25690238976,
            filesystem_total_bytes=40 * 1024**3,
        )
        payload.update(self.gate_changes)
        return ProviderAccounting.model_validate_json(json.dumps(payload))

    def observe(self, operation_id, plan, phase=None, revision=1):
        phase = self.phase if phase is None else phase
        digest = hashlib.sha256((operation_id + phase + str(revision)).encode()).hexdigest()
        payload = dict(
            operation_id=operation_id,
            plan_sha256=plan.plan_sha256,
            resource_domain_sha256=plan.resource_domain_sha256,
            ledger_ref=plan.ledger_ref,
            progress=dict(phase=phase, remote_revision=revision, provider_receipt_sha256=digest),
        )
        payload.update(self.wrong_reply)
        return ProviderObservation.model_validate_json(json.dumps(payload))

    async def accept(self, operation_id, plan):
        self.calls.append(operation_id)
        if self.loss == "before":
            raise ConnectionError("synthetic response lost before acceptance")
        if operation_id not in self.jobs:
            self.attempts += 1
            self.reserved += plan.request.result_reservation_bytes
            self.grant_used += 1
            self.jobs[operation_id] = self.observe(operation_id, plan)
        if self.loss == "after":
            raise ConnectionError("synthetic response lost after acceptance")
        return self.jobs[operation_id]

    async def lookup(self, operation_id, plan):
        return self.jobs.get(operation_id)

    async def cancel_pending(self, operation_id, plan):
        self.cancellations += 1
        result = self.observe(operation_id, plan, "CANCELLED", revision=2)
        self.jobs[operation_id] = result
        return result


@pytest.fixture
def lifecycle(operator):
    context, grant, request, settings = operator
    plan = prepare_plan(context, grant, "c" * 64, request, int(time.time()))
    provider = SyntheticProvider(context)
    store = AnalysisStore(context.binding.analysis_journal)
    return OperatorLifecycle(context, store, provider), provider, grant, request, plan, settings


@pytest.mark.asyncio
async def test_missing_provider_cannot_create_journal_or_lock(lifecycle):
    coordinator, _, grant, request, plan, _ = lifecycle
    blocked = OperatorLifecycle(coordinator.context, coordinator.store)
    with pytest.raises(OperationRejected, match="Operator operation rejected") as error:
        await blocked.submit(str(uuid4()), grant, "c" * 64, request, plan.plan_sha256)
    assert error.value.reason == "trusted_native_provider_required"
    assert not coordinator.store.path.exists() and not coordinator.context.lock_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("loss", ["before", "after"])
async def test_response_loss_restart_is_lookup_only_no_double_charge(lifecycle, loss):
    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())
    provider.loss = loss
    with pytest.raises(ConnectionError):
        await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    assert coordinator.read(identity, plan.plan_sha256).progress.phase == "UNKNOWN_OUTCOME"
    used = (provider.attempts, provider.reserved)
    restarted = OperatorLifecycle(
        coordinator.context, AnalysisStore(coordinator.store.path), provider
    )
    for _ in range(3):
        result = await restarted.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
        assert result.progress.phase == ("RESERVED" if loss == "after" else "UNKNOWN_OUTCOME")
    assert provider.calls == [identity] and (provider.attempts, provider.reserved) == used
    assert provider.authorizations == 1


@pytest.mark.asyncio
async def test_two_batches_same_provider_preserve_existing_cumulative_usage(lifecycle):
    coordinator, provider, grant, request, plan, _ = lifecycle
    first = str(uuid4())
    await coordinator.submit(first, grant, "c" * 64, request, plan.plan_sha256)
    provider.jobs[first] = provider.observe(first, plan, "SUCCEEDED", 2)
    assert (await coordinator.reconcile(first, plan.plan_sha256)).progress.phase == "SUCCEEDED"
    second = str(uuid4())
    await OperatorLifecycle(
        coordinator.context, AnalysisStore(coordinator.store.path), provider
    ).submit(second, grant, "c" * 64, request, plan.plan_sha256)
    assert provider.calls == [first, second]
    assert provider.attempts == 84 and provider.reserved == 9798942720 + 2 * 134217728
    assert provider.grant_used == 2
    with sqlite3.connect(coordinator.store.path) as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            "admissions",
            "operator_plans_v1",
            "operator_events_v1",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"cumulative_attempts": 500}, "authoritative_budget_exhausted"),
        ({"cumulative_reserved_bytes": 10737418240}, "authoritative_budget_exhausted"),
        ({"grant_attempts": 6}, "authoritative_budget_exhausted"),
        ({"filesystem_free_bytes": 2147483648}, "authoritative_disk_floor_denied"),
        ({"attempt_ceiling": 501}, "provider_accounting_inconsistent"),
        ({"in_flight_reserved_bytes": 10737418240}, "provider_accounting_inconsistent"),
        ({"resource_domain_sha256": "d" * 64}, "provider_accounting_binding_mismatch"),
        ({"ledger_ref": "independent-ledger"}, "provider_accounting_binding_mismatch"),
        ({"runner_sha256": "d" * 64}, "provider_accounting_binding_mismatch"),
    ],
)
async def test_authoritative_accounting_denial_precedes_admission(lifecycle, changes, reason):
    coordinator, provider, grant, request, plan, _ = lifecycle
    provider.gate_changes = changes
    with pytest.raises(OperationRejected) as error:
        await coordinator.submit(str(uuid4()), grant, "c" * 64, request, plan.plan_sha256)
    assert error.value.reason == reason
    assert not coordinator.store.path.exists() and not provider.calls
    assert (provider.attempts, provider.reserved) == (82, 9798942720)


@pytest.mark.asyncio
async def test_completed_read_and_retry_survive_expired_grant(lifecycle):
    coordinator, provider, grant, request, plan, settings = lifecycle
    identity = str(uuid4())
    provider.phase = "SUCCEEDED"
    result = await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    expired = grant.model_copy(update={"status": "revoked", "valid_until_unix": 2})
    assert (
        await coordinator.submit(identity, expired, "d" * 64, request, plan.plan_sha256) == result
    )
    no_provider = OperatorLifecycle(coordinator.context, AnalysisStore(coordinator.store.path))
    assert no_provider.read(identity, plan.plan_sha256) == result
    with pytest.raises(OperationRejected):
        await coordinator.submit(str(uuid4()), expired, "d" * 64, request, plan.plan_sha256)
    assert provider.calls == [identity] and provider.authorizations == 1


@pytest.mark.asyncio
async def test_pending_local_cancel_wins_before_send_and_replay_does_not_dispatch(lifecycle):
    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())
    assert coordinator.store.admit_operation(identity, plan)
    result = await coordinator.cancel_pending(identity, plan.plan_sha256, grant, "c" * 64)
    assert result.progress.phase == "CANCELLED"
    assert (
        await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    ) == result
    assert provider.calls == [] and provider.cancellations == 1 and provider.reserved == 9798942720


@pytest.mark.asyncio
async def test_remote_pending_cancel_retains_consumed_reservation(lifecycle):
    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())
    await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    before = provider.reserved
    assert (
        await coordinator.cancel_pending(identity, plan.plan_sha256, grant, "c" * 64)
    ).progress.phase == "CANCELLED"
    assert provider.cancellations == 1 and provider.reserved == before


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["RUNNING", "EXTRACTING", "UNKNOWN_OUTCOME"])
async def test_active_or_unknown_cancel_never_calls_termination(lifecycle, phase):
    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())
    provider.phase = phase
    await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    with pytest.raises(OperationRejected) as error:
        await coordinator.cancel_pending(identity, plan.plan_sha256, grant, "c" * 64)
    assert error.value.reason == "pending_state_unconfirmed_or_active"
    assert provider.cancellations == 0


def test_additive_store_preserves_legacy_identity_and_atomic_first_admission(lifecycle):
    coordinator, _, _, _, plan, _ = lifecycle
    legacy = str(uuid4())
    assert coordinator.store.admit(legacy, "legacy", "native-dc", "a" * 64)
    operation_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: AnalysisStore(coordinator.store.path).admit_operation(operation_id, plan),
                range(12),
            )
        )
    assert sum(results) == 1
    coordinator.store.require(legacy, "legacy", "native-dc", "a" * 64)
    with sqlite3.connect(coordinator.store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    with pytest.raises(InvalidInputError):
        coordinator.store.admit_operation(
            operation_id, plan.model_copy(update={"grant_sha256": "d" * 64})
        )
    with pytest.raises(InvalidInputError):
        coordinator.store.admit_operation(legacy, plan)


@pytest.mark.parametrize("fault", ["progress", "plan", "missing_table"])
def test_corrupt_lifecycle_fails_closed_without_reinitialization(lifecycle, fault):
    coordinator, _, _, _, plan, _ = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    with sqlite3.connect(coordinator.store.path) as db:
        if fault == "progress":
            db.execute("UPDATE operator_events_v1 SET progress_json='{}'")
        elif fault == "plan":
            db.execute("UPDATE operator_plans_v1 SET plan_json='{}'")
        else:
            db.execute("DROP TABLE operator_events_v1")
    before = coordinator.store.path.read_bytes()
    with pytest.raises(ConfigurationError):
        coordinator.store.operation(identity)
    assert coordinator.store.path.read_bytes() == before


@pytest.mark.asyncio
async def test_journal_status_cli_is_local_bounded_and_read_only(lifecycle, capsys):
    coordinator, _, _, _, plan, settings = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    before = coordinator.store.path.read_bytes()
    args = [
        "operation",
        "journal-status",
        "--settings",
        str(settings),
        "--context",
        "operator",
        "--operation-id",
        identity,
        "--expected-plan-sha256",
        plan.plan_sha256,
    ]
    assert main(args) == 0
    output = capsys.readouterr().out
    assert "LOCAL_LAST_OBSERVATION" in output and str(coordinator.store.path) not in output
    assert coordinator.store.path.read_bytes() == before
    assert main([*args[:-1], "d" * 64]) == 1
    assert "durable_operation_binding_mismatch" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cancelled_coroutine_keeps_intent_for_restart(lifecycle):
    import asyncio

    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())

    async def cancelled(operation_id, admitted):
        raise asyncio.CancelledError

    provider.accept = cancelled
    with pytest.raises(asyncio.CancelledError):
        await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    assert coordinator.read(identity, plan.plan_sha256).progress.phase == "UNKNOWN_OUTCOME"
    assert (
        await coordinator.reconcile(identity, plan.plan_sha256)
    ).progress.phase == "UNKNOWN_OUTCOME"


@pytest.mark.asyncio
async def test_expiry_while_awaiting_authorization_denies_admission(lifecycle, monkeypatch):
    import cadence_mcp_bridge.operator_lifecycle as module

    coordinator, provider, grant, request, plan, _ = lifecycle
    real = provider.authorize

    async def delayed(plan, grant):
        result = await real(plan, grant)
        monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: grant.valid_until_unix))
        return result

    provider.authorize = delayed
    with pytest.raises(OperationRejected) as error:
        await coordinator.submit(str(uuid4()), grant, "c" * 64, request, plan.plan_sha256)
    assert error.value.reason == "authority_inactive"
    assert not coordinator.store.path.exists() and not provider.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "00000000-0000-4000-8000-000000000000"),
        ("plan_sha256", "d" * 64),
        ("resource_domain_sha256", "d" * 64),
        ("ledger_ref", "other-ledger"),
    ],
)
async def test_wrong_remote_identity_retains_intent_for_lookup(lifecycle, field, value):
    coordinator, provider, grant, request, plan, _ = lifecycle
    provider.wrong_reply = {field: value}
    identity = str(uuid4())
    with pytest.raises(OperationRejected) as error:
        await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    assert error.value.reason == "provider_operation_identity_mismatch"
    assert coordinator.read(identity, plan.plan_sha256).progress.phase == "UNKNOWN_OUTCOME"
    assert provider.calls == [identity]


@pytest.mark.asyncio
async def test_shared_domain_lock_serializes_clients_while_provider_awaits(lifecycle):
    import asyncio

    from cadence_mcp_bridge.runtime_context import RuntimeRejected

    coordinator, provider, grant, request, plan, _ = lifecycle
    entered, release = asyncio.Event(), asyncio.Event()
    real = provider.accept

    async def held(identity, plan):
        entered.set()
        await release.wait()
        return await real(identity, plan)

    provider.accept = held
    task = asyncio.create_task(
        coordinator.submit(str(uuid4()), grant, "c" * 64, request, plan.plan_sha256)
    )
    await entered.wait()
    try:
        with pytest.raises(RuntimeRejected):
            await OperatorLifecycle(coordinator.context, coordinator.store, provider).submit(
                str(uuid4()), grant, "c" * 64, request, plan.plan_sha256
            )
        assert provider.authorizations == 1
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_two_client_journals_use_same_authoritative_provider_identity(lifecycle):
    from dataclasses import replace

    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())
    first = await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    journal = coordinator.store.path.with_name("second-client.sqlite3")
    binding = coordinator.context.binding.model_copy(update={"analysis_journal": journal})
    context = replace(coordinator.context, binding=binding)
    second = await OperatorLifecycle(context, AnalysisStore(journal), provider).submit(
        identity, grant, "c" * 64, request, plan.plan_sha256
    )
    assert first.plan == second.plan and first.operation_id == second.operation_id
    assert provider.attempts == 83 and provider.reserved == 9798942720 + 134217728
    assert provider.calls == [identity, identity]  # remote identity prevents a second reservation


@pytest.mark.parametrize("kind", ["revision", "regression", "terminal", "capacity"])
def test_progress_revision_terminal_and_capacity_are_durable(lifecycle, kind):
    coordinator, provider, _, _, plan, _ = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    record = coordinator.read(identity, plan.plan_sha256)
    record = coordinator.store.advance_operation(
        identity, record.progress, OperationProgress(phase="UNKNOWN_OUTCOME")
    )
    record = coordinator._observe(record, provider.observe(identity, plan))
    if kind == "revision":
        bad = provider.observe(identity, plan, "RUNNING", 1)
        with pytest.raises(OperationRejected, match="Operator operation rejected"):
            coordinator._observe(record, bad)
    elif kind == "regression":
        record = coordinator._observe(record, provider.observe(identity, plan, "RUNNING", 2))
        with pytest.raises(OperationRejected):
            coordinator._observe(record, provider.observe(identity, plan, "RESERVED", 3))
    elif kind == "terminal":
        record = coordinator._observe(record, provider.observe(identity, plan, "SUCCEEDED", 2))
        with pytest.raises(OperationRejected):
            coordinator._observe(record, provider.observe(identity, plan, "FAILED", 3))
    else:
        for revision in range(2, 63):
            record = coordinator._observe(
                record, provider.observe(identity, plan, "RESERVED", revision)
            )
        assert record.event_count == 64
        with pytest.raises(ConfigurationError):
            coordinator._observe(record, provider.observe(identity, plan, "RESERVED", 63))
    assert coordinator.read(identity, plan.plan_sha256) == record


def test_lifecycle_page_capacity_rolls_back_without_losing_existing_history(lifecycle, monkeypatch):
    import cadence_mcp_bridge.analysis_store as module

    coordinator, _, _, _, plan, _ = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    initial = coordinator.store.operation(identity)
    # Cap the DB at its current size; a failed insert must preserve existing history.
    monkeypatch.setattr(module, "MAX_BYTES", coordinator.store.path.stat().st_size)
    large = plan.model_copy(update={"ledger_ref": "x" * 64})
    with pytest.raises(ConfigurationError):
        for _ in range(100):
            coordinator.store.admit_operation(str(uuid4()), large)
    assert coordinator.store.operation(identity) == initial


def test_hardlinked_journal_is_rejected_without_mutating_other_name(lifecycle):
    coordinator, _, _, _, plan, _ = lifecycle
    coordinator.store.admit_operation(str(uuid4()), plan)
    alternate = coordinator.store.path.with_name("other-work.sqlite3")
    alternate.hardlink_to(coordinator.store.path)
    before = alternate.read_bytes()
    with pytest.raises(ConfigurationError):
        coordinator.store.admit_operation(str(uuid4()), plan)
    assert alternate.read_bytes() == before


@pytest.mark.asyncio
async def test_locally_admitted_cancellation_observes_other_clients_active_job(lifecycle):
    coordinator, provider, grant, _, plan, _ = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    provider.jobs[identity] = provider.observe(identity, plan, "RUNNING")
    with pytest.raises(OperationRejected) as error:
        await coordinator.cancel_pending(identity, plan.plan_sha256, grant, "c" * 64)
    assert error.value.reason == "pending_state_unconfirmed_or_active"
    assert provider.cancellations == 0
    assert coordinator.read(identity, plan.plan_sha256).progress.phase == "RUNNING"


@pytest.mark.asyncio
async def test_pending_cancellation_response_loss_leaves_lookup_only_intent(lifecycle):
    coordinator, provider, grant, request, plan, _ = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    real = provider.cancel_pending

    async def lost(identity, plan):
        await real(identity, plan)
        raise ConnectionError("synthetic cancellation response lost")

    provider.cancel_pending = lost
    with pytest.raises(ConnectionError):
        await coordinator.cancel_pending(identity, plan.plan_sha256, grant, "c" * 64)
    assert coordinator.read(identity, plan.plan_sha256).progress.phase == "UNKNOWN_OUTCOME"
    assert (
        await coordinator.submit(identity, grant, "c" * 64, request, plan.plan_sha256)
    ).progress.phase == "CANCELLED"
    assert provider.calls == [] and provider.cancellations == 1
    assert provider.reserved == 9798942720


def test_known_remote_progress_cannot_regress_to_unknown(lifecycle):
    coordinator, provider, _, _, plan, _ = lifecycle
    identity = str(uuid4())
    coordinator.store.admit_operation(identity, plan)
    record = coordinator.store.operation(identity)
    record = coordinator.store.advance_operation(
        identity, record.progress, OperationProgress(phase="UNKNOWN_OUTCOME")
    )
    record = coordinator._observe(record, provider.observe(identity, plan, "RUNNING"))
    with pytest.raises(OperationRejected):
        coordinator._observe(record, provider.observe(identity, plan, "UNKNOWN_OUTCOME", 2))
    assert coordinator.read(identity, plan.plan_sha256) == record
