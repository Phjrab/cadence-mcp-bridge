"""Operator repair boundaries; no Cadence execution and no installation mutation."""

import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess

import pytest

from cadence_mcp_bridge import _installation_repair as repair
from cadence_mcp_bridge import bootstrap
from cadence_mcp_bridge.__main__ import main


def test_export_is_exclusive_and_never_contacts_vm(tmp_path, monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise AssertionError("export contacted a process")

    monkeypatch.setattr("subprocess.Popen", denied)
    output = tmp_path / "repair.py"
    assert main(["runner", "export-repair-helper", "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert result["remote_contact"] is False
    assert result["protected_permissions_changed"] is False
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        bootstrap.export_repair_helper(output)
    assert output.read_bytes() == before


@pytest.mark.parametrize("path", ["/", "relative", "/a/../b", "/a//b", "/a/./b"])
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValueError, match="path"):
        repair.valid_path(path)


def test_acl_retains_owner_rights_and_denies_named_writer_effectively():
    before = (
        "user::rwx\nuser:501:rwx\t#effective:rwx\ngroup::rwx\nmask::rwx\nother::rwx\n"
        "default:user::rwx\ndefault:user:501:rwx\ndefault:group::rwx\n"
        "default:mask::rwx\ndefault:other::rwx\n"
    )
    after = repair.restricted_acl(before)
    assert "user::rwx\n" in after
    assert "user:501:rwx\n" in after
    assert "mask::r-x\n" in after
    assert "default:user:501:r-x\n" in after
    assert "default:user::rwx\n" in after
    assert "#effective" not in after


def test_chmod_intermediate_keeps_defaults_and_named_entry():
    before = "user::rwx\nuser:501:rwx\ngroup::rwx\nmask::rwx\nother::rwx\n"
    before += "default:user::rwx\ndefault:group::rwx\ndefault:other::rwx\n"
    interim = repair.chmod_acl(before, 0o755)
    assert "group::rwx\n" in interim
    assert "mask::r-x\n" in interim
    assert "default:group::rwx\n" in interim
    assert repair.normalize_acl(interim) != repair.normalize_acl(repair.restricted_acl(before))


@pytest.mark.parametrize("case", ["hash", "authority", "content", "owner", "mode", "acl"])
def test_whole_plan_drift_denied_before_any_mutation(monkeypatch, case):
    row = {
        "path": "/operator/cadence/code", "dev": 1, "ino": 2, "uid": 500, "gid": 500,
        "kind": "file", "sha256": "a" * 64, "size": 3, "mtime": 1.0,
        "reason": "remove_shared_code_write_preserve_content_owner_rx", "mode": 0o777,
        "acl": "user::rwx\ngroup::rwx\nother::rwx\n", "after_mode": 0o755,
        "after_acl": "user::rwx\ngroup::r-x\nother::r-x\n",
    }
    old = {"scope": {}, "records": [row]}
    now = copy.deepcopy(old)
    request = {"plan": old, "expected_plan_sha256": repair.digest(old),
               "operator_authority": "fixture human authorization"}
    if case == "hash":
        request["expected_plan_sha256"] = "b" * 64
    elif case == "authority":
        request["operator_authority"] = ""
    elif case == "content":
        now["records"][0]["sha256"] = "c" * 64
    elif case == "owner":
        now["records"][0]["uid"] = 501
    elif case == "mode":
        now["records"][0]["mode"] = 0o777 ^ 0o100
    else:
        now["records"][0]["acl"] += "user:501:rwx\n"
    monkeypatch.setattr(repair, "plan", lambda _: {"plan": now})

    def denied(*args, **kwargs):
        raise AssertionError("invalid plan reached mutation")

    monkeypatch.setattr(repair, "open_fixed", denied)
    with pytest.raises(ValueError):
        repair._mutate_locked(request)


def test_directory_descriptor_never_walks_child_acl(monkeypatch):
    class Directory:
        st_mode = 0o40755

    monkeypatch.setattr(repair.os, "fstat", lambda _: Directory())
    assert repair.descriptor_path(7).endswith("/7/.")


@pytest.mark.skipif(os.name != "posix", reason="requires Linux descriptor/ACL operations")
@pytest.mark.parametrize("admin_identity", [False, True])
def test_real_acl_partial_recovery_repeat_and_rollback(tmp_path, monkeypatch, admin_identity):
    if shutil.which("getfacl") is None or shutil.which("setfacl") is None:
        pytest.skip("ACL utilities absent")
    directory = tmp_path / "code-directory"
    directory.mkdir()
    code = directory / "code"
    code.write_bytes(b"synthetic immutable code")
    code.chmod(0o777)
    directory.chmod(0o777)
    lock = tmp_path / "resource.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    subprocess.run(["setfacl", "-m", "d:u::rwx,d:g::rwx,d:o::rwx,u:501:rwx",
                    str(directory)], check=True)
    result = repair.plan({
        "installation_roots": [str(tmp_path)],
        "paths": sorted([str(directory), str(code)]), "links": [],
        "profile_sha256": "a" * 64, "resource_lock": str(lock),
    })
    result["plan"].update(schema_version=2, recipe_id="standard-vm-trust-v1", profile={})
    result["plan_sha256"] = repair.digest(result["plan"])
    # Only the pure recipe discovery is synthetic; all inode/ACL/lock operations
    # below are real Linux operations on disposable fixtures.
    monkeypatch.setattr(repair, "inventory", lambda _: {"plan": result["plan"]})
    request = {"plan": result["plan"], "expected_plan_sha256": result["plan_sha256"],
               "operator_authority": "synthetic test only"}
    real_process = subprocess.Popen

    def fail_acl_once(argv, *args, **kwargs):
        if argv[0].endswith("setfacl"):
            raise OSError("synthetic interruption between chmod and ACL")
        return real_process(argv, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", fail_acl_once)
        with pytest.raises(OSError):
            repair.mutate(request)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    # Simulate the helper's administrator identity while OS actions remain
    # ordinary permissions on these disposable owned files.
    if admin_identity:
        monkeypatch.setattr(repair.os, "getuid", lambda: 0)
    repair.mutate(request)
    repair.mutate(request)
    assert stat.S_IMODE(code.stat().st_mode) == 0o755
    assert code.read_bytes() == b"synthetic immutable code"
    repair.mutate(request, rollback=True)
    for record in result["plan"]["records"]:
        actual = repair.snapshot(record["path"])
        assert actual["mode"] == record["mode"]
        assert repair.normalize_acl(actual["acl"]) == repair.normalize_acl(record["acl"])
    assert code.read_bytes() == b"synthetic immutable code"


@pytest.mark.skipif(os.name != "posix", reason="requires Linux inode/ACL operations")
def test_hardlinked_code_never_changes_alias(tmp_path):
    code = tmp_path / "code"
    code.write_bytes(b"synthetic")
    os.link(code, tmp_path / "unlisted-alias")
    before = code.stat().st_mode
    with pytest.raises(ValueError, match="hardlinked_code"):
        repair.plan({"installation_roots": [str(tmp_path)], "paths": [str(code)],
                     "links": [], "profile_sha256": "a" * 64,
                     "resource_lock": str(tmp_path / "lock")})
    assert code.stat().st_mode == before


@pytest.mark.parametrize("wrong_profile", [False, True])
def test_private_plan_binds_selected_operator_profile(tmp_path, monkeypatch, wrong_profile):
    from pathlib import Path

    from cadence_mcp_bridge import operator_transport
    from cadence_mcp_bridge.environments import load_environment

    profile = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
    _, raw = load_environment(profile)
    selected_hash = repair.digest(json.loads(raw))
    plan = {"scope": {"profile_sha256": "f" * 64 if wrong_profile else selected_hash},
            "records": []}
    result = {"plan": plan, "plan_sha256": repair.digest(plan),
              "readonly_compatibility_links": [],
              "dependency_scope": "wrappers_32bit_binaries_shared_library_trees",
              "native_runtime_attestation": "NOT_ATTESTED"}

    def fixed(argv, data, env, **bounds):
        assert "StrictHostKeyChecking=yes" in argv
        assert argv[-1] == "inventory"
        assert data == raw
        assert bounds == {"timeout": 60, "limit": 262144}
        return 0, json.dumps(result).encode(), b""

    monkeypatch.setattr(operator_transport, "run_fixed", fixed)
    monkeypatch.setattr(shutil, "which", lambda _: "ssh.exe")
    output = tmp_path / "plan.private.json"
    if wrong_profile:
        with pytest.raises(ValueError, match="repair_profile_binding"):
            bootstrap.prepare_repair(profile, output)
        assert not output.exists()
    else:
        report = bootstrap.prepare_repair(profile, output)
        assert report["protected_permissions_changed"] is False
        assert report["execution_authorized"] is False
        assert json.loads(output.read_bytes()) == result


def test_public_apply_rejects_arbitrary_paths_before_open(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("unscoped plan reached a filesystem operation")

    monkeypatch.setattr(repair, "open_fixed", denied)
    plan = {"schema_version": 1, "scope": {"paths": ["/etc/ssh/sshd_config"]}}
    with pytest.raises(ValueError, match="fixed_profile_recipe_required"):
        repair.mutate({"plan": plan, "expected_plan_sha256": repair.digest(plan),
                       "operator_authority": "a plan is not human authority"})


@pytest.mark.skipif(os.name != "posix", reason="requires Linux path/descriptor operations")
def test_reference_recipe_cannot_follow_code_link_into_pdk(tmp_path):
    import platform
    import pwd

    root = tmp_path / "cadence"
    ic, ms = root / "IC615", root / "MMSIM121"
    paths = [ic / "share/bin" / name for name in (
        "cdnWrapperWithOA2010", ".cdnWrapper_core", ".cdnWrapper_argv_parsing",
        ".cdnWrapper_dev", ".cdnWrapper_help", ".cdnWrapper_cwlg", ".cdsWrapperLib")]
    paths += [ic / "tools.lnx86" / name for name in (
        ".oawrap", ".cdnWrapper_pscompat", "dfII/bin/ocean", "dfII/bin/virtuoso",
        "dfII/bin/32bit/virtuoso", "bin/cds_plat", "bin/cds_plat.dat")]
    paths += [ic / "share/dfII/bin/.dfII_init", ms / "tools.lnx86/bin/spectre",
              ms / "tools.lnx86/spectre/bin/32bit/spectre",
              ms / "tools.lnx86/bin/.preHostEnvCheck"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic code, never executed")
    for path in [ic / "tools.lnx86/lib", ic / "oa_v22.41.029/lib", ms / "tools.lnx86/lib"]:
        path.mkdir(parents=True)
    (ic / "tools").symlink_to(ic / "tools.lnx86", target_is_directory=True)
    (ms / "tools").symlink_to(ms / "tools.lnx86", target_is_directory=True)
    (ic / "oa").symlink_to(ic / "oa_v22.41.029", target_is_directory=True)
    protected = root / "pdk/do-not-change"
    protected.parent.mkdir()
    protected.write_bytes(b"synthetic protected PDK")
    protected.chmod(0o666)
    (ic / "tools.lnx86/lib/plugin.so").symlink_to(protected)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = {
        "schema_version": 1,
        "host": {"hostname": platform.node(), "os": platform.system(),
                 "architecture": platform.machine(), "python_version": platform.python_version(),
                 "user": pwd.getpwuid(os.getuid()).pw_name},
        "tools": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for name, path in [("virtuoso", ic / "tools/dfII/bin/virtuoso"),
                                     ("ocean", ic / "tools/dfII/bin/ocean"),
                                     ("spectre", ms / "tools/bin/spectre")]},
        "paths": {"protected_roots": [str(root)], "workspace_root": str(workspace),
                  "managed_root": str(workspace / ".cadence_mcp")},
    }
    before = protected.stat().st_mode
    with pytest.raises(ValueError, match="dependency_code_role_escape"):
        repair.inventory(profile)
    assert protected.stat().st_mode == before
    assert protected.read_bytes() == b"synthetic protected PDK"


def test_fractional_mtime_inventory_uses_cross_python_stable_json(tmp_path, monkeypatch):
    path = tmp_path / "code"
    path.write_bytes(b"fictional installation contents")
    os.utime(path, (1234567890.1234567, 1234567890.1234567))
    monkeypatch.setattr(repair, "open_fixed", lambda p: os.open(p, os.O_RDONLY))
    monkeypatch.setattr(repair, "acl", lambda fd: "user::rw-\ngroup::r--\nother::r--\n")
    monkeypatch.setattr(os.path, "realpath", lambda p: p)
    record = repair.snapshot(str(path))
    assert isinstance(record["mtime"], str)
    assert record["mtime"] == format(path.stat().st_mtime, ".17g")
    # A Python2.6 JSON serializer can no longer truncate a numeric mtime.
    wire = repair.canonical(record)
    assert repair.digest(json.loads(wire)) == hashlib.sha256(wire).hexdigest()
    assert repair.metadata_equal("mtime", path.stat().st_mtime, record["mtime"])
    assert not repair.metadata_equal("mtime", path.stat().st_mtime + 0.01, record["mtime"])
    assert repair.metadata_equal("mtime", None, None)


@pytest.mark.parametrize(
    "ic,ms,expected",
    [
        ("/opt/cadence/IC6", "/opt/cadence/IC6x", "/opt/cadence"),
        ("/opt/cadence/IC6x", "/opt/cadence/IC6", "/opt/cadence"),
        ("/home/user/cadence/IC615", "/home/user/cadence/MMSIM121", "/home/user/cadence"),
        ("/opt/ic/install", "/opt/ms/install", "/opt"),
    ],
)
def test_vendor_root_prefix_does_not_drop_spectre_targets(ic, ms, expected):
    base = repair.common_installation_root(ic, ms)
    assert base == expected
    assert repair.inside(ic, base) and repair.inside(ms, base)
