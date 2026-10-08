"""Disposable actual-file/process tests; no Cadence, native VM or user grants."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from cadence_mcp_bridge import _shared_reservations as ledger

SEED = {"campaign_id": "AUTO-PHASE-01", "count": 82, "result_reserved_bytes": 9798942720}
AMOUNT = 16 * 1024**2
ASSET = Path(ledger.__file__).resolve()
CHILD = """
import importlib.util,json,os,sys,time
spec=importlib.util.spec_from_file_location("fixed_reservations",sys.argv[1])
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
root,op,binding,crash=sys.argv[2],sys.argv[3],json.loads(sys.argv[4]),sys.argv[5]
if crash.startswith("write"):
    count=[0]; original=m.write_new
    def fault(path,value):
        original(path,value); count[0]+=1
        if count[0]==int(crash[5:]): os._exit(91)
    m.write_new=fault
elif crash=="rename":
    original=os.replace if os.name=="nt" else os.rename
    def fault(src,dst):
        original(src,dst); os._exit(91)
    if os.name=="nt": os.replace=fault
    else: os.rename=fault
for retry in range(100):
    try:
        print(json.dumps(m.reserve(root,op,binding),sort_keys=True)); sys.exit(0)
    except OSError:
        time.sleep(0.02)
    except ValueError as error:
        print(str(error)); sys.exit(70)
sys.exit(75)
"""


@pytest.fixture
def root(tmp_path):
    # POSIX tests must select a --basetemp below a trusted private HOME, not /tmp.
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    (root / "sim-mcp-v2-jobs").mkdir(mode=0o700)
    (root / ledger.JOBS).mkdir(mode=0o700)
    (root / "run.lock").write_bytes(b"")  # Only disposable fixtures provision state.
    os.chmod(root / "run.lock", 0o600)
    ledger.write_new(str(root / ledger.LEDGER), SEED)
    return root


def binding(root, **updates):
    value = {
        "root_sha256": ledger.digest(str(root.resolve()).encode("utf-8")),
        "resource_domain_sha256": "a" * 64,
        "ledger_ref": ledger.LEDGER,
        "grant_sha256": "b" * 64,
        "runner_sha256": "c" * 64,
        "plan_sha256": "d" * 64,
        "execution_input_sha256": "1" * 64,
        "expires_at": int(time.time()) + 600,
        "max_attempts": 8,
        "max_reserved_bytes": 8 * AMOUNT,
        "reserve_bytes": AMOUNT,
        "disk_floor_bytes": 0,
    }
    value.update(updates)
    return value


def job(root):
    op = str(uuid4())
    record = root / ledger.JOBS / op
    record.mkdir(mode=0o700)
    (record / "work").mkdir(mode=0o700)
    return op


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def reserve(root, op, permit):
    return ledger.reserve(str(root), op, permit)


def lookup(root, op, permit):
    return ledger.lookup(str(root), op, permit)


def child(root, op, permit, crash="none"):
    return subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            CHILD,
            str(ASSET),
            str(root),
            op,
            json.dumps(permit),
            crash,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def finish(process):
    stdout, stderr = process.communicate(timeout=30)
    assert stderr == b""
    return process.returncode, stdout.decode("ascii")


def test_two_batches_replay_restart_and_expired_read(root, monkeypatch):
    first, second = job(root), job(root)
    permit = binding(root)
    before = snapshot(root)
    assert lookup(root, first, permit) is None
    assert snapshot(root) == before
    receipt = reserve(root, first, permit)
    assert receipt["status"] == "RESERVATION_COMMITTED_NOT_DISPATCHED"
    after_first = snapshot(root)
    assert reserve(root, first, permit) == receipt
    assert snapshot(root) == after_first
    code, reply = finish(child(root, first, permit))
    assert code == 0 and json.loads(reply) == receipt
    assert snapshot(root) == after_first
    second_receipt = reserve(root, second, {**permit, "plan_sha256": "e" * 64})
    assert second_receipt["after"]["count"] == 84
    assert (
        ledger.read(str(root / ledger.LEDGER))["result_reserved_bytes"]
        == SEED["result_reserved_bytes"] + 2 * AMOUNT
    )
    monkeypatch.setattr(ledger.time, "time", lambda: permit["expires_at"] + 1)
    assert lookup(root, first, permit) == receipt
    assert reserve(root, first, permit) == receipt
    with pytest.raises(ValueError, match="expired"):
        reserve(root, job(root), permit)


@pytest.mark.parametrize("limit", ["attempts", "bytes"])
def test_grant_capacity_is_shared_across_clients(root, limit):
    first, second = job(root), job(root)
    permit = binding(
        root, **({"max_attempts": 1} if limit == "attempts" else {"max_reserved_bytes": AMOUNT})
    )
    reserve(root, first, permit)
    before = snapshot(root)
    code, text = finish(child(root, second, {**permit, "plan_sha256": "e" * 64}))
    assert code == 70 and text.strip() == "reservation_grant_capacity"
    assert snapshot(root) == before


def test_same_operation_process_race_consumes_one_slot(root):
    op, permit = job(root), binding(root)
    results = [finish(p) for p in [child(root, op, permit) for _ in range(8)]]
    assert all(code == 0 for code, _ in results)
    assert len({reply for _, reply in results}) == 1
    assert ledger.read(str(root / ledger.LEDGER))["count"] == 83
    assert len(list(root.rglob("reservation-receipt.json"))) == 1


def test_two_clients_compete_for_last_grant_slot(root):
    ids, permit = [job(root), job(root)], binding(root, max_attempts=1)
    results = [finish(p) for p in [child(root, op, permit) for op in ids]]
    assert sorted(code for code, _ in results) == [0, 70]
    assert ledger.read(str(root / ledger.LEDGER))["count"] == 83


@pytest.mark.parametrize("stage", ["write1", "write2", "write3", "rename", "write4"])
def test_process_death_never_blind_retries_or_refunds(root, stage):
    op, permit = job(root), binding(root)
    code, _ = finish(child(root, op, permit, stage))
    assert code == 91
    before = snapshot(root)
    count = ledger.read(str(root / ledger.LEDGER))["count"]
    assert count == (83 if stage in ("rename", "write4") else 82)
    if stage.startswith("write") and stage != "write4":
        assert (root / (ledger.LEDGER + ".ade-tmp")).exists()
        for action in (lookup, reserve):
            with pytest.raises(ValueError, match="ambiguous_barrier"):
                action(root, op, permit)
    elif stage == "rename":
        assert lookup(root, op, permit)["status"] == "UNKNOWN_OUTCOME"
        assert reserve(root, op, permit)["status"] == "UNKNOWN_OUTCOME"
        next_op = job(root)
        with pytest.raises(ValueError, match="unresolved_intent"):
            reserve(root, next_op, permit)
    else:
        assert lookup(root, op, permit)["status"] == "RESERVATION_COMMITTED_NOT_DISPATCHED"
        assert reserve(root, op, permit) == lookup(root, op, permit)
    assert snapshot(root) == before


def test_later_legacy_advancement_does_not_prove_missing_receipt(root):
    op, permit = job(root), binding(root)
    assert finish(child(root, op, permit, "rename"))[0] == 91
    # Emulate legitimate legacy advancement under the same domain after our rename.
    advanced = dict(
        SEED, count=84, result_reserved_bytes=SEED["result_reserved_bytes"] + 2 * AMOUNT
    )
    (root / ledger.LEDGER).write_bytes(ledger.canonical(advanced))
    before = snapshot(root)
    assert lookup(root, op, permit)["status"] == "UNKNOWN_OUTCOME"
    with pytest.raises(ValueError, match="unresolved_intent"):
        reserve(root, job(root), permit)
    assert snapshot(root) == before


def test_existing_legacy_lock_is_respected(root):
    op, permit = job(root), binding(root)
    fd = ledger.open_lock(str(root))
    try:
        # Child attempts the same physical file lock; no alternate alias/DB lock.
        process = child(root, op, permit)
        time.sleep(0.25)
        assert process.poll() is None
        assert ledger.read(str(root / ledger.LEDGER)) == SEED
    finally:
        os.close(fd)
    assert finish(process)[0] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"plan_sha256": "e" * 64},
        {"execution_input_sha256": "e" * 64},
        {"runner_sha256": "e" * 64},
        {"resource_domain_sha256": "e" * 64},
        {"reserve_bytes": 2 * AMOUNT},
    ],
)
def test_conflicting_replay_is_preserved(root, change):
    op, permit = job(root), binding(root)
    reserve(root, op, permit)
    before = snapshot(root)
    with pytest.raises(ValueError, match="replay_identity"):
        reserve(root, op, {**permit, **change})
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "change",
    [
        {"max_attempts": 9},
        {"max_reserved_bytes": 9 * AMOUNT},
        {"expires_at": int(time.time()) + 1200},
        {"runner_sha256": "e" * 64},
        {"resource_domain_sha256": "e" * 64},
    ],
)
def test_same_grant_policy_drift_cannot_reset_usage(root, change):
    permit = binding(root)
    reserve(root, job(root), permit)
    before = snapshot(root)
    with pytest.raises(ValueError, match="grant_binding_drift"):
        reserve(root, job(root), {**permit, **change})
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_attempts", True),
        ("reserve_bytes", 1.0),
        ("max_attempts", 501),
        ("max_reserved_bytes", ledger.CEILING_BYTES + 1),
        ("ledger_ref", "other/counter.json"),
        ("root_sha256", "f" * 64),
        ("plan_sha256", "d" * 64 + "\\n"),
    ],
)
def test_invalid_binding_does_not_mutate(root, field, value):
    before = snapshot(root)
    with pytest.raises(ValueError):
        reserve(root, job(root), binding(root, **{field: value}))
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "counter",
    [
        dict(SEED, count=True),
        dict(SEED, count=21, result_reserved_bytes=1611661312),
        dict(SEED, count=501),
        dict(SEED, result_reserved_bytes=1),
        {**SEED, "epoch": 2},
    ],
)
def test_corrupt_counter_is_never_initialized_or_reset(root, counter):
    (root / ledger.LEDGER).write_bytes(ledger.canonical(counter))
    before = snapshot(root)
    with pytest.raises(ValueError, match="counter_integrity"):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before


def test_duplicate_key_counter_is_rejected(root):
    raw = ledger.canonical(SEED).replace(b'"count":82', b'"count":81,"count":82')
    (root / ledger.LEDGER).write_bytes(raw)
    before = snapshot(root)
    with pytest.raises(ValueError, match="noncanonical"):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before


@pytest.mark.parametrize("limited", ["count", "bytes"])
def test_global_existing_consumption_still_limits_new_grants(root, limited):
    value = dict(SEED)
    value["count" if limited == "count" else "result_reserved_bytes"] = (
        ledger.CEILING_COUNT if limited == "count" else ledger.CEILING_BYTES
    )
    (root / ledger.LEDGER).write_bytes(ledger.canonical(value))
    before = snapshot(root)
    with pytest.raises(ValueError, match="cumulative_capacity"):
        reserve(root, job(root), binding(root, grant_sha256="f" * 64))
    assert snapshot(root) == before


def test_disk_floor_counts_every_unsettled_reservation(root, monkeypatch):
    permit = binding(root, disk_floor_bytes=AMOUNT)
    reserve(root, job(root), permit)
    monkeypatch.setattr(ledger, "free_bytes", lambda _: 3 * AMOUNT - 1)
    before = snapshot(root)
    with pytest.raises(ValueError, match="physical_disk_floor"):
        reserve(root, job(root), binding(root, grant_sha256="f" * 64, disk_floor_bytes=AMOUNT))
    assert snapshot(root) == before


def test_missing_existing_domain_files_never_creates_replacement(root):
    (root / "run.lock").unlink()
    before = snapshot(root)
    with pytest.raises(OSError):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before


def test_existing_active_or_unreconciled_legacy_job_blocks(root):
    op, permit = job(root), binding(root)
    ledger.write_new(str(root / ledger.JOBS / "active"), op)
    before = snapshot(root)
    with pytest.raises(ValueError, match="active_legacy_job"):
        reserve(root, op, permit)
    assert snapshot(root) == before
    (root / ledger.JOBS / "active").unlink()  # Disposable state only.
    ledger.write_new(
        str(root / ledger.JOBS / op / "work/attempt-reserved"),
        dict(SEED, count=83, result_reserved_bytes=SEED["result_reserved_bytes"] + AMOUNT),
    )
    before = snapshot(root)
    with pytest.raises(ValueError, match="legacy_unreconciled"):
        reserve(root, op, permit)
    assert snapshot(root) == before


@pytest.mark.parametrize("leaf", ["run.lock", ledger.LEDGER])
def test_hardlinked_shared_files_are_rejected(root, leaf):
    original = root / leaf
    other = root / "hardlink"
    other.hardlink_to(original)
    before = snapshot(root)
    with pytest.raises(ValueError, match="unsafe_path"):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before


@pytest.mark.parametrize("change", ["empty", "boolean_version", "float_counter"])
def test_receipt_corruption_is_not_repaired(root, change):
    op, permit = job(root), binding(root)
    reserve(root, op, permit)
    receipt = root / ledger.JOBS / op / "work/reservation-receipt.json"
    value = json.loads(receipt.read_bytes())
    if change == "empty":
        value = {}
    elif change == "boolean_version":
        value["schema_version"] = True
    else:
        value["after"]["count"] = float(value["after"]["count"])
    receipt.write_bytes(ledger.canonical(value))
    before = snapshot(root)
    with pytest.raises(ValueError, match="receipt_binding"):
        lookup(root, op, permit)
    assert snapshot(root) == before


def test_lookup_of_durable_receipt_can_follow_later_legacy_counter(root):
    op, permit = job(root), binding(root)
    receipt = reserve(root, op, permit)
    (root / ledger.LEDGER).write_bytes(
        ledger.canonical(
            dict(SEED, count=84, result_reserved_bytes=SEED["result_reserved_bytes"] + 2 * AMOUNT)
        )
    )
    before = snapshot(root)
    assert lookup(root, op, permit) == receipt
    assert snapshot(root) == before


@pytest.mark.skipif(os.name == "nt", reason="Requires real POSIX flock; covered by Ubuntu CI")
def test_independent_legacy_flock_blocks_our_reservation(root):
    code = (
        "import fcntl,os,sys; fd=os.open(sys.argv[1],os.O_RDWR); "
        "fcntl.flock(fd,fcntl.LOCK_EX); print('LOCKED',flush=True); "
        "sys.stdin.read(1); os.close(fd)"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", code, str(root / "run.lock")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stdout.readline() == b"LOCKED\n"
    before = snapshot(root)
    try:
        with pytest.raises(OSError):
            reserve(root, job(root), binding(root))
        assert snapshot(root) == before
    finally:
        _, error = process.communicate(input=b"x", timeout=10)
        assert process.returncode == 0 and error == b""


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode enforcement; covered by Ubuntu CI")
@pytest.mark.parametrize("path", ["run.lock", ledger.LEDGER, ledger.JOBS])
def test_actual_group_writable_component_is_refused(root, path):
    target = root / path
    original = target.stat().st_mode
    os.chmod(target, original | 0o020)
    before = snapshot(root)
    try:
        with pytest.raises(ValueError, match="unsafe_owner_or_mode"):
            reserve(root, job(root), binding(root))
        assert snapshot(root) == before
    finally:
        os.chmod(target, original)


def test_missing_counter_does_not_initialize_a_new_budget(root):
    (root / ledger.LEDGER).unlink()  # Disposable fixture only.
    before = snapshot(root)
    with pytest.raises(OSError):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before


def test_legacy_default_json_serialization_remains_accepted(root):
    raw = json.dumps(SEED, sort_keys=True).encode("ascii")
    (root / ledger.LEDGER).write_bytes(raw)
    op, permit = job(root), binding(root)
    assert lookup(root, op, permit) is None
    assert (root / ledger.LEDGER).read_bytes() == raw
    assert reserve(root, op, permit)["after"]["count"] == 83


def test_second_batch_can_change_compiled_input_within_same_grant(root):
    permit = binding(root)
    first = reserve(root, job(root), permit)
    second = reserve(root, job(root), {**permit, "execution_input_sha256": "2" * 64})
    assert second["after"]["count"] == first["after"]["count"] + 1
    assert second["intent_sha256"] != first["intent_sha256"]


def test_pre32_legacy_markers_remain_readable_and_unchanged(root):
    markers = []
    for step in (1, 2, 3):
        op = job(root)
        marker = root / ledger.JOBS / op / "work/attempt-reserved"
        value = {
            "campaign_id": "AUTO-PHASE-01",
            "count": 21 + step,
            "result_reserved_bytes": 1611661312 + step * 134217728,
        }
        # Original legacy adapter's exact serialization.
        marker.write_bytes(json.dumps(value, sort_keys=True).encode("ascii"))
        os.chmod(marker, 0o600)
        markers.append((marker, marker.read_bytes()))
    current = (root / ledger.LEDGER).read_bytes()
    op, permit = job(root), binding(root)
    assert lookup(root, op, permit) is None
    assert (root / ledger.LEDGER).read_bytes() == current
    assert reserve(root, op, permit)["after"]["count"] == 83
    assert all(marker.read_bytes() == before for marker, before in markers)


@pytest.mark.parametrize("field,value", [("count", 21), ("result_reserved_bytes", 1745879039)])
def test_legacy_marker_below_original_domain_floor_is_rejected(root, field, value):
    op = job(root)
    marker = root / ledger.JOBS / op / "work/attempt-reserved"
    old = dict(campaign_id="AUTO-PHASE-01", count=22, result_reserved_bytes=1745879040)
    old[field] = value
    ledger.write_new(str(marker), old)
    before = snapshot(root)
    with pytest.raises(ValueError, match="counter_integrity"):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before


def test_unincremented_native_policy_baseline_is_not_a_reserved_marker(root):
    op = job(root)
    marker = root / ledger.JOBS / op / "work/attempt-reserved"
    ledger.write_new(
        str(marker),
        {"campaign_id": "AUTO-PHASE-01", "count": 21, "result_reserved_bytes": 1611661312},
    )
    before = snapshot(root)
    with pytest.raises(ValueError, match="counter_integrity"):
        lookup(root, job(root), binding(root))
    with pytest.raises(ValueError, match="counter_integrity"):
        reserve(root, job(root), binding(root))
    assert snapshot(root) == before
