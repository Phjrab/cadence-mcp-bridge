"""Conserved real-file accounting/policy transitions on disposable domains only."""

import json
from pathlib import Path

import pytest
from test_domain_provisioning import domain as domain
from test_domain_provisioning import request
from test_shared_reservations import binding, job, snapshot
from test_shared_reservations import root as root

from cadence_mcp_bridge import _domain_migration as migration
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import _shared_reservations as ledger
from cadence_mcp_bridge import domain_provisioning
from cadence_mcp_bridge.environments import load_environment


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


@pytest.mark.parametrize("failure", ["partial", "file_fsync", "after_rename"])
def test_policy_publication_interruption_retains_evidence_and_same_plan_recovers(
    domain, monkeypatch, failure
):
    root, value = setup_registered(domain, monkeypatch)
    before = snapshot(root)
    proposal = migration.result_limit_plan(value, "a" * 64)
    request = dict(
        plan=proposal["plan"],
        expected_plan_sha256=proposal["plan_sha256"],
        operator_authority="SYNTHETIC NOT USER APPROVAL",
    )
    final = root / ledger.REGISTRY / ledger.RESULT_POLICY_FILE
    original_write, original_rename = installer.exclusive, migration.os.rename

    def fail_write(path, data, *args, **kwargs):
        if Path(path).name.startswith(".result-policy-v6-"):
            if failure == "partial":
                Path(path).write_bytes(data[:7])
                Path(path).chmod(0o600)
                raise OSError("synthetic partial policy")
            original_write(path, data, *args, **kwargs)
            raise OSError("synthetic policy file fsync failure")
        return original_write(path, data, *args, **kwargs)

    def fail_rename(source, target):
        original_rename(source, target)
        if Path(target) == final:
            raise OSError("synthetic after policy rename")

    if failure == "after_rename":
        monkeypatch.setattr(migration.os, "rename", fail_rename)
    else:
        monkeypatch.setattr(installer, "exclusive", fail_write)
    with pytest.raises(OSError, match="synthetic"):
        migration.apply_result_limit(request, "a" * 64)
    retained = {p.name: p.read_bytes() for p in root.glob(".result-policy-v6-*")}
    assert final.exists() == (failure == "after_rename")
    if failure != "after_rename":
        assert len(retained) == 1
        # Incomplete private evidence never enters the strict reservation index.
        assert (
            ledger.effective_policy(str(root), proposal["plan"]["anchor"])["result_ceiling_bytes"]
            == ledger.CEILING_BYTES
        )
    monkeypatch.setattr(installer, "exclusive", original_write)
    monkeypatch.setattr(migration.os, "rename", original_rename)
    recovered = migration.apply_result_limit(request, "a" * 64)
    assert recovered["created"] == (failure != "after_rename")
    assert recovered["result_ceiling_bytes"] == 17179869184
    assert {p.name: p.read_bytes() for p in root.glob(".result-policy-v6-*")} == retained
    for name, data in before.items():
        assert (root / name).read_bytes() == data
    assert not migration.apply_result_limit(request, "a" * 64)["created"]


def test_cross_directory_policy_publication_syncs_destination_before_source(domain, monkeypatch):
    root, value = setup_registered(domain, monkeypatch)
    proposal = migration.result_limit_plan(value, "a" * 64)
    request = dict(
        plan=proposal["plan"],
        expected_plan_sha256=proposal["plan_sha256"],
        operator_authority="SYNTHETIC NOT USER APPROVAL",
    )
    after_rename, calls = [], []
    original_rename, original_sync = migration.os.rename, ledger.sync_directory

    def rename(source, target):
        original_rename(source, target)
        if Path(target).name == ledger.RESULT_POLICY_FILE:
            after_rename.append(True)

    def sync(path):
        if after_rename:
            calls.append(Path(path))
        return original_sync(path)

    monkeypatch.setattr(migration.os, "rename", rename)
    monkeypatch.setattr(ledger, "sync_directory", sync)
    monkeypatch.setattr(installer, "_sync_directory", sync)
    migration.apply_result_limit(request, "a" * 64)
    assert calls[:2] == [root / ledger.REGISTRY, root]
    assert calls[-1] == root / ledger.REGISTRY


@pytest.fixture
def retained_v7_domain(domain, monkeypatch):
    root, value = setup_registered(domain, monkeypatch)
    upgrade(root)
    value["limits"]["result_reserved_bytes"] = ledger.MAX_POLICY_BYTES
    anchor = ledger.read(str(root / ledger.REGISTRY / "manifest.json"))
    anchor_sha = ledger.digest(ledger.canonical(anchor))
    pointer = "7" * 64
    ledger.write_new(str(root / "active-native-provider.json"),
                     dict(schema_version=1, manifest_sha256=pointer))
    history = root / "native-provider-history"
    history.mkdir(mode=0o700)
    ledger.write_new(
        str(history / (pointer + ".json")),
        dict(schema_version=1, manifest_sha256=pointer, identity_manifest_sha256=anchor_sha,
             operator_authority="SYNTHETIC FIXTURE ONLY"),
    )
    monkeypatch.setattr(migration, "profile", lambda _profile, _limit: str(root))
    monkeypatch.setattr(migration, "retained_v7_quiet", lambda _: None)
    monkeypatch.setattr(ledger, "free_bytes", lambda _: 64 * 1024**3)
    permit = binding(
        root, resource_domain_sha256=anchor["resource_domain_sha256"],
        max_attempts=56, max_reserved_bytes=56 * ledger.LEGACY_RESERVATION,
        reserve_bytes=ledger.LEGACY_RESERVATION,
    )
    last = dict(permit, reserve_bytes=8 * 1024**2)
    counter = ledger.read(str(root / ledger.LEDGER))
    for command in [permit] * 54 + [last, last]:
        previous = job(root)
        after = dict(
            counter,
            count=counter["count"] + 1,
            result_reserved_bytes=counter["result_reserved_bytes"] + command["reserve_bytes"],
        )
        intent = dict(schema_version=1, operation_id=previous, binding=command,
                      before=counter, after=after)
        old_receipt = ledger.receipt_for(intent)
        work = root / ledger.JOBS / previous / "work"
        ledger.write_new(str(root / ledger.REGISTRY / (previous + ".json")), intent)
        ledger.write_new(str(work / "reservation-intent.json"), intent)
        ledger.write_new(str(work / "reservation-receipt.json"), old_receipt)
        ledger.write_new(str(work / "attempt-reserved"), after)
        counter = after
    (root / ledger.LEDGER).write_bytes(ledger.canonical(counter))
    assert counter == ledger.RESULT_POLICY_V7_BASELINE
    return root, value, anchor, previous, last, old_receipt


def test_v7_populated_audit_publish_recovery_admission_and_replay(retained_v7_domain, monkeypatch):
    root, value, _, previous, permit, old_receipt = retained_v7_domain
    request = dict(
        plan=None, expected_plan_sha256=None, operator_authority="SYNTHETIC V7 TEST SCOPE",
    )
    successor = root / ledger.REGISTRY / ledger.RESULT_POLICY_V7_FILE
    new_permit = dict(permit, grant_sha256="5" * 64, max_attempts=2,
                      max_reserved_bytes=256 * 1024**2, reserve_bytes=128 * 1024**2)
    first = job(root)
    second = job(root)
    before = snapshot(root)
    with pytest.raises(ValueError, match="cumulative_capacity"):
        ledger.reserve(str(root), first, new_permit)
    proposal = migration.result_limit_v7_plan(value, "a" * 64)
    assert proposal["plan"]["snapshot"]["transaction_count"] == 56
    assert snapshot(root) == before
    request.update(plan=proposal["plan"], expected_plan_sha256=proposal["plan_sha256"])

    rename = migration.os.rename

    def interrupted_after_rename(source, target):
        rename(source, target)
        if Path(target) == successor:
            raise OSError("synthetic interruption after publishing v7")

    monkeypatch.setattr(migration.os, "rename", interrupted_after_rename)
    with pytest.raises(OSError, match="synthetic interruption"):
        migration.apply_result_limit_v7(request, "a" * 64)
    monkeypatch.setattr(migration.os, "rename", rename)
    result = migration.apply_result_limit_v7(request, "a" * 64)
    assert result["created"] is False
    assert result["result_ceiling_bytes"] == ledger.RESULT_POLICY_V7_BYTES
    assert result["reservation_cost"] == 0 and result["ledger_modified"] is False
    assert result["policy_receipt_sha256"] == ledger.digest(successor.read_bytes())
    assert migration.apply_result_limit_v7(request, "a" * 64) == result
    for path, raw in before.items():
        assert (root / path).read_bytes() == raw
    assert ledger.lookup(str(root), previous, permit) == old_receipt
    assert ledger.reserve(str(root), first, new_permit)["after"]["result_reserved_bytes"] > (
        ledger.MAX_POLICY_BYTES
    )
    receipt = ledger.reserve(str(root), second, new_permit)
    assert receipt["after"]["count"] == 140
    assert receipt["after"]["result_reserved_bytes"] == 17331912704
    after = snapshot(root)
    assert ledger.reserve(str(root), second, new_permit) == receipt
    assert ledger.lookup(str(root), previous, permit) == old_receipt
    with pytest.raises(ValueError, match="baseline_drift"):
        migration.apply_result_limit_v7(request, "a" * 64)
    other = job(root)
    with pytest.raises(ValueError, match="cumulative_capacity"):
        ledger.reserve(str(root), other, dict(new_permit, grant_sha256="6" * 64))
    assert snapshot(root) == after


def test_v7_rejects_scope_drift_and_broken_predecessor(retained_v7_domain):
    root, value, anchor, _, _, _ = retained_v7_domain
    proposal = migration.result_limit_v7_plan(value, "a" * 64)
    request = dict(plan=proposal["plan"], expected_plan_sha256=proposal["plan_sha256"],
                   operator_authority="SYNTHETIC V7 TEST SCOPE")
    prior = root / ledger.REGISTRY / ledger.RESULT_POLICY_FILE
    prior_record = ledger.read(str(prior))
    prior_record["operator_authority"] = "different valid predecessor content"
    prior.write_bytes(ledger.canonical(prior_record))
    before = snapshot(root)
    with pytest.raises(ValueError, match="snapshot_drift"):
        migration.apply_result_limit_v7(request, "a" * 64)
    assert snapshot(root) == before

    updated = migration.result_limit_v7_plan(value, "a" * 64)
    request.update(plan=updated["plan"], expected_plan_sha256=updated["plan_sha256"])
    assert migration.apply_result_limit_v7(request, "a" * 64)["created"]
    prior_record["operator_authority"] = "newer conflicting predecessor content"
    prior.write_bytes(ledger.canonical(prior_record))
    with pytest.raises(ValueError, match="retained_v7_binding"):
        ledger.effective_policy(str(root), anchor)


def test_v7_fixed_transport_binds_both_reports(retained_v7_domain, tmp_path, monkeypatch):
    root, value, _, _, _, _ = retained_v7_domain
    _, _, helper = domain_provisioning.contents()
    profile = tmp_path / "profile.json"
    profile.write_bytes(ledger.canonical(value))
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setattr(domain_provisioning.shutil, "which", lambda _: "ssh.exe")
    seen = []

    def transport(argv, payload, environment, **bounds):
        action = argv[-2]
        seen.append(action)
        assert argv[-1] == helper and "StrictHostKeyChecking=yes" in argv
        assert "plan-result-limit-v7" in argv[-4]
        assert bounds == {"timeout": 60, "limit": 262144}
        request = json.loads(payload)
        if action == "plan-result-limit-v7":
            result = migration.result_limit_v7_plan(request, helper)
        else:
            assert action == "apply-result-limit-v7"
            result = migration.apply_result_limit_v7(request, helper)
        return 0, ledger.canonical(result), b""

    before = snapshot(root)
    monkeypatch.setattr(domain_provisioning, "run_fixed", transport)
    environment, _ = load_environment(profile)
    for action in ("plan-result-limit-v7", "apply-result-limit-v7"):
        with pytest.raises(ValueError, match="fixed_domain_entry_not_bound"):
            domain_provisioning._transport(environment, b"", helper, action, tmp_path / "no-entry")
    assert not seen
    plan = domain_provisioning.prepare(profile, plan_path, helper, result_limit_v7=True)
    assert snapshot(root) == before
    result = domain_provisioning.apply_existing(
        profile, plan_path, receipt_path, plan["plan_sha256"], helper,
        "SYNTHETIC FIXTURE ONLY", result_limit_v7=True,
    )
    assert result["created"] is True and result["ledger_modified"] is False
    assert seen == ["plan-result-limit-v7", "apply-result-limit-v7"]
    for name, raw in before.items():
        assert (root / name).read_bytes() == raw

    def tampered_transport(*args, **kwargs):
        result = json.loads(receipt_path.read_bytes())
        result["policy_receipt_sha256"] = "0" * 64
        return 0, ledger.canonical(result), b""

    monkeypatch.setattr(domain_provisioning, "run_fixed", tampered_transport)
    with pytest.raises(ValueError, match="result_limit_apply_receipt_binding"):
        domain_provisioning.apply_existing(
            profile, plan_path, tmp_path / "bad-receipt.json", plan["plan_sha256"], helper,
            "SYNTHETIC FIXTURE ONLY", result_limit_v7=True,
        )
    assert not (tmp_path / "bad-receipt.json").exists()
