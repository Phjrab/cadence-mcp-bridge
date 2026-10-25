"""Synthetic fixed TTY framing; owned Linux files are not VM qualification."""

import base64
import copy
import hashlib
import io
import json
import os
import shlex
import socket
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_binding_initializer_rebind import (
    evidence,
    operator,
    operator_base,
    ordinary_account_output_owner,
    registered,
)

from cadence_mcp_bridge import binding_initializer as initializer
from cadence_mcp_bridge.domain_provisioning import _canonical

__all__ = ["evidence", "operator", "operator_base", "ordinary_account_output_owner", "registered"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def material(monkeypatch):
    value = dict(host=dict(hostname="synthetic-vm", architecture="i686", user="operator"),
                 paths=dict(managed_root="/home/operator/work/.cadence_mcp"))
    profile = SimpleNamespace(model_dump=lambda **_: copy.deepcopy(value),
        host=SimpleNamespace(**value["host"]), paths=SimpleNamespace(**value["paths"]),
        limits=SimpleNamespace(disk_floor_bytes=2_147_483_648, disk_floor_percent=10))
    plan, registration = {"synthetic": True}, {"synthetic_registration": True}
    monkeypatch.setattr(initializer, "helper_bytes", lambda *_: b"print('synthetic')\n")
    monkeypatch.setattr(initializer, "_expected_transitions", lambda *_: [])
    result = initializer.tty_material(profile, registration, plan, sha(_canonical(plan)),
                                      "SYNTHETIC_NOT_HUMAN_AUTHORITY")
    return result, profile, registration, plan


def remote(material, monkeypatch, phase="apply"):
    monkeypatch.setitem(sys.modules, "pwd", SimpleNamespace(getpwnam=lambda _: None))
    namespace = {"__name__": "synthetic_unexecuted_entry"}
    exec(compile(material[0][phase + "_entry"], "synthetic_tty_entry", "exec"), namespace)
    return namespace


def terminal(material, stdout=b'{"synthetic":true}\n', stderr=b"", code=0):
    pins = material[0]["pins"]

    def stream(raw):
        return dict(bytes=len(raw), sha256=sha(raw),
                    base64=base64.b64encode(raw).decode("ascii"))

    return dict(schema_version=1, kind="FIXED_INITIALIZER_TTY_TERMINAL",
        status="HELPER_SUCCEEDED" if code == 0 else "FAILED_OR_UNKNOWN", returncode=code,
        helper_started=True, files_retained=True,
        **{key: pins[key] for key in ("frame_sha256", "helper_sha256", "plan_sha256")},
        stdout=stream(stdout), stderr=stream(stderr))


def test_factory_is_local_and_keeps_request_and_plan_immutable(material, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("local material factory reached process/network")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result, profile, registration, plan = material
    before = copy.deepcopy((registration, plan))
    again = initializer.tty_material(profile, registration, plan, sha(_canonical(plan)),
                                     "SYNTHETIC_NOT_HUMAN_AUTHORITY")
    assert again == result
    assert (registration, plan) == before
    assert result["stage_path"].startswith(profile.paths.managed_root + "/initializer-tty-")
    assert result["root_path"].startswith("/root/cadence-mcp-initializer-tty-")
    assert result["pins"]["frame_sha256"] == sha(result["frame"])
    assert json.loads(result["postcheck_request"])["operator_authority"] is None


def test_real_exported_helper_and_observed_plan_are_reused(evidence):
    plan = json.loads(evidence["plan_path"].read_bytes())
    profile = evidence["context"].contracts.environment
    plan["registration"]["environment_sha256"] = sha(_canonical(profile.model_dump(mode="json")))
    result = initializer.tty_material(profile, plan["registration"], plan,
        sha(_canonical(plan)), "SYNTHETIC_REGISTERED_TEST_NOT_AUTHORITY")
    helper = initializer.helper_bytes(profile, plan["registration"])
    assert result["frame"].startswith(helper)
    assert result["pins"]["helper_sha256"] == sha(helper)
    assert result["transitions"] == initializer._expected_transitions(
        plan, profile.model_dump(mode="json"), plan["registration"])


@pytest.mark.parametrize("authority", ["", "a" * 513, None, 1])
def test_factory_rejects_missing_or_oversize_authority(material, authority):
    _, profile, registration, plan = material
    with pytest.raises(ValueError, match="exact_plan_and_actual_authority"):
        initializer.tty_material(profile, registration, plan, sha(_canonical(plan)), authority)


def test_factory_rejects_plan_mismatch_and_source_overflow(material, monkeypatch):
    _, profile, registration, plan = material
    with pytest.raises(ValueError, match="exact_plan"):
        initializer.tty_material(profile, registration, plan, "f" * 64, "synthetic")
    monkeypatch.setattr(initializer, "helper_bytes", lambda *_: b"x" * 262_145)
    with pytest.raises(ValueError, match="frame_bound"):
        initializer.tty_material(profile, registration, plan, sha(_canonical(plan)), "synthetic")


def test_all_generated_entries_fit_windows_ssh_command_bound(material):
    value = material[0]
    for key in ("stage_entry", "apply_entry", "postcheck_entry"):
        source = value[key]
        source.encode("ascii")
        compile(source, "fixed_entry", "exec")
        command = ["C:\\Windows\\System32\\OpenSSH\\ssh.exe", "-o", "BatchMode=yes",
                   "-o", "StrictHostKeyChecking=yes", "-tt", "cadence-vm",
                   "/usr/bin/sudo", "-n", "--", "/usr/bin/python", "-E", "-s", "-B",
                   "-c", shlex.quote(source)]
        assert len(subprocess.list2cmdline(command)) < 32_767
        assert value["pins"][key + "_sha256"] == sha(source.encode("ascii"))


@pytest.mark.parametrize("change", [lambda raw: raw[:-1], lambda raw: raw + b"x",
                                    lambda raw: b"x" + raw[1:]])
def test_generated_entry_rejects_inexact_frame(material, monkeypatch, change):
    namespace = remote(material, monkeypatch)
    with pytest.raises(ValueError, match="tty_rejected"):
        namespace["frame"](change(material[0]["frame"]))


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_exact_single_terminal_preserves_raw_streams(material, ending):
    row = terminal(material, b"out\r\n", b"failure\x00\n", code=1)
    assert initializer.parse_tty_terminal(_canonical(row) + ending, material[0]) == (
        1, b"out\r\n", b"failure\x00\n")


@pytest.mark.parametrize("noise", [b"banner\n", b"\n", b" ", b"{}\n"])
def test_parser_rejects_noise_instead_of_selecting_a_json_line(material, noise):
    with pytest.raises(ValueError):
        initializer.parse_tty_terminal(noise + _canonical(terminal(material)) + b"\n", material[0])


@pytest.mark.parametrize("change", [
    lambda row: row.update(frame_sha256="f" * 64),
    lambda row: row.update(helper_started=False),
    lambda row: row.update(returncode=True),
    lambda row: row["stdout"].update(bytes=True),
    lambda row: row["stdout"].update(base64="!!!!"),
    lambda row: row["stdout"].update(sha256="f" * 64),
    lambda row: row["stderr"].update(bytes=1_048_577),
])
def test_parser_rejects_forged_pins_types_and_stream_bounds(material, change):
    row = terminal(material)
    change(row)
    with pytest.raises(ValueError):
        initializer.parse_tty_terminal(_canonical(row) + b"\r\n", material[0])


def test_parser_rejects_duplicate_fields_and_unterminated_data(material):
    raw = _canonical(terminal(material))
    with pytest.raises(ValueError):
        initializer.parse_tty_terminal(raw, material[0])
    with pytest.raises(ValueError):
        initializer.parse_tty_terminal(raw[:-1] + b',"schema_version":1}\n', material[0])


def test_disk_floor_includes_block_rounding_and_metadata_overhead(material, monkeypatch):
    namespace = remote(material, monkeypatch)
    config = namespace["CONFIG"]
    floor = config["disk_floor_bytes"]
    namespace["os"] = SimpleNamespace(statvfs=lambda _: SimpleNamespace(
        f_bavail=(floor + 4096) // 4096, f_frsize=4096, f_blocks=(floor * 4) // 4096))
    with pytest.raises(ValueError, match="tty_rejected"):
        namespace["floor"]("/synthetic", [1], 32768)


def test_factory_reserves_exact_observed_plan_receipt_without_changing_caps(material, monkeypatch):
    value, _, _, plan = material
    monkeypatch.setattr(initializer.repair, "os", SimpleNamespace(getuid=lambda: 0))
    receipt = initializer.repair.receipt_bytes(plan)
    assert value["limits"]["observed_plan_receipt_bytes"] == len(receipt)
    assert value["limits"]["user_stage_min_overhead_bytes"] == 32_768
    assert value["limits"]["root_stage_min_overhead_bytes"] == 65_536
    assert value["limits"]["managed_receipt_min_overhead_bytes"] == 65_536
    assert all(value["limits"][key] == cap for key, cap in initializer.TTY_LIMITS.items())


def test_factory_rejects_observed_plan_receipt_past_existing_engine_limit(material, monkeypatch):
    _, profile, registration, plan = material
    monkeypatch.setattr(initializer.repair, "LIMIT", 1)
    with pytest.raises(ValueError, match="observed_receipt_bound"):
        initializer.tty_material(profile, registration, plan, sha(_canonical(plan)), "synthetic")


def test_parent_capture_caps_direct_fd_streams_and_kills_only_owned_pid(material, monkeypatch):
    namespace = remote(material, monkeypatch)
    namespace["CONFIG"].update(stdout_bytes=3, stderr_bytes=2)
    chunks = {10: [b"abcdef", b""], 12: [b"xyz", b""]}
    killed, written, pipes = [], {20: b"", 21: b""}, iter([(10, 11), (12, 13)])
    fake_os = SimpleNamespace(pipe=lambda: next(pipes), fork=lambda: 123, close=lambda _: None,
        times=lambda: (0, 0, 0, 0, 0), read=lambda fd, _: chunks[fd].pop(0),
        waitpid=lambda *_: (123, 0), WNOHANG=1, WIFEXITED=lambda _: True,
        WEXITSTATUS=lambda _: 0, kill=lambda pid, sig: killed.append((pid, sig)))
    namespace["os"] = fake_os
    namespace["signal"] = SimpleNamespace(SIGKILL=9)
    namespace["select"] = SimpleNamespace(select=lambda readers, *_: (readers, [], []))
    namespace["write_file"] = lambda fd, raw: written.__setitem__(fd, written[fd] + raw)
    assert namespace["capture"](b"", b"", 20, 21, [20, 21], 65) is False
    assert written == {20: b"abc", 21: b"xy"}
    assert len(killed) == 1 and killed[0][0] == 123


def test_capture_child_closes_all_inherited_spool_and_directory_fds(material, monkeypatch):
    namespace = remote(material, monkeypatch)
    closed, pipes = [], iter([(10, 11), (12, 13)])

    class ChildExit(BaseException):
        pass

    def exit_child(code):
        assert code == 0
        raise ChildExit

    namespace["os"] = SimpleNamespace(pipe=lambda: next(pipes), fork=lambda: 0,
        close=closed.append, dup2=lambda *_: None, _exit=exit_child,
        times=lambda: (0, 0, 0, 0, 0))
    namespace["sys"] = SimpleNamespace(stdout=SimpleNamespace(flush=lambda: None),
                                       stderr=SimpleNamespace(flush=lambda: None))
    namespace["child"] = lambda *_: None
    with pytest.raises(ChildExit):
        namespace["capture"](b"", b"", 20, 21, [20, 21, 22, 23, 22], 65)
    assert all(fd in closed for fd in (20, 21, 22, 23))
    assert 1 not in closed and 2 not in closed


@pytest.mark.skipif(os.name != "posix", reason="Owned synthetic Linux fork and pipe capture")
@pytest.mark.parametrize("overflow", [False, True])
def test_owned_linux_actual_fork_captures_direct_fd_writes(
    material, monkeypatch, tmp_path, overflow,
):
    namespace = remote(material, monkeypatch)
    namespace["CONFIG"].update(stdout_bytes=16, stderr_bytes=8)
    out_raw = b"x" * 32 if overflow else b"out\x00\n"
    err_raw = b"err\n"

    def synthetic_child(*_):
        os.write(1, out_raw)
        os.write(2, err_raw)

    namespace["child"] = synthetic_child
    namespace["sys"] = SimpleNamespace(stdout=SimpleNamespace(flush=lambda: None),
                                       stderr=SimpleNamespace(flush=lambda: None))
    out_path, err_path = tmp_path / "stdout", tmp_path / "stderr"
    with out_path.open("xb", buffering=0) as out, err_path.open("xb", buffering=0) as err:
        success = namespace["capture"](b"", b"", out.fileno(), err.fileno(),
                                       [out.fileno(), err.fileno()], os.times()[4] + 65)
        assert success is not overflow
    assert out_path.read_bytes() == out_raw[:16]
    # A stopped overflowing helper may have exited before its second write.
    assert err_path.read_bytes() in (b"", err_raw) if overflow else err_path.read_bytes() == err_raw


@pytest.mark.skipif(os.name != "posix", reason="Owned Linux bounded fork cancellation")
def test_owned_linux_capture_uses_elapsed_bootstrap_deadline_and_retains_partial_output(
    material, monkeypatch, tmp_path,
):
    namespace = remote(material, monkeypatch)
    kills = []
    proxy = SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})

    def kill(pid, sig):
        kills.append((pid, sig))
        os.kill(pid, sig)

    proxy.kill = kill
    namespace["os"] = proxy

    def synthetic_child(*_):
        os.write(1, b"retained owned child output\n")
        # The parent has milliseconds remaining and must terminate this owned
        # child, rather than replacing that elapsed budget with a fresh65s.
        namespace["select"].select([], [], [], 5)

    namespace["child"] = synthetic_child
    namespace["sys"] = SimpleNamespace(stdout=SimpleNamespace(flush=lambda: None),
                                       stderr=SimpleNamespace(flush=lambda: None))
    before = os.times()[4]
    out_path, err_path = tmp_path / "stdout", tmp_path / "stderr"
    with (
        out_path.open("xb", buffering=0) as out,
        err_path.open("xb", buffering=0) as err,
        pytest.raises(ValueError, match="tty_rejected"),
    ):
        namespace["capture"](b"", b"", out.fileno(), err.fileno(),
            [out.fileno(), err.fileno()], before + 0.1)
    assert os.times()[4] - before < 2
    assert len(kills) == 1 and kills[0][0] != os.getpid()
    assert out_path.read_bytes() in (b"", b"retained owned child output\n")
    assert err_path.read_bytes() == b""


def test_factory_exposes_coherent_bounded_helper_and_transport_budgets(material):
    limits = material[0]["limits"]
    assert {key: limits[key] for key in (
        "helper_mutation_seconds", "helper_inspection_seconds", "apply_bootstrap_seconds",
        "apply_ssh_seconds", "stage_ssh_seconds", "postcheck_ssh_seconds", "cleanup_seconds",
        "diagnostic_bytes",
    )} == dict(helper_mutation_seconds=3600, helper_inspection_seconds=60,
        apply_bootstrap_seconds=3660, apply_ssh_seconds=3720, stage_ssh_seconds=120,
        postcheck_ssh_seconds=120, cleanup_seconds=5, diagnostic_bytes=2048)


@pytest.mark.skipif(os.name != "posix", reason="Owned Linux no-follow/file metadata seam")
@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_owned_linux_file_seam_rejects_aliases(material, monkeypatch, tmp_path, kind):
    namespace = remote(material, monkeypatch)
    original = tmp_path / "original"
    original.write_bytes(b"synthetic")
    original.chmod(0o600)
    alias = tmp_path / "alias"
    if kind == "symlink":
        alias.symlink_to(original)
    else:
        os.link(original, alias)
    with pytest.raises((ValueError, OSError)):
        namespace["file_open"](str(alias), os.getuid(), os.getgid(), 0o600)
    assert original.read_bytes() == b"synthetic"


@pytest.mark.skipif(os.name != "posix", reason="Owned Linux exclusive creation seam")
def test_owned_linux_file_seam_preserves_claim_on_replay(material, monkeypatch, tmp_path):
    namespace = remote(material, monkeypatch)
    path = str(tmp_path / "frame")
    fd = namespace["file_open"](path, os.getuid(), os.getgid(), 0o600, True)
    try:
        namespace["write_file"](fd, b"preserved")
        os.fsync(fd)
        with pytest.raises(FileExistsError):
            namespace["file_open"](path, os.getuid(), os.getgid(), 0o600, True)
        assert namespace["read_file"](path, fd, 9) == b"preserved"
    finally:
        os.close(fd)


def test_stage_rechecks_frame_after_final_sync_before_terminal(material, monkeypatch):
    namespace = remote(material, monkeypatch, "stage")
    events = []
    account = SimpleNamespace(pw_uid=500, pw_gid=500)
    info = SimpleNamespace(st_uid=500, st_gid=500, st_mode=stat.S_IFDIR | 0o700)
    namespace["runtime"] = lambda _: account
    namespace["sys"] = SimpleNamespace(stdin=io.BytesIO(material[0]["frame"]),
        stdout=SimpleNamespace(write=lambda _: events.append("terminal")))
    namespace["os"] = SimpleNamespace(mkdir=lambda *_: None, fstat=lambda _: info,
                                      fsync=lambda _: None, close=lambda _: None)
    namespace["chain"] = lambda *_: [("synthetic", 1, ())]
    namespace["guard"] = lambda _: events.append("guard")
    namespace["floor"] = lambda *_: None
    namespace["file_open"] = lambda *_: 2
    namespace["write_file"] = lambda *_: None
    namespace["read_file"] = lambda *_: events.append("read") or material[0]["frame"]
    namespace["identity"] = lambda _: ()
    namespace["same_name"] = lambda *_: None
    namespace["sync"] = lambda *_: events.append("sync")
    namespace["stage"]()
    assert events[-4:] == ["sync", "read", "guard", "terminal"]


def test_stage_late_sync_drift_cannot_publish_success(material, monkeypatch):
    namespace = remote(material, monkeypatch, "stage")
    events = []
    info = SimpleNamespace(st_uid=500, st_gid=500, st_mode=stat.S_IFDIR | 0o700)
    namespace["runtime"] = lambda _: SimpleNamespace(pw_uid=500, pw_gid=500)
    namespace["sys"] = SimpleNamespace(stdin=io.BytesIO(material[0]["frame"]),
        stdout=SimpleNamespace(write=lambda _: events.append("terminal")))
    namespace["os"] = SimpleNamespace(mkdir=lambda *_: None, fstat=lambda _: info,
                                      fsync=lambda _: None, close=lambda _: None)
    namespace["chain"] = lambda *_: [("synthetic", 1, ())]
    namespace["guard"] = lambda _: None
    namespace["floor"] = lambda *_: None
    namespace["file_open"] = lambda *_: 2
    namespace["write_file"] = lambda *_: None
    namespace["read_file"] = lambda *_: (b"changed" if events else material[0]["frame"])
    namespace["identity"] = lambda _: ()
    namespace["same_name"] = lambda *_: None
    namespace["sync"] = lambda *_: events.append("sync")
    with pytest.raises(ValueError):
        namespace["stage"]()
    assert "terminal" not in events


def test_stage_late_same_content_metadata_drift_cannot_publish_success(material, monkeypatch):
    namespace = remote(material, monkeypatch, "stage")
    state = {"metadata": 0, "reads": 0}
    info = SimpleNamespace(st_uid=500, st_gid=500, st_mode=stat.S_IFDIR | 0o700)
    namespace["runtime"] = lambda _: SimpleNamespace(pw_uid=500, pw_gid=500)
    namespace["sys"] = SimpleNamespace(stdin=io.BytesIO(material[0]["frame"]),
        stdout=SimpleNamespace(write=lambda _: pytest.fail("stale stage receipt published")))
    namespace["os"] = SimpleNamespace(mkdir=lambda *_: None, fstat=lambda _: info,
                                      fsync=lambda _: None, close=lambda _: None)
    namespace["chain"] = lambda *_: [("synthetic", 1, ())]
    namespace["guard"] = lambda _: None
    namespace["floor"] = lambda *_: None
    namespace["file_open"] = lambda *_: 2
    namespace["write_file"] = lambda *_: None

    def read(*_):
        state["reads"] += 1
        if state["reads"] == 2:
            state["metadata"] = 1
        return material[0]["frame"]

    namespace["read_file"] = read
    namespace["identity"] = lambda _: state["metadata"]
    namespace["same_name"] = lambda *_: None
    namespace["sync"] = lambda *_: None
    with pytest.raises(ValueError):
        namespace["stage"]()


@pytest.mark.parametrize("drift", ["none", "bytes", "metadata", "deadline", "close_deadline"])
def test_apply_final_sync_revalidates_entire_terminal_union(material, monkeypatch, drift):
    namespace = remote(material, monkeypatch)
    raw = material[0]["frame"]
    state = {"syncs": 0, "metadata": 0, "buffers": {11: raw}, "now": 100}
    output = io.StringIO()
    floors = []
    files = iter((11, 12, 13, 14))

    def info(fd):
        owner = 500 if fd == 100 else 0
        return SimpleNamespace(st_uid=owner, st_gid=owner, st_mode=stat.S_IFDIR | 0o700,
                               marker=(fd, state["metadata"] if fd == 13 else 0))

    def capture(*args):
        assert args[-1] == 100 + namespace["CONFIG"]["apply_bootstrap_seconds"]
        assert state["now"] == 200
        state["buffers"].update({13: b"retained stdout\n", 14: b"retained stderr\n"})
        return True

    def sync(*_):
        state["syncs"] += 1
        if state["syncs"] == 2:
            if drift == "bytes":
                state["buffers"][13] = b"late output replacement\n"
            elif drift == "metadata":
                state["metadata"] = 1
            elif drift == "deadline":
                state["now"] = 100 + namespace["CONFIG"]["apply_bootstrap_seconds"]

    def runtime(_):
        state["now"] = 200
        return SimpleNamespace(pw_uid=500, pw_gid=500)

    namespace["runtime"] = runtime
    namespace["sys"] = SimpleNamespace(stdout=output)
    namespace["os"] = SimpleNamespace(isatty=lambda _: True, umask=lambda _: None,
        mkdir=lambda *_: None, fstat=info, fsync=lambda _: None,
        close=lambda _: state.update(now=100 + namespace["CONFIG"]["apply_bootstrap_seconds"])
        if drift == "close_deadline" else None,
        times=lambda: (0, 0, 0, 0, state["now"]))
    namespace["chain"] = lambda path, _: [(path, 100 if path == material[0]["stage_path"]
                                          else 101, ())]
    namespace["floor"] = lambda *args: floors.append(args)
    namespace["file_open"] = lambda *_: next(files)
    namespace["read_file"] = lambda _path, fd, _limit: state["buffers"].get(fd, b"")
    namespace["write_file"] = lambda fd, content: state["buffers"].__setitem__(fd, content)
    namespace["identity"] = lambda value: value.marker
    namespace["same_name"] = lambda *_: None
    namespace["guard"] = lambda _: None
    namespace["sync"] = sync
    namespace["capture"] = capture
    namespace["apply"]()
    code, stdout, stderr = initializer.parse_tty_terminal(output.getvalue().encode("ascii"),
                                                        material[0])
    assert code == (0 if drift == "none" else 1)
    assert stdout == b"retained stdout\n" and stderr == b"retained stderr\n"
    limits = material[0]["limits"]
    receipt = limits["observed_plan_receipt_bytes"]
    assert floors == [
        (namespace["CONFIG"]["managed_root"], [receipt], 65_536),
        ("/root", [len(raw), limits["stdout_bytes"], limits["stderr_bytes"], receipt], 65_536),
    ]
