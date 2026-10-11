"""Operator repair boundaries; no Cadence execution and no installation mutation."""

import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys

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
def test_real_acl_partial_recovery_repeat_and_rollback(tmp_path, monkeypatch):
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
    # Resume with the same real identity: root cannot reuse a user receipt.
    repair.mutate(request)
    repair.mutate(request)
    assert stat.S_IMODE(code.stat().st_mode) == 0o755
    assert code.read_bytes() == b"synthetic immutable code"
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", fail_acl_once)
        with pytest.raises(OSError):
            repair.mutate(request, rollback=True)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o777
    assert "default:group::r-x" in repair.snapshot(str(directory))["acl"]
    repair.mutate(request, rollback=True)
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
@pytest.mark.parametrize("large_inventory", [False, True])
def test_private_plan_binds_selected_operator_profile(
    tmp_path, monkeypatch, wrong_profile, large_inventory
):
    from pathlib import Path

    from cadence_mcp_bridge import operator_transport
    from cadence_mcp_bridge.environments import load_environment

    profile = Path(__file__).resolve().parents[2] / "docs/examples/onboarding/environment.json"
    _, raw = load_environment(profile)
    selected_hash = repair.digest(json.loads(raw))
    plan = {"scope": {"profile_sha256": "f" * 64 if wrong_profile else selected_hash},
            "records": []}
    if large_inventory:
        plan["records"] = [{"acl": "user::rwx\n" * 256} for _ in range(128)]
    result = {"plan": plan, "plan_sha256": repair.digest(plan),
              "readonly_compatibility_links": [],
              "dependency_scope": "wrappers_32bit_binaries_shared_library_trees",
              "native_runtime_attestation": "NOT_ATTESTED"}

    response = json.dumps(result).encode()
    if large_inventory:
        assert 262144 < len(response) < repair.LIMIT
    response_file = tmp_path / "synthetic-inventory-response.json"
    response_file.write_bytes(response)
    request_file = tmp_path / "synthetic-inventory-request.json"
    request_file.write_bytes(raw)
    real_process = subprocess.Popen

    def synthetic_inventory(argv, *args, **kwargs):
        assert "StrictHostKeyChecking=yes" in argv
        assert argv[-1] == "inventory"
        # Substitute only the owned child executable. The actual transport's
        # request/timeout/output bound validation and pipe handling still run.
        return real_process(
            [sys.executable, "-c",
             "import pathlib,sys; "
             "assert sys.stdin.buffer.read()==pathlib.Path(sys.argv[2]).read_bytes(); "
             "sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())",
             str(response_file), str(request_file)], *args, **kwargs
        )

    monkeypatch.setattr(operator_transport.subprocess, "Popen", synthetic_inventory)
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


def test_rollback_chmod_intermediate_preserves_restricted_named_and_default_acl():
    before = "user::rwx\nuser:501:rwx\ngroup::rwx\nmask::rwx\nother::rwx\n"
    before += "default:user::rwx\ndefault:group::rwx\ndefault:other::rwx\n"
    after = repair.restricted_acl(before)
    interim = repair.chmod_acl(after, 0o777)
    assert "mask::rwx\n" in interim
    assert "other::rwx\n" in interim
    assert "default:group::r-x\n" in interim
    assert repair.normalize_acl(interim) != repair.normalize_acl(before)
    assert repair.normalize_acl(interim) != repair.normalize_acl(after)


@pytest.mark.skipif(os.name != "posix", reason="requires held Linux descriptor/ACL operations")
@pytest.mark.parametrize("drift", ["named-acl", "default-acl", "contents"])
def test_held_descriptor_rejects_drift_after_path_snapshot(tmp_path, monkeypatch, drift):
    if shutil.which("getfacl") is None or shutil.which("setfacl") is None:
        pytest.skip("ACL utilities absent")
    target = tmp_path / "code"
    if drift == "default-acl":
        target.mkdir()
    else:
        target.write_bytes(b"synthetic immutable code")
    target.chmod(0o777)
    prepared = repair.plan({
        "installation_roots": [str(tmp_path)], "paths": [str(target)], "links": [],
        "profile_sha256": "a" * 64, "resource_lock": str(tmp_path / "lock"),
    })
    real_open = repair.open_fixed
    opens = 0

    def race(path):
        nonlocal opens
        fd = real_open(path)
        opens += 1
        if opens == 3:
            if drift == "contents":
                target.write_bytes(b"x" * len(target.read_bytes()))
            else:
                entry = "d:u:501:r-x" if drift == "default-acl" else "u:501:r-x"
                subprocess.run(["setfacl", "-m", entry, str(target)], check=True)
        return fd

    def denied(*args):
        raise AssertionError("unreviewed descriptor drift reached chmod")

    monkeypatch.setattr(repair, "open_fixed", race)
    monkeypatch.setattr(repair.os, "fchmod", denied)
    with pytest.raises(ValueError, match="prechange_descriptor_drift"):
        repair._mutate_locked({"plan": prepared["plan"],
            "expected_plan_sha256": prepared["plan_sha256"],
            "operator_authority": "SYNTHETIC-ONLY"})
    assert stat.S_IMODE(target.stat().st_mode) == 0o777


@pytest.mark.skipif(os.name != "posix", reason="requires held Linux descriptor/ACL operations")
def test_descriptor_snapshot_rejects_content_change_during_acl_collection(tmp_path, monkeypatch):
    if shutil.which("getfacl") is None:
        pytest.skip("ACL utility absent")
    target = tmp_path / "code"
    target.write_bytes(b"synthetic immutable code")
    target.chmod(0o777)
    prepared = repair.plan({
        "installation_roots": [str(tmp_path)], "paths": [str(target)], "links": [],
        "profile_sha256": "a" * 64, "resource_lock": str(tmp_path / "lock"),
    })
    real_acl = repair.acl
    reads = 0

    def race(fd):
        nonlocal reads
        value = real_acl(fd)
        reads += 1
        if reads == 3:
            saved = target.stat()
            target.write_bytes(b"x" * len(target.read_bytes()))
            os.utime(target, ns=(saved.st_atime_ns, saved.st_mtime_ns))
        return value

    def denied(*args):
        raise AssertionError("intra-snapshot drift reached chmod")

    monkeypatch.setattr(repair, "acl", race)
    monkeypatch.setattr(repair.os, "fchmod", denied)
    with pytest.raises(ValueError, match="snapshot_race"):
        repair._mutate_locked({"plan": prepared["plan"],
            "expected_plan_sha256": prepared["plan_sha256"],
            "operator_authority": "SYNTHETIC-ONLY"})
    assert stat.S_IMODE(target.stat().st_mode) == 0o777


@pytest.mark.parametrize("count", [240, 257])
def test_valid_large_acl_plan_has_whole_protocol_bound(monkeypatch, count):
    acl = "user::rwx\n" + "".join(f"user:{10000000 + i}:rwx\n" for i in range(1810))
    acl += "group::rwx\nmask::rwx\nother::rwx\n"
    assert 32000 < len(acl.encode()) <= 32768

    def record(path):
        return {"path": path, "dev": 1, "ino": 2, "uid": 500, "gid": 500,
                "kind": "directory", "sha256": None, "size": None, "mtime": None,
                "mode": 0o777, "acl": acl}

    monkeypatch.setattr(repair, "snapshot", record)
    monkeypatch.setattr(repair.os.path, "realpath", lambda path: path)
    request = {"installation_roots": ["/synthetic/cadence"],
               "paths": [f"/synthetic/cadence/dir-{i:04d}" for i in range(count)],
               "links": [], "profile_sha256": "a" * 64,
               "resource_lock": "/synthetic/work/.cadence_mcp/run.lock"}
    if count == 257:
        with pytest.raises(ValueError, match="inventory_serialized_limit"):
            repair.plan(request)
    else:
        result = repair.plan(request)
        assert len(result["plan"]["records"]) == count
        assert 15_000_000 < len(repair.canonical(result)) + 1 <= repair.LIMIT
        maximum_request = {"plan": result["plan"],
                           "expected_plan_sha256": result["plan_sha256"],
                           "operator_authority": "💥" * 512}
        assert len(repair.canonical(maximum_request)) + 1 <= repair.LIMIT


def test_inventory_envelope_growth_rejects_even_when_records_fit():
    result = {"plan": {"records": [], "profile": {}}, "plan_sha256": "a" * 64,
              "readonly_compatibility_links": ["x" * repair.LIMIT]}
    with pytest.raises(ValueError, match="inventory_serialized_limit"):
        repair.bounded_inventory(result)


@pytest.mark.parametrize("rollback", [False, True])
def test_oversized_mutation_request_rejects_before_inventory_or_lock(monkeypatch, rollback):
    def denied(*args, **kwargs):
        raise AssertionError("oversized request touched installation or lock")

    monkeypatch.setattr(repair, "inventory", denied)
    monkeypatch.setattr(repair, "open_fixed", denied)
    request = {"plan": {"padding": "x" * repair.LIMIT},
               "expected_plan_sha256": "a" * 64, "operator_authority": "fixture"}
    with pytest.raises(ValueError, match="request_limit"):
        repair.mutate(request, rollback)


@pytest.mark.parametrize("unsafe", [None, "/srv/shared", "/home/student", "/"])
def test_unlisted_ancestors_checked_to_root_without_mutation(monkeypatch, unsafe):
    from types import SimpleNamespace

    paths = {}
    observed = []

    def open_directory(path, *args):
        descriptor = len(paths) + 100
        paths[descriptor] = path
        observed.append(path)
        return descriptor

    def info(descriptor):
        return SimpleNamespace(st_mode=0o40775 if paths[descriptor] == unsafe else 0o40755)

    def denied(*args, **kwargs):
        raise AssertionError("read-only ancestor check attempted mutation")

    monkeypatch.setattr(repair, "open_fixed", open_directory)
    monkeypatch.setattr(repair.os, "open", open_directory)
    monkeypatch.setattr(repair.os, "fstat", info)
    monkeypatch.setattr(repair.os, "close", lambda descriptor: None)
    monkeypatch.setattr(repair.os, "fchmod", denied, raising=False)
    monkeypatch.setattr(repair.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(repair.os, "O_NONBLOCK", 0, raising=False)
    monkeypatch.setattr(repair.os, "O_DIRECTORY", 0, raising=False)
    monkeypatch.setattr(repair.subprocess, "Popen", denied)
    roots = ["/srv/shared/cadence", "/home/student/workspace"]
    if unsafe is None:
        repair.verify_unlisted_ancestors(roots)
        assert set(observed) == {"/", "/srv", "/srv/shared", "/home", "/home/student"}
        assert not set(roots).intersection(observed)
    else:
        with pytest.raises(ValueError, match="unlisted_ancestor_trust"):
            repair.verify_unlisted_ancestors(roots)


@pytest.fixture
def actual_recipe_layout():
    if os.name != "posix":
        pytest.skip("requires actual Linux installation ancestry")
    import platform
    import pwd
    import tempfile
    from pathlib import Path

    if shutil.which("getfacl") is None:
        pytest.skip("ACL utilities absent")
    # Use a disposable owned home subtree: /tmp is itself writable and would
    # correctly block the fixed recipe before the controlled shared ancestor.
    with tempfile.TemporaryDirectory(prefix="cadence-mcp-ancestry-", dir=Path.home()) as owned:
        shared = Path(owned) / "shared"
        root, workspace = shared / "cadence", shared / "workspace"
        ic, ms = root / "IC615", root / "MMSIM121"
        code_paths = [ic / "share/bin" / name for name in (
            "cdnWrapperWithOA2010", ".cdnWrapper_core", ".cdnWrapper_argv_parsing",
            ".cdnWrapper_dev", ".cdnWrapper_help", ".cdnWrapper_cwlg", ".cdsWrapperLib")]
        code_paths += [ic / "tools.lnx86" / name for name in (
            ".oawrap", ".cdnWrapper_pscompat", "dfII/bin/ocean", "dfII/bin/virtuoso",
            "dfII/bin/32bit/virtuoso", "bin/cds_plat", "bin/cds_plat.dat")]
        code_paths += [ic / "share/dfII/bin/.dfII_init", ms / "tools.lnx86/bin/spectre",
                       ms / "tools.lnx86/spectre/bin/32bit/spectre",
                       ms / "tools.lnx86/bin/.preHostEnvCheck"]
        for path in code_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic code, never executed")
        for path in [ic / "tools.lnx86/lib", ic / "oa_v22.41.029/lib", ms / "tools.lnx86/lib"]:
            path.mkdir(parents=True)
        (ic / "tools").symlink_to(ic / "tools.lnx86", target_is_directory=True)
        (ms / "tools").symlink_to(ms / "tools.lnx86", target_is_directory=True)
        (ic / "oa").symlink_to(ic / "oa_v22.41.029", target_is_directory=True)
        workspace.mkdir()
        profile = {
            "schema_version": 1,
            "host": {"hostname": platform.node(), "os": platform.system(),
                     "architecture": platform.machine(),
                     "python_version": platform.python_version(),
                     "user": pwd.getpwuid(os.getuid()).pw_name},
            "tools": {name: {"path": str(path),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for name, path in [("virtuoso", ic / "tools/dfII/bin/virtuoso"),
                                         ("ocean", ic / "tools/dfII/bin/ocean"),
                                         ("spectre", ms / "tools/bin/spectre")]},
            "paths": {"protected_roots": [str(root)], "workspace_root": str(workspace),
                      "managed_root": str(workspace / ".cadence_mcp")},
        }
        managed = workspace / ".cadence_mcp"
        managed.mkdir(mode=0o700)
        (managed / "run.lock").write_bytes(b"owned synthetic reservation lock")
        (managed / "run.lock").chmod(0o600)
        yield shared, root, workspace, code_paths, profile


def test_actual_recipe_rejects_unlisted_writable_parent_and_preserves_it(actual_recipe_layout):
    shared, root, workspace, code_paths, profile = actual_recipe_layout
    shared.chmod(0o775)
    before = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    with pytest.raises(ValueError, match="unlisted_ancestor_trust"):
        repair.inventory(profile)
    assert stat.S_IMODE(shared.stat().st_mode) == 0o775
    assert before == {
        str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths
    }
    # Correct only this owned synthetic fixture; the recipe itself stays
    # read-only and never selects ancestors beyond its exact two roots.
    shared.chmod(0o755)
    result = repair.inventory(profile)
    assert str(shared) not in result["plan"]["scope"]["paths"]
    assert str(root) in result["plan"]["scope"]["paths"]
    assert str(workspace) in result["plan"]["scope"]["paths"]
    assert before == {
        str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths
    }


@pytest.mark.parametrize("race", ["recipe-to-lock", "held-target", "changed", "no-op"])
def test_actual_recipe_rejects_ancestor_drift_during_apply(actual_recipe_layout, monkeypatch, race):
    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o755 if race == "no-op" else 0o777)
    prepared = repair.inventory(profile)
    request = {"plan": prepared["plan"], "expected_plan_sha256": prepared["plan_sha256"],
               "operator_authority": "SYNTHETIC-ONLY"}
    before = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    events, validated, target_reads = [], False, 0
    real_inventory, real_snapshot = repair.inventory, repair.snapshot_descriptor

    def inventory(selected):
        result = real_inventory(selected)
        if race == "recipe-to-lock":
            shared.chmod(0o775)
        return result

    def snapshot(path, fd):
        nonlocal target_reads
        result = real_snapshot(path, fd)
        if validated and path == str(target):
            target_reads += 1
            if race == "held-target" and target_reads == 2:
                shared.chmod(0o775)
        return result

    def emit(value):
        nonlocal validated
        events.append(value)
        if value["event"] == "validated":
            validated = True
            if race == "no-op":
                shared.chmod(0o775)
        if value["event"] == "changed" and race == "changed":
            shared.chmod(0o775)

    monkeypatch.setattr(repair, "inventory", inventory)
    monkeypatch.setattr(repair, "snapshot_descriptor", snapshot)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="unlisted_ancestor_trust"):
        repair.mutate(request)
    assert stat.S_IMODE(shared.stat().st_mode) == 0o775
    assert all(event["event"] != "complete" for event in events)
    assert target.read_bytes() == before[str(target)][0]
    changed = [event for event in events if event["event"] == "changed"]
    assert len(changed) == (1 if race == "changed" else 0)
    if race == "changed":
        assert stat.S_IMODE(target.stat().st_mode) == 0o755
    else:
        assert before == {
            str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths
        }
    assert str(shared) not in prepared["plan"]["scope"]["paths"]


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("race", ["held-target", "changed", "no-op", "none"])
def test_apply_rechecks_omitted_ancestors_at_mutation_and_completion(monkeypatch, rollback, race):
    from types import SimpleNamespace

    row = {
        "path": "/operator/cadence/code", "dev": 1, "ino": 2, "uid": 500, "gid": 500,
        "kind": "file", "sha256": "a" * 64, "size": 3, "mtime": "1",
        "reason": "remove_shared_code_write_preserve_content_owner_rx", "mode": 0o777,
        "acl": "user::rwx\ngroup::rwx\nother::rwx\n", "after_mode": 0o755,
        "after_acl": "user::rwx\ngroup::r-x\nother::r-x\n",
    }
    roots = ["/operator/cadence", "/operator/work"]
    original = {"scope": {"installation_roots": roots}, "records": [row]}
    now = copy.deepcopy(row)
    if rollback != (race == "no-op"):
        now.update(mode=row["after_mode"], acl=row["after_acl"])
    unsafe, mutations, checks, events = False, [], [], []

    def emit(value):
        nonlocal unsafe
        events.append(value["event"])
        if (race == "changed" and value["event"] == "changed") or (
            race == "no-op" and value["event"] == "validated"
        ):
            unsafe = True

    def held(path, fd):
        nonlocal unsafe
        assert path == row["path"]
        if race == "held-target":
            unsafe = True
        return {key: value for key, value in now.items() if key not in (
            "reason", "after_mode", "after_acl"
        )}

    def ancestors(selected):
        assert selected == roots
        checks.append(selected)
        if unsafe:
            raise ValueError("unlisted_ancestor_trust")

    def chmod(fd, mode):
        mutations.append(mode)
        now.update(mode=mode, acl=row["acl"] if rollback else row["after_acl"])

    monkeypatch.setattr(repair, "plan", lambda scope: {"plan": {"records": [now]}})
    monkeypatch.setattr(repair, "snapshot", lambda path: copy.deepcopy(now))
    monkeypatch.setattr(repair, "snapshot_descriptor", held)
    monkeypatch.setattr(repair, "verify_unlisted_ancestors", ancestors)
    monkeypatch.setattr(repair, "open_fixed", lambda path: 100)
    monkeypatch.setattr(repair.os, "fstat", lambda fd: SimpleNamespace(
        st_dev=1, st_ino=2, st_mode=stat.S_IFREG | now["mode"], st_nlink=1
    ))
    monkeypatch.setattr(repair.os, "close", lambda fd: None)
    monkeypatch.setattr(repair.os, "fchmod", chmod, raising=False)
    monkeypatch.setattr(repair, "acl", lambda fd: now["acl"])
    monkeypatch.setattr(repair, "emit", emit)
    request = {"plan": original, "expected_plan_sha256": repair.digest(original),
               "operator_authority": "SYNTHETIC-ONLY"}
    if race == "none":
        repair._mutate_locked(request, rollback)
        assert events[-1] == "complete"
        assert len(checks) == 2
    else:
        with pytest.raises(ValueError, match="unlisted_ancestor_trust"):
            repair._mutate_locked(request, rollback)
        assert "complete" not in events
    assert len(mutations) == (1 if race in ("changed", "none") else 0)


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("drift", [None, "mode", "acl", "content", "owner", "count"])
def test_completion_requires_whole_exact_requested_target_state(monkeypatch, rollback, drift):
    old = {
        "path": "/operator/cadence/code", "dev": 1, "ino": 2, "uid": 500, "gid": 500,
        "kind": "file", "sha256": "a" * 64, "size": 3, "mtime": "1",
        "reason": "remove_shared_code_write_preserve_content_owner_rx", "mode": 0o777,
        "acl": "user::rwx\ngroup::rwx\nother::rwx\n", "after_mode": 0o755,
        "after_acl": "user::rwx\ngroup::r-x\nother::r-x\n",
    }
    original = {"scope": {"paths": [old["path"]]}, "records": [old]}
    now = copy.deepcopy(old)
    if not rollback:
        now.update(mode=old["after_mode"], acl=old["after_acl"])
    if drift == "mode":
        now["mode"] ^= 0o020
    elif drift == "acl":
        now["acl"] += "user:501:r-x\n"
    elif drift == "content":
        now["sha256"] = "b" * 64
    elif drift == "owner":
        now["uid"] += 1
    records = [] if drift == "count" else [now]
    calls = []

    def final_plan(scope):
        calls.append(scope)
        return {"plan": {"records": records}}

    monkeypatch.setattr(repair, "plan", final_plan)
    if drift is None:
        repair.verify_completed_targets(original, rollback)
    else:
        reason = "completion_metadata" if drift in ("mode", "acl") else (
            "completion_record_count" if drift == "count" else "completion_protected_drift"
        )
        with pytest.raises(ValueError, match=reason):
            repair.verify_completed_targets(original, rollback)
    assert calls == [original["scope"]]


@pytest.mark.parametrize("stage", ["no-op", "already-processed"])
@pytest.mark.parametrize("drift", ["mode", "acl", "contents", "link"])
def test_actual_completion_rechecks_skipped_and_processed_recipe(
    actual_recipe_layout, monkeypatch, stage, drift
):
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    if shutil.which("setfacl") is None:
        pytest.skip("ACL utilities absent")
    target = code_paths[0]
    target.chmod(0o777)
    prepared = repair.inventory(profile)
    request = {"plan": prepared["plan"], "expected_plan_sha256": prepared["plan_sha256"],
               "operator_authority": "SYNTHETIC-ONLY"}
    if stage == "no-op":
        repair.mutate(request)
    events = []
    before_content = target.read_bytes()

    def emit(value):
        events.append(value)
        if value["event"] != ("validated" if stage == "no-op" else "changed"):
            return
        if drift == "mode":
            target.chmod(0o775)
        elif drift == "acl":
            subprocess.run(["setfacl", "-m", "u:501:r--", str(target)], check=True)
        elif drift == "contents":
            target.write_bytes(b"x" * len(before_content))
        else:
            # Change only the text of an owned link; its resolved code is unchanged.
            link = Path(profile["tools"]["virtuoso"]["path"]).parents[2]
            link.unlink()
            link.symlink_to("tools.lnx86", target_is_directory=True)

    monkeypatch.setattr(repair, "emit", emit)
    reason = {"mode": "completion_metadata", "acl": "completion_metadata",
              "contents": "completion_protected_drift", "link": "link_drift"}[drift]
    with pytest.raises(ValueError, match=reason):
        repair.mutate(request)
    assert all(event["event"] != "complete" for event in events)
    assert len([event for event in events if event["event"] == "changed"]) == (
        1 if stage == "already-processed" else 0
    )
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    if drift != "contents":
        assert target.read_bytes() == before_content


def _receipt_request(prepared):
    return {"plan": prepared["plan"], "expected_plan_sha256": prepared["plan_sha256"],
            "operator_authority": "SYNTHETIC-ONLY"}


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("drift", ["mode", "acl", "hash", "extra-record"])
def test_absent_receipt_never_authenticates_fabricated_original(monkeypatch, rollback, drift):
    monkeypatch.setattr(repair.os, "getuid", lambda: 500, raising=False)
    now = {"path": "/owned/code", "mode": 0o755,
           "acl": "user::rwx\ngroup::r-x\nother::r-x\n", "sha256": "a" * 64,
           "after_mode": 0o755, "after_acl": "user::rwx\ngroup::r-x\nother::r-x\n"}
    original = {"scope": {}, "records": [copy.deepcopy(now)]}
    if drift == "mode":
        original["records"][0]["mode"] = 0o777
    elif drift == "acl":
        original["records"][0]["acl"] = "user::rwx\ngroup::rwx\nother::rwx\n"
    elif drift == "hash":
        original["records"][0]["sha256"] = "b" * 64
    else:
        original["records"].append(copy.deepcopy(now))
    monkeypatch.setattr(repair, "receipt_directory", lambda plan, create: None)
    monkeypatch.setattr(repair, "plan", lambda scope: {"plan": {"records": [now]}})

    def denied(*args):
        raise AssertionError("unobserved original reached receipt publication")

    monkeypatch.setattr(repair, "publish_receipt", denied)
    request = {"plan": original, "expected_plan_sha256": repair.digest(original)}
    with pytest.raises(
        ValueError, match="repair_applied_receipt_required|repair_initial_before_required"
    ):
        repair.authenticate_applied_plan(request, rollback)


@pytest.mark.parametrize("rollback", [False, True])
def test_exact_existing_receipt_does_not_republish_or_require_before(monkeypatch, rollback):
    monkeypatch.setattr(repair.os, "getuid", lambda: 500, raising=False)
    original = {"scope": {}, "records": []}
    opened = []
    monkeypatch.setattr(repair, "receipt_directory", lambda plan, create: 7)
    monkeypatch.setattr(repair, "read_receipt", lambda directory, name, data, plan: True)
    monkeypatch.setattr(repair.os, "close", opened.append)

    def denied(*args):
        raise AssertionError("existing receipt was rewritten")

    monkeypatch.setattr(repair, "publish_receipt", denied)
    monkeypatch.setattr(repair, "plan", denied)
    repair.authenticate_applied_plan({"plan": original}, rollback)
    assert opened == [7]


def _receipt_path(prepared):
    from pathlib import Path

    uid = os.getuid()
    managed = Path(prepared["plan"]["scope"]["resource_lock"]).parent
    directory = managed / f"trust-repair-v1-{'admin' if uid == 0 else 'user'}-{uid}"
    return directory / (prepared["plan_sha256"] + ".json")


@pytest.mark.parametrize("healthy", [False, True])
def test_actual_apply_receipt_is_durable_and_preserved_through_retry_rollback(
    actual_recipe_layout, monkeypatch, healthy
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o755 if healthy else 0o777)
    prepared = repair.inventory(profile)
    receipt = _receipt_path(prepared)
    assert not receipt.parent.exists()  # read-only inventory did not provision
    real_fchmod = os.fchmod
    observed = []

    def checked_chmod(fd, mode):
        assert receipt.exists()
        assert receipt.read_bytes() == repair.receipt_bytes(prepared["plan"])
        observed.append(mode)
        return real_fchmod(fd, mode)

    monkeypatch.setattr(repair.os, "fchmod", checked_chmod)
    request = _receipt_request(prepared)
    repair.mutate(request)
    info, before = receipt.stat(), receipt.read_bytes()
    assert stat.S_IMODE(info.st_mode) == 0o400
    assert stat.S_IMODE(receipt.parent.stat().st_mode) == 0o700
    assert info.st_uid == os.getuid() and info.st_nlink == 1
    repair.mutate(request)
    repair.mutate(request, rollback=True)
    repair.mutate(request, rollback=True)
    assert receipt.read_bytes() == before and receipt.stat().st_ino == info.st_ino
    assert stat.S_IMODE(paths[0].stat().st_mode) == (0o755 if healthy else 0o777)
    assert observed == ([] if healthy else [0o755, 0o777])


@pytest.mark.parametrize("action", ["apply", "rollback"])
def test_actual_unobserved_after_state_rejects_without_receipt(actual_recipe_layout, action):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    paths[0].chmod(0o755)  # external change: no actual prior helper apply
    with pytest.raises(
        ValueError, match="repair_initial_before_required|repair_applied_receipt_required"
    ):
        repair.mutate(_receipt_request(prepared), rollback=action == "rollback")
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert not _receipt_path(prepared).exists()


def test_actual_caller_changed_plan_and_digest_cannot_expand_permissions(actual_recipe_layout):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o755)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    forged = copy.deepcopy(prepared["plan"])
    row = next(row for row in forged["records"] if row["path"] == str(paths[0]))
    row.update(mode=0o777, acl="user::rwx\ngroup::rwx\nother::rwx\n")
    malicious = {"plan": forged, "expected_plan_sha256": repair.digest(forged),
                 "operator_authority": "self-computed digest is not provenance"}
    with pytest.raises(ValueError, match="repair_applied_receipt_required"):
        repair.mutate(malicious, rollback=True)
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert _receipt_path(prepared).read_bytes() == repair.receipt_bytes(prepared["plan"])


@pytest.mark.parametrize("tamper", ["contents", "mode", "symlink", "hardlink", "directory"])
def test_actual_untrusted_receipt_is_preserved_and_rejected(actual_recipe_layout, tamper):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    repair.mutate(_receipt_request(prepared))
    receipt = _receipt_path(prepared)
    if tamper == "contents":
        receipt.chmod(0o600)
        data = receipt.read_bytes().replace(
            b"observed-before-explicit-apply", b"fabricat-before-explicit-apply"
        )
        receipt.write_bytes(data)
        receipt.chmod(0o400)
    elif tamper == "mode":
        receipt.chmod(0o600)
    elif tamper == "symlink":
        old = receipt.with_name("preserved-original.json")
        receipt.rename(old)
        receipt.symlink_to(old)
    elif tamper == "hardlink":
        os.link(receipt, receipt.with_name("preserved-hardlink.json"))
    else:
        receipt.parent.chmod(0o750)
    before = paths[0].stat().st_mode
    with pytest.raises((ValueError, OSError)):
        repair.mutate(_receipt_request(prepared), rollback=True)
    assert paths[0].stat().st_mode == before and receipt.exists()


@pytest.mark.parametrize(
    "interruption", ["write", "file-fsync", "link", "unlink", "directory-fsync"]
)
def test_actual_receipt_publication_interruption_never_changes_target(
    actual_recipe_layout, monkeypatch, interruption
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    receipt = _receipt_path(prepared)
    original_write, original_fsync = os.write, os.fsync
    original_link, original_unlink = os.link, os.unlink
    interrupted = False

    def write(fd, data):
        nonlocal interrupted
        if interruption == "write" and not interrupted:
            interrupted = True
            original_write(fd, data[:8])
            raise OSError("synthetic interrupted write")
        return original_write(fd, data)

    def fsync(fd):
        nonlocal interrupted
        info = os.fstat(fd)
        should_fail = (interruption == "file-fsync" and stat.S_ISREG(info.st_mode)) or (
            interruption == "directory-fsync" and receipt.exists() and stat.S_ISDIR(info.st_mode)
        )
        if should_fail and not interrupted:
            interrupted = True
            raise OSError("synthetic interrupted fsync")
        return original_fsync(fd)

    def link(source, target):
        nonlocal interrupted
        if interruption == "link" and not interrupted:
            interrupted = True
            raise OSError("synthetic interrupted link")
        return original_link(source, target)

    def unlink(path):
        nonlocal interrupted
        if interruption == "unlink" and not interrupted:
            interrupted = True
            raise OSError("synthetic interrupted unlink")
        return original_unlink(path)

    with monkeypatch.context() as patch:
        patch.setattr(repair.os, "write", write)
        patch.setattr(repair.os, "fsync", fsync)
        patch.setattr(repair.os, "link", link)
        patch.setattr(repair.os, "unlink", unlink)
        with pytest.raises(OSError):
            repair.mutate(_receipt_request(prepared))
    assert interrupted and stat.S_IMODE(paths[0].stat().st_mode) == 0o777
    evidence = list(receipt.parent.iterdir())
    assert evidence  # candidates/final are never erased after a failure
    preserved = {p.name: p.read_bytes() for p in evidence}
    if interruption == "unlink":
        with pytest.raises(ValueError, match="repair_receipt_trust"):
            repair.mutate(_receipt_request(prepared))
        assert stat.S_IMODE(paths[0].stat().st_mode) == 0o777
    else:
        repair.mutate(_receipt_request(prepared))
        assert stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    for name, data in preserved.items():
        assert (receipt.parent / name).read_bytes() == data


def test_actual_root_namespace_rejects_user_owned_receipt(actual_recipe_layout, monkeypatch):
    _, _, _, paths, profile = actual_recipe_layout
    if os.getuid() == 0:
        pytest.skip("ordinary host identity required for a forged administrator receipt")
    prepared = repair.inventory(profile)
    repair.mutate(_receipt_request(prepared))
    receipt = _receipt_path(prepared)
    forged_directory = receipt.parent.with_name("trust-repair-v1-admin-0")
    forged_directory.mkdir(mode=0o700)
    forged = forged_directory / receipt.name
    forged.write_bytes(receipt.read_bytes())
    forged.chmod(0o400)
    monkeypatch.setattr(repair.os, "getuid", lambda: 0)
    monkeypatch.setattr(repair.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="repair_receipt_directory"):
        repair.authenticate_applied_plan(_receipt_request(prepared), rollback=True)
    assert forged.exists() and stat.S_IMODE(paths[0].stat().st_mode) == 0o644


@pytest.mark.parametrize("stage", ["validated", "changed"])
def test_actual_detached_receipt_directory_prevents_completion(
    actual_recipe_layout, monkeypatch, stage
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    receipt = _receipt_path(prepared)
    detached = receipt.parent.with_name("preserved-detached-receipt-directory")
    events = []

    def emit(event):
        events.append(event)
        if event["event"] == stage:
            receipt.parent.rename(detached)

    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="repair_applied_receipt_required"):
        repair.mutate(_receipt_request(prepared))
    assert (detached / receipt.name).read_bytes() == repair.receipt_bytes(prepared["plan"])
    assert not any(event["event"] == "complete" for event in events)
    assert stat.S_IMODE(paths[0].stat().st_mode) == (0o777 if stage == "validated" else 0o755)


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("race", ["read", "file-fsync", "directory-fsync"])
def test_actual_receipt_namespace_rechecked_after_read_and_durability(
    actual_recipe_layout, monkeypatch, rollback, race
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    receipt = _receipt_path(prepared)
    inode, directory_inode = receipt.stat().st_ino, receipt.parent.stat().st_ino
    preserved = receipt.read_bytes()
    detached = receipt.parent.with_name("preserved-during-receipt-read")
    real_read, real_fsync, real_receipt = os.read, os.fsync, repair.read_receipt
    calls, active, renamed = 0, False, False
    events = []

    def read_receipt(*args):
        nonlocal calls, active
        calls += 1
        # Initial admission authenticates the linked receipt. Detach it during
        # the final completion check or the immediate pre-rollback chmod check.
        active = calls == 2
        return real_receipt(*args)

    def detach(fd, directory=False):
        nonlocal renamed
        expected = directory_inode if directory else inode
        if active and not renamed and os.fstat(fd).st_ino == expected:
            receipt.parent.rename(detached)
            renamed = True

    def read(fd, limit):
        if race == "read":
            detach(fd)
        return real_read(fd, limit)

    def fsync(fd):
        if race == "file-fsync":
            detach(fd)
        elif race == "directory-fsync":
            detach(fd, directory=True)
        return real_fsync(fd)

    monkeypatch.setattr(repair, "read_receipt", read_receipt)
    monkeypatch.setattr(repair.os, "read", read)
    monkeypatch.setattr(repair.os, "fsync", fsync)
    monkeypatch.setattr(repair, "emit", events.append)
    with pytest.raises(ValueError, match="repair_receipt_namespace"):
        repair.mutate(request, rollback)
    assert renamed and stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert (detached / receipt.name).read_bytes() == preserved
    assert not any(event["event"] in ("changed", "complete") for event in events)
