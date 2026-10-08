"""Authentic-record/gate disposable tests; probes are synthetic, never EDA."""

import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_operator_confirmation import confirmed_domain as confirmed_fixture
from test_shared_reservations import root as root_fixture
from test_shared_reservations import snapshot

from cadence_mcp_bridge import _native_copy as copying
from cadence_mcp_bridge import _native_gate as gate_module
from cadence_mcp_bridge import _native_operations as operations
from cadence_mcp_bridge import _operator_confirmation as confirmation
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge.operator_lifecycle import ProviderAccounting

confirmed_domain = confirmed_fixture
root = root_fixture


@pytest.fixture
def qualified(confirmed_domain, monkeypatch):
    root, profile, request = confirmed_domain
    profile["limits"].update(disk_floor_bytes=0, disk_floor_percent=0)
    source_lib = root.parent / "SourceLib"
    source_lib.mkdir(mode=0o700)
    source = source_lib / "SourceCell"
    source.mkdir(mode=0o700)
    (source / "synthetic-oa").write_bytes(b"synthetic OA placeholder, not native evidence")
    state = root.parent / "synthetic-state"
    state.mkdir(mode=0o700)
    (state / "ADE_state.info").write_bytes(
        b'designInfo = \'("SourceLib" "SourceCell" "schematic" "spectre")\n'
        b'projectDir = \'"~/simulation"\n'
    )
    source_ade = {
        "source_tree_sha256": copying.snapshot(str(source.resolve()))["tree_sha256"],
        "ade_state_tree_sha256": copying.snapshot(str(state.resolve()))["tree_sha256"],
        "model_includes": [],
    }
    raw = confirmation.canonical(profile)
    grant = json.loads(request["grant_json"])
    grant["environment_sha256"] = confirmation.digest(raw)
    request.update(
        profile_json=raw.decode("ascii"), grant_json=confirmation.canonical(grant).decode("ascii")
    )
    request["grant_sha256"] = confirmation.digest(request["grant_json"].encode("ascii"))
    confirmation.confirm(request, "a" * 64)
    registered = {
        "schema_version": 1,
        "identity_manifest_sha256": request["identity_manifest_sha256"],
        **{key: grant[key] for key in ("environment_sha256", "design_sha256", "pdk_sha256")},
        "routes": [
            {
                "design_id": "new-rc",
                "analysis_id": "new-rc-dc",
                "analysis": "dc",
                "variables": [],
                "source_cell": str(source.resolve()),
                "source_state": str(state.resolve()),
                "ade": source_ade,
            }
        ],
    }
    probe = SimpleNamespace(
        observe=lambda *args: {"total_bytes": 40 * 1024**3, "free_bytes": 20 * 1024**3}
    )
    gate = gate_module.ConfirmedGate(
        profile,
        raw,
        registered,
        grant["runner_sha256"],
        "e" * 64,
        (
            accounting,
            confirmation,
            probe,
            None,
            copying,
        ),
    )
    monkeypatch.setattr(gate, "occupancy", lambda: (123, 4096))
    plan = {
        "schema_version": 1,
        **{
            key: grant[key]
            for key in (
                "resource_domain_sha256",
                "runner_sha256",
                "ledger_ref",
                "environment_sha256",
                "design_sha256",
                "pdk_sha256",
            )
        },
        "grant_sha256": request["grant_sha256"],
        "analysis": "dc",
        "attempt_cost": 1,
        "accounting": "existing_remote_shared_ledger_no_reset",
        "request": {
            "schema_version": 1,
            "design_id": "new-rc",
            "analysis_id": "new-rc-dc",
            "values": [],
            "result_reservation_bytes": 16 * 1024**2,
        },
    }
    return root, gate, plan, request


def test_gate_uses_confirmed_logical_id_existing_ledger_and_fresh_accounting(qualified):
    root, gate, plan, _ = qualified
    before = snapshot(root)
    with accounting.ReservationSession(str(root)) as session:
        reservation, observation = gate.check(session, plan, "submit")
    parsed = ProviderAccounting.model_validate_json(confirmation.canonical(observation))
    assert parsed.ledger_ref == "shared-ledger"
    assert reservation["ledger_ref"] == "sim-mcp-v2-jobs/counter.json"
    assert parsed.cumulative_attempts == 82 and parsed.grant_attempts == 0
    assert parsed.logical_bytes == 123 and parsed.allocated_bytes == 4096
    assert reservation["execution_input_sha256"] != reservation["plan_sha256"]
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "change",
    [
        {"runner_sha256": "9" * 64},
        {"design_sha256": "9" * 64},
        {"ledger_ref": "elsewhere"},
        {"schema_version": True},
        {"attempt_cost": True},
        {"extra": "code"},
        {"grant_sha256": "9" * 64},
    ],
)
def test_gate_denies_invalid_identity_before_admission(qualified, change):
    root, gate, plan, _ = qualified
    wrong = dict(plan, **change)
    before = snapshot(root)
    with accounting.ReservationSession(str(root)) as session, pytest.raises((ValueError, OSError)):
        gate.check(session, wrong, "submit")
    assert snapshot(root) == before


def test_no_record_or_revocation_cannot_authorize(qualified):
    root, gate, plan, request = qualified
    confirmation.revoke(
        {
            "profile": gate.profile,
            "grant_sha256": request["grant_sha256"],
            "identity_manifest_sha256": gate.anchor,
            "operator_authority": "SYNTHETIC-revoke",
        },
        "a" * 64,
    )
    before = snapshot(root)
    assert gate.read(plan)["grant_sha256"] == plan["grant_sha256"]
    with (
        accounting.ReservationSession(str(root)) as session,
        pytest.raises(ValueError, match="revoked"),
    ):
        gate.check(session, plan, "submit")
    assert snapshot(root) == before


def test_capacity_accounts_new_batches_and_never_resets(qualified):
    root, gate, plan, _ = qualified
    with accounting.ReservationSession(str(root)) as session:
        for _ in range(6):
            reservation, observation = gate.check(session, plan, "submit")
            op = str(uuid4())
            journal = operations.OperationJournal(str(root), op, plan, accounting)
            journal.create(reservation)
            receipt = session.reserve(op, reservation)
            journal.append(session, "RESERVED", operations.digest(operations.canonical(receipt)))
        assert observation["cumulative_attempts"] == 87
        before_counter = (root / accounting.LEDGER).read_bytes()
        with pytest.raises(ValueError, match="capacity"):
            gate.check(session, plan, "submit")
        _, attestation = gate.check(session, plan, "authorize")
        assert attestation["grant_attempts"] == 6
        _, cancellation = gate.check(session, plan, "cancel_pending")
        assert cancellation["cumulative_attempts"] == 88 and cancellation["grant_attempts"] == 6
    assert (root / accounting.LEDGER).read_bytes() == before_counter


def test_disk_and_probe_failure_cannot_write(qualified):
    root, gate, plan, _ = qualified
    gate.probe.observe = lambda *args: {"total_bytes": 1000, "free_bytes": 1}
    before = snapshot(root)
    with (
        accounting.ReservationSession(str(root)) as session,
        pytest.raises(ValueError, match="capacity"),
    ):
        gate.check(session, plan, "submit")
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "number,reason",
    [
        ("0.55", "grid"),
        ("2", "numeric_region"),
        ("expr()", "scalar"),
        ("NaN", "scalar"),
    ],
)
def test_registered_numeric_checks_are_independent_of_client(qualified, number, reason):
    root, gate, plan, _ = qualified
    wrong = copy.deepcopy(plan)
    wrong["request"]["design_id"] = "new-mos"
    wrong["request"]["analysis_id"] = "new-mos-dc"
    wrong["request"]["values"] = [{"logical_id": "voltage", "unit": "V", "value": number}]
    gate.registration["routes"].append(
        {
            **gate.registration["routes"][0],
            "design_id": "new-mos",
            "analysis_id": "new-mos-dc",
            "analysis": "dc",
            "variables": [
                {
                    "logical_id": "voltage",
                    "cadence_binding": "VB",
                    "unit": "V",
                    "value_type": "real",
                    "mutation_policy": "owned_copy_only",
                    "range_status": "qualified",
                    "minimum": "0",
                    "maximum": "1",
                    "fixed_value": None,
                    "step_policy": "grid",
                    "step": "0.1",
                }
            ],
        }
    )
    before = snapshot(root)
    with (
        accounting.ReservationSession(str(root)) as session,
        pytest.raises(ValueError, match=reason),
    ):
        gate.check(session, wrong, "submit")
    assert snapshot(root) == before


def test_changed_source_denied_before_reservation(qualified):
    from pathlib import Path

    root, gate, plan, _ = qualified
    (Path(gate.route(plan)["source_cell"]) / "synthetic-oa").write_bytes(
        b"modified synthetic source"
    )
    before = snapshot(root)
    with (
        accounting.ReservationSession(str(root)) as session,
        pytest.raises(ValueError, match="source_registration_drift"),
    ):
        gate.check(session, plan, "submit")
    assert snapshot(root) == before


@pytest.mark.parametrize("point", ["before_probe", "during_probe"])
def test_activation_is_rechecked_under_existing_lock_before_reserving(qualified, point):
    root, gate, plan, _ = qualified
    calls = []
    active = [point != "before_probe"]

    def activation():
        # A second owner must never acquire the existing lock during a gate.
        with pytest.raises((ValueError, OSError)):
            accounting.ReservationSession(str(root))
        calls.append(active[0])
        if not active[0]:
            raise ValueError("native_runtime_revoked")

    observe = gate.probe.observe

    def change(*args):
        result = observe(*args)
        active[0] = False
        return result

    gate.activation = activation
    gate.probe.observe = change
    before = snapshot(root)
    coordinator = operations.NativeCoordinator(str(root), accounting, gate, None)
    with pytest.raises(ValueError, match="revoked"):
        coordinator.accept(str(uuid4()), plan)
    assert calls == ([False] if point == "before_probe" else [True, False])
    assert snapshot(root) == before
