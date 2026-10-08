"""Conserved real-file accounting/policy transitions on disposable domains only."""

import json
from pathlib import Path

import pytest
from test_domain_provisioning import domain as domain
from test_domain_provisioning import request
from test_shared_reservations import binding, job, snapshot
from test_shared_reservations import root as root

from cadence_mcp_bridge import _domain_migration as migration
from cadence_mcp_bridge import _shared_reservations as ledger


def upgrade(root):
    manifest = ledger.read(str(root / ledger.REGISTRY / "manifest.json"))
    record = dict(
        schema_version=6,
        kind="EXPLICIT_RETAINED_RESULT_LIMIT_16GIB",
        root_sha256=manifest["root_sha256"],
        resource_domain_sha256=manifest["resource_domain_sha256"],
        identity_manifest_sha256=ledger.digest(ledger.canonical(manifest)),
        policy_sha256=ledger.RESULT_POLICY_SHA,
        baseline=ledger.read(str(root / ledger.LEDGER)),
        plan_sha256="e" * 64,
        operator_authority="SYNTHETIC FIXTURE ONLY NOT HUMAN CONSENT",
    )
    ledger.write_new(str(root / ledger.REGISTRY / ledger.RESULT_POLICY_FILE), record)
    return manifest


@pytest.mark.parametrize("upgraded", [False, True])
def test_crossing_old_limit_requires_explicit_policy_and_preserves_replay(root, upgraded):
    if upgraded:
        upgrade(root)
    permit = binding(
        root,
        max_attempts=10,
        max_reserved_bytes=10 * ledger.LEGACY_RESERVATION,
        reserve_bytes=ledger.LEGACY_RESERVATION,
    )
    for _ in range(6):
        ledger.reserve(str(root), job(root), permit)
    before = snapshot(root)
    op = job(root)
    if not upgraded:
        with pytest.raises(ValueError, match="cumulative_capacity"):
            ledger.reserve(str(root), op, permit)
        for path, raw in before.items():
            assert (root / path).read_bytes() == raw
    else:
        result = ledger.reserve(str(root), op, permit)
        used = ledger.read(str(root / ledger.LEDGER))
        assert used["count"] == 89 and used["result_reserved_bytes"] > ledger.CEILING_BYTES
        after = snapshot(root)
        assert ledger.reserve(str(root), op, permit) == result
        assert snapshot(root) == after
        (root / ledger.REGISTRY / ledger.RESULT_POLICY_FILE).unlink()  # Disposable fixture only.
        with pytest.raises(ValueError, match="counter_policy_capacity"):
            ledger.lookup(str(root), op, permit)
        assert ledger.read(str(root / ledger.LEDGER)) == used


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_sha256", "0" * 64),
        ("identity_manifest_sha256", "0" * 64),
        ("operator_authority", ""),
        ("schema_version", True),
        ("resource_domain_sha256", "0" * 64),
    ],
)
def test_policy_tampering_rejects_without_spending(root, field, value):
    upgrade(root)
    path = root / ledger.REGISTRY / ledger.RESULT_POLICY_FILE
    record = ledger.read(str(path))
    record[field] = value
    path.write_bytes(ledger.canonical(record))
    op = job(root)
    before = snapshot(root)
    with pytest.raises(ValueError, match="retained_policy_binding"):
        ledger.reserve(str(root), op, binding(root))
    assert snapshot(root) == before


def setup_registered(domain, monkeypatch):
    root, value, _, _ = domain
    migration.apply(request(domain), "a" * 64)
    home = root.parent / "home"
    home.mkdir(mode=0o700)
    index_dir = home / ".cadence_mcp-domain"
    index_dir.mkdir(mode=0o700)
    anchor = ledger.read(str(root / ledger.REGISTRY / "manifest.json"))
    ledger.write_new(
        str(index_dir / "manifest.json"),
        dict(
            schema_version=1,
            root=str(root),
            resource_domain_sha256=anchor["resource_domain_sha256"],
            identity_manifest_sha256=ledger.digest(ledger.canonical(anchor)),
            plan_sha256="b" * 64,
        ),
    )
    monkeypatch.setattr(migration.os.path, "expanduser", lambda _: str(index_dir / "manifest.json"))
    return root, value


def test_apply_repeat_and_interrupted_postcheck_preserve_existing_files(domain, monkeypatch):
    root, value = setup_registered(domain, monkeypatch)
    before = snapshot(root)
    proposal = migration.result_limit_plan(value, "a" * 64)
    assert snapshot(root) == before
    req = dict(
        plan=proposal["plan"],
        expected_plan_sha256=proposal["plan_sha256"],
        operator_authority="SYNTHETIC NOT USER APPROVAL",
    )
    original = ledger.effective_policy

    def fail_after_write(*args):
        if (root / ledger.REGISTRY / ledger.RESULT_POLICY_FILE).exists():
            raise OSError("synthetic interrupted postcheck")
        return original(*args)

    monkeypatch.setattr(ledger, "effective_policy", fail_after_write)
    with pytest.raises(OSError, match="interrupted"):
        migration.apply_result_limit(req, "a" * 64)
    monkeypatch.setattr(ledger, "effective_policy", original)
    result = migration.apply_result_limit(req, "a" * 64)
    assert result["created"] is False and result["result_ceiling_bytes"] == 17179869184
    assert result["execution_authorized"] is False and result["ledger_modified"] is False
    for path, raw in before.items():
        assert (root / path).read_bytes() == raw
    after = snapshot(root)
    assert migration.apply_result_limit(req, "a" * 64)["created"] is False
    assert snapshot(root) == after


def test_consumption_after_plan_rejects_without_reset(domain, monkeypatch):
    root, value = setup_registered(domain, monkeypatch)
    proposal = migration.result_limit_plan(value, "a" * 64)
    req = dict(
        plan=proposal["plan"],
        expected_plan_sha256=proposal["plan_sha256"],
        operator_authority="SYNTHETIC NOT USER APPROVAL",
    )
    counter = ledger.read(str(root / ledger.LEDGER))
    counter["count"] += 1
    counter["result_reserved_bytes"] += ledger.LEGACY_RESERVATION
    (root / ledger.LEDGER).write_bytes(ledger.canonical(counter))
    before = snapshot(root)
    with pytest.raises(ValueError, match="snapshot_drift"):
        migration.apply_result_limit(req, "a" * 64)
    assert snapshot(root) == before


def test_current_policy_record_binds_latest_limits_and_preserves_prior_files():
    policy_dir = Path(__file__).resolve().parents[2] / "docs/policy"
    record = json.loads((policy_dir / "PHASE_RESULT_LIMIT_V6.json").read_bytes())
    assert ledger.digest(ledger.canonical(record)) == ledger.RESULT_POLICY_SHA
    assert record["max_new_results_bytes"] == 17179869184
    assert record["max_spectre_attempts"] == 500
    assert record["maximum_corrections_same_change"] == 20
    assert ledger.CEILING_BYTES == 10737418240
    assert (
        json.loads((policy_dir / "PHASE_RESULT_LIMIT_V4.json").read_bytes())[
            "max_new_results_bytes"
        ]
        == 10737418240
    )
