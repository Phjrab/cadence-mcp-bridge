"""Genuine zero-history policies on disposable files; no real VM budgets."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from cadence_mcp_bridge import _fresh_domain as setup
from cadence_mcp_bridge import _shared_reservations as accounting


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    guest_home = tmp_path / "home"
    guest_home.mkdir(mode=0o700)
    workspace = guest_home / "workspace"
    workspace.mkdir(mode=0o700)
    value = json.loads(
        (
            Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
        ).read_bytes()
    )
    value["limits"]["spectre_attempts"] = 3
    value["limits"]["result_reserved_bytes"] = 1024 * 1024
    root = workspace / ".cadence_mcp"
    index = guest_home / ".cadence_mcp-domain"
    monkeypatch.setattr(setup, "home", lambda: str(guest_home))
    monkeypatch.setattr(setup, "profile", lambda profile: (str(root), str(index)))
    return root, index, value


def request(fresh):
    _, _, value = fresh
    planned = setup.plan_fresh(value, "a" * 64)
    return {
        "plan": planned["plan"],
        "expected_plan_sha256": planned["plan_sha256"],
        "operator_authority": "SYNTHETIC ONLY, not real operator consent",
    }


def files(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def reserve(root, identity, amount=65536):
    anchor = accounting.read(str(root / accounting.REGISTRY / "manifest.json"))
    binding = {
        "root_sha256": anchor["root_sha256"],
        "resource_domain_sha256": anchor["resource_domain_sha256"],
        "ledger_ref": accounting.LEDGER,
        "identity_manifest_sha256": accounting.digest(accounting.canonical(anchor)),
        "grant_sha256": "b" * 64,
        "runner_sha256": "c" * 64,
        "plan_sha256": "d" * 64,
        "execution_input_sha256": "e" * 64,
        "expires_at": 4000000000,
        "max_attempts": 10,
        "max_reserved_bytes": 1024 * 1024,
        "reserve_bytes": amount,
        "disk_floor_bytes": 0,
    }
    work = root / accounting.JOBS / identity / "work"
    work.mkdir(parents=True, mode=0o700)
    work.parent.chmod(0o700)
    return binding, accounting.reserve(str(root), identity, binding)


def test_fresh_zero_policy_two_batches_and_replay_never_reset(fresh):
    root, index, _ = fresh
    req = request(fresh)
    assert not root.exists() and not index.exists()
    assert setup.apply_fresh(req, "a" * 64)["ledger_initialized"] is True
    assert accounting.read(str(root / accounting.LEDGER))["count"] == 0
    for _ in range(2):
        identity = str(uuid4())
        binding, receipt = reserve(root, identity)
        before = files(root)
        assert accounting.reserve(str(root), identity, binding) == receipt
        assert accounting.lookup(str(root), identity, binding) == receipt
        assert files(root) == before
    consumed = files(root)
    assert setup.apply_fresh(req, "a" * 64)["ledger_initialized"] is False
    assert files(root) == consumed
    counter = accounting.read(str(root / accounting.LEDGER))
    assert counter["count"] == 2 and counter["result_reserved_bytes"] == 131072
    assert counter["campaign_id"] != "AUTO-PHASE-01"


def test_fresh_policy_exhaustion_is_not_grant_capacity(fresh):
    root, _, _ = fresh
    setup.apply_fresh(request(fresh), "a" * 64)
    for _ in range(3):
        reserve(root, str(uuid4()))
    before = accounting.read(str(root / accounting.LEDGER))
    with pytest.raises(ValueError, match="cumulative_capacity"):
        reserve(root, str(uuid4()))
    assert accounting.read(str(root / accounting.LEDGER)) == before


def test_existing_legacy_history_rejects_even_different_new_root(fresh):
    root, index, value = fresh
    legacy = index.parent / "old-workspace" / ".cadence_mcp" / "sim-mcp-v2-jobs"
    legacy.mkdir(parents=True)
    (legacy / "counter.json").write_bytes(b"retained historical evidence")
    with pytest.raises(ValueError, match="existing_history"):
        setup.plan_fresh(value, "a" * 64)
    assert not root.exists() and not index.exists()


def test_stale_plan_when_history_appears_never_creates_counter(fresh):
    root, index, _ = fresh
    req = request(fresh)
    legacy = index.parent / "old-workspace" / ".cadence_mcp" / "sim-mcp-v2-jobs"
    legacy.mkdir(parents=True)
    (legacy / "counter.json").write_bytes(b"retained history")
    with pytest.raises(ValueError, match="existing_history"):
        setup.apply_fresh(req, "a" * 64)
    assert not root.exists() and not (index / "manifest.json").exists()
    assert (legacy / "counter.json").read_bytes() == b"retained history"


def test_partial_initialization_recovers_without_replacing_existing_bytes(fresh, monkeypatch):
    root, index, _ = fresh
    req = request(fresh)
    original = accounting.write_new

    def failure(path, value):
        if path.endswith("reservation-identity/manifest.json"):
            raise OSError("synthetic power interruption")
        return original(path, value)

    monkeypatch.setattr(accounting, "write_new", failure)
    with pytest.raises(OSError):
        setup.apply_fresh(req, "a" * 64)
    before = files(root)
    monkeypatch.setattr(accounting, "write_new", original)
    assert setup.apply_fresh(req, "a" * 64)["ledger_initialized"]
    assert all(files(root)[key] == data for key, data in before.items())
    assert (index / "complete.json").exists()


def test_same_home_index_denies_second_workspace_or_policy(fresh, monkeypatch):
    root, index, value = fresh
    req = request(fresh)
    setup.apply_fresh(req, "a" * 64)
    before = files(root)
    different = index.parent / "different-workspace" / ".cadence_mcp"
    different.parent.mkdir()
    monkeypatch.setattr(setup, "profile", lambda profile: (str(different), str(index)))
    with pytest.raises(ValueError, match="already_registered"):
        setup.plan_fresh(value, "a" * 64)
    with pytest.raises(ValueError, match="anchor_binding"):
        setup.apply_fresh(req, "a" * 64)
    assert not different.exists() and files(root) == before


@pytest.mark.parametrize("field", ["hash", "policy", "authority", "campaign"])
def test_forged_initialization_binding_has_no_counter(fresh, field):
    root, index, _ = fresh
    req = request(fresh)
    if field == "hash":
        req["expected_plan_sha256"] = "b" * 64
    elif field == "authority":
        req["operator_authority"] = ""
    elif field == "policy":
        req["plan"]["anchor"]["policy"]["attempt_ceiling"] = 500
    else:
        req["plan"]["anchor"]["policy"]["campaign_id"] = "AUTO-PHASE-01"
    if field in ("policy", "campaign"):
        req["expected_plan_sha256"] = setup.digest(setup.canonical(req["plan"]))
    with pytest.raises(ValueError):
        setup.apply_fresh(req, "a" * 64)
    assert not root.exists() and not index.exists()


def test_missing_home_index_cannot_reset_existing_root(fresh):
    root, index, _ = fresh
    req = request(fresh)
    setup.apply_fresh(req, "a" * 64)
    # A deliberately removed fixture index simulates incomplete operator history,
    # not a supported reset/delete operation.
    for p in index.iterdir():
        p.unlink()
    index.rmdir()
    before = files(root)
    with pytest.raises(ValueError, match="never_reinitialize"):
        setup.apply_fresh(req, "a" * 64)
    assert files(root) == before


def test_existing_registration_preserves_consumption_and_denies_fresh_replacement(fresh):
    root, index, value = fresh
    value["limits"]["spectre_attempts"] = 500
    value["limits"]["result_reserved_bytes"] = 10737418240
    root.mkdir(mode=0o700)
    for name in ("sim-mcp-v2-jobs", accounting.JOBS, accounting.REGISTRY):
        (root / name).mkdir(mode=0o700)
    (root / "run.lock").write_bytes(b"")
    (root / "run.lock").chmod(0o600)
    anchor = setup.make_anchor(value, str(root), str(uuid4()))
    anchor["schema_version"] = 1
    del anchor["policy"]
    anchor["baseline"] = {
        "campaign_id": "AUTO-PHASE-01",
        "count": 82,
        "result_reserved_bytes": 9798942720,
    }
    accounting.write_new(str(root / accounting.REGISTRY / "manifest.json"), anchor)
    accounting.write_new(str(root / accounting.LEDGER), anchor["baseline"])
    prior = files(root)
    plan = {
        "schema_version": 1,
        "profile": value,
        "helper_manifest_sha256": "a" * 64,
        "identity_manifest_sha256": setup.digest(setup.canonical(anchor)),
    }
    req = {
        "plan": plan,
        "expected_plan_sha256": setup.digest(setup.canonical(plan)),
        "operator_authority": "synthetic existing VM fixture",
    }
    receipt = setup.register_existing(req, "a" * 64)
    assert receipt["ledger_modified"] is False and receipt["ledger_initialized"] is False
    after = files(index)
    assert setup.register_existing(req, "a" * 64) == receipt
    assert files(index) == after and files(root) == prior
    with pytest.raises(ValueError, match="already_registered"):
        setup.plan_fresh(value, "a" * 64)


def test_package_setup_staging_is_fixed_and_rejects_stale_bytes_before_ssh(
    fresh, tmp_path, monkeypatch
):
    from cadence_mcp_bridge import domain_provisioning

    calls = []
    monkeypatch.setattr(domain_provisioning.shutil, "which", lambda name: "ssh.exe")
    example = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
    _, _, expected = domain_provisioning.contents(True)

    def fixed(argv, payload, environment, **limits):
        calls.append(argv)
        assert argv[-1] == expected and "StrictHostKeyChecking=yes" in argv
        assert "sudo" not in argv
        supplied = json.loads(payload)
        assert len(payload) < 262144
        assert set(supplied["files"]) == {
            "setup.py",
            "migration.py",
            "reservations.py",
            "installer.py",
            "probe.py",
            "manifest.json",
        }
        assert limits == {"timeout": 60, "limit": 262144}
        return (
            0,
            json.dumps(
                {
                    "status": "STANDARD_VM_SETUP_HELPER_STAGED",
                    "manifest_sha256": expected,
                    "changed_files": 6,
                    "execution_authorized": False,
                }
            ).encode(),
            b"",
        )

    monkeypatch.setattr(domain_provisioning, "run_fixed", fixed)
    with pytest.raises(ValueError, match="helper_package_binding"):
        domain_provisioning.stage_setup(example, "b" * 64)
    assert calls == []
    assert domain_provisioning.stage_setup(example, expected)["changed_files"] == 6


def test_replaced_or_orphan_home_index_never_reinitializes(fresh):
    root, index, _ = fresh
    req = request(fresh)
    setup.apply_fresh(req, "a" * 64)
    before = files(root)
    index_record = accounting.read(str(index / "manifest.json"))
    index_record["root"] = "/unrelated"
    (index / "manifest.json").write_bytes(accounting.canonical(index_record))
    with pytest.raises(ValueError, match="existing_domain_conflict"):
        setup.apply_fresh(req, "a" * 64)
    assert files(root) == before


@pytest.mark.parametrize("changed", ["reservations.py", "installer.py", "probe.py", "migration.py"])
def test_setup_retained_helpers_ignore_replaced_paths_and_poisoned_cache(
    tmp_path, monkeypatch, changed,
):
    import sys
    import types

    from cadence_mcp_bridge import domain_provisioning

    output = tmp_path / "helper"
    domain_provisioning.export(output, True)
    values = {name: (output / name).read_bytes() for name in setup.MEMBERS}
    marker = tmp_path / "unreviewed-setup-code"
    replacement = ("from pathlib import Path\nPath(" + repr(str(marker)) +
                   ").write_text('executed')\n").encode()
    (output / changed).write_bytes(replacement)
    for name in ("reservations", "installer", "probe", "migration"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType("untrusted_cached_" + name))
    monkeypatch.setattr(setup, "__package__", "")
    monkeypatch.setattr(setup, "_VALIDATED_HELPERS", None, raising=False)
    setup.load_validated_helpers(values, str(output))
    retained_accounting, retained_installer, retained_probe, retained_migration = setup.helpers()
    assert retained_installer.canonical({"checked": True}) == b'{"checked":true}'
    retained_accounting.counter_shape({
        "campaign_id": "AUTO-PHASE-01", "count": 82, "result_reserved_bytes": 9798942720,
    })
    example = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
    retained_probe.validate_profile(json.loads(example.read_bytes()))
    assert retained_migration.helpers() == setup.helpers()[:3]
    assert not marker.exists() and (output / changed).read_bytes() == replacement
    assert all(module is not sys.modules[module.__name__] for module in setup.helpers())


@pytest.mark.parametrize("name", ["platform", "types", "subprocess"])
def test_setup_retained_transitive_imports_ignore_bundle_and_cwd_aliases(
    tmp_path, monkeypatch, name,
):
    import sys

    from cadence_mcp_bridge import domain_provisioning

    output = tmp_path / "helper"
    domain_provisioning.export(output, True)
    values = {member: (output / member).read_bytes() for member in setup.MEMBERS}
    marker = tmp_path / "unreviewed-setup-dependency"
    (output / (name + ".py")).write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) +
        ").write_text('executed')\nraise RuntimeError('must-not-import')\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(output)
    monkeypatch.setattr(sys, "path", [str(output), "", ".", *sys.path])
    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(setup, "__package__", "")
    monkeypatch.setattr(setup, "_VALIDATED_HELPERS", None, raising=False)
    setup.load_validated_helpers(values, str(output))
    assert len(setup.helpers()) == 4
    assert setup.helpers()[3].helpers() == setup.helpers()[:3]
    assert not marker.exists()
    assert all(Path(entry or ".").resolve() != output for entry in sys.path)


@pytest.mark.parametrize("name", ["json", "hashlib", "stat", "os", "uuid"])
def test_direct_setup_startup_ignores_unlisted_stdlib_shadow(tmp_path, name):
    import subprocess
    import sys

    from cadence_mcp_bridge import domain_provisioning

    output = tmp_path / "helper"
    domain_provisioning.export(output, True)
    marker = tmp_path / "unreviewed-setup-startup"
    (output / (name + ".py")).write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) +
        ").write_text('executed')\nraise RuntimeError('must-not-import')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", str(output / "setup.py"), "plan-fresh", "a" * 64],
        cwd=output, input=b"{}", capture_output=True, timeout=15, check=False,
    )
    assert result.returncode == 1
    assert result.stderr.splitlines() == [b"STANDARD_VM_DOMAIN_SETUP_REJECTED"]
    assert not marker.exists()


def test_standalone_setup_requires_complete_asset_validation(monkeypatch):
    monkeypatch.setattr(setup, "__package__", "")
    monkeypatch.setattr(setup, "_VALIDATED_HELPERS", None, raising=False)
    with pytest.raises(ValueError, match="setup_helpers_not_validated"):
        setup.helpers()


def test_failed_setup_revalidation_clears_prior_authenticated_helpers(monkeypatch):
    monkeypatch.setattr(setup, "__package__", "")
    monkeypatch.setattr(setup, "_VALIDATED_HELPERS", (object(), object(), object(), object()),
                        raising=False)
    with pytest.raises(ValueError, match="migration_asset_location"):
        setup.validate_assets("short")
    with pytest.raises(ValueError, match="setup_helpers_not_validated"):
        setup.helpers()



def test_memory_loaded_setup_preserves_legitimate_first_import_path(tmp_path, monkeypatch):
    import sys
    import sysconfig
    import types

    from cadence_mcp_bridge import domain_provisioning

    output = tmp_path / "helper"
    domain_provisioning.export(output, True)
    stdlib = sysconfig.get_path("stdlib")
    monkeypatch.setattr(sys, "path", [stdlib, *sys.path])
    loaded = types.ModuleType("fixed_setup")
    loaded.__file__ = str(output / "setup.py")
    loaded.__package__ = ""
    exec(compile((output / "setup.py").read_bytes(), loaded.__file__, "exec"), loaded.__dict__)
    assert sys.path[0] == stdlib
