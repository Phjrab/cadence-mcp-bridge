"""Disposable local metadata transactions, never actual design or EDA evidence."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from cadence_mcp_bridge import design_revisions
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.design_revisions import (
    RevisionEvidence,
    RevisionRecord,
    RevisionRejected,
    RevisionStore,
)
from cadence_mcp_bridge.schematic_plan import (
    DeviceRegistry,
    RevisionBinding,
    SchematicPlan,
    dry_run_plan,
    synthetic_inverter_fixture,
)


def fixture() -> tuple[RevisionBinding, DeviceRegistry, SchematicPlan]:
    binding = RevisionBinding(
        workspace_id="qa",
        design_id="inverter",
        revision_id="r-one",
        source_baseline_sha256="a" * 64,
    )
    registry, plan = synthetic_inverter_fixture(binding)
    return binding, registry, plan


def test_atomic_immutable_retry_parent_and_evidence_scope(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    root = store.add(plan, registry, binding)
    assert store.add(plan, registry, binding) == root
    assert store.read("qa", "inverter", "r-one") == root
    assert root.status == "plan_validated" and not root.execution_authorized
    child_binding = binding.model_copy(
        update={
            "revision_id": "r-two",
            "parent_revision_id": "r-one",
            "parent_revision_sha256": root.revision_sha256,
        }
    )
    child = store.add(plan.model_copy(update={"binding": child_binding}), registry, child_binding)
    ref = RevisionEvidence(
        evidence_id="result-one",
        binding=binding,
        revision_sha256=root.revision_sha256,
        semantic_sha256=plan.semantic_sha256,
        kind="simulation",
        operation_id=str(uuid4()),
        result_sha256="b" * 64,
        reported_outcome="pass",
    )
    store.attach(ref)
    store.attach(ref)
    assert store.evidence("qa", "inverter", "r-one") == [ref]
    assert store.evidence("qa", "inverter", "r-two") == []
    assert child.status == "plan_validated"
    with pytest.raises(RevisionRejected, match="evidence_revision_mismatch"):
        store.attach(ref.model_copy(update={"binding": child_binding}))
    with pytest.raises(RevisionRejected, match="immutable_evidence_conflict"):
        store.attach(ref.model_copy(update={"reported_outcome": "fail"}))


def test_parent_baseline_and_expected_binding_reject_without_partial_record(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    root = store.add(plan, registry, binding)
    for changes in ({"parent_revision_sha256": "c" * 64}, {"source_baseline_sha256": "d" * 64}):
        child = binding.model_copy(
            update={
                "revision_id": "child",
                "parent_revision_id": "r-one",
                "parent_revision_sha256": root.revision_sha256,
                **changes,
            }
        )
        with pytest.raises(ValueError):
            store.add(plan.model_copy(update={"binding": child}), registry, child)
        with pytest.raises(RevisionRejected, match="revision_not_found"):
            store.read("qa", "inverter", "child")
    with pytest.raises(ValueError):
        store.add(plan, registry, binding.model_copy(update={"design_id": "wrong"}))


def test_database_identity_protects_existing_operational_journal(tmp_path: Path) -> None:
    path = tmp_path / "analysis.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE preserved (spent INTEGER)")
        conn.execute("INSERT INTO preserved VALUES (126)")
    before = path.read_bytes()
    store = RevisionStore(path)
    with pytest.raises(RevisionRejected, match="foreign_database_denied"):
        store.initialize()
    assert path.read_bytes() == before
    missing = tmp_path / "absent.sqlite3"
    with pytest.raises(RevisionRejected, match="not_initialized"):
        RevisionStore(missing).read("qa", "inverter", "r-one")
    assert not missing.exists()


def test_interrupted_transaction_rolls_back_and_parallel_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    with pytest.raises(RuntimeError), store.connection(write=True) as conn:
        conn.execute("INSERT INTO revisions VALUES('a','b','c','x','invalid')")
        raise RuntimeError("simulated power interruption before commit")
    with store.connection(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 0
    binding, registry, plan = fixture()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: RevisionStore(store.path).add(plan, registry, binding), range(2))
        )
    assert results[0] == results[1]
    with store.connection(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1


def test_revision_conflict_and_tampering_reject(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    store.add(plan, registry, binding)
    other = binding.model_copy(update={"source_baseline_sha256": "b" * 64})
    with pytest.raises(RevisionRejected, match="immutable_revision_conflict"):
        store.add(plan.model_copy(update={"binding": other}), registry, other)
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE revisions SET digest=?", ("0" * 64,))
    with pytest.raises(RevisionRejected, match="revision_digest_mismatch"):
        store.read("qa", "inverter", "r-one")


def test_installed_style_cli_example_record_show_has_no_verification_promotion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    examples = tmp_path / "example"
    assert main(["operator-design", "example", "--output", str(examples)]) == 0
    capsys.readouterr()
    store = tmp_path / "revisions.sqlite3"
    assert main(["operator-design", "init", "--store", str(store)]) == 0
    capsys.readouterr()
    command = ["operator-design", "record", "--store", str(store)]
    for name in ("plan", "registry", "binding"):
        command.extend(["--" + name, str(examples / (name + ".json"))])
    assert main(command) == 0
    first = json.loads(capsys.readouterr().out)
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before
    assert (
        main(
            [
                "operator-design",
                "show",
                "--store",
                str(store),
                "--workspace",
                "synthetic-work",
                "--design",
                "inverter",
                "--revision",
                "draft-one",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert set(result["verification"].values()) == {"NOT_ASSESSED"}
    assert result["remote_contact"] is False and result["execution_authorized"] is False


@pytest.mark.parametrize("tamper", ["semantic-diff", "display-hash", "electrical-wiring"])
def test_rehashed_payload_still_requires_actual_plan_validation(
    tmp_path: Path, tamper: str
) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    original = store.add(plan, registry, binding)
    raw = json.loads(original.model_dump_json())
    if tamper == "semantic-diff":
        raw["validation"]["semantic_diff"] = []
    elif tamper == "display-hash":
        raw["validation"]["display_sha256"] = "e" * 64
    else:
        raw["plan"]["dut"]["instances"][0]["connections"][0]["net_id"] = "input"
        altered = SchematicPlan.model_validate_json(json.dumps(raw["plan"]))
        raw["validation"]["plan_sha256"] = altered.plan_sha256
        raw["validation"]["semantic_sha256"] = altered.semantic_sha256
    # The ordinary digest and embedded binding checks alone all match. The
    # independent dry-run on read must still detect the false validation.
    forged = RevisionRecord.model_validate_json(json.dumps(raw))
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE revisions SET digest=?, payload=?",
            (forged.revision_sha256, forged.model_dump_json()),
        )
    preserved = store.path.read_bytes()
    with pytest.raises(ValueError, match="validation_mismatch|wiring rule"):
        RevisionStore(store.path).read("qa", "inverter", "r-one")
    assert store.path.read_bytes() == preserved


def test_ordering_only_retry_keeps_original_record_and_database(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    first = store.add(plan, registry, binding)
    raw_plan = json.loads(plan.model_dump_json())
    raw_registry = json.loads(registry.model_dump_json())
    for circuit in (raw_plan["dut"], raw_plan["testbench"]):
        for key in ("nets", "pins", "instances"):
            circuit[key].reverse()
        for instance in circuit["instances"]:
            instance["connections"].reverse()
            instance["parameters"].reverse()
    raw_registry["devices"].reverse()
    for device in raw_registry["devices"]:
        device["parameters"].reverse()
        device["terminals"].reverse()
    reordered_plan = SchematicPlan.model_validate_json(json.dumps(raw_plan))
    reordered_registry = DeviceRegistry.model_validate_json(json.dumps(raw_registry))
    before = store.path.read_bytes()
    retried = RevisionStore(store.path).add(reordered_plan, reordered_registry, binding)
    assert retried == first
    assert retried.revision_sha256 == first.revision_sha256
    assert store.path.read_bytes() == before


def test_invalid_model_copy_reference_is_not_persisted(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    record = store.add(plan, registry, binding)
    reference = RevisionEvidence(
        evidence_id="unverified-result",
        binding=binding,
        revision_sha256=record.revision_sha256,
        semantic_sha256=plan.semantic_sha256,
        kind="simulation",
        operation_id=str(uuid4()),
        result_sha256="b" * 64,
        reported_outcome="pass",
    )
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.attach(reference.model_copy(update={"provenance": "actual_lvs_verified"}))
    assert store.path.read_bytes() == before
    assert RevisionStore(store.path).evidence("qa", "inverter", "r-one") == []


def test_capacity_failure_rolls_back_without_making_prior_records_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    root = store.add(plan, registry, binding)
    cap = store.path.stat().st_size
    monkeypatch.setattr(design_revisions, "MAX_BYTES", cap)
    child_binding = binding.model_copy(
        update={
            "revision_id": "r-two",
            "parent_revision_id": "r-one",
            "parent_revision_sha256": root.revision_sha256,
        }
    )
    with pytest.raises((sqlite3.DatabaseError, RevisionRejected)):
        store.add(plan.model_copy(update={"binding": child_binding}), registry, child_binding)
    assert store.path.stat().st_size <= cap
    assert RevisionStore(store.path).read("qa", "inverter", "r-one") == root
    with pytest.raises(RevisionRejected, match="revision_not_found"):
        store.read("qa", "inverter", "r-two")
    assert store.add(plan, registry, binding) == root


def test_parent_depth_limit_cannot_commit_an_unreadable_child(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    current = store.add(plan, registry, binding)
    # Materialize an entirely valid fixture chain efficiently; each payload has
    # its independently calculated parent digest and complete dry-run result.
    with sqlite3.connect(store.path) as connection:
        for number in range(2, 65):
            child_binding = binding.model_copy(
                update={
                    "revision_id": f"r-{number}",
                    "parent_revision_id": current.plan.binding.revision_id,
                    "parent_revision_sha256": current.revision_sha256,
                }
            )
            child_plan = plan.model_copy(update={"binding": child_binding})
            current = RevisionRecord(
                plan=child_plan,
                registry=registry,
                validation=dry_run_plan(child_plan, registry, child_binding, current.plan),
                status="plan_validated",
            )
            connection.execute(
                "INSERT INTO revisions VALUES(?,?,?,?,?)",
                (
                    binding.workspace_id,
                    binding.design_id,
                    child_binding.revision_id,
                    current.revision_sha256,
                    current.model_dump_json(),
                ),
            )
    assert store.read("qa", "inverter", "r-64") == current
    child_binding = binding.model_copy(
        update={
            "revision_id": "r-65",
            "parent_revision_id": "r-64",
            "parent_revision_sha256": current.revision_sha256,
        }
    )
    with pytest.raises(RevisionRejected, match="revision_parent_cycle_or_depth"):
        store.add(plan.model_copy(update={"binding": child_binding}), registry, child_binding)
    assert store.read("qa", "inverter", "r-64") == current
    with pytest.raises(RevisionRejected, match="revision_not_found"):
        store.read("qa", "inverter", "r-65")


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
@pytest.mark.parametrize("operation", ["initialize", "read"])
def test_linked_sidecars_cannot_modify_other_files(
    tmp_path: Path, suffix: str, operation: str
) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    if operation == "read":
        store.initialize()
        binding, registry, plan = fixture()
        store.add(plan, registry, binding)
    target = tmp_path / "protected-evidence"
    target.write_bytes(b"prior operator evidence; never SQLite sidecar")
    sidecar = tmp_path / (store.path.name + suffix)
    try:
        sidecar.symlink_to(target)
    except OSError:
        pytest.skip("host does not permit creating an owned symlink fixture")
    before = target.read_bytes()
    with pytest.raises(RevisionRejected, match="revision_store_links_denied"):
        if operation == "initialize":
            store.initialize()
        else:
            store.read("qa", "inverter", "r-one")
    assert target.read_bytes() == before
    assert sidecar.is_symlink()
    if operation == "initialize":
        assert not store.path.exists()


def test_foreign_hot_journal_is_not_recovered_before_identity_rejection(tmp_path: Path) -> None:
    path = tmp_path / "foreign-analysis.sqlite3"
    crashed_writer = """
import os
import sqlite3
import sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA journal_mode=DELETE')
connection.execute('PRAGMA synchronous=FULL')
connection.execute('PRAGMA cache_size=5')
connection.execute('CREATE TABLE preserved (value BLOB)')
connection.executemany('INSERT INTO preserved VALUES(?)', [(b'a' * 8192,)] * 32)
connection.commit()
connection.execute('BEGIN IMMEDIATE')
connection.execute('UPDATE preserved SET value=?', (b'b' * 8192,))
os._exit(0)
"""
    subprocess.run([sys.executable, "-I", "-c", crashed_writer, str(path)], check=True)
    journal = path.with_name(path.name + "-journal")
    before_db = path.read_bytes()
    before_journal = journal.read_bytes()
    assert before_journal[:8] == bytes.fromhex("d9d505f920a163d7")
    binding, registry, plan = fixture()
    with pytest.raises(RevisionRejected, match="foreign_database_denied"):
        RevisionStore(path).add(plan, registry, binding)
    assert path.read_bytes() == before_db
    assert journal.read_bytes() == before_journal


def test_owned_store_hot_journal_recovers_on_write_retry_without_new_record(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    original = store.add(plan, registry, binding)
    before = store.path.read_bytes()
    crashed_writer = """
import os
import sqlite3
import sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA synchronous=FULL')
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
connection.execute("UPDATE revisions SET payload=replace(payload, 'inverter', 'corruptx')")
os._exit(0)
"""
    subprocess.run([sys.executable, "-I", "-c", crashed_writer, str(store.path)], check=True)
    journal = store.path.with_name(store.path.name + "-journal")
    assert journal.read_bytes()[:8] == bytes.fromhex("d9d505f920a163d7")
    assert store.path.read_bytes() != before
    restarted = RevisionStore(store.path)
    assert restarted.add(plan, registry, binding) == original
    assert restarted.read("qa", "inverter", "r-one") == original
    assert store.path.read_bytes() == before
    with restarted.connection(write=False) as connection:
        assert connection.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1


def test_wal_database_is_rejected_without_creating_sidecars(tmp_path: Path) -> None:
    store = RevisionStore(tmp_path / "revisions.sqlite3")
    store.initialize()
    binding, registry, plan = fixture()
    store.add(plan, registry, binding)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.close()
    before = store.path.read_bytes()
    assert not store.path.with_name(store.path.name + "-wal").exists()
    assert not store.path.with_name(store.path.name + "-shm").exists()
    with pytest.raises(RevisionRejected):
        store.read("qa", "inverter", "r-one")
    assert store.path.read_bytes() == before
    assert not store.path.with_name(store.path.name + "-wal").exists()
    assert not store.path.with_name(store.path.name + "-shm").exists()
