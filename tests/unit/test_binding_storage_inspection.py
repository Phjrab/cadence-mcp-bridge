"""Portable contract/bound tests and optional Linux owned-file read guards."""

import ast
import errno
import importlib.util
import io
import json
import os
import posixpath
import stat
import subprocess
import sys
import types
from importlib.resources import files
from pathlib import Path

import pytest

SOURCE = Path(str(files("cadence_mcp_bridge").joinpath("_binding_storage_inspection.py")))
spec = importlib.util.spec_from_file_location("storage_prereq_draft", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def inspection_request():
    profile = dict(
        schema_version=1,
        environment_id="synthetic-env",
        ssh_alias="synthetic-vm",
        host=dict(
            hostname="synthetic",
            user="operator",
            os="Linux",
            architecture="i686",
            python_version="2.6.6",
        ),
        paths=dict(
            workspace_root="/home/operator/work",
            managed_root="/home/operator/work/.cadence_mcp",
            job_root="/home/operator/work/.cadence_mcp/jobs",
            result_root="/home/operator/work/.cadence_mcp/results",
            protected_roots=["/synthetic-vendor"],
        ),
        tools=dict(
            (name, dict(path="/synthetic-vendor/" + name, sha256="a" * 64, version="synthetic"))
            for name in ("virtuoso", "ocean", "spectre")
        ),
        limits=dict(
            disk_floor_bytes=2147483648,
            disk_floor_percent=10,
            spectre_attempts=500,
            result_reserved_bytes=17179869184,
            eda_concurrency=1,
            paid_resources=0,
        ),
        requested_capabilities=["dc"],
    )
    return dict(
        schema_version=1,
        kind="FIXED_STORAGE_PREREQUISITE_INSPECTION",
        profile=profile,
        profile_canonical_sha256=probe.digest(probe.canonical(profile)),
        resource_domain_sha256=probe.digest(
            probe.canonical(dict(hostname="synthetic", architecture="i686"))
        ),
        identity_manifest_sha256="b" * 64,
    )


@pytest.mark.parametrize(
    "change",
    [
        "valid",
        "extra",
        "pretty",
        "profile-pin",
        "domain-pin",
        "identity-pin",
        "nonhome",
        "managed-alias",
        "oversize",
    ],
)
def test_closed_request_never_accepts_remote_path_or_command_choices(inspection_request, change):
    if change == "extra":
        inspection_request["command"] = "arbitrary"
    elif change in ("profile-pin", "domain-pin", "identity-pin"):
        inspection_request[
            {
                "profile-pin": "profile_canonical_sha256",
                "domain-pin": "resource_domain_sha256",
                "identity-pin": "identity_manifest_sha256",
            }[change]
        ] = "wrong"
    elif change in ("nonhome", "managed-alias"):
        replacement = "/tmp/work" if change == "nonhome" else "/home/operator/work/../other"
        inspection_request["profile"]["paths"]["workspace_root"] = replacement
        for name, suffix in (
            ("managed_root", ""),
            ("job_root", "/jobs"),
            ("result_root", "/results"),
        ):
            inspection_request["profile"]["paths"][name] = replacement + "/.cadence_mcp" + suffix
        inspection_request["profile_canonical_sha256"] = probe.digest(
            probe.canonical(inspection_request["profile"])
        )
    raw = (
        json.dumps(inspection_request, indent=2).encode()
        if change == "pretty"
        else probe.canonical(inspection_request)
    )
    if change == "oversize":
        raw += b" " * probe.INPUT_BYTES
    if change == "valid":
        assert probe.parse_request(raw) == inspection_request
    else:
        with pytest.raises(ValueError):
            probe.parse_request(raw)


def test_path_budget_counts_missing_candidates_and_deadline_and_output_are_finite(
    inspection_request, monkeypatch
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    monkeypatch.setattr(probe, "MAX_PATHS", 3)
    monkeypatch.setattr(inspector, "opened", lambda *args: 97)
    monkeypatch.setattr(facade, "close", lambda fd: None)

    def missing(selected):
        raise OSError(errno.ENOENT, "private path must never be emitted")

    monkeypatch.setattr(probe.os, "lstat", missing)
    for name in ("one", "two", "three"):
        assert inspector.observe_path(name, "/" + name)["status"] == "MISSING"
    assert inspector.observe_path("four", "/four")["error_code"] == "inspected_path_bound"
    assert len(inspector.paths) == 3
    monkeypatch.setattr(probe.os, "times", lambda: (0, 0, 0, 0, inspector.deadline))
    with pytest.raises(ValueError, match="inspection_deadline"):
        inspector.check()
    with pytest.raises(ValueError, match="output_bound"):
        probe.bounded_result(dict(large="x" * probe.OUTPUT_BYTES))
    assert "private path" not in probe.canonical(inspector.records).decode()


@pytest.mark.parametrize("kind", ["empty", "entries", "infinite", "inaccessible"])
def test_stage_occupancy_is_bounded_closed_and_never_reads_existing_contents(
    inspection_request, monkeypatch, kind
):
    inspector = probe.Inspector(inspection_request)
    record = dict(status="OBSERVED", metadata=dict(mode=stat.S_IFDIR | 0o700))
    monkeypatch.setattr(inspector, "observe_path", lambda *a: record)
    consumed, closed = [], []

    def names(selected):
        try:
            if kind == "inaccessible":
                raise OSError(errno.EACCES, "denied")
            while kind == "infinite" or len(consumed) < (2 if kind == "entries" else 0):
                consumed.append(True)
                yield "private-retained-stage"
        finally:
            closed.append(True)

    monkeypatch.setattr(inspector, "names", names)
    monkeypatch.setattr(inspector, "read", lambda *a: pytest.fail("existing contents read"))
    if kind in ("infinite", "inaccessible"):
        with pytest.raises((ValueError, OSError)):
            inspector.stage()
    else:
        inspector.stage()
        assert record["entry_count"] == (2 if kind == "entries" else 0)
        assert record["empty"] is (kind == "empty")
    assert closed == [True] and len(consumed) <= 257


def test_loop_inventory_redacts_unrelated_associations_and_closes_at_bound(
    inspection_request, monkeypatch
):
    inspector = probe.Inspector(inspection_request)
    closed = []

    def names(selected):
        try:
            for index in range(1000):
                yield "loop" + str(index)
        finally:
            closed.append(True)

    monkeypatch.setattr(inspector, "names", names)
    monkeypatch.setattr(inspector, "observe_path", lambda *a: None)
    monkeypatch.setattr(inspector, "read", lambda *a: (b"/secret/other-user/private-image\n", {}))
    monkeypatch.setattr(probe, "MAX_LOOP_DEVICES", 2)
    with pytest.raises(ValueError, match="loop_inventory_bound"):
        inspector.loops()
    assert closed == [True]
    monkeypatch.setattr(probe, "MAX_LOOP_DEVICES", 1000)
    monkeypatch.setattr(inspector, "names", lambda p: (name for name in ("loop0", "loop1")))
    result = inspector.loops()
    assert all(
        row["association"] == "OTHER_REDACTED" and not row["available_for_use"] for row in result
    )
    assert "secret" not in probe.canonical(result).decode()


def test_kernel_mount_report_only_includes_selected_roles_and_redacts_other_paths(
    inspection_request, monkeypatch
):
    inspector = probe.Inspector(inspection_request)
    filesystems = b"nodev\tsysfs\n\text2\n\text4\n"
    mountinfo = (
        b"1 0 8:1 / / rw - ext4 /dev/private-root rw\n"
        b"2 1 7:1 / /unrelated/private-user rw - ext2 /secret/image rw\n"
    )
    monkeypatch.setattr(
        inspector,
        "read",
        lambda selected, *a: (filesystems if selected == "/proc/filesystems" else mountinfo, {}),
    )
    result = inspector.kernel()
    assert result["filesystems_listed"] == {"ext2": True, "ext3": False, "ext4": True}
    assert all(
        len(rows) == 1 and rows[0]["filesystem"] == "ext4"
        for rows in result["selected_mounts"].values()
    )
    assert "private" not in probe.canonical(result).decode()
    assert not result["persistent_backing_established"] and not result["loop_feasibility_assessed"]


def test_inspector_contains_no_system_execution_or_mutation_operations():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden = {
        "subprocess",
        "platform",
        "Popen",
        "popen",
        "system",
        "execv",
        "execve",
        "chmod",
        "chown",
        "mkdir",
        "unlink",
        "remove",
        "rename",
        "rmdir",
        "truncate",
        "ftruncate",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not ({item.name for item in node.names} & forbidden)
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", None))
            assert name not in forbidden
    # Internal os.open calls are only read-only, optionally directory/no-follow.
    assert "os.O_WRONLY" not in SOURCE.read_text() and "os.O_CREAT" not in SOURCE.read_text()


def synthetic_stat(mode=stat.S_IFREG | 0o755, inode=2):
    return os.stat_result((mode, inode, 1, 1, 0, 0, 24, 1, 2, 3))


def os_facade(monkeypatch):
    facade = types.ModuleType("synthetic_os")
    facade.__dict__.update(vars(os))
    facade.path = posixpath
    monkeypatch.setattr(probe, "os", facade)
    return facade


@pytest.mark.parametrize("kind", ["image", "device", "leaf-link"])
def test_metadata_only_leaf_uses_retained_parent_and_never_opens_special_node(
    inspection_request, monkeypatch, kind
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    selected = "/dev/loop0" if kind == "device" else "/var/lib/observer/retained.ext2"
    expected_parent = posixpath.dirname(selected)
    opened, inspected, closed = [], [], []

    def parent(selected_parent, directory):
        assert selected_parent == expected_parent and directory
        opened.append(selected_parent)
        return 97

    def observed(anchored):
        assert anchored == "/proc/self/fd/97/" + posixpath.basename(selected)
        inspected.append(anchored)
        mode = {"image": stat.S_IFREG, "device": stat.S_IFBLK, "leaf-link": stat.S_IFLNK}[kind]
        return synthetic_stat(mode | 0o600)

    monkeypatch.setattr(inspector, "opened", parent)
    monkeypatch.setattr(inspector, "guard", lambda: None)
    monkeypatch.setattr(facade, "lstat", observed)
    monkeypatch.setattr(facade, "open", lambda *args: pytest.fail("metadata leaf opened"))
    monkeypatch.setattr(facade, "close", lambda fd: closed.append(fd))
    row = inspector.observe_path(kind, selected)
    assert row["status"] == ("SYMLINK_OBSERVED_NOT_FOLLOWED" if kind == "leaf-link" else "OBSERVED")
    assert opened == [expected_parent] and len(inspected) == 1 and closed == [97]


@pytest.mark.parametrize("kind", ["image", "device"])
def test_metadata_only_leaf_rejects_ancestor_symlink_before_any_leaf_inspection(
    inspection_request, monkeypatch, kind
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    selected = "/dev/loop0" if kind == "device" else "/var/lib/observer/retained.ext2"

    def parent(selected_parent, directory):
        assert selected_parent == posixpath.dirname(selected) and directory
        raise ValueError("path_type_or_symlink_refused")

    monkeypatch.setattr(inspector, "opened", parent)
    monkeypatch.setattr(
        facade, "lstat", lambda *args: pytest.fail("escaped leaf metadata inspected")
    )
    monkeypatch.setattr(facade, "open", lambda *args: pytest.fail("special device opened"))
    row = inspector.observe_path(kind, selected)
    assert row["status"] == "INCOMPLETE" and row["error_code"] == "path_type_or_symlink_refused"


@pytest.mark.parametrize("change", ["valid", "escape", "readlink-drift", "loop"])
def test_binary_alias_is_fixed_root_bounded_and_rejects_drift_before_read(
    inspection_request, monkeypatch, change
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    symlink = synthetic_stat(stat.S_IFLNK | 0o777)
    ordinary = synthetic_stat()
    target = (
        "/home/private/secret"
        if change == "escape"
        else ("/bin/mount" if change == "loop" else "../usr/bin/mount")
    )

    def observed(selected):
        return (
            symlink
            if selected == "/bin/mount"
            else (
                ordinary if selected == "/usr/bin/mount" else synthetic_stat(stat.S_IFDIR | 0o755)
            )
        )

    links, closed = [], []

    def leaf(selected):
        assert selected == "/proc/self/fd/97/mount"
        return (
            synthetic_stat(stat.S_IFLNK | 0o777, inode=3)
            if (change == "readlink-drift" and links)
            else symlink
        )

    def link(selected):
        assert selected == "/proc/self/fd/97/mount"
        links.append(selected)
        return target

    def parent(selected, directory):
        assert selected == "/bin" and directory
        return 97

    monkeypatch.setattr(facade, "lstat", leaf)
    monkeypatch.setattr(inspector, "see", observed)
    monkeypatch.setattr(inspector, "opened", parent)
    monkeypatch.setattr(inspector, "guard", lambda: None)
    monkeypatch.setattr(facade, "readlink", link)
    monkeypatch.setattr(facade, "close", lambda fd: closed.append(fd))
    reads = []

    def read(selected, limit):
        reads.append((selected, limit))
        assert change == "valid" and selected == "/usr/bin/mount"
        return b"synthetic fixed binary", probe.metadata(ordinary)

    monkeypatch.setattr(inspector, "read", read)
    inspector.binary("mount-bin", "/bin/mount")
    row = inspector.records[-1]
    if change == "valid":
        assert row["status"] == "OBSERVED" and reads == [("/usr/bin/mount", probe.MAX_FILE_BYTES)]
        assert row["sha256"] == probe.digest(b"synthetic fixed binary")
        assert row["links"][0]["target_sha256"] == probe.digest(target.encode())
        assert not row["binary_executed"] and not row["dependency_trust_assessed"]
    else:
        assert not reads and row["status"] == "INCOMPLETE"
        assert (
            row["error_code"]
            == {
                "escape": "system_alias_escape",
                "readlink-drift": "link_metadata_drift",
                "loop": "system_alias_depth",
            }[change]
        )
    assert "private" not in probe.canonical(inspector.records).decode()
    assert len(closed) == len(links) == (9 if change == "loop" else 1)


def test_alias_transient_ancestor_swap_never_reads_outside_retained_parent_or_leaks_fd(
    inspection_request, monkeypatch
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    expected = synthetic_stat(stat.S_IFLNK | 0o777)
    swapped, reads, closed = [], [], []

    def parent(selected, directory):
        assert selected == "/bin" and directory
        swapped.append(True)
        return 97

    def observed(selected):
        assert selected == "/proc/self/fd/97/mount"
        return expected

    def link(selected):
        assert selected == "/proc/self/fd/97/mount", "absolute alias followed swapped ancestor"
        reads.append(selected)
        return "../usr/bin/mount"

    def guard():
        assert swapped
        raise ValueError("path_metadata_drift")

    monkeypatch.setattr(inspector, "opened", parent)
    monkeypatch.setattr(inspector, "guard", guard)
    monkeypatch.setattr(facade, "lstat", observed)
    monkeypatch.setattr(facade, "readlink", link)
    monkeypatch.setattr(facade, "close", lambda fd: closed.append(fd))
    with pytest.raises(ValueError, match="path_metadata_drift"):
        inspector.alias_target("/bin/mount", expected)
    assert reads == ["/proc/self/fd/97/mount"] and closed == [97]


@pytest.mark.parametrize("failure", ["none", "file-bound", "total-bound", "deadline", "drift"])
def test_read_always_closes_and_obeys_byte_deadline_and_metadata_bounds(
    inspection_request, monkeypatch, failure
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    monkeypatch.setattr(inspector, "opened", lambda selected: 97)
    closed, called, cursor = [], [], [0]

    def observed(fd):
        return synthetic_stat(inode=3 if failure == "drift" and called else 2)

    monkeypatch.setattr(facade, "fstat", observed)
    monkeypatch.setattr(facade, "close", lambda fd: closed.append(fd))

    def read(fd, amount):
        called.append(amount)
        raw = b"12345"[cursor[0] : cursor[0] + amount]
        cursor[0] += len(raw)
        return raw

    monkeypatch.setattr(facade, "read", read)
    monkeypatch.setattr(inspector, "guard", lambda: None)
    if failure == "total-bound":
        monkeypatch.setattr(probe, "MAX_HASH_BYTES", 4)
    if failure == "deadline":

        def expired():
            raise ValueError("inspection_deadline")

        monkeypatch.setattr(inspector, "check", expired)
    if failure == "none":
        raw, unused = inspector.read("/synthetic", 10)
        assert raw == b"12345"
    else:
        with pytest.raises(
            ValueError,
            match={
                "file-bound": "read_byte_bound",
                "total-bound": "read_byte_bound",
                "deadline": "inspection_deadline",
                "drift": "file_content_metadata_drift",
            }[failure],
        ):
            inspector.read("/synthetic", 4 if failure == "file-bound" else 10)
    assert closed == [97]
    if failure == "total-bound":
        assert called == [4] and inspector.hashed == 4


@pytest.mark.parametrize("initial, expected_sizes", [(6, []), (4, [2])])
def test_aggregate_budget_is_strict_even_at_exact_cap_and_does_not_probe_eof(
    inspection_request, monkeypatch, initial, expected_sizes
):
    facade = os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    inspector.hashed = initial
    monkeypatch.setattr(probe, "MAX_HASH_BYTES", 6)
    monkeypatch.setattr(inspector, "opened", lambda selected: 97)
    monkeypatch.setattr(facade, "fstat", lambda fd: synthetic_stat())
    calls, closed = [], []

    def read(fd, amount):
        calls.append(amount)
        assert amount <= 6 - inspector.hashed
        return b"x" * amount

    monkeypatch.setattr(facade, "read", read)
    monkeypatch.setattr(facade, "close", lambda fd: closed.append(fd))
    with pytest.raises(ValueError, match="read_byte_bound"):
        inspector.read("/synthetic", 10)
    assert calls == expected_sizes and inspector.hashed == 6 and closed == [97]


def test_directory_library_setup_failure_occurs_before_fd_is_opened(
    inspection_request, monkeypatch
):
    facade = os_facade(monkeypatch)
    facade.name = "posix"
    inspector = probe.Inspector(inspection_request)
    monkeypatch.setattr(
        inspector, "opened", lambda *a: pytest.fail("fd acquired before libc setup")
    )

    def unavailable(*args, **kwargs):
        raise OSError("synthetic unavailable library")

    monkeypatch.setitem(sys.modules, "ctypes", types.SimpleNamespace(CDLL=unavailable))
    with pytest.raises(OSError, match="synthetic unavailable library"):
        list(inspector.names("/sys/block"))


@pytest.mark.parametrize("change", ["valid", "pin", "legacy", "legacy-prior", "legacy-anchor"])
def test_identity_is_retained_canonical_anchor_not_a_ledger_reset(
    inspection_request, monkeypatch, change
):
    inspector = probe.Inspector(inspection_request)
    anchor = dict(
        root_sha256=probe.digest(inspector.root.encode()),
        resource_domain_sha256=inspection_request["resource_domain_sha256"],
        ledger_ref="sim-mcp-v2-jobs/counter.json",
        legacy_operation_ids=[],
    )
    expected = dict(anchor)
    seal = None
    if change.startswith("legacy"):
        expected["legacy_operation_ids"] = ["retained-operation"]
        seal = dict(
            schema_version=1,
            prior_anchor_sha256=probe.digest(probe.canonical(anchor)),
            anchor=expected,
            plan_sha256="c" * 64,
        )
        if change == "legacy-prior":
            seal["prior_anchor_sha256"] = "d" * 64
        elif change == "legacy-anchor":
            anchor["ledger_ref"] = "sim-mcp-v2-jobs/replaced.json"
            seal["prior_anchor_sha256"] = probe.digest(probe.canonical(anchor))
    inspection_request["identity_manifest_sha256"] = probe.digest(probe.canonical(expected))
    if change == "pin":
        inspection_request["identity_manifest_sha256"] = "b" * 64
    reads = []

    def retained(selected, limit):
        reads.append(selected)
        if selected.endswith("/legacy-seal.json"):
            if seal is None:
                raise OSError(errno.ENOENT, "missing")
            return probe.canonical(seal), {}
        assert selected.endswith("/manifest.json")
        return probe.canonical(anchor), {}

    monkeypatch.setattr(inspector, "read", retained)
    monkeypatch.setattr(inspector, "guard", lambda: None)
    if change in ("valid", "legacy"):
        inspector.identity()
    else:
        with pytest.raises(ValueError, match="identity_"):
            inspector.identity()
    assert len(reads) == 2 and all("counter.json" not in selected for selected in reads)


def test_profile_hash_is_explicitly_canonical_not_runtime_raw_file_hash(inspection_request):
    raw_profile = json.dumps(inspection_request["profile"], indent=2).encode()
    assert probe.digest(raw_profile) != inspection_request["profile_canonical_sha256"]
    inspection_request["profile_canonical_sha256"] = probe.digest(raw_profile)
    with pytest.raises(ValueError, match="profile_binding"):
        probe.parse_request(probe.canonical(inspection_request))


def test_bootstrap_total_deadline_cannot_be_reset_by_inspector(inspection_request, monkeypatch):
    monkeypatch.setattr(probe, "_FIXED_BOOTSTRAP_DEADLINE", probe.os.times()[4] - 1, raising=False)
    inspector = probe.Inspector(inspection_request)
    with pytest.raises(ValueError, match="inspection_deadline"):
        inspector.check()


def test_synthetic_run_records_exact_backing_image_without_qualification(
    inspection_request, monkeypatch
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getuid", lambda: 500, raising=False)
    monkeypatch.setattr(facade, "geteuid", lambda: 500, raising=False)
    monkeypatch.setattr(
        facade, "uname", lambda: ("Linux", "synthetic", "unused", "unused", "i686"), raising=False
    )
    system = types.ModuleType("synthetic_sys")
    system.__dict__.update(vars(sys))
    system.version_info = (2, 6, 6)
    monkeypatch.setattr(probe, "sys", system)
    monkeypatch.setitem(
        sys.modules,
        "pwd",
        types.SimpleNamespace(getpwuid=lambda unused: types.SimpleNamespace(pw_name="operator")),
    )
    inspector = probe.Inspector(inspection_request)
    observed = []
    monkeypatch.setattr(inspector, "identity", lambda: None)
    monkeypatch.setattr(inspector, "stage", lambda: None)
    monkeypatch.setattr(
        inspector, "observe_path", lambda role, selected: observed.append((role, selected))
    )
    monkeypatch.setattr(inspector, "binary", lambda *args: None)
    monkeypatch.setattr(inspector, "kernel", lambda: {})
    monkeypatch.setattr(inspector, "loops", lambda: [])
    monkeypatch.setattr(inspector, "guard", lambda: None)
    facts = inspector.run()
    assert observed[-1] == (
        "backing-image",
        probe.BACKING + "/" + inspection_request["resource_domain_sha256"] + ".ext2",
    )
    assert not facts["ready_for_apply"] and not facts["execution_authorized"]
    assert not facts["runtime_trust_assessed"] and not facts["acl_assessed"]
    assert (
        facts["intentional_remote_writes"]
        == facts["new_simulations"]
        == facts["reserved_bytes"]
        == 0
    )


@pytest.mark.parametrize(
    "change", ["valid", "tamper", "truncated", "args", "not-isolated", "no-bytecode-flag"]
)
def test_exact_in_memory_bootstrap_uses_pinned_source_and_no_file_or_cwd_imports(tmp_path, change):
    bootstrap = SOURCE.with_name("_binding_storage_bootstrap.py").read_text(encoding="utf-8")
    source = SOURCE.read_bytes()
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(bootstrap).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("SOURCE_")
    }
    assert assignments["SOURCE_BYTES"] == len(source)
    assert assignments["SOURCE_SHA256"] == probe.digest(source)
    assert assignments["SOURCE_NAME"] == "<cadence-storage-prerequisite-readonly>"
    # Neither CWD nor PYTHONPATH may supply modules to the isolated memory entry.
    for name in ("json", "platform", "hashlib"):
        (tmp_path / (name + ".py")).write_text("raise RuntimeError('UNTRUSTED_CWD_MODULE')\n")
    frame = source + b"{}"
    if change == "tamper":
        frame = b"X" + frame[1:]
    elif change == "truncated":
        frame = source[:-1]
    flags = [] if change == "not-isolated" else ["-E", "-s"]
    if change != "no-bytecode-flag":
        flags.append("-B")
    command = [sys.executable] + flags + ["-c", bootstrap]
    if change == "args":
        command.append("arbitrary-path")
    environment = dict(os.environ, PYTHONPATH=str(tmp_path))
    result = subprocess.run(
        command,
        input=frame,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert b"UNTRUSTED_CWD_MODULE" not in result.stdout + result.stderr
    if change in ("not-isolated", "no-bytecode-flag"):
        assert result.returncode == 1 and not result.stdout
        assert result.stderr.strip() == b"STORAGE_INSPECTOR_ISOLATED_PYTHON_REQUIRED"
    else:
        assert result.returncode == 0 and result.stderr == b""
        observed = json.loads(result.stdout)
        assert observed["status"] == "INCOMPLETE" and not observed["ready_for_apply"]
        assert not observed["execution_authorized"]
        expected = (
            "inspector_source_binding"
            if change in ("tamper", "truncated")
            else (
                "no_command_or_path_arguments"
                if change == "args"
                else (
                    "closed_shape"
                    if hasattr(probe.signal, "SIGALRM")
                    else "ordinary_standard_linux_required"
                )
            )
        )
        assert observed["error_code"] == expected
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "hashlib.py",
        "json.py",
        "platform.py",
    ]


def test_bootstrap_normal_import_is_inert_with_no_input_os_or_path_effects(monkeypatch):
    target = SOURCE.with_name("_binding_storage_bootstrap.py")
    selected = importlib.util.spec_from_file_location("synthetic_inert_bootstrap", target)
    module = importlib.util.module_from_spec(selected)
    before = list(sys.path)

    def forbidden(*args, **kwargs):
        pytest.fail("normal import attempted an entry-only side effect")

    monkeypatch.setattr(
        sys,
        "stdin",
        types.SimpleNamespace(read=forbidden, buffer=types.SimpleNamespace(read=forbidden)),
    )
    monkeypatch.setattr(sys, "exit", forbidden)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for name in ("getcwd", "chdir", "open", "system"):
        monkeypatch.setattr(os, name, forbidden)
    selected.loader.exec_module(module)
    assert sys.path == before and probe.digest(SOURCE.read_bytes()) == module.SOURCE_SHA256


@pytest.mark.skipif(sys.platform != "linux", reason="ordinary Linux retained dirfd fixture")
@pytest.mark.parametrize("change", ["unchanged", "symlink", "ancestor-link", "replace-during-read"])
def test_actual_owned_file_reads_reject_links_and_races_without_mutation(
    tmp_path, inspection_request, monkeypatch, change
):
    inspector = probe.Inspector(inspection_request)
    parent = tmp_path / "owned"
    parent.mkdir(mode=0o700)
    leaf = parent / "binary"
    leaf.write_bytes(b"synthetic fixture bytes")
    before = leaf.read_bytes()
    if change == "symlink":
        alias = parent / "alias"
        alias.symlink_to(leaf)
        with pytest.raises(ValueError, match="path_type_or_symlink_refused"):
            inspector.read(str(alias), 1024)
    elif change == "ancestor-link":
        alias = tmp_path / "alias-parent"
        alias.symlink_to(parent, target_is_directory=True)
        with pytest.raises(ValueError, match="path_type_or_symlink_refused"):
            inspector.read(str(alias / "binary"), 1024)
    elif change == "replace-during-read":
        real_read, once = probe.os.read, []

        def replaced(fd, amount):
            data = real_read(fd, amount)
            if not once:
                once.append(True)
                saved = parent / "retained-original"
                leaf.rename(saved)
                leaf.write_bytes(before)
            return data

        monkeypatch.setattr(probe.os, "read", replaced)
        with pytest.raises(ValueError, match="drift"):
            inspector.read(str(leaf), 1024)
        assert (parent / "retained-original").read_bytes() == before
    else:
        raw, observed = inspector.read(str(leaf), 1024)
        assert raw == before and observed["inode"] == leaf.stat().st_ino
        assert sorted(path.name for path in parent.iterdir()) == ["binary"]
    assert leaf.read_bytes() == before


@pytest.mark.parametrize(
    "selected, magic",
    [
        ("/proc", 0x9FA0),
        ("/proc/321", 0x9FA0),
        ("/sys", 0x62656572),
        ("/sys/block", 0x62656572),
        ("/sys/devices", 0x62656572),
        ("/sys/devices/virtual", 0x62656572),
        ("/sys/devices/virtual/block", 0x62656572),
        ("/sys/devices/virtual/block/loop0", 0x62656572),
        ("/sys/devices/virtual/block/loop999/loop", 0x62656572),
    ],
)
@pytest.mark.parametrize("field", ["nlink", "size", "mtime", "ctime"])
def test_only_proven_closed_kernel_directories_allow_volatile_metadata(
    inspection_request, monkeypatch, selected, magic, field
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    inspector = probe.Inspector(inspection_request)
    expected = probe.metadata(synthetic_stat(stat.S_IFDIR | 0o555))
    actual = dict(expected, **{field: "changed" if field in ("mtime", "ctime") else 77})
    assert not inspector.metadata_equal(selected, expected, actual)
    inspector.kernel_directories[selected] = magic
    assert inspector.metadata_equal(selected, expected, actual)
    assert expected[field] != actual[field], "observed metadata must remain unmodified"


@pytest.mark.parametrize(
    "selected, magic",
    [
        ("/home/operator/vendor", 0x9FA0),
        ("/var/lib/cadence-mcp-bridge", 0x62656572),
        ("/proc/self", 0x9FA0),
        ("/proc/322", 0x9FA0),
        ("/proc/321/fd", 0x9FA0),
        ("/sys/devices/other", 0x62656572),
        ("/sys/devices/virtual/block/loop1000", 0x62656572),
        ("/sys/devices/virtual/block/loop0/loop/other", 0x62656572),
        ("/proc", 0x62656572),
        ("/sys", 0x9FA0),
    ],
)
def test_kernel_exception_never_spreads_to_static_paths_other_processes_or_wrong_filesystems(
    inspection_request, monkeypatch, selected, magic
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    inspector = probe.Inspector(inspection_request)
    inspector.kernel_directories[selected] = magic
    expected = probe.metadata(synthetic_stat(stat.S_IFDIR | 0o555))
    for field in ("nlink", "size", "mtime", "ctime"):
        actual = dict(expected, **{field: "changed" if field in ("mtime", "ctime") else 77})
        assert not inspector.metadata_equal(selected, expected, actual)


@pytest.mark.parametrize("field", ["device", "inode", "mode", "uid", "gid", "rdev"])
def test_proven_kernel_directory_retains_every_namespace_and_permission_guard(
    inspection_request, monkeypatch, field
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    inspector = probe.Inspector(inspection_request)
    inspector.kernel_directories["/proc"] = 0x9FA0
    expected = probe.metadata(synthetic_stat(stat.S_IFDIR | 0o555))
    actual = dict(expected, **{field: expected[field] + 1})
    assert not inspector.metadata_equal("/proc", expected, actual)
    assert inspector.failure_context["changed_fields"] == [field]


def test_kernel_directory_pin_is_not_a_regular_file_metadata_exception(
    inspection_request, monkeypatch
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    inspector = probe.Inspector(inspection_request)
    inspector.kernel_directories["/proc"] = 0x9FA0
    expected = probe.metadata(synthetic_stat(stat.S_IFREG | 0o555))
    assert not inspector.metadata_equal("/proc", expected, dict(expected, size=100))


@pytest.mark.parametrize("selected", ["/proc", "/proc/321", "/sys/block"])
@pytest.mark.parametrize("change", ["valid", "fs-type", "owner", "group-write", "type"])
def test_pin_requires_closed_kernel_path_exact_filesystem_and_safe_opened_directory(
    inspection_request, monkeypatch, selected, change
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    monkeypatch.setattr(facade, "getuid", lambda: 500, raising=False)
    inspector = probe.Inspector(inspection_request)
    mode = stat.S_IFDIR | 0o555
    if change == "group-write":
        mode |= stat.S_IWGRP
    elif change == "type":
        mode = stat.S_IFREG | 0o555
    info = types.SimpleNamespace(st_mode=mode, st_uid=123 if change == "owner" else 0)
    observed = []
    magic = 0x9FA0 if selected.startswith("/proc") else 0x62656572
    monkeypatch.setattr(facade, "fstat", lambda fd: info if fd == 97 else pytest.fail("wrong fd"))

    def filesystem(fd):
        assert fd == 97
        observed.append(fd)
        return 0xEF53 if change == "fs-type" else magic

    monkeypatch.setattr(probe, "kernel_filesystem_type", filesystem)
    if change == "valid":
        inspector.pin_kernel_directory(selected, 97)
        assert inspector.kernel_directories == {selected: magic} and observed == [97]
    else:
        with pytest.raises(ValueError, match="^kernel_directory_identity$"):
            inspector.pin_kernel_directory(selected, 97)
        assert inspector.kernel_directories == {}


@pytest.mark.parametrize("selected", ["/proc/321", "/proc", "/sys"])
def test_only_current_process_kernel_directory_can_be_owned_by_operator(
    inspection_request, monkeypatch, selected
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    monkeypatch.setattr(facade, "getuid", lambda: 500, raising=False)
    inspector = probe.Inspector(inspection_request)
    monkeypatch.setattr(
        facade, "fstat", lambda fd: types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o555, st_uid=500)
    )
    monkeypatch.setattr(probe, "kernel_filesystem_type", lambda fd: 0x9FA0)
    if selected == "/proc/321":
        inspector.pin_kernel_directory(selected, 97)
        assert inspector.kernel_directories == {selected: 0x9FA0}
    else:
        with pytest.raises(ValueError, match="^kernel_directory_identity$"):
            inspector.pin_kernel_directory(selected, 97)
        assert not inspector.kernel_directories


@pytest.mark.parametrize(
    "selected",
    ["/", "/tmp", "/proc/self", "/proc/322", "/sys/other", "/sys/block/loop0", "/sys/../sys"],
)
def test_unclosed_paths_never_trigger_kernel_filesystem_probe(
    inspection_request, monkeypatch, selected
):
    facade = os_facade(monkeypatch)
    monkeypatch.setattr(facade, "getpid", lambda: 321)
    inspector = probe.Inspector(inspection_request)
    monkeypatch.setattr(facade, "fstat", lambda fd: pytest.fail("unclosed directory inspected"))
    monkeypatch.setattr(
        probe, "kernel_filesystem_type", lambda fd: pytest.fail("unclosed filesystem probed")
    )
    inspector.pin_kernel_directory(selected, 97)
    assert inspector.kernel_directories == {}


def test_metadata_drift_provenance_is_bounded_hashed_and_retains_static_guard(
    inspection_request, monkeypatch
):
    os_facade(monkeypatch)
    inspector = probe.Inspector(inspection_request)
    inspector.phase = "binaries"
    selected = "/private/operator/" + "secret" * 1000
    expected = probe.metadata(synthetic_stat())
    actual = dict(expected, size=25, inode=3)
    assert not inspector.metadata_equal(selected, expected, actual)
    assert inspector.failure_context == {
        "phase": "binaries",
        "path_sha256": probe.digest(selected.encode("ascii")),
        "changed_fields": ["inode", "size"],
    }
    record = inspector.record_error("mount-bin", ValueError("path_metadata_drift"))
    assert record["status"] == "INCOMPLETE"
    assert record["error_context"] == inspector.failure_context
    raw = probe.canonical(record)
    assert len(raw) < 1024 and b"secret" not in raw and b"/private" not in raw


def test_main_preserves_bounded_drift_context_without_authorizing_or_claiming_success(
    inspection_request, monkeypatch
):
    inspector = probe.Inspector(inspection_request)
    inspector.phase = "final"
    expected = probe.metadata(synthetic_stat())

    def incomplete():
        assert not inspector.metadata_equal(
            "/private/static-file", expected, dict(expected, size=99),
        )
        raise ValueError("path_metadata_drift")

    monkeypatch.setattr(inspector, "run", incomplete)
    monkeypatch.setattr(probe, "Inspector", lambda request: inspector)
    monkeypatch.setattr(probe, "parse_request", lambda raw: inspection_request)
    monkeypatch.setattr(probe, "_FIXED_BOOTSTRAP_ACTIVE", True, raising=False)
    monkeypatch.setattr(probe, "signal", types.SimpleNamespace(SIGALRM=14))
    output = io.BytesIO()
    monkeypatch.setattr(
        probe,
        "sys",
        types.SimpleNamespace(argv=["fixed-inspector"], stdin=io.BytesIO(b"{}"), stdout=output),
    )
    probe.main()
    result = json.loads(output.getvalue())
    assert result["status"] == "INCOMPLETE" and result["error_code"] == "path_metadata_drift"
    assert not result["ready_for_apply"] and not result["execution_authorized"]
    assert result["error_context"] == inspector.failure_context
    assert b"/private" not in output.getvalue() and len(output.getvalue()) < 1024


@pytest.mark.skipif(sys.platform != "linux", reason="local Linux kernel directory and owned child")
def test_actual_local_proc_guard_survives_owned_child_churn_without_relaxing_static_files(
    inspection_request,
):
    import select

    inspector = probe.Inspector(inspection_request)
    before = probe.metadata(os.lstat("/proc"))
    fd = inspector.opened("/proc", True)
    try:
        assert inspector.kernel_directories["/proc"] == 0x9FA0
        assert inspector.seen["/proc"]["inode"] == before["inode"]
        # This is a disposable local Python child, never Cadence or an SSH process.
        child = subprocess.Popen(
            [sys.executable, "-E", "-s", "-B", "-c", "import sys; sys.stdout.write('R'); "
             "sys.stdout.flush(); sys.stdin.buffer.read(1)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert select.select([child.stdout], [], [], 10)[0], "owned child did not become ready"
            assert child.stdout.read(1) == b"R"
            assert os.path.isdir("/proc/" + str(child.pid))
            inspector.guard()
            child.stdin.write(b"X")
            child.stdin.flush()
            out, error = child.communicate(timeout=10)
            assert child.returncode == 0 and out == error == b""
            inspector.guard()
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
    finally:
        os.close(fd)
    assert inspector.hashed == 0 and inspector.records == []


@pytest.mark.skipif(sys.platform != "linux", reason="local Linux retained static metadata")
def test_actual_static_directory_volatile_metadata_is_still_exact(
    inspection_request, tmp_path,
):
    parent = tmp_path / "static-installation-fixture"
    parent.mkdir(mode=0o700)
    inspector = probe.Inspector(inspection_request)
    fd = inspector.opened(str(parent), True)
    try:
        assert str(parent) not in inspector.kernel_directories
        before = parent.stat()
        os.utime(parent, (before.st_atime, before.st_mtime + 2))
        with pytest.raises(ValueError, match="^path_metadata_drift$"):
            inspector.guard()
        assert inspector.failure_context["path_sha256"] == probe.digest(str(parent).encode("ascii"))
        assert "mtime" in inspector.failure_context["changed_fields"]
    finally:
        os.close(fd)
