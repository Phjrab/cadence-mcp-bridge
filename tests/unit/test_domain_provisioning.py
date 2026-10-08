"""Disposable existing-domain records; not operator consent or Cadence evidence."""

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from cadence_mcp_bridge import _domain_migration as migration
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import domain_provisioning
from cadence_mcp_bridge.__main__ import main

EXAMPLE = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"


@pytest.fixture
def domain(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    (root / "sim-mcp-v2-jobs").mkdir(mode=0o700)
    (root / accounting.JOBS).mkdir(mode=0o700)
    (root / "run.lock").write_bytes(b"")
    (root / "run.lock").chmod(0o600)
    baseline = {"campaign_id": "AUTO-PHASE-01", "count": 82, "result_reserved_bytes": 9798942720}
    accounting.write_new(str(root / accounting.LEDGER), baseline)
    operation = str(uuid4())
    work = root / accounting.JOBS / operation / "work"
    work.mkdir(mode=0o700, parents=True)
    work.parent.chmod(0o700)
    accounting.write_new(str(work / "attempt-reserved"), baseline)
    value = json.loads(EXAMPLE.read_bytes())
    value["limits"]["spectre_attempts"] = 500
    value["limits"]["result_reserved_bytes"] = 10737418240
    # Synthetic root/host binding only. Native identity and flock are separate cases.
    monkeypatch.setattr(migration, "profile", lambda profile: str(root))
    real_lock = installer._operator_lock
    monkeypatch.setattr(installer, "_operator_lock", lambda root: None)
    return root, value, operation, real_lock


def request(domain):
    _, value, _, _ = domain
    plan = migration.plan(value, "a" * 64)
    return {
        "plan": plan["plan"],
        "expected_plan_sha256": plan["plan_sha256"],
        "operator_authority": "synthetic test scope, NOT a human approval",
    }


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_plan_is_readonly_and_apply_preserves_counter_history(domain):
    root, _, _, _ = domain
    before = snapshot(root)
    req = request(domain)
    assert snapshot(root) == before
    assert req["plan"]["authority"] == "PLAN_IS_NOT_OPERATOR_APPROVAL"
    receipt = migration.apply(req, "a" * 64)
    assert receipt["anchor_created"] is True
    assert receipt["execution_authorized"] is False
    assert receipt["ledger_initialized"] is False and receipt["ledger_modified"] is False
    for name, data in before.items():
        assert (root / name).read_bytes() == data
    after = snapshot(root)
    repeated = migration.apply(req, "a" * 64)
    assert repeated["anchor_created"] is False
    assert snapshot(root) == after
    assert accounting.read(str(root / accounting.REGISTRY / "manifest.json"))["baseline"] == {
        "campaign_id": "AUTO-PHASE-01",
        "count": 82,
        "result_reserved_bytes": 9798942720,
    }


def test_known_interrupted_anchor_creation_resumes_without_reset(domain, monkeypatch):
    root, _, _, _ = domain
    req = request(domain)
    original = accounting.write_new

    def interrupted(path, value):
        if path.endswith("reservation-identity/manifest.json"):
            raise OSError("synthetic interruption")
        return original(path, value)

    monkeypatch.setattr(accounting, "write_new", interrupted)
    before = (root / accounting.LEDGER).read_bytes()
    with pytest.raises(OSError, match="synthetic interruption"):
        migration.apply(req, "a" * 64)
    assert list((root / accounting.REGISTRY).iterdir()) == []
    assert (root / accounting.LEDGER).read_bytes() == before
    monkeypatch.setattr(accounting, "write_new", original)
    assert migration.apply(req, "a" * 64)["anchor_created"]
    assert (root / accounting.LEDGER).read_bytes() == before


def test_consumption_after_plan_rejects_and_preserves_new_usage(domain):
    root, _, _, _ = domain
    req = request(domain)
    current = {
        "campaign_id": "AUTO-PHASE-01",
        "count": 83,
        "result_reserved_bytes": accounting.expected_bytes(83, []),
    }
    (root / accounting.LEDGER).write_bytes(accounting.canonical(current))
    with pytest.raises(ValueError, match="migration_snapshot_drift"):
        migration.apply(req, "a" * 64)
    assert accounting.read(str(root / accounting.LEDGER)) == current
    assert not (root / accounting.REGISTRY).exists()


def test_forged_anchor_is_recomputed_before_writes(domain):
    root, _, _, _ = domain
    req = request(domain)
    req["plan"]["anchor"]["ledger_ref"] = "/etc/passwd"
    req["expected_plan_sha256"] = migration.digest(migration.canonical(req["plan"]))
    with pytest.raises(ValueError, match="migration_snapshot_drift"):
        migration.apply(req, "a" * 64)
    assert not (root / accounting.REGISTRY).exists()


@pytest.mark.parametrize("field", ["hash", "helper", "authority", "schema"])
def test_stale_binding_or_invalid_request_creates_no_state(domain, field):
    root, _, _, _ = domain
    req = request(domain)
    if field == "hash":
        req["expected_plan_sha256"] = "b" * 64
    elif field == "authority":
        req["operator_authority"] = ""
    elif field == "schema":
        req["plan"]["schema_version"] = True
        req["expected_plan_sha256"] = migration.digest(migration.canonical(req["plan"]))
    before = snapshot(root)
    with pytest.raises(ValueError):
        migration.apply(req, "b" * 64 if field == "helper" else "a" * 64)
    assert snapshot(root) == before


def test_orphan_registry_or_changed_receipt_never_reinitializes(domain):
    root, _, _, _ = domain
    req = request(domain)
    (root / accounting.REGISTRY).mkdir(mode=0o700)
    with pytest.raises(ValueError, match="migration_unrecorded_partial_state"):
        migration.apply(req, "a" * 64)
    assert not (root / "operator-domain-migration").exists()


def test_active_or_unresolved_domain_denies_plan_without_changes(domain):
    root, value, _, _ = domain
    (root / accounting.JOBS / "active").write_bytes(b"unresolved")
    before = snapshot(root)
    with pytest.raises(ValueError, match="migration_active_or_unresolved"):
        migration.plan(value, "a" * 64)
    assert snapshot(root) == before


def test_identity_index_is_usable_by_existing_accounting_without_new_budget(domain):
    root, _, _, _ = domain
    req = request(domain)
    receipt = migration.apply(req, "a" * 64)
    anchor = req["plan"]["anchor"]
    binding = {
        "root_sha256": anchor["root_sha256"],
        "resource_domain_sha256": anchor["resource_domain_sha256"],
        "ledger_ref": accounting.LEDGER,
        "identity_manifest_sha256": receipt["identity_manifest_sha256"],
    }
    assert accounting.identity_manifest(str(root), binding) == anchor
    assert (
        accounting.audit(str(root), anchor["baseline"], anchor, receipt["identity_manifest_sha256"])
        == []
    )


def test_export_is_package_only_exclusive_and_makes_no_remote_call(tmp_path, monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr(domain_provisioning, "run_fixed", spy)
    output = tmp_path / "helper"
    report = domain_provisioning.export(output)
    assert report["remote_contact"] is False and report["ledger_initialized"] is False
    assert (
        report["manifest_sha256"]
        == hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    )
    assert set(p.name for p in output.iterdir()) == set(migration.MEMBERS) | {"manifest.json"}
    spy.assert_not_called()
    with pytest.raises(ValueError):
        domain_provisioning.export(output)


def test_stale_local_helper_hash_is_denied_before_ssh(tmp_path, monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr(domain_provisioning, "run_fixed", spy)
    with pytest.raises(ValueError, match="helper_package_binding"):
        domain_provisioning.prepare(EXAMPLE, tmp_path / "plan.json", "b" * 64)
    spy.assert_not_called()


def test_cli_export_and_denial_never_expose_private_paths(tmp_path, capsys):
    target = tmp_path / "helper"
    assert main(["domain", "export-helper-bundle", "--output", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["execution_authorized"] is False
    assert main(["domain", "export-helper-bundle", "--output", str(target)]) == 1
    report = capsys.readouterr().out
    assert str(target) not in report and "OPERATOR_DOMAIN_SETUP_REJECTED" in report


def test_linux_domain_busy_uses_existing_lock(domain, monkeypatch):
    if os.name != "posix":
        pytest.skip("actual POSIX flock")
    import fcntl

    root, value, _, real_lock = domain
    monkeypatch.setattr(installer, "_operator_lock", real_lock)
    with (root / "run.lock").open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="operator_domain_busy"):
            migration.plan(value, "a" * 64)
    assert not (root / accounting.REGISTRY).exists()


@pytest.mark.parametrize("field", ["helper", "plan", "profile", "authority"])
def test_apply_cli_rejects_stale_authority_or_binding_before_ssh(
    domain, tmp_path, monkeypatch, field
):
    _, value, _, _ = domain
    spy = MagicMock()
    monkeypatch.setattr(domain_provisioning, "run_fixed", spy)
    _, _, helper = domain_provisioning.contents()
    receipt = migration.plan(value, helper)
    path = tmp_path / "private-plan.json"
    path.write_bytes(json.dumps(receipt).encode())
    profile = tmp_path / "environment.json"
    profile.write_bytes(json.dumps(value).encode())
    expected = receipt["plan_sha256"]
    authority = "synthetic operator instruction, not actual consent"
    if field == "helper":
        helper = "b" * 64
    elif field == "plan":
        expected = "b" * 64
    elif field == "profile":
        value["ssh_alias"] = "another-host"
        profile.write_bytes(json.dumps(value).encode())
    else:
        authority = "invalid\nrecord"
    with pytest.raises(ValueError):
        domain_provisioning.apply_existing(
            profile, path, tmp_path / "out", expected, helper, authority
        )
    spy.assert_not_called()


def test_apply_cli_fixed_transport_verifies_remote_conservation_receipt(
    domain, tmp_path, monkeypatch
):
    _, value, _, _ = domain
    _, _, helper = domain_provisioning.contents()
    plan = migration.plan(value, helper)
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(json.dumps(plan).encode())
    profile_path = tmp_path / "environment.json"
    profile_path.write_bytes(json.dumps(value).encode())
    monkeypatch.setattr(domain_provisioning.shutil, "which", lambda name: "ssh.exe")
    invocations = []

    def transport(argv, payload, environment, **bounds):
        invocations.append(argv)
        request = json.loads(payload)
        assert request["operator_authority"] == "synthetic scope only"
        assert bounds == {"timeout": 60, "limit": 262144}
        result = migration.apply(request, helper)
        return 0, json.dumps(result).encode(), b""

    monkeypatch.setattr(domain_provisioning, "run_fixed", transport)
    result = domain_provisioning.apply_existing(
        profile_path,
        plan_path,
        tmp_path / "receipt.json",
        plan["plan_sha256"],
        helper,
        "synthetic scope only",
    )
    assert result["ledger_modified"] is False and result["execution_authorized"] is False
    assert invocations[0][-2:] == ["apply-existing", helper]
    assert "StrictHostKeyChecking=yes" in invocations[0]
    assert "sudo" not in invocations[0]

    def corrupted(argv, payload, environment, **bounds):
        result = json.loads((tmp_path / "receipt.json").read_bytes())
        result["reservation_cost"] = 1
        return 0, json.dumps(result).encode(), b""

    monkeypatch.setattr(domain_provisioning, "run_fixed", corrupted)
    with pytest.raises(ValueError, match="apply_receipt_binding"):
        domain_provisioning.apply_existing(
            profile_path,
            plan_path,
            tmp_path / "bad-receipt.json",
            plan["plan_sha256"],
            helper,
            "synthetic scope only",
        )
    assert not (tmp_path / "bad-receipt.json").exists()
