"""Protected old/generic native coverage on owned synthetic files only."""

import errno
from uuid import uuid4

import pytest
from test_storage_worker import store as store

from cadence_mcp_bridge import _storage_worker as worker
from cadence_mcp_bridge.storage import StorageSnapshot, snapshot_digest


def generic_job(path, identity):
    job = path / "native-mcp-v1-jobs" / identity
    operation = job / "work" / "operation"
    operation.mkdir(parents=True)
    plan = dict(analysis="dc", schema_version=1)
    (operation / "admission.json").write_bytes(worker.canonical(dict(
        schema_version=1, operation_id=identity, plan=plan, plan_sha256=worker.digest(plan),
        binding={"synthetic": True},
    )))
    (job / "work" / "retained-result.bin").write_bytes(b"protected output evidence")
    return job


@pytest.mark.parametrize("old", [False, True])
def test_native_old_and_generic_job_roots_share_one_protected_group_without_collisions(store, old):
    io, root, path = store
    identity = str(uuid4())
    generic_job(path, identity)
    if old:
        leaf = path / "native-mcp-v1-jobs" / str(uuid4())
        leaf.mkdir(parents=True)
        (leaf / "request.json").write_bytes(worker.canonical(dict(analysis="dc")))
    before = {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    observed = StorageSnapshot.model_validate(worker.snapshot(io, root, False, native_generic=True))
    assert observed.snapshot_id == snapshot_digest(observed)
    native = [a for a in observed.artifacts if a.storage_group_id == "native"]
    assert len(native) == 1 and native[0].job_count == (2 if old else 1)
    assert native[0].analysis_type == "dc" and native[0].retention_class == "REPLAY_REQUIRED"
    assert native[0].deletion_status == "PROTECTED_OR_UNKNOWN" and native[0].replay_dependency
    assert observed.group_coverage["native"] == "SCANNED" and observed.coverage_complete
    assert native[0].size_bytes == sum(
        len(raw) for p, raw in before.items() if p.parts[-1] != "counter.json"
    )
    assert before == {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    legacy = worker.snapshot(io, root, False)
    assert sum(a["job_count"] for a in legacy["artifacts"] if
               a["storage_group_id"] == "native") == (1 + int(old))


def test_partial_old_native_scan_cannot_be_hidden_by_successful_generic_scan(store, monkeypatch):
    io, root, path = store
    identity = str(uuid4())
    (path / "native-mcp-v1-jobs" / identity).mkdir(parents=True)
    generic_job(path, str(uuid4()))
    real = io.open

    def fail_old(parent, name, **options):
        if name == "native-mcp-v1-jobs":
            raise OSError(errno.EACCES, "synthetic inaccessible protected root")
        return real(parent, name, **options)

    monkeypatch.setattr(io, "open", fail_old)
    value = worker.snapshot(io, root, False, native_generic=True)
    assert value["group_coverage"]["native"] == "BLOCKED"
    assert value["group_coverage_reason"]["native"] == "io_unavailable"
    assert not value["coverage_complete"]
    assert all(a["deletion_status"] != "ELIGIBLE" for a in value["artifacts"])


def test_both_native_generations_share_node_budget_and_busy_inventory_remains_protected(
    store, monkeypatch,
):
    io, root, path = store
    leaf = path / "native-mcp-v1-jobs" / str(uuid4())
    leaf.mkdir(parents=True)
    (leaf / "request.json").write_bytes(worker.canonical(dict(analysis="dc")))
    generic_job(path, str(uuid4()))
    monkeypatch.setattr(worker, "MAX_NODES", 2)
    before = {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    value = worker.snapshot(io, root, False, native_generic=True)
    assert not value["coverage_complete"] and value["group_coverage"]["native"] == "PARTIAL"
    assert value["scan_nodes"] <= 6 * worker.MAX_NODES
    busy = worker.snapshot(io, root, False, lock_held=False, native_generic=True)
    assert busy["active_eda"] and not busy["coverage_complete"]
    assert all(a["retention_class"] == "ACTIVE" for a in busy["artifacts"])
    assert before == {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
