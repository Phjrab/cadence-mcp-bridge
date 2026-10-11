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
        assert argv[-8:-4] == ["-E", "-s", "-B", "-c"]
        assert argv[-3].endswith("/" + helper)
        assert "migration_entry_source_binding" in argv[-4]
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


def test_unmarked_retained_job_is_sealed_as_legacy_and_cannot_be_reserved(domain):
    root, _, _, _ = domain
    identity = str(uuid4())
    work = root / accounting.JOBS / identity / "work"
    work.mkdir(mode=0o700, parents=True)
    work.parent.chmod(0o700)
    req = request(domain)
    receipt = migration.apply(req, "a" * 64)
    assert identity in req["plan"]["anchor"]["legacy_operation_ids"]
    binding = {
        "root_sha256": req["plan"]["anchor"]["root_sha256"],
        "resource_domain_sha256": req["plan"]["anchor"]["resource_domain_sha256"],
        "ledger_ref": accounting.LEDGER,
        "identity_manifest_sha256": receipt["identity_manifest_sha256"],
        "grant_sha256": "b" * 64,
        "runner_sha256": "c" * 64,
        "plan_sha256": "d" * 64,
        "execution_input_sha256": "e" * 64,
        "expires_at": 4000000000,
        "max_attempts": 2,
        "max_reserved_bytes": 33554432,
        "reserve_bytes": 16777216,
        "disk_floor_bytes": 0,
    }
    before = snapshot(root)
    with pytest.raises(ValueError, match="identity_class_conflict"):
        accounting.reserve(str(root), identity, binding)
    assert snapshot(root) == before


def test_append_only_classification_correction_preserves_old_anchor_and_counter(domain):
    root, value, _, _ = domain
    # Exact historical bug state, no generic reservation or execution.
    current = migration.snapshot(str(root))
    old = migration.anchor_for(value, str(root), current)
    old["legacy_operation_ids"] = []
    (root / accounting.REGISTRY).mkdir(mode=0o700)
    accounting.write_new(str(root / accounting.REGISTRY / "manifest.json"), old)
    before = snapshot(root)
    planned = migration.plan(value, "a" * 64, True)
    req = {
        "plan": planned["plan"],
        "expected_plan_sha256": planned["plan_sha256"],
        "operator_authority": "synthetic correction only",
    }
    corrected = migration.apply(req, "a" * 64)
    assert corrected["anchor_created"]
    after = snapshot(root)
    assert all(after[k] == data for k, data in before.items())
    assert not migration.apply(req, "a" * 64)["anchor_created"]
    binding = {
        "root_sha256": old["root_sha256"],
        "resource_domain_sha256": old["resource_domain_sha256"],
        "ledger_ref": accounting.LEDGER,
        "identity_manifest_sha256": corrected["identity_manifest_sha256"],
    }
    actual = accounting.identity_manifest(str(root), binding)
    assert actual["legacy_operation_ids"] == [domain[2]]
    assert (
        accounting.audit(
            str(root), current["baseline"], actual, binding["identity_manifest_sha256"]
        )
        == []
    )
    binding["identity_manifest_sha256"] = accounting.digest(accounting.canonical(old))
    with pytest.raises(ValueError, match="identity_manifest_binding"):
        accounting.identity_manifest(str(root), binding)


def test_large_retained_inventory_uses_protocol_limit_and_duplicate_rejection(
    domain, tmp_path, monkeypatch
):
    root, value, _, _ = domain
    # More retained marked slots exceed32KiB even with short Linux inode metadata.
    # This fixture advances only its disposable counter, never a VM ledger.
    extended = {
        "campaign_id": "AUTO-PHASE-01",
        "count": 88,
        "result_reserved_bytes": accounting.expected_bytes(88, []),
    }
    (root / accounting.LEDGER).write_bytes(accounting.canonical(extended))
    (root / accounting.JOBS / domain[2] / "work" / "attempt-reserved").write_bytes(
        accounting.canonical(extended)
    )
    for count in range(22, 88):
        work = root / accounting.JOBS / str(uuid4()) / "work"
        work.mkdir(mode=0o700, parents=True)
        work.parent.chmod(0o700)
        accounting.write_new(
            str(work / "attempt-reserved"),
            {
                "campaign_id": "AUTO-PHASE-01",
                "count": count,
                "result_reserved_bytes": accounting.expected_bytes(count, []),
            },
        )
    for _ in range(61):
        work = root / accounting.JOBS / str(uuid4()) / "work"
        work.mkdir(mode=0o700, parents=True)
        work.parent.chmod(0o700)
    _, _, helper = domain_provisioning.contents()
    planned = migration.plan(value, helper)
    raw = json.dumps(planned).encode()
    assert 32768 < len(raw) < 262144
    domain_provisioning._closed_document(raw)
    profile = tmp_path / "environment.json"
    profile.write_bytes(json.dumps(value).encode())
    monkeypatch.setattr(domain_provisioning.shutil, "which", lambda name: "ssh.exe")
    monkeypatch.setattr(domain_provisioning, "run_fixed", lambda *args, **kwargs: (0, raw, b""))
    assert (
        domain_provisioning.prepare(profile, tmp_path / "large-plan.json", helper)["plan_sha256"]
        == planned["plan_sha256"]
    )
    migration.apply(
        {
            "plan": planned["plan"],
            "expected_plan_sha256": planned["plan_sha256"],
            "operator_authority": "synthetic inventory",
        },
        helper,
    )
    assert (root / accounting.REGISTRY / "manifest.json").stat().st_size < accounting.LIMIT
    for invalid in (b'{"x":1,"x":2}', b'{"x":NaN}', b" " * 262145):
        with pytest.raises(ValueError):
            domain_provisioning._closed_document(invalid)


@pytest.mark.parametrize("count,allowed", [(129, True), (160, True), (240, False)])
def test_retained_job_classification_obeys_serialized_anchor_capacity(domain, count, allowed):
    root, _, original_id, _ = domain
    identities = [original_id]
    for _ in range(count - 1):
        identity = str(uuid4())
        (root / accounting.JOBS / identity / "work").mkdir(mode=0o700, parents=True)
        (root / accounting.JOBS / identity).chmod(0o700)
        identities.append(identity)
    before = snapshot(root)
    if not allowed:
        with pytest.raises(ValueError, match="migration_anchor_size_limit"):
            request(domain)
        assert snapshot(root) == before
        assert not (root / accounting.REGISTRY).exists()
        return
    req = request(domain)
    assert req["plan"]["anchor"]["legacy_operation_ids"] == sorted(identities)
    receipt = migration.apply(req, "a" * 64)
    binding = dict(
        root_sha256=req["plan"]["anchor"]["root_sha256"],
        resource_domain_sha256=req["plan"]["anchor"]["resource_domain_sha256"],
        ledger_ref=accounting.LEDGER,
        identity_manifest_sha256=receipt["identity_manifest_sha256"],
    )
    assert accounting.identity_manifest(str(root), binding)["legacy_operation_ids"] == sorted(
        identities
    )
    assert (root / accounting.REGISTRY / "manifest.json").stat().st_size <= accounting.LIMIT
    for name, data in before.items():
        assert (root / name).read_bytes() == data
    assert migration.apply(req, "a" * 64)["anchor_created"] is False


@pytest.mark.parametrize("changed", ["reservations.py", "installer.py", "probe.py"])
def test_validated_helper_bytes_survive_path_replacement_and_cached_module_poisoning(
    tmp_path, monkeypatch, changed,
):
    import sys
    import types

    output = tmp_path / "helper"
    domain_provisioning.export(output)
    values = {name: (output / name).read_bytes() for name in migration.MEMBERS}
    marker = tmp_path / "unreviewed-code-executed"
    replacement = ("from pathlib import Path\nPath(" + repr(str(marker)) +
                   ").write_text('executed')\n").encode()
    # Exact manifest-checked retained values preceded a same-UID path replacement.
    (output / changed).write_bytes(replacement)
    for name in ("reservations", "installer", "probe"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType("untrusted_cached_" + name))
    monkeypatch.setattr(migration, "__package__", "")
    monkeypatch.setattr(migration, "_VALIDATED_HELPERS", None)
    migration.load_validated_helpers(values, str(output))
    retained_accounting, retained_installer, retained_probe = migration.helpers()
    assert retained_installer.canonical({"checked": True}) == b'{"checked":true}'
    retained_accounting.counter_shape({
        "campaign_id": "AUTO-PHASE-01", "count": 82, "result_reserved_bytes": 9798942720,
    })
    retained_probe.validate_profile(json.loads(EXAMPLE.read_bytes()))
    assert not marker.exists()
    assert (output / changed).read_bytes() == replacement
    assert all(module is not sys.modules[module.__name__] for module in migration.helpers())


def test_standalone_helpers_require_complete_asset_validation(monkeypatch):
    monkeypatch.setattr(migration, "__package__", "")
    monkeypatch.setattr(migration, "_VALIDATED_HELPERS", None)
    with pytest.raises(ValueError, match="migration_helpers_not_validated"):
        migration.helpers()



def test_failed_asset_revalidation_clears_previous_helper_state(monkeypatch):
    monkeypatch.setattr(migration, "__package__", "")
    monkeypatch.setattr(migration, "_VALIDATED_HELPERS", (object(), object(), object()))
    with pytest.raises(ValueError, match="migration_asset_location"):
        migration.validate_assets("short")
    with pytest.raises(ValueError, match="migration_helpers_not_validated"):
        migration.helpers()


@pytest.mark.parametrize("name", ["platform", "types", "subprocess"])
def test_validated_helper_transitive_import_cannot_use_new_bundle_module(
    tmp_path, monkeypatch, name,
):
    import sys

    output = tmp_path / "helper"
    domain_provisioning.export(output)
    values = {member: (output / member).read_bytes() for member in migration.MEMBERS}
    marker = tmp_path / "unreviewed-transitive-import"
    (output / (name + ".py")).write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) +
        ").write_text('executed')\nraise RuntimeError('must-not-import')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(output)
    monkeypatch.setattr(sys, "path", [str(output), "", ".", *sys.path])
    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(migration, "__package__", "")
    monkeypatch.setattr(migration, "_VALIDATED_HELPERS", None)
    migration.load_validated_helpers(values, str(output))
    assert len(migration.helpers()) == 3
    assert not marker.exists()
    assert all(Path(entry or ".").resolve() != output for entry in sys.path)


@pytest.mark.parametrize("name", ["json", "hashlib", "stat", "os"])
def test_standalone_migration_startup_cannot_import_unlisted_bundle_stdlib_shadow(
    tmp_path, name,
):
    import subprocess
    import sys

    output = tmp_path / "helper"
    domain_provisioning.export(output)
    marker = tmp_path / "unreviewed-startup-import"
    (output / (name + ".py")).write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) +
        ").write_text('executed')\nraise RuntimeError('must-not-import')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", str(output / "migration.py"),
         "inventory-existing", "a" * 64],
        cwd=output, input=b"{}", capture_output=True, timeout=15, check=False,
    )
    assert result.returncode == 1
    assert result.stderr.replace(b"\r\n", b"\n") == b"OPERATOR_DOMAIN_MIGRATION_REJECTED\n"
    assert not marker.exists()



def test_memory_loaded_migration_preserves_stdlib_first_entry_and_filters_bundle_aliases(
    tmp_path, monkeypatch,
):
    import sys
    import types

    output = tmp_path / "helper"
    domain_provisioning.export(output)
    stdlib = str(Path(os.__file__).resolve().parent)
    monkeypatch.chdir(output)
    monkeypatch.setattr(sys, "path", [stdlib, str(output), "", ".", *sys.path])
    module = types.ModuleType("migration")
    module.__file__ = str(output / "migration.py")
    module.__package__ = ""
    exec(compile((output / "migration.py").read_bytes(), module.__file__, "exec"), module.__dict__)
    assert sys.path[0] == stdlib
    assert all(Path(entry or ".").resolve() != output for entry in sys.path)
    assert module._VALIDATED_HELPERS is None


@pytest.mark.parametrize("missing", ["environment", "user-site"])
def test_direct_migration_requires_isolated_python_before_untrusted_imports(tmp_path, missing):
    import subprocess
    import sys

    output = tmp_path / "helper"
    domain_provisioning.export(output)
    search = tmp_path / "untrusted-search"
    search.mkdir()
    marker = tmp_path / "unreviewed-hook-executed"
    shadow = ("from pathlib import Path\nPath(" + repr(str(marker)) +
              ").write_text('executed')\nraise RuntimeError('unreviewed-hook')\n")
    (search / "hashlib.py").write_text(shadow, encoding="utf-8")
    environment = dict(os.environ, PYTHONPATH=str(search), PYTHONUSERBASE=str(search))
    flags = ["-s", "-B"] if missing == "environment" else ["-E", "-B"]
    result = subprocess.run(
        [sys.executable, *flags, str(output / "migration.py"),
         "inventory-existing", "a" * 64],
        cwd=output, input=b"{}", capture_output=True, timeout=15, check=False,
        env=environment,
    )
    assert result.returncode == 1
    assert result.stdout == b""
    assert result.stderr.replace(b"\r\n", b"\n") == (
        b"OPERATOR_DOMAIN_MIGRATION_ISOLATED_PYTHON_REQUIRED\n"
    )
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix", reason="actual POSIX fixed shell startup")
def test_fixed_launcher_blocks_real_versioned_user_site_startup(tmp_path):
    import shlex
    import subprocess
    import sys

    output = tmp_path / "helper"
    domain_provisioning.export(output)
    home = tmp_path / "isolated-home"
    home.mkdir()
    environment = dict(os.environ, HOME=str(home), APPDATA=str(home), USERPROFILE=str(home))
    interpreter = sys._base_executable
    probe = subprocess.run(
        [interpreter, "-E", "-s", "-B", "-c",
         "import site; print(site.getusersitepackages())"],
        env=environment, capture_output=True, check=True,
    )
    user_site = Path(probe.stdout.decode().strip())
    assert user_site.is_relative_to(home)
    user_site.mkdir(parents=True)
    user_marker, pth_marker = home / "usercustomize-executed", home / "pth-executed"
    (user_site / "usercustomize.py").write_text(
        "open(" + repr(str(user_marker)) + ", 'w').write('executed')\n", encoding="utf-8",
    )
    (user_site / "unreviewed.pth").write_text(
        "import builtins; builtins.open(" + repr(str(pth_marker)) +
        ", 'w').write('executed')\n", encoding="utf-8",
    )
    # Positive control proves these real versioned site hooks run before a
    # script-level guard when -s is absent; this is disposable fixture evidence.
    control = subprocess.run(
        [interpreter, "-E", "-B", "-c", "pass"], env=environment,
        capture_output=True, check=True,
    )
    assert not control.stdout and user_marker.exists() and pth_marker.exists()
    user_marker.rename(home / "retained-unsafe-usercustomize-control")
    pth_marker.rename(home / "retained-unsafe-pth-control")
    launcher = output / "domain-operator.sh"
    source = launcher.read_text()
    assert source.count("/usr/bin/python") == 1
    # Hosted fixture binds the fixed interpreter to the tested CPython; the
    # distributed standard-VM launcher retains literal /usr/bin/python.
    launcher.write_text(source.replace("/usr/bin/python", shlex.quote(interpreter)))
    result = subprocess.run(
        ["/bin/sh", str(launcher), "inventory-existing", "a" * 64],
        env=environment, cwd=output, input=b"{}", capture_output=True, check=False,
    )
    assert result.returncode == 1 and not result.stdout
    assert result.stderr == b"OPERATOR_DOMAIN_MIGRATION_REJECTED\n"
    assert not user_marker.exists() and not pth_marker.exists()


def test_fixed_launcher_is_manifest_bound_and_closed():
    assets, raw, _ = domain_provisioning.contents()
    launcher = assets["domain-operator.sh"]
    assert b"exec /usr/bin/python -E -s -B -c " in launcher
    assert b"migration_entry_source_binding" in launcher
    assert b"__CADENCE_DOMAIN_ENTRY__" not in launcher
    assert json.loads(raw)["files"]["domain-operator.sh"] == {
        "sha256": hashlib.sha256(launcher).hexdigest(), "bytes": len(launcher),
    }


@pytest.mark.skipif(os.name != "posix", reason="actual retained migration entry files")
@pytest.mark.parametrize("replace_manifest", [False, True])
def test_fixed_migration_entry_rejects_replaced_source_before_code_runs(tmp_path, replace_manifest):
    from cadence_mcp_bridge import _domain_entry as entry

    output = tmp_path / "helper"
    result = domain_provisioning.export(output)
    marker = tmp_path / "unreviewed-migration-executed"
    changed = ("open(" + repr(str(marker)) + ", 'w').write('executed')\n").encode()
    (output / "migration.py").write_bytes(changed)
    if replace_manifest:
        manifest = json.loads((output / "manifest.json").read_bytes())
        manifest["files"]["migration.py"] = {"sha256": hashlib.sha256(changed).hexdigest(),
                                               "bytes": len(changed)}
        (output / "manifest.json").write_bytes(migration.canonical(manifest))
    with pytest.raises(ValueError, match="migration_entry_(manifest|source)_binding"):
        entry.run(str(output), "inventory-existing", result["manifest_sha256"])
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix", reason="actual executing migration byte binding")
def test_fixed_migration_entry_late_replacement_cannot_gain_new_manifest_identity(
    tmp_path, monkeypatch
):
    from cadence_mcp_bridge import _domain_entry as entry

    output = tmp_path / "helper"
    result = domain_provisioning.export(output)
    marker = tmp_path / "replacement-code-executed"
    original, replaced = entry.read, []

    def read(path):
        raw = original(path)
        if path.endswith("/migration.py"):
            changed = ("open(" + repr(str(marker)) + ", 'w').write('executed')\n").encode()
            (output / "migration.py").write_bytes(changed)
            manifest = json.loads((output / "manifest.json").read_bytes())
            manifest["files"]["migration.py"] = {"sha256": hashlib.sha256(changed).hexdigest(),
                                                   "bytes": len(changed)}
            (output / "manifest.json").write_bytes(migration.canonical(manifest))
            replaced.append(True)
        return raw

    monkeypatch.setattr(entry, "read", read)
    with pytest.raises(ValueError, match="migration_asset_binding"):
        entry.run(str(output), "inventory-existing", result["manifest_sha256"])
    assert replaced == [True] and not marker.exists()
