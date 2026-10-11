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
    result["plan"].update(schema_version=2, recipe_id="standard-vm-trust-v1", profile={},
                          readonly_compatibility_links=[])
    result["plan_sha256"] = repair.digest(result["plan"])
    # Only the pure recipe discovery is synthetic; all inode/ACL/lock operations
    # below are real Linux operations on disposable fixtures.
    def fixed_inventory(_):
        fresh = repair.plan(result["plan"]["scope"])
        fresh["plan"].update(schema_version=2, recipe_id="standard-vm-trust-v1", profile={},
                              readonly_compatibility_links=[])
        fresh["plan_sha256"] = repair.digest(fresh["plan"])
        return fresh

    monkeypatch.setattr(repair, "inventory", fixed_inventory)
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
    request_file.write_bytes(Path(repair.__file__).read_bytes() + raw)
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
    # The new receipt chain guard catches the recipe-to-lock race before target
    # validation; later races still reach the exact prechange/completion guard.
    reason = ("repair_receipt_ancestor_trust" if race == "recipe-to-lock"
              else "unlisted_ancestor_trust")
    with pytest.raises(ValueError, match=reason):
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
@pytest.mark.parametrize(
    "race", ["read", "file-fsync", "directory-fsync", "final-hash", "final-file-check"]
)
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
    real_hash, real_lstat = repair.file_hash, os.lstat
    calls, active, renamed, hashed = 0, False, False, False
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

    def file_hash(fd):
        nonlocal hashed
        selected = active and os.fstat(fd).st_ino == inode
        if selected and race == "final-hash":
            detach(fd)
        result = real_hash(fd)
        if selected:
            hashed = True
        return result

    def lstat(path):
        nonlocal renamed
        if (active and hashed and not renamed and race == "final-file-check" and
                str(path).startswith("/proc/self/fd/") and
                str(path).endswith("/" + receipt.name)):
            receipt.parent.rename(detached)
            renamed = True
        return real_lstat(path)

    monkeypatch.setattr(repair, "read_receipt", read_receipt)
    monkeypatch.setattr(repair.os, "read", read)
    monkeypatch.setattr(repair.os, "fsync", fsync)
    monkeypatch.setattr(repair, "file_hash", file_hash)
    monkeypatch.setattr(repair.os, "lstat", lstat)
    monkeypatch.setattr(repair, "emit", events.append)
    with pytest.raises(ValueError, match="repair_receipt_namespace"):
        repair.mutate(request, rollback)
    assert renamed and stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert (detached / receipt.name).read_bytes() == preserved
    assert not any(event["event"] in ("changed", "complete") for event in events)


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("syscall", ["file-fsync", "directory-fsync"])
@pytest.mark.parametrize("drift", ["rename", "unlink", "replace", "contents"])
def test_actual_receipt_file_rechecked_after_durability(
    actual_recipe_layout, monkeypatch, rollback, syscall, drift
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    receipt = _receipt_path(prepared)
    original = receipt.read_bytes()
    inode, directory_inode = receipt.stat().st_ino, receipt.parent.stat().st_ino
    original_fsync, original_receipt = os.fsync, repair.read_receipt
    calls, active, changed = 0, False, False
    events = []
    evidence = receipt.with_name("preserved-prior-receipt.json")

    def read_receipt(*args):
        nonlocal calls, active
        calls += 1
        active = calls == 2
        return original_receipt(*args)

    def fsync(fd):
        nonlocal changed
        expected = inode if syscall == "file-fsync" else directory_inode
        if active and not changed and os.fstat(fd).st_ino == expected:
            changed = True
            if drift == "contents":
                before = receipt.stat()
                receipt.chmod(0o600)
                receipt.write_bytes(original.replace(b"observed-before", b"fabricat-before"))
                receipt.chmod(0o400)
                os.utime(receipt, ns=(before.st_atime_ns, before.st_mtime_ns))
            elif drift == "unlink":
                # Retain fixture evidence separately before simulating external
                # unlink; the production helper never deletes failed receipts.
                evidence.write_bytes(original)
                receipt.unlink()
            else:
                receipt.rename(evidence)
                if drift == "replace":
                    receipt.write_bytes(original)
                    receipt.chmod(0o400)
        return original_fsync(fd)

    monkeypatch.setattr(repair, "read_receipt", read_receipt)
    monkeypatch.setattr(repair.os, "fsync", fsync)
    monkeypatch.setattr(repair, "emit", events.append)
    with pytest.raises(
        ValueError, match="repair_receipt_race|repair_receipt_binding|repair_receipt_directory_race"
    ):
        repair.mutate(request, rollback)
    assert changed and stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert not any(event["event"] in ("changed", "complete") for event in events)
    if drift != "contents":
        assert evidence.read_bytes() == original


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("syscall", ["file-fsync", "directory-fsync"])
@pytest.mark.parametrize("ancestor", ["unlisted-middle", "selected-workspace"])
def test_actual_receipt_named_parent_chain_rechecked_after_durability(
    actual_recipe_layout, monkeypatch, rollback, syscall, ancestor
):
    shared, _, workspace, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    receipt = _receipt_path(prepared)
    file_inode, directory_inode = receipt.stat().st_ino, receipt.parent.stat().st_ino
    real_fsync, real_receipt = os.fsync, repair.read_receipt
    calls, active, changed = 0, False, False
    events = []

    def read_receipt(*args):
        nonlocal calls, active
        calls += 1
        active = calls == 2
        return real_receipt(*args)

    def fsync(fd):
        nonlocal changed
        inode = file_inode if syscall == "file-fsync" else directory_inode
        if active and not changed and os.fstat(fd).st_ino == inode:
            changed = True
            (shared if ancestor == "unlisted-middle" else workspace).chmod(0o775)
        return real_fsync(fd)

    monkeypatch.setattr(repair, "read_receipt", read_receipt)
    monkeypatch.setattr(repair.os, "fsync", fsync)
    monkeypatch.setattr(repair, "emit", events.append)
    with pytest.raises(
        ValueError, match="repair_receipt_ancestor_trust|repair_receipt_ancestor_drift"
    ):
        repair.mutate(request, rollback)
    assert changed and stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert receipt.read_bytes() == repair.receipt_bytes(prepared["plan"])
    assert not any(event["event"] in ("changed", "complete") for event in events)


def test_actual_receipt_allows_only_exact_planned_workspace_before_state(actual_recipe_layout):
    _, _, workspace, paths, profile = actual_recipe_layout
    workspace.chmod(0o777)
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o755
    repair.mutate(request, rollback=True)
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o777
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o777
    assert _receipt_path(prepared).read_bytes() == repair.receipt_bytes(prepared["plan"])


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("syscall", ["file-fsync", "directory-fsync"])
def test_actual_receipt_directory_metadata_rechecked_after_durability(
    actual_recipe_layout, monkeypatch, rollback, syscall
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    receipt = _receipt_path(prepared)
    file_inode, directory_inode = receipt.stat().st_ino, receipt.parent.stat().st_ino
    real_fsync, real_receipt = os.fsync, repair.read_receipt
    calls, active, changed = 0, False, False
    events = []

    def read_receipt(*args):
        nonlocal calls, active
        calls += 1
        active = calls == 2
        return real_receipt(*args)

    def fsync(fd):
        nonlocal changed
        inode = file_inode if syscall == "file-fsync" else directory_inode
        if active and not changed and os.fstat(fd).st_ino == inode:
            changed = True
            (receipt.parent / "preserved-external-entry").write_bytes(b"external synthetic drift")
        return real_fsync(fd)

    monkeypatch.setattr(repair, "read_receipt", read_receipt)
    monkeypatch.setattr(repair.os, "fsync", fsync)
    monkeypatch.setattr(repair, "emit", events.append)
    with pytest.raises(ValueError, match="repair_receipt_directory_race"):
        repair.mutate(request, rollback)
    assert changed and stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert (receipt.parent / "preserved-external-entry").exists()
    assert not any(event["event"] in ("changed", "complete") for event in events)


@pytest.mark.parametrize("rollback", [False, True])
def test_actual_detached_managed_parent_rejected_after_named_entry_read(
    actual_recipe_layout, monkeypatch, rollback
):
    _, _, _, paths, profile = actual_recipe_layout
    paths[0].chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    repair.mutate(request)
    receipt = _receipt_path(prepared)
    managed = receipt.parent.parent
    detached = managed.with_name("preserved-detached-managed-root")
    real_lstat, real_receipt = os.lstat, repair.read_receipt
    calls, active, changed = 0, False, False
    events = []

    def read_receipt(*args):
        nonlocal calls, active
        calls += 1
        active = calls == 2
        return real_receipt(*args)

    def lstat(path, *args, **kwargs):
        nonlocal changed
        result = real_lstat(path, *args, **kwargs)
        if active and not changed and str(path).endswith("/" + receipt.parent.name):
            changed = True
            managed.rename(detached)
        return result

    monkeypatch.setattr(repair, "read_receipt", read_receipt)
    monkeypatch.setattr(repair.os, "lstat", lstat)
    monkeypatch.setattr(repair, "emit", events.append)
    with pytest.raises((ValueError, OSError)):
        repair.mutate(request, rollback)
    assert changed and stat.S_IMODE(paths[0].stat().st_mode) == 0o755
    assert (detached / receipt.parent.name / receipt.name).exists()
    assert not any(event["event"] in ("changed", "complete") for event in events)


@pytest.mark.parametrize(
    "drift", [None, "held-mode", "held-link", "named-inode", "named-parent", "final-entry"]
)
def test_resource_lock_binds_held_inode_parent_and_final_fixed_entry(monkeypatch, drift):
    from types import SimpleNamespace

    lock = "/operator/work/.cadence_mcp/run.lock"
    row = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600, st_uid=500,
               st_gid=500, st_nlink=1, st_size=0, st_mtime=1, st_ctime=1)
    parent_row = dict(row, st_ino=3, st_mode=stat.S_IFDIR | 0o700, st_nlink=2)
    expected, parent_expected = SimpleNamespace(**row), SimpleNamespace(**parent_row)
    observed = {10: dict(row), 11: dict(parent_row), 20: dict(row), 21: dict(parent_row)}
    if drift == "held-mode":
        observed[10]["st_mode"] |= 0o020
    elif drift == "held-link":
        observed[10]["st_nlink"] = 2
    elif drift == "named-inode":
        observed[20]["st_ino"] = 9
    elif drift == "named-parent":
        observed[21]["st_ino"] = 9
    entries = {lock: dict(observed[20]), os.path.dirname(lock): dict(observed[21])}
    if drift == "final-entry":
        entries[lock]["st_ino"] = 9
    closed = []
    monkeypatch.setattr(repair.os, "fstat", lambda fd: SimpleNamespace(**observed[fd]))
    monkeypatch.setattr(repair, "open_fixed", lambda path: 20 if path == lock else 21)
    monkeypatch.setattr(repair.os, "lstat", lambda path: SimpleNamespace(**entries[path]))
    monkeypatch.setattr(repair.os.path, "realpath", lambda path: path)
    monkeypatch.setattr(repair.os, "close", closed.append)
    if drift is None:
        repair.verify_resource_lock(lock, 10, 11, expected, parent_expected)
    else:
        reason = "resource_lock_drift" if drift.startswith("held-") else "resource_lock_binding"
        with pytest.raises(ValueError, match=reason):
            repair.verify_resource_lock(lock, 10, 11, expected, parent_expected)
    assert closed == ([] if drift and drift.startswith("held-") else [20, 21])


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize(
    "race", ["before-snapshot", "after-snapshot", "after-receipt", "last-snapshot"]
)
def test_actual_recipe_rejects_hardlink_before_target_mutation(
    actual_recipe_layout, monkeypatch, rollback, race
):
    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target, alias = code_paths[0], shared / "outside-reviewed-alias"
    target.chmod(0o777)
    prepared = repair.inventory(profile)
    request = {"plan": prepared["plan"], "expected_plan_sha256": prepared["plan_sha256"],
               "operator_authority": "SYNTHETIC-ONLY"}
    if rollback:
        repair.mutate(request)
    before = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    events, validated, reads, linked = [], False, 0, False
    real_snapshot, real_receipt = repair.snapshot_descriptor, repair.verify_applied_receipt

    def add_link():
        nonlocal linked
        if not linked:
            os.link(target, alias)
            linked = True

    def snapshot(path, fd):
        nonlocal reads
        selected = validated and path == str(target)
        if selected:
            reads += 1
        if selected and reads == 2 and race == "before-snapshot":
            add_link()
        result = real_snapshot(path, fd)
        if selected and ((reads == 2 and race == "after-snapshot") or
                         (reads == 3 and race == "last-snapshot")):
            add_link()
        return result

    def receipt(selected):
        real_receipt(selected)
        if validated and race == "after-receipt":
            add_link()

    def emit(value):
        nonlocal validated
        events.append(value)
        if value["event"] == "validated":
            validated = True

    monkeypatch.setattr(repair, "snapshot_descriptor", snapshot)
    monkeypatch.setattr(repair, "verify_applied_receipt", receipt)
    monkeypatch.setattr(repair, "emit", emit)
    reason = "prechange_hardlink" if race == "last-snapshot" else "hardlinked_code"
    with pytest.raises(ValueError, match=reason):
        repair.mutate(request, rollback)
    assert linked and target.stat().st_nlink == 2
    assert before == {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    assert (alias.read_bytes(), alias.stat().st_mode) == before[str(target)]
    assert not any(event["event"] in ("changed", "complete") for event in events)


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize(
    "race", ["open", "flock", "receipt", "held-target", "last-target", "no-op", "changed"]
)
def test_actual_recipe_rejects_detached_resource_lock(
    actual_recipe_layout, monkeypatch, rollback, race
):
    import fcntl
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o777)
    prepared = repair.inventory(profile)
    request = {"plan": prepared["plan"], "expected_plan_sha256": prepared["plan_sha256"],
               "operator_authority": "SYNTHETIC-ONLY"}
    if rollback or race == "no-op":
        repair.mutate(request)
    if rollback and race == "no-op":
        repair.mutate(request, True)
    before = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    lock = Path(prepared["plan"]["scope"]["resource_lock"])
    detached = lock.with_name("preserved-detached-run.lock")
    original_lock = lock.read_bytes()
    events, validated, reads, replaced, second_fd = [], False, 0, False, None
    real_open, real_flock = repair.open_fixed, fcntl.flock
    real_receipt, real_snapshot = repair.authenticate_applied_plan, repair.snapshot_descriptor

    def replace():
        nonlocal replaced, second_fd
        if replaced:
            return
        lock.rename(detached)
        lock.write_bytes(original_lock)
        lock.chmod(0o600)
        # Demonstrate a second real flock can acquire this replacement inode.
        second_fd = os.open(lock, os.O_RDONLY)
        real_flock(second_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        replaced = True

    def open_fixed(path):
        fd = real_open(path)
        if path == str(lock) and race == "open":
            replace()
        return fd

    def flock(fd, operation):
        real_flock(fd, operation)
        if race == "flock":
            replace()

    def receipt(selected, selected_rollback):
        real_receipt(selected, selected_rollback)
        if race == "receipt":
            replace()

    def snapshot(path, fd):
        nonlocal reads
        result = real_snapshot(path, fd)
        if validated and path == str(target):
            reads += 1
            if ((race == "held-target" and reads == 2) or
                    (race == "last-target" and reads == 3)):
                replace()
        return result

    def emit(value):
        nonlocal validated
        events.append(value)
        if value["event"] == "validated":
            validated = True
            if race == "no-op":
                replace()
        if value["event"] == "changed" and race == "changed":
            replace()

    monkeypatch.setattr(repair, "open_fixed", open_fixed)
    monkeypatch.setattr(fcntl, "flock", flock)
    monkeypatch.setattr(repair, "authenticate_applied_plan", receipt)
    monkeypatch.setattr(repair, "snapshot_descriptor", snapshot)
    monkeypatch.setattr(repair, "emit", emit)
    try:
        with pytest.raises(ValueError, match="resource_lock_(drift|binding)"):
            repair.mutate(request, rollback)
    finally:
        if second_fd is not None:
            os.close(second_fd)
    assert replaced and lock.stat().st_ino != detached.stat().st_ino
    assert lock.read_bytes() == detached.read_bytes() == original_lock
    assert not any(event["event"] == "complete" for event in events)
    changes = [event for event in events if event["event"] == "changed"]
    assert len(changes) == (1 if race == "changed" else 0)
    if race == "changed":
        assert target.read_bytes() == before[str(target)][0]
        assert stat.S_IMODE(target.stat().st_mode) == (0o777 if rollback else 0o755)
    else:
        assert before == {
            str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths
        }


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("drift", ["hardlink", "detached-lock"])
def test_actual_recipe_rechecks_target_and_lock_before_acl_mutation(
    actual_recipe_layout, monkeypatch, rollback, drift
):
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o777)
    subprocess.run(["setfacl", "-m", "u:501:rwx,g::rwx,m::rwx", str(target)], check=True)
    prepared = repair.inventory(profile)
    request = {"plan": prepared["plan"], "expected_plan_sha256": prepared["plan_sha256"],
               "operator_authority": "SYNTHETIC-ONLY"}
    if rollback:
        repair.mutate(request)
    before = repair.snapshot(str(target))
    expected_mode = 0o777 if rollback else 0o755
    expected_acl = repair.chmod_acl(before["acl"], expected_mode)
    others = {str(path): (path.read_bytes(), path.stat().st_mode)
              for path in code_paths if path != target}
    lock = Path(prepared["plan"]["scope"]["resource_lock"])
    events, validated, interrupted = [], False, False
    real_acl, real_process = repair.acl, repair.subprocess.Popen

    def acl(fd):
        nonlocal interrupted
        result = real_acl(fd)
        if (validated and not interrupted and os.fstat(fd).st_ino == target.stat().st_ino and
                stat.S_IMODE(os.fstat(fd).st_mode) == expected_mode):
            if drift == "hardlink":
                os.link(target, shared / "preserved-outside-alias")
            else:
                old = lock.read_bytes()
                lock.rename(lock.with_name("preserved-detached-run.lock"))
                lock.write_bytes(old)
                lock.chmod(0o600)
            interrupted = True
        return result

    def process(argv, *args, **kwargs):
        if argv[0].endswith("setfacl"):
            raise AssertionError("intervening drift reached ACL mutation")
        return real_process(argv, *args, **kwargs)

    def emit(value):
        nonlocal validated
        events.append(value)
        if value["event"] == "validated":
            validated = True

    monkeypatch.setattr(repair, "acl", acl)
    monkeypatch.setattr(repair.subprocess, "Popen", process)
    monkeypatch.setattr(repair, "emit", emit)
    reason = "hardlinked_code" if drift == "hardlink" else "resource_lock_(drift|binding)"
    with pytest.raises(ValueError, match=reason):
        repair.mutate(request, rollback)
    assert interrupted
    assert stat.S_IMODE(target.stat().st_mode) == expected_mode
    assert target.read_bytes() == code_paths[1].read_bytes()
    fd = repair.open_fixed(str(target))
    try:
        assert repair.normalize_acl(real_acl(fd)) == repair.normalize_acl(expected_acl)
    finally:
        os.close(fd)
    assert others == {str(path): (path.read_bytes(), path.stat().st_mode)
                      for path in code_paths if path != target}
    assert not any(event["event"] in ("changed", "complete") for event in events)


@pytest.mark.parametrize("recipe", [None, "caller-arbitrary", "standard-vm-trust-v1"])
def test_completion_enumeration_selects_only_registered_fixed_recipe(monkeypatch, recipe):
    calls = []
    expected = {"scope": {"paths": ["/fixed/code"]}, "records": []}
    monkeypatch.setattr(
        repair, "inventory", lambda profile: calls.append(profile) or {"plan": expected}
    )
    original = {"recipe_id": recipe, "profile": {"fixed": "synthetic-only"}}
    if recipe == "standard-vm-trust-v1":
        assert repair.completion_inventory(original) is expected
        assert calls == [original["profile"]]
    else:
        with pytest.raises(ValueError, match="fixed_profile_recipe_required"):
            repair.completion_inventory(original)
        assert not calls


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("stage", ["no-op", "already-processed"])
@pytest.mark.parametrize("drift", ["create", "rename"])
@pytest.mark.parametrize("library", ["ic", "spectre", "oa"])
def test_actual_completion_reenumerates_fixed_library_membership(
    actual_recipe_layout, monkeypatch, rollback, stage, drift, library
):
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o777)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    if rollback or stage == "no-op":
        repair.mutate(request)
    if rollback and stage == "no-op":
        repair.mutate(request, True)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    ms = Path(profile["tools"]["spectre"]["path"].split("/tools", 1)[0])
    directory = {"ic": ic / "tools.lnx86/lib", "spectre": ms / "tools.lnx86/lib",
                 "oa": ic / "oa/lib"}[library]
    new_library = directory / "unreviewed-runtime.so"
    pending = shared / "preserved-pending-library"
    if drift == "rename":
        pending.write_bytes(b"unreviewed synthetic shared object, never executed")
        pending.chmod(0o777)
    baseline = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    events, injected = [], False

    def emit(value):
        nonlocal injected
        events.append(value)
        if not injected and value["event"] == (
            "validated" if stage == "no-op" else "changed"
        ):
            if drift == "create":
                new_library.write_bytes(b"unreviewed synthetic shared object, never executed")
                new_library.chmod(0o777)
            else:
                pending.rename(new_library)
            injected = True

    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="completion_recipe_scope"):
        repair.mutate(request, rollback)
    assert injected and new_library.exists()
    assert new_library.read_bytes() == b"unreviewed synthetic shared object, never executed"
    assert stat.S_IMODE(new_library.stat().st_mode) == 0o777
    assert str(new_library.resolve()) not in prepared["plan"]["scope"]["paths"]
    assert not any(event["event"] == "complete" for event in events)
    assert len([event for event in events if event["event"] == "changed"]) == (
        1 if stage == "already-processed" else 0
    )
    for path in code_paths:
        assert path.read_bytes() == baseline[str(path)][0]
        if path != target or stage == "no-op":
            assert path.stat().st_mode == baseline[str(path)][1]
        else:
            assert stat.S_IMODE(path.stat().st_mode) == (0o777 if rollback else 0o755)


@pytest.mark.parametrize("missing", [False, True])
def test_fixed_apply_requires_authenticated_external_link_membership(monkeypatch, missing):
    original = {"schema_version": 2, "recipe_id": "standard-vm-trust-v1",
                "scope": {}, "profile": {}, "records": []}
    if not missing:
        original["readonly_compatibility_links"] = []
    fresh = dict(original, readonly_compatibility_links=[{
        "path": "/fixed/new.so", "resolved": "/outside/library", "exists": True,
        "target": "/outside/library",
    }])
    monkeypatch.setattr(repair, "inventory", lambda selected: {"plan": fresh})
    monkeypatch.setattr(repair, "open_fixed", lambda path: pytest.fail("binding reached lock"))
    with pytest.raises(ValueError, match="fixed_external_link_binding_required"):
        repair.mutate({"plan": original, "expected_plan_sha256": repair.digest(original),
                       "operator_authority": "SYNTHETIC-ONLY"})


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("stage", ["no-op", "already-processed"])
@pytest.mark.parametrize("drift", ["create", "rename", "retarget-same-resolution"])
@pytest.mark.parametrize("library", ["ic", "spectre", "oa"])
def test_actual_completion_binds_external_library_link_membership(
    actual_recipe_layout, monkeypatch, rollback, stage, drift, library
):
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o777)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    ms = Path(profile["tools"]["spectre"]["path"].split("/tools", 1)[0])
    directory = {"ic": ic / "tools.lnx86/lib", "spectre": ms / "tools.lnx86/lib",
                 "oa": ic / "oa/lib"}[library]
    external = shared / "preserved-external-library"
    external.write_bytes(b"synthetic external code, never executed or mutated")
    external.chmod(0o777)
    new_link = directory / "unreviewed-external.so"
    pending = shared / "preserved-pending-link"
    if drift == "retarget-same-resolution":
        new_link.symlink_to(external)
    if drift == "rename":
        pending.symlink_to(external)
    prepared = repair.inventory(profile)
    assert prepared["plan"]["readonly_compatibility_links"] == (
        prepared["readonly_compatibility_links"]
    )
    assert str(external) not in prepared["plan"]["scope"]["paths"]
    request = _receipt_request(prepared)
    if rollback or stage == "no-op":
        repair.mutate(request)
    if rollback and stage == "no-op":
        repair.mutate(request, True)
    baseline = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    external_before = (external.read_bytes(), external.stat().st_mode)
    events, injected = [], False

    def emit(value):
        nonlocal injected
        events.append(value)
        if not injected and value["event"] == (
            "validated" if stage == "no-op" else "changed"
        ):
            if drift == "create":
                new_link.symlink_to(external)
            elif drift == "rename":
                pending.rename(new_link)
            else:
                new_link.unlink()
                new_link.symlink_to(str(external.parent) + "/./" + external.name)
            injected = True

    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="completion_external_links"):
        repair.mutate(request, rollback)
    assert injected and new_link.is_symlink() and new_link.resolve() == external
    assert external_before == (external.read_bytes(), external.stat().st_mode)
    assert not any(event["event"] == "complete" for event in events)
    assert len([event for event in events if event["event"] == "changed"]) == (
        1 if stage == "already-processed" else 0
    )
    for path in code_paths:
        assert path.read_bytes() == baseline[str(path)][0]
        if path != target or stage == "no-op":
            assert path.stat().st_mode == baseline[str(path)][1]
        else:
            assert stat.S_IMODE(path.stat().st_mode) == (0o777 if rollback else 0o755)


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("stage", ["no-op", "already-processed"])
@pytest.mark.parametrize("drift", ["retarget", "detach-parent"])
@pytest.mark.parametrize("observation", ["readlink", "exists", "trailing-realpath"])
def test_actual_external_link_observation_rechecks_held_entry_and_parent(
    actual_recipe_layout, monkeypatch, rollback, stage, drift, observation
):
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o777)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    directory = ic / "tools.lnx86/lib"
    external = shared / "preserved-external-library"
    external.write_bytes(b"synthetic external code, never executed or mutated")
    external.chmod(0o777)
    link = directory / "unreviewed-external.so"
    link.symlink_to(external)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    if rollback or stage == "no-op":
        repair.mutate(request)
    if rollback and stage == "no-op":
        repair.mutate(request, True)
    baseline = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    external_before = (external.read_bytes(), external.stat().st_mode)
    events, active, injected, resolution_reads = [], False, False, 0
    original = {"readlink": repair.os.readlink, "exists": repair.os.path.exists,
                "trailing-realpath": repair.os.path.realpath}

    def observe(path, *args, **kwargs):
        nonlocal injected, resolution_reads
        value = original[observation](path, *args, **kwargs)
        if active and str(path).startswith("/proc/") and str(path).endswith("/" + link.name):
            resolution_reads += 1
            threshold = 2 if observation == "trailing-realpath" else 1
            if not injected and resolution_reads == threshold:
                if drift == "retarget":
                    link.unlink()
                    link.symlink_to(str(external.parent) + "/./" + external.name)
                else:
                    directory.rename(directory.with_name("preserved-detached-lib"))
                    directory.mkdir()
                    link.symlink_to(external)
                injected = True
        return value

    def emit(value):
        nonlocal active
        events.append(value)
        if value["event"] == ("validated" if stage == "no-op" else "changed"):
            active = True

    module, name = ((repair.os, "readlink") if observation == "readlink" else
                    (repair.os.path, "exists" if observation == "exists" else "realpath"))
    monkeypatch.setattr(module, name, observe)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="external_link_race"):
        repair.mutate(request, rollback)
    assert injected and link.is_symlink() and link.resolve() == external
    assert external_before == (external.read_bytes(), external.stat().st_mode)
    assert not any(event["event"] == "complete" for event in events)
    assert len([event for event in events if event["event"] == "changed"]) == (
        1 if stage == "already-processed" else 0
    )
    for path in code_paths:
        assert path.read_bytes() == baseline[str(path)][0]
        if path != target or stage == "no-op":
            assert path.stat().st_mode == baseline[str(path)][1]
        else:
            assert stat.S_IMODE(path.stat().st_mode) == (0o777 if rollback else 0o755)


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("stage", ["no-op", "already-processed"])
@pytest.mark.parametrize("drift", ["retarget", "detach-parent"])
def test_actual_external_binding_rechecked_after_internal_target_hashes(
    actual_recipe_layout, monkeypatch, rollback, stage, drift
):
    from pathlib import Path

    shared, root, workspace, code_paths, profile = actual_recipe_layout
    target = code_paths[0]
    target.chmod(0o777)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    directory = ic / "tools.lnx86/lib"
    external = shared / "preserved-external-library"
    external.write_bytes(b"synthetic external code, never executed or mutated")
    external.chmod(0o777)
    link = directory / "unreviewed-external.so"
    link.symlink_to(external)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    if rollback or stage == "no-op":
        repair.mutate(request)
    if rollback and stage == "no-op":
        repair.mutate(request, True)
    baseline = {str(path): (path.read_bytes(), path.stat().st_mode) for path in code_paths}
    external_before = (external.read_bytes(), external.stat().st_mode)
    events, active, injected, watched_reads = [], False, False, 0
    real_hash, watched_inode = repair.file_hash, code_paths[1].stat().st_ino

    def file_hash(fd):
        nonlocal injected, watched_reads
        value = real_hash(fd)
        if active and os.fstat(fd).st_ino == watched_inode:
            watched_reads += 1
            # Two reads occur in stored-path completion validation; the next
            # is after external collection in the full fresh fixed inventory.
            if watched_reads == 3:
                if drift == "retarget":
                    link.unlink()
                    link.symlink_to(str(external.parent) + "/./" + external.name)
                else:
                    directory.rename(directory.with_name("preserved-detached-lib"))
                    directory.mkdir()
                    link.symlink_to(external)
                injected = True
        return value

    def emit(value):
        nonlocal active
        events.append(value)
        if value["event"] == ("validated" if stage == "no-op" else "changed"):
            active = True

    monkeypatch.setattr(repair, "file_hash", file_hash)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="external_link_race"):
        repair.mutate(request, rollback)
    assert injected and link.is_symlink() and link.resolve() == external
    assert external_before == (external.read_bytes(), external.stat().st_mode)
    assert not any(event["event"] == "complete" for event in events)
    assert len([event for event in events if event["event"] == "changed"]) == (
        1 if stage == "already-processed" else 0
    )
    for path in code_paths:
        assert path.read_bytes() == baseline[str(path)][0]
        if path != target or stage == "no-op":
            assert path.stat().st_mode == baseline[str(path)][1]
        else:
            assert stat.S_IMODE(path.stat().st_mode) == (0o777 if rollback else 0o755)


@pytest.mark.parametrize("name", ["json", "hashlib", "stat", "os", "subprocess"])
def test_direct_repair_ignores_unlisted_stdlib_shadow(tmp_path, name):
    output = tmp_path / "helper"
    output.mkdir()
    exported = output / "repair.py"
    bootstrap.export_repair_helper(exported)
    marker = tmp_path / "unreviewed-repair-code"
    (output / (name + ".py")).write_text(
        "from pathlib import Path\nPath(" + ascii(str(marker)) +
        ").write_text('executed')\nraise RuntimeError('must-not-import')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", str(exported), "inventory"],
        cwd=output, input=b"{}", capture_output=True, timeout=15, check=False,
    )
    assert result.returncode == 1 and not result.stderr
    assert json.loads(result.stdout)["event"] == "rejected"
    assert not marker.exists()


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("stage", ["no-op", "already-processed"])
def test_external_parent_chain_reopened_after_fixed_leaf_read(
    actual_recipe_layout, monkeypatch, rollback, stage
):
    import inspect
    from pathlib import Path

    shared, _, _, code_paths, profile = actual_recipe_layout
    code_paths[0].chmod(0o777)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    directory = ic / "tools.lnx86/lib"
    external = shared / "preserved-external-library"
    external.write_bytes(b"synthetic external code, never mutated")
    link = directory / "unreviewed-external.so"
    link.symlink_to(external)
    prepared = repair.inventory(profile)
    request = _receipt_request(prepared)
    if rollback or stage == "no-op":
        repair.mutate(request)
    if rollback and stage == "no-op":
        repair.mutate(request, True)
    external_before = (external.read_bytes(), external.stat().st_mode)
    events, active, injected = [], False, False
    real_lstat = repair.os.lstat
    ancestor = directory.parent
    detached = ancestor.with_name("preserved-detached-ancestor")

    def lstat(path, *args, **kwargs):
        nonlocal injected
        value = real_lstat(path, *args, **kwargs)
        caller = inspect.currentframe().f_back
        if (active and not injected and str(path) == str(link) and
                caller.f_code.co_name == "external_link_record"):
            ancestor.rename(detached)
            injected = True
        return value

    def emit(value):
        nonlocal active
        events.append(value)
        if value["event"] == ("validated" if stage == "no-op" else "changed"):
            active = True

    monkeypatch.setattr(repair.os, "lstat", lstat)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="external_link_race"):
        repair.mutate(request, rollback)
    assert injected and detached.exists() and not link.exists()
    assert external_before == (external.read_bytes(), external.stat().st_mode)
    assert not any(event["event"] == "complete" for event in events)


@pytest.mark.parametrize("rollback", [False, True])
def test_external_only_library_parent_is_exact_repair_target(actual_recipe_layout, rollback):
    from pathlib import Path

    shared, _, _, _, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    nested = ic / "tools.lnx86/lib/external-only/nested"
    nested.mkdir(parents=True)
    nested.parent.chmod(0o777)
    nested.chmod(0o777)
    external = shared / "preserved-external-library"
    external.write_bytes(b"external bytes outside all mutation paths")
    external.chmod(0o777)
    (nested / "unreviewed-external.so").symlink_to(external)
    prepared = repair.inventory(profile)
    paths = prepared["plan"]["scope"]["paths"]
    assert str(nested) in paths and str(nested.parent) in paths
    assert str(external) not in paths
    external_before = (external.read_bytes(), external.stat().st_mode)
    request = _receipt_request(prepared)
    repair.mutate(request)
    assert stat.S_IMODE(nested.stat().st_mode) == 0o755
    assert stat.S_IMODE(nested.parent.stat().st_mode) == 0o755
    if rollback:
        repair.mutate(request, True)
        assert stat.S_IMODE(nested.stat().st_mode) == 0o777
        assert stat.S_IMODE(nested.parent.stat().st_mode) == 0o777
    assert external_before == (external.read_bytes(), external.stat().st_mode)


@pytest.mark.parametrize("variable", ["PYTHONPATH", "PYTHONUSERBASE"])
def test_repair_rejects_unisolated_python_before_absolute_search_hook(tmp_path, variable):
    exported = tmp_path / "repair.py"
    bootstrap.export_repair_helper(exported)
    hook = tmp_path / "unreviewed-hook"
    hook.mkdir()
    marker = tmp_path / "unreviewed-executed"
    (hook / "hashlib.py").write_text(
        "from pathlib import Path\nPath(" + ascii(str(marker)) + ").write_text('executed')\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment[variable] = str(hook)
    result = subprocess.run(
        [sys.executable, "-B", str(exported), "inventory"],
        env=environment, input=b"{}", capture_output=True, timeout=15, check=False,
    )
    assert result.returncode == 1 and not result.stdout
    assert result.stderr.splitlines() == [b"INSTALLATION_REPAIR_ISOLATED_PYTHON_REQUIRED"]
    assert not marker.exists()


@pytest.mark.parametrize("tampered", [False, True])
def test_large_fixed_inventory_helper_uses_short_command_and_bound_stdin(tampered):
    source = b"# owned synthetic filler\n" * 2000 + (
        b"import sys\ndef main():\n"
        b"    assert sys.stdin.read() == '{\"private\":true}'\n"
        b"    sys.stdout.write('SYNTHETIC_FIXED_INVENTORY_PASS')\n"
    )
    assert 32768 < len(source) < 131072
    code = bootstrap._repair_inventory_script(source)
    assert len(code) < 8192
    supplied = source[:-1] + b"x" if tampered else source
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", "-c", code, "inventory"],
        input=supplied + b'{"private":true}', capture_output=True, timeout=15, check=False,
    )
    if tampered:
        assert result.returncode == 1 and not result.stdout
        assert result.stderr.splitlines() == [b"INSTALLATION_REPAIR_SOURCE_REJECTED"]
    else:
        assert result.returncode == 0 and not result.stderr
        assert result.stdout == b"SYNTHETIC_FIXED_INVENTORY_PASS"


@pytest.mark.parametrize("retarget", [False, True])
def test_external_lexical_ancestor_rechecked_after_final_leaf(
    actual_recipe_layout, monkeypatch, retarget
):
    import inspect

    shared, _, _, _, _ = actual_recipe_layout
    original = shared / "preserved-oa-v1"
    alternate = shared / "preserved-oa-v2"
    original.mkdir()
    alternate.mkdir()
    target = shared / "preserved-vendor-leaf"
    target.write_bytes(b"external bytes must remain unchanged")
    leaf = original / "compatibility.so"
    leaf.symlink_to(target)
    # Both directories contain the same symlink inode: leaf identity alone
    # cannot detect a lexical ancestor switch; the original canonical parent lives.
    os.link(leaf, alternate / leaf.name, follow_symlinks=False)
    alias = shared / "oa"
    alias.symlink_to(original, target_is_directory=True)
    fixed = alias / leaf.name
    baseline = (target.read_bytes(), target.stat(), leaf.lstat())
    real_lstat, injected = repair.os.lstat, False

    def lstat(path, *args, **kwargs):
        nonlocal injected
        value = real_lstat(path, *args, **kwargs)
        caller = inspect.currentframe().f_back
        if (retarget and not injected and str(path) == str(fixed) and
                caller.f_code.co_name == "external_link_record"):
            alias.unlink()
            alias.symlink_to(alternate, target_is_directory=True)
            injected = True
        return value

    monkeypatch.setattr(repair.os, "lstat", lstat)
    if retarget:
        with pytest.raises(ValueError, match="external_link_race"):
            repair.external_link_record(str(fixed), str(target))
        assert injected
    else:
        result = repair.external_link_record(str(fixed), str(target))
        assert result["resolved"] == str(target)
    assert original.is_dir() and alternate.is_dir()
    assert baseline == (target.read_bytes(), target.stat(), leaf.lstat())
    assert leaf.lstat().st_ino == fixed.lstat().st_ino


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("library", ["ic", "spectre", "oa"])
@pytest.mark.parametrize("drift", ["create", "rename"])
def test_final_walk_membership_changes_during_later_target_hash_reject(
    actual_recipe_layout, monkeypatch, rollback, library, drift
):
    import inspect
    from pathlib import Path

    shared, _, _, code_paths, profile = actual_recipe_layout
    code_paths[0].chmod(0o777)
    request = _receipt_request(repair.inventory(profile))
    repair.mutate(request)
    if rollback:
        repair.mutate(request, True)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    ms = Path(profile["tools"]["spectre"]["path"].split("/tools", 1)[0])
    directory = {"ic": ic / "tools.lnx86/lib", "spectre": ms / "tools.lnx86/lib",
                 "oa": ic / "oa/lib"}[library]
    added, pending = directory / "late-unreviewed.so", shared / "preserved-pending-code"
    raw = b"synthetic shared object; never executed"
    if drift == "rename":
        pending.write_bytes(raw)
        pending.chmod(0o777)
    before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}
    real_plan, real_hash = repair.plan, repair.file_hash
    active, hashing, injected, events = False, False, False, []

    def plan(value):
        nonlocal hashing
        if active and inspect.currentframe().f_back.f_code.co_name == "inventory":
            hashing = True  # The final fixed-library walk has already completed.
        return real_plan(value)

    def file_hash(fd):
        nonlocal injected
        result = real_hash(fd)
        if hashing and not injected:
            if drift == "rename":
                pending.rename(added)
            else:
                added.write_bytes(raw)
                added.chmod(0o777)
            injected = True
        return result

    def emit(value):
        nonlocal active
        events.append(value)
        if value["event"] == "validated":
            active = True

    monkeypatch.setattr(repair, "plan", plan)
    monkeypatch.setattr(repair, "file_hash", file_hash)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="library_membership_race"):
        repair.mutate(request, rollback)
    assert injected and added.read_bytes() == raw and stat.S_IMODE(added.stat().st_mode) == 0o777
    assert not any(v["event"] in {"complete", "changed"} for v in events)
    assert before == {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}


@pytest.mark.parametrize("rollback", [False, True])
def test_internal_link_retarget_after_fixed_resolution_rejects_completion(
    actual_recipe_layout, monkeypatch, rollback
):
    import inspect
    from pathlib import Path

    _, _, _, code_paths, profile = actual_recipe_layout
    code_paths[0].chmod(0o777)
    request = _receipt_request(repair.inventory(profile))
    repair.mutate(request)
    if rollback:
        repair.mutate(request, True)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    link, retained = ic / "tools", ic / "preserved-old-tools-alias"
    before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}
    original, active, injected, events = repair.os.path.realpath, False, False, []

    def realpath(path, *args, **kwargs):
        nonlocal injected
        result = original(path, *args, **kwargs)
        if (active and not injected and str(path) == str(link) and
                inspect.currentframe().f_back.f_code.co_name == "external_link_record"):
            link.rename(retained)
            link.symlink_to("./tools.lnx86")
            injected = True
        return result

    def emit(value):
        nonlocal active
        events.append(value)
        if value["event"] == "validated":
            active = True

    monkeypatch.setattr(repair.os.path, "realpath", realpath)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="external_link_race"):
        repair.mutate(request, rollback)
    assert injected and retained.is_symlink() and link.resolve() == retained.resolve()
    assert not any(v["event"] in {"complete", "changed"} for v in events)
    assert before == {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}


@pytest.mark.parametrize("rollback", [False, True])
def test_internal_only_library_parents_are_exact_repair_targets(actual_recipe_layout, rollback):
    from pathlib import Path

    _, _, _, code_paths, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    nested = ic / "tools.lnx86/lib/internal-only/nested"
    nested.mkdir(parents=True)
    nested.parent.chmod(0o777)
    nested.chmod(0o777)
    link = nested / "owned-internal.so"
    link.symlink_to(code_paths[0])
    before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}
    link_before = link.lstat()
    prepared = repair.inventory(profile)
    assert str(nested) in prepared["plan"]["scope"]["paths"]
    assert str(nested.parent) in prepared["plan"]["scope"]["paths"]
    request = _receipt_request(prepared)
    repair.mutate(request)
    assert stat.S_IMODE(nested.stat().st_mode) == 0o755
    assert stat.S_IMODE(nested.parent.stat().st_mode) == 0o755
    repair.mutate(request)
    if rollback:
        repair.mutate(request, True)
        repair.mutate(request, True)
        assert stat.S_IMODE(nested.stat().st_mode) == 0o777
        assert stat.S_IMODE(nested.parent.stat().st_mode) == 0o777
    assert link_before == link.lstat()
    assert before == {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}


@pytest.mark.parametrize("external", [False, True])
def test_unvisited_nested_library_directory_alias_rejects_before_repair(
    actual_recipe_layout, external
):
    from pathlib import Path

    shared, _, _, code_paths, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    target = shared / "preserved-external-directory" if external else ic / "tools.lnx86/bin"
    if external:
        target.mkdir()
        (target / "unreviewed.so").write_bytes(b"synthetic unvisited code")
    alias = ic / "tools.lnx86/lib/unvisited-directory"
    alias.symlink_to(target, target_is_directory=True)
    before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}
    with pytest.raises(ValueError, match="library_directory_alias_not_enumerated"):
        repair.inventory(profile)
    assert alias.is_symlink() and target.is_dir()
    assert before == {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}


def test_library_snapshot_retains_bounded_digest_not_aggregate_names(actual_recipe_layout):
    shared, _, _, _, _ = actual_recipe_layout
    directory = shared / "owned-membership-directory"
    directory.mkdir()
    for index in range(1000):
        (directory / f"member-{index:04d}").write_bytes(b"synthetic")
    signature, names = repair.library_directory_snapshot(str(directory))
    assert len(signature) == 64 and len(names) == 1000
    (directory / "later-member").write_bytes(b"retained synthetic")
    assert repair.library_directory_snapshot(str(directory))[0] != signature


def test_library_membership_signature_hashes_canonical_bytes_once(monkeypatch):
    import hashlib
    from types import SimpleNamespace

    directory = SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFDIR | 0o755,
        st_uid=500, st_gid=500, st_nlink=2, st_size=4096, st_mtime=1.25, st_ctime=2.5)
    monkeypatch.setattr(repair, "lexical_parent_snapshot", lambda path: [])
    monkeypatch.setattr(repair.os.path, "realpath", lambda path: path)
    monkeypatch.setattr(repair, "open_fixed", lambda path: 7)
    monkeypatch.setattr(repair.os, "fstat", lambda fd: directory)
    monkeypatch.setattr(repair.os, "lstat", lambda path: directory)
    monkeypatch.setattr(repair.os, "close", lambda fd: None)
    monkeypatch.setattr(repair, "bounded_directory_names", lambda fd: ["a.so", "b.so"])
    monkeypatch.setattr(repair, "descriptor_path", lambda fd: "/owned")
    signature, names = repair.library_directory_snapshot("/owned")
    expected = ("/owned", [1, 2, directory.st_mode, 500, 500, 2, 4096, "1.25", "2.5"],
                ["a.so", "b.so"], [])
    assert signature == hashlib.sha256(repair.canonical(expected)).hexdigest()
    assert names == ["a.so", "b.so"]


def test_library_stream_rejects_before_materializing_oversized_directory(actual_recipe_layout,
                                                                       monkeypatch):
    shared, _, _, _, _ = actual_recipe_layout
    directory = shared / "owned-bounded-stream"
    directory.mkdir()
    for index in range(9):
        (directory / f"entry-{index}").write_bytes(b"synthetic")
    monkeypatch.setattr(repair, "MAX_ITEMS", 8)
    monkeypatch.setattr(repair.os, "listdir", lambda *a: pytest.fail("unbounded listdir"))
    monkeypatch.setattr(repair.os, "walk", lambda *a, **kw: pytest.fail("unbounded walk"))
    with pytest.raises(ValueError, match="library_membership_limit"):
        repair.library_directory_snapshot(str(directory))
    monkeypatch.setattr(repair, "MAX_ITEMS", 9)
    signature, names = repair.library_directory_snapshot(str(directory))
    assert len(signature) == 64 and len(names) == 9


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("shared_target", [False, True])
def test_standard_vm_tcl_aliases_enumerate_sourced_code_exactly(
    actual_recipe_layout, rollback, shared_target
):
    from pathlib import Path

    _, _, _, code_paths, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    scripts = []
    for stem in ("tcl", "tk"):
        entry = ic / "share/lib/tcltk" / (stem + "8.4")
        target = entry.parent / "08.49" if shared_target else entry
        target.mkdir(parents=True, exist_ok=True)
        if shared_target:
            entry.symlink_to("08.49", target_is_directory=True)
        script = target / (stem + "-init.tcl")
        script.write_bytes(b"# synthetic sourced code; never executed\n")
        script.chmod(0o777)
        scripts.append(script)
        (ic / "tools.lnx86/lib" / (stem + "8.4")).symlink_to(entry, target_is_directory=True)
        (ic / "tools.lnx86/lib" / stem).symlink_to(stem + "8.4", target_is_directory=True)
    original = {str(p): p.read_bytes() for p in code_paths + scripts}
    prepared = repair.inventory(profile)
    for script in scripts:
        assert str(script) in prepared["plan"]["scope"]["paths"]
    request = _receipt_request(prepared)
    repair.mutate(request)
    repair.mutate(request)
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o755 for p in scripts)
    if rollback:
        repair.mutate(request, True)
        repair.mutate(request, True)
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o777 for p in scripts)
    assert original == {str(p): p.read_bytes() for p in code_paths + scripts}


def test_standard_vm_tcl_alias_cannot_expand_to_other_installation_code(actual_recipe_layout):
    from pathlib import Path

    _, _, _, _, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    (ic / "tools.lnx86/lib/tcl").symlink_to(ic / "tools.lnx86/bin", target_is_directory=True)
    with pytest.raises(ValueError, match="library_directory_alias_not_enumerated"):
        repair.inventory(profile)


@pytest.mark.parametrize("rollback", [False, True])
def test_empty_traversed_library_namespace_is_exact_repair_target(actual_recipe_layout, rollback):
    from pathlib import Path

    _, _, _, code_paths, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    directory = ic / "tools.lnx86/lib/empty-code-namespace/nested"
    directory.mkdir(parents=True)
    directory.parent.chmod(0o777)
    directory.chmod(0o777)
    before = {str(p): p.read_bytes() for p in code_paths}
    prepared = repair.inventory(profile)
    assert str(directory) in prepared["plan"]["scope"]["paths"]
    assert str(directory.parent) in prepared["plan"]["scope"]["paths"]
    request = _receipt_request(prepared)
    repair.mutate(request)
    repair.mutate(request)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    assert stat.S_IMODE(directory.parent.stat().st_mode) == 0o755
    if rollback:
        repair.mutate(request, True)
        repair.mutate(request, True)
        assert stat.S_IMODE(directory.stat().st_mode) == 0o777
        assert stat.S_IMODE(directory.parent.stat().st_mode) == 0o777
    assert before == {str(p): p.read_bytes() for p in code_paths}


@pytest.mark.parametrize("name", ["package.itcl", "package.itk", "extensionless-source"])
def test_fixed_tcl_code_roles_include_any_sourceable_filename(actual_recipe_layout, name):
    from pathlib import Path

    _, _, _, _, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    target = ic / "share/lib/tcltk/tcl8.4"
    target.mkdir(parents=True)
    script = target / name
    script.write_bytes(b"# synthetic sourceable file\n")
    script.chmod(0o777)
    (ic / "tools.lnx86/lib/tcl").symlink_to(target, target_is_directory=True)
    prepared = repair.inventory(profile)
    assert str(script) in prepared["plan"]["scope"]["paths"]
    repair.mutate(_receipt_request(prepared))
    assert stat.S_IMODE(script.stat().st_mode) == 0o755
    assert script.read_bytes() == b"# synthetic sourceable file\n"


def test_fixed_vendor_roots_use_final_tools_segment(actual_recipe_layout):
    from pathlib import Path

    shared, _, _, _, profile = actual_recipe_layout
    source = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0]).parent
    parent = shared / "tools"
    parent.mkdir()
    destination = parent / "cadence"
    source.rename(destination)
    # The owned fixture uses absolute installation aliases. Preserve their
    # internal relationship after relocation rather than leave dangling links
    # to the old test installation.
    for relative in ('IC615/tools', 'MMSIM121/tools', 'IC615/oa'):
        alias = destination / relative
        target = alias.readlink()
        assert str(target).startswith(str(source) + '/')
        alias.unlink()
        alias.symlink_to(str(target).replace(str(source), str(destination), 1),
                         target_is_directory=True)

    def relocate(value):
        if isinstance(value, str):
            return value.replace(str(source), str(destination))
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        return value

    prepared = repair.inventory(relocate(profile))
    assert prepared["plan"]["recipe_id"] == "standard-vm-trust-v1"
    assert any(str(destination) in path for path in prepared["plan"]["scope"]["paths"])


@pytest.mark.parametrize("name", ["data", "doc", "samples", "license", "package64"])
@pytest.mark.parametrize("rollback", [False, True])
def test_fixed_tcl_descendants_do_not_use_native_library_exclusions(
    actual_recipe_layout, name, rollback
):
    from pathlib import Path

    _, _, _, _, profile = actual_recipe_layout
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    target = ic / "share/lib/tcltk/tcl8.4"
    directory = target / name
    directory.mkdir(parents=True)
    script = directory / "source.itcl"
    script.write_bytes(b"# owned fixture, never executed\n")
    directory.chmod(0o777)
    script.chmod(0o777)
    (ic / "tools.lnx86/lib/tcl").symlink_to(target, target_is_directory=True)
    prepared = repair.inventory(profile)
    assert {str(directory), str(script)} <= set(prepared["plan"]["scope"]["paths"])
    request = _receipt_request(prepared)
    repair.mutate(request)
    repair.mutate(request)
    for path in (directory, script):
        assert stat.S_IMODE(path.stat().st_mode) == 0o755
    if rollback:
        repair.mutate(request, True)
        for path in (directory, script):
            assert stat.S_IMODE(path.stat().st_mode) == 0o777
    assert script.read_bytes() == b"# owned fixture, never executed\n"


@pytest.mark.parametrize("kind", ["external", "internal"])
@pytest.mark.parametrize("bound", ["count", "bytes"])
def test_compatibility_records_are_bounded_before_retaining(monkeypatch, kind, bound):
    records = [] if kind == "external" else {}
    usage = [0, 0]
    record = {"path": "/owned/alias", "resolved": "/trusted/library", "metadata": [1, 2]}
    size = 2 * len(repair.canonical(record))
    monkeypatch.setattr(repair, "MAX_ITEMS", 1 if bound == "count" else 20)
    monkeypatch.setattr(repair, "LIMIT", size if bound == "bytes" else size * 20)
    repair.retain_compatibility_record(records, record, usage,
                                       None if kind == "external" else record["path"])
    before, before_usage = records.copy(), usage[:]
    with pytest.raises(ValueError, match="inventory_compatibility_limit"):
        repair.retain_compatibility_record(records, record, usage,
                                           None if kind == "external" else "/owned/second")
    assert records == before and usage == before_usage
    if kind == "internal":
        repair.retain_compatibility_record(records, record, usage, record["path"])
        assert records == before and usage == before_usage


@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("drift", ["create", "rename"])
def test_earlier_directory_changes_during_later_final_membership_scan_reject(
    actual_recipe_layout, monkeypatch, rollback, drift
):
    from pathlib import Path

    shared, _, _, code_paths, profile = actual_recipe_layout
    code_paths[0].chmod(0o777)
    request = _receipt_request(repair.inventory(profile))
    repair.mutate(request)
    if rollback:
        repair.mutate(request, True)
    ic = Path(profile["tools"]["virtuoso"]["path"].split("/tools", 1)[0])
    earlier = ic / "oa/lib/late-unreviewed.so"
    later = str(ic / "tools.lnx86/lib")
    pending = shared / "preserved-pending-library"
    raw = b"owned synthetic library, never executed"
    if drift == "rename":
        pending.write_bytes(raw)
    before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}
    real_snapshot = repair.library_directory_snapshot
    active, injected, calls, events = False, False, {}, []

    def snapshot(path):
        nonlocal injected
        value = real_snapshot(path)
        if active:
            calls[path] = calls.get(path, 0) + 1
            if path == later and calls[path] == 2 and not injected:
                if drift == "rename":
                    pending.rename(earlier)
                else:
                    earlier.write_bytes(raw)
                injected = True
        return value

    def emit(value):
        nonlocal active
        events.append(value)
        if value["event"] == "validated":
            active = True

    monkeypatch.setattr(repair, "library_directory_snapshot", snapshot)
    monkeypatch.setattr(repair, "emit", emit)
    with pytest.raises(ValueError, match="library_membership_race"):
        repair.mutate(request, rollback)
    assert injected and earlier.read_bytes() == raw
    assert not any(event["event"] in {"complete", "changed"} for event in events)
    assert before == {str(p): (p.read_bytes(), p.stat().st_mode) for p in code_paths}
