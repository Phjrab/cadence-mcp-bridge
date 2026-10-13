"""Real disposable records/accounting/process tests, no Cadence or user grants."""

import copy
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_shared_reservations import AMOUNT, SEED, binding, snapshot
from test_shared_reservations import root as root_fixture

from cadence_mcp_bridge import _native_operations as native
from cadence_mcp_bridge import _shared_reservations as ledger
from cadence_mcp_bridge.operator_lifecycle import ProviderObservation

root = root_fixture


class Gate:
    def __init__(self, root):
        self.permit = binding(root)
        self.denied = False
        self.calls = []

    def read(self, plan):
        assert plan["runner_sha256"] == self.permit["runner_sha256"]

    def check(self, session, plan, action):
        self.calls.append(action)
        if self.denied:
            raise ValueError("synthetic gate denied")
        permit = dict(self.permit, plan_sha256=native.digest(native.canonical(plan)))
        return permit, {}


class Worker:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def start(self, session, journal, plan):
        self.calls += 1
        if self.fail:
            raise OSError("synthetic fork failed")
        journal.append(session, "RUNNING", "1" * 64)
        journal.append(session, "EXTRACTING", "2" * 64)
        journal.append(session, "SUCCEEDED", "3" * 64)


@pytest.fixture
def provider(root):
    gate, worker = Gate(root), Worker()
    plan = {
        key: gate.permit[key]
        for key in ("resource_domain_sha256", "ledger_ref", "runner_sha256", "grant_sha256")
    }
    plan["ledger_ref"] = ledger.LEDGER_REF
    plan["request"] = {"result_reservation_bytes": AMOUNT}
    return native.NativeCoordinator(str(root), ledger, gate, worker), plan, gate, worker


def test_replay_restart_and_two_batches_once(provider, root):
    coordinator, plan, gate, worker = provider
    first, second = str(uuid4()), str(uuid4())
    unchanged = snapshot(root)
    assert coordinator.lookup(first, plan) is None
    assert coordinator.authorize(first, plan) == {}
    assert snapshot(root) == unchanged
    reply = coordinator.accept(first, plan)
    assert (
        ProviderObservation.model_validate_json(native.canonical(reply)).progress.phase
        == "SUCCEEDED"
    )
    after = snapshot(root)
    gate.denied = True  # Lookup after expiry/revocation/exhaustion never dispatches.
    restarted = native.NativeCoordinator(str(root), ledger, gate, worker)
    for _ in range(3):
        assert restarted.lookup(first, plan) == reply
        assert restarted.accept(first, plan) == reply
    assert snapshot(root) == after and worker.calls == 1
    gate.denied = False
    assert restarted.accept(second, plan)["progress"]["phase"] == "SUCCEEDED"
    counter = ledger.read(str(root / ledger.LEDGER))
    assert counter["count"] == SEED["count"] + 2
    assert counter["result_reserved_bytes"] == SEED["result_reserved_bytes"] + AMOUNT * 2
    assert worker.calls == 2


def test_gate_failure_before_any_admission(provider, root):
    coordinator, plan, gate, worker = provider
    gate.denied = True
    before = snapshot(root)
    with pytest.raises(ValueError, match="gate denied"):
        coordinator.accept(str(uuid4()), plan)
    assert snapshot(root) == before and worker.calls == 0


def test_fork_failure_retains_intent_and_never_dispatches_again(provider, root):
    coordinator, plan, gate, worker = provider
    worker.fail = True
    op = str(uuid4())
    with pytest.raises(OSError):
        coordinator.accept(op, plan)
    after = snapshot(root)
    assert coordinator.lookup(op, plan)["progress"]["phase"] == "DISPATCHED"
    assert coordinator.accept(op, plan)["progress"]["phase"] == "DISPATCHED"
    with pytest.raises(ValueError, match="active_or_unknown"):
        coordinator.cancel_pending(op, plan)
    assert snapshot(root) == after and worker.calls == 1


def test_absent_cancellation_tombstone_prevents_later_accept(provider, root):
    coordinator, plan, gate, worker = provider
    op = str(uuid4())
    before_counter = (root / ledger.LEDGER).read_bytes()
    cancelled = coordinator.cancel_pending(op, plan)
    assert cancelled["progress"]["phase"] == "CANCELLED"
    assert coordinator.accept(op, plan) == cancelled
    assert coordinator.cancel_pending(op, plan) == cancelled
    assert (root / ledger.LEDGER).read_bytes() == before_counter and worker.calls == 0


def test_admission_without_receipt_is_unknown_not_redispatch(provider, root):
    coordinator, plan, gate, worker = provider
    op = str(uuid4())
    journal = coordinator.journal(op, plan)
    with ledger.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
    after = snapshot(root)
    assert coordinator.accept(op, plan)["progress"]["phase"] == "UNKNOWN_OUTCOME"
    with pytest.raises(ValueError, match="active_or_unknown"):
        coordinator.cancel_pending(op, plan)
    assert snapshot(root) == after and worker.calls == 0


@pytest.mark.parametrize("phase", ["DISPATCHED", "RUNNING", "EXTRACTING", "EXTRACTION_FAILED"])
def test_active_phase_cancel_denied(provider, root, phase):
    coordinator, plan, gate, worker = provider
    op = str(uuid4())
    journal = coordinator.journal(op, plan)
    with ledger.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
        receipt = session.reserve(op, permit)
        journal.append(session, "RESERVED", native.digest(native.canonical(receipt)))
        for step in native.PHASES[1 : native.PHASES.index(phase) + 1]:
            journal.append(session, step, "e" * 64)
    before = snapshot(root)
    with pytest.raises(ValueError, match="active_or_unknown"):
        coordinator.cancel_pending(op, plan)
    assert snapshot(root) == before


def test_reserved_cancel_retains_consumption(provider, root):
    coordinator, plan, gate, _ = provider
    op = str(uuid4())
    journal = coordinator.journal(op, plan)
    with ledger.ReservationSession(str(root)) as session:
        permit, _ = gate.check(session, plan, "submit")
        journal.create(permit)
        receipt = session.reserve(op, permit)
        journal.append(session, "RESERVED", native.digest(native.canonical(receipt)))
    before = (root / ledger.LEDGER).read_bytes()
    assert coordinator.cancel_pending(op, plan)["progress"]["phase"] == "CANCELLED"
    assert (root / ledger.LEDGER).read_bytes() == before


@pytest.mark.parametrize("failure", ["gap", "extra", "partial", "chain", "receipt", "terminal"])
def test_tampered_or_partial_record_preserved_rejected(provider, root, failure):
    coordinator, plan, _, _ = provider
    op = str(uuid4())
    coordinator.accept(op, plan)
    journal = coordinator.journal(op, plan)
    path = root / ledger.JOBS / op / "work/operation"
    if failure == "gap":
        (path / "02.json").unlink()  # Disposable fault injection only.
    elif failure == "extra":
        (path / "other.json").write_bytes(b"{}")
    elif failure == "partial":
        (path / "06.json").write_bytes(b"{")
    elif failure == "receipt":
        item = root / ledger.JOBS / op / "work/reservation-receipt.json"
        value = ledger.read(str(item))
        value["intent_sha256"] = "9" * 64
        item.write_bytes(native.canonical(value))
    else:
        value = native.read(str(path / "05.json"))
        if failure == "chain":
            value["previous_sha256"] = "9" * 64
        else:
            value["phase"] = "RUNNING"
        (path / "05.json").write_bytes(native.canonical(value))
    before = snapshot(root)
    with pytest.raises((ValueError, KeyError)):
        journal.observation()
    assert snapshot(root) == before


def test_same_id_different_plan_and_legacy_directory_denied(provider, root):
    coordinator, plan, _, worker = provider
    op = str(uuid4())
    coordinator.accept(op, plan)
    wrong = copy.deepcopy(plan)
    wrong["request"]["result_reservation_bytes"] += 1
    with pytest.raises(ValueError, match="replay_conflict"):
        coordinator.accept(op, wrong)
    legacy = str(uuid4())
    directory = root / ledger.JOBS / legacy
    directory.mkdir(mode=0o700)
    (directory / "work").mkdir(mode=0o700)
    with pytest.raises(ValueError, match="occupied_identity"):
        coordinator.accept(legacy, plan)
    assert worker.calls == 1


def test_worker_requires_actual_session_not_fd_or_json(provider):
    coordinator, plan, gate, _ = provider
    journal = coordinator.journal(str(uuid4()), plan)
    for pretend in (None, {}, SimpleNamespace(root=coordinator.root, fd=1)):
        with pytest.raises(ValueError, match="owned_session"):
            journal.append(pretend, "RESERVED", "e" * 64)


@pytest.mark.skipif(os.name != "posix", reason="actual fork/flock requires POSIX")
def test_forked_worker_holds_lock_but_lookup_and_retry_remain_available(provider, root):
    coordinator, plan, gate, _ = provider
    release = root / "fixture-release"
    entered = root / "fixture-entered"

    def work(session, journal, plan):
        entered.write_bytes(b"entered")
        deadline = time.time() + 15
        while not release.exists() and time.time() < deadline:
            time.sleep(0.02)
        if not release.exists():
            raise ValueError("fixture timeout")
        journal.append(session, "EXTRACTING", "4" * 64)
        journal.append(session, "SUCCEEDED", "5" * 64)

    fork = native.ForkWorker(work)
    started = []

    def start(session, journal, plan):
        started.append(fork.start(session, journal, plan))

    coordinator.worker = SimpleNamespace(start=start)
    op = str(uuid4())
    coordinator.accept(op, plan)
    try:
        deadline = time.time() + 10
        while not entered.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert entered.exists()
        assert coordinator.lookup(op, plan)["progress"]["phase"] == "RUNNING"
        assert coordinator.accept(op, plan)["progress"]["phase"] == "RUNNING"
        with pytest.raises((ValueError, OSError)):
            ledger.ReservationSession(str(root))
        with pytest.raises((ValueError, OSError)):
            coordinator.accept(str(uuid4()), plan)
        with pytest.raises((ValueError, OSError)):
            coordinator.cancel_pending(op, plan)
    finally:
        release.write_bytes(b"release")
        _, status = os.waitpid(started[0], 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert coordinator.lookup(op, plan)["progress"]["phase"] == "SUCCEEDED"
    with ledger.ReservationSession(str(root)):
        pass
    assert ledger.read(str(root / ledger.LEDGER))["count"] == SEED["count"] + 1
