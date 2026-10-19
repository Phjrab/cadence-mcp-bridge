"""Disposable helper pieces; no actual VM, Cadence, authority or source deployment."""

import copy
import errno
import json
import os
import platform
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_shared_reservations import root

from cadence_mcp_bridge import _binding_observation as observer
from cadence_mcp_bridge import _native_copy as copying
from cadence_mcp_bridge import _physical_metadata as physical

__all__ = ["root"]


def assets():
    base = Path(observer.__file__).parent
    return {
        name: (base / source).read_bytes().replace(b"\r\n", b"\n")
        for name, source in (
            ("copy.py", "_native_copy.py"),
            ("reservations.py", "_shared_reservations.py"),
            ("process.py", "_native_eda_worker.py"),
        )
    }


@pytest.fixture
def selected(tmp_path, root):
    source = tmp_path / "source" / "Cell"
    state = tmp_path / "state"
    source.mkdir(mode=0o700, parents=True)
    state.mkdir(mode=0o700)
    (source / "sch.oa").write_bytes(b"synthetic OA placeholder")
    (state / "ADE_state.info").write_bytes(b"synthetic state placeholder")
    scan = dict(
        schema_version=1, observation_id=str(uuid4()), nonce="a" * 64,
        library="Synthetic", cell="Cell", view="schematic",
        variables=[dict(logical_id="input-plus", cadence_binding="qa_vp")],
    )
    profile = dict(
        paths=dict(managed_root=str(root), protected_roots=[str(tmp_path)]),
        host=dict(hostname=platform.node(), architecture=platform.machine(),
                  os=platform.system(), python_version=platform.python_version(),
                  user="synthetic"),
        limits=dict(disk_floor_bytes=0, disk_floor_percent=0),
        tools=dict(ocean=dict(path=str(tmp_path / "ocean"), sha256="f" * 64)),
    )
    if os.name == "posix":
        import pwd

        profile["host"]["user"] = pwd.getpwuid(os.getuid()).pw_name
    profile_raw = observer.canonical(profile)
    route = dict(
        design_id="synthetic", analysis_id="synthetic-dc",
        profile=dict(binding=dict(library="Synthetic", cell="Cell", view="schematic")),
        source_cell=str(source), source_state=str(state), variables=scan["variables"],
        libraries=[dict(name="Synthetic", path=str(source.parent),
                        tree_sha256=copying.dependency_snapshot(str(source.parent))["tree_sha256"])],
        ade=dict(source_tree_sha256=copying.snapshot(str(source))["tree_sha256"],
                 ade_state_tree_sha256=copying.snapshot(str(state))["tree_sha256"]),
    )
    registration_raw = observer.canonical(dict(
        environment_sha256=observer.digest(profile_raw), routes=[route],
    ))
    selection = dict(
        schema_version=1, design_id="synthetic", analysis_id="synthetic-dc",
        profile_sha256=observer.digest(profile_raw),
        registration_sha256=observer.digest(registration_raw),
        request_sha256=observer.digest(observer.canonical(scan)),
        collector_sha256=observer.digest(observer.render_collector(scan)),
        helper_sha256=observer.digest(Path(observer.__file__).read_bytes().replace(b"\r\n", b"\n")),
    )
    worker = observer.BindingObservationWorker(
        profile_raw, registration_raw, selection, assets(), observer.HELPER_PINS,
    )
    return worker, scan, (profile_raw, registration_raw, selection)


@pytest.fixture
def controlled_inventory(selected, monkeypatch):
    # Only the external conflicting-work inventory is synthetic. The dedicated
    # child's /proc identity, group ownership and termination remain real.
    worker, _, _ = selected
    monkeypatch.setattr(worker, "_check_conflicting_processes", lambda: None)


def declared_manifest(worker, members, metadata):
    """Explicit synthetic baseline; never an operational approval or discovery."""
    directories = set()
    for member in members:
        current = member["path"].rsplit("/", 1)[0] or "/"
        while True:
            directories.add(current)
            if current == "/":
                break
            current = current.rsplit("/", 1)[0] or "/"
    return dict(
        schema_version=1, scope="DECLARED_MEMBERS_ONLY",
        profile_sha256=worker.selection["profile_sha256"],
        registration_sha256=worker.selection["registration_sha256"],
        worker_sha256=worker.selection["helper_sha256"],
        request_sha256=worker.selection["request_sha256"],
        members=sorted(members, key=lambda value: value["path"]),
        directories=[dict(path=path, metadata=metadata(path)) for path in sorted(directories)],
    )


def rebind_declared_documents(worker):
    worker.selection["profile_sha256"] = observer.digest(observer.canonical(worker.profile))
    worker.registration["environment_sha256"] = worker.selection["profile_sha256"]
    worker.selection["registration_sha256"] = observer.digest(
        observer.canonical(worker.registration),
    )


@pytest.fixture
def declared_case(selected):
    worker, _, _ = selected
    worker.profile["paths"]["protected_roots"] = ["/synthetic-runtime"]
    worker.profile["tools"]["ocean"] = dict(
        path="/synthetic-runtime/ocean", sha256="a" * 64,
    )
    worker.route["libraries"] = [dict(
        name="Synthetic", path="/synthetic-library", tree_sha256="b" * 64,
    )]
    rebind_declared_documents(worker)
    info = dict(device=1, inode=2, mode=stat.S_IFREG | 0o500, uid=0, gid=0,
                nlink=1, size=8, mtime="100", ctime="100")
    members = [
        dict(role="runtime", path="/synthetic-runtime/ocean", sha256="a" * 64,
             metadata=dict(info)),
        dict(role="library_init", path="/synthetic-library/libInit.il", sha256="b" * 64,
             metadata=dict(info)),
    ]
    manifest = declared_manifest(worker, members, lambda _: {
        **info, "mode": stat.S_IFDIR | 0o700, "nlink": 2,
    })
    return worker, manifest


@pytest.fixture
def declared_real_case(selected, tmp_path):
    if os.name != "posix" or sys.platform != "linux" or os.getuid() == 0:
        pytest.skip("ordinary Linux no-follow file inspection")
    worker, request, _ = selected
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    ocean = runtime / "ocean"
    ocean.write_bytes(b"synthetic executable placeholder; never executed\n")
    ocean.chmod(0o700)
    dependency = runtime / "runtime-library"
    dependency.write_bytes(b"synthetic runtime library\n")
    dependency.chmod(0o600)
    library = Path(worker.route["libraries"][0]["path"])
    init = library / "libInit.il"
    init.write_bytes(b"synthetic init placeholder; never evaluated\n")
    init.chmod(0o600)
    worker.profile["tools"]["ocean"] = dict(
        path=str(ocean), sha256=observer.digest(ocean.read_bytes()),
    )
    rebind_declared_documents(worker)
    members = [dict(
        role=role, path=str(path), sha256=observer.digest(path.read_bytes()),
        metadata=physical.metadata(path.lstat()),
    ) for role, path in (("runtime", ocean), ("runtime", dependency), ("library_init", init))]
    manifest = declared_manifest(worker, members, lambda path: physical.metadata(os.lstat(path)))
    return worker, request, manifest, ocean, dependency, init


def check_declared(worker, manifest):
    raw = observer.canonical(manifest)
    return worker._declared_code_members(raw, observer.digest(raw))


@pytest.mark.parametrize("change", [
    "version-bool", "scope", "extra", "profile", "registration", "worker", "request",
    "empty-members", "too-many-members", "too-many-directories", "member-extra", "role",
    "file-bool", "file-negative", "file-overflow", "file-hardlink", "file-special",
    "file-size", "file-mode", "time-nan", "time-noncanonical", "time-number", "digest",
    "path-relative", "path-dot", "path-parent", "path-empty", "path-newline",
    "path-unicode", "path-overlong", "path-depth", "path-role-root", "init-role-root",
    "members-unsorted", "member-duplicate", "directory-duplicate", "directory-unsorted",
    "directory-missing", "directory-extra", "directory-file-alias", "directory-type",
    "directory-mode", "metadata-extra", "directory-metadata-extra", "missing-ocean",
    "decoded-profile-drift", "decoded-registration-drift",
])
def test_declared_members_reject_invalid_complete_manifest_before_fs(
    declared_case, monkeypatch, change,
):
    worker, manifest = declared_case
    runtime = next(item for item in manifest["members"] if item["role"] == "runtime")
    init = next(item for item in manifest["members"] if item["role"] == "library_init")
    if change == "version-bool":
        manifest["schema_version"] = True
    elif change == "scope":
        manifest["scope"] = "COMPLETE_CLOSURE"
    elif change == "extra":
        manifest["approved"] = True
    elif change in ("profile", "registration", "worker", "request"):
        manifest[change + "_sha256"] = "f" * 64
    elif change == "empty-members":
        manifest["members"] = []
    elif change == "too-many-members":
        manifest["members"] *= 65
    elif change == "too-many-directories":
        manifest["directories"] *= 342
    elif change == "member-extra":
        runtime["command"] = "untrusted"
    elif change == "role":
        runtime["role"] = "loader-complete"
    elif change == "file-bool":
        runtime["metadata"]["size"] = False
    elif change == "file-negative":
        runtime["metadata"]["uid"] = -1
    elif change == "file-overflow":
        runtime["metadata"]["inode"] = 2**63
    elif change == "file-hardlink":
        runtime["metadata"]["nlink"] = 2
    elif change == "file-special":
        runtime["metadata"]["mode"] = stat.S_IFIFO | 0o600
    elif change == "file-size":
        runtime["metadata"]["size"] = 16 * 1024**2 + 1
    elif change == "file-mode":
        runtime["metadata"]["mode"] |= 0o020
    elif change.startswith("time-"):
        runtime["metadata"]["ctime"] = {
            "time-nan": "nan", "time-noncanonical": "100.0", "time-number": 100,
        }[change]
    elif change == "digest":
        runtime["sha256"] = "A" * 64
    elif change.startswith("path-"):
        runtime["path"] = {
            "path-relative": "synthetic-runtime/ocean", "path-dot": "/synthetic-runtime/./ocean",
            "path-parent": "/synthetic-runtime/../ocean", "path-empty": "/synthetic-runtime//ocean",
            "path-newline": "/synthetic-runtime/ocean\n", "path-unicode": "/synthetic-runtime/회로",
            "path-overlong": "/" + "x" * 512, "path-depth": "/" + "/".join(["x"] * 65),
            "path-role-root": "/unregistered/ocean",
        }[change]
    elif change == "init-role-root":
        init["path"] = "/unregistered/libInit.il"
    elif change == "members-unsorted":
        manifest["members"].reverse()
    elif change == "member-duplicate":
        manifest["members"].append(copy.deepcopy(runtime))
    elif change == "directory-duplicate":
        manifest["directories"].append(copy.deepcopy(manifest["directories"][-1]))
    elif change == "directory-unsorted":
        manifest["directories"].reverse()
    elif change == "directory-missing":
        manifest["directories"].pop(0)
    elif change == "directory-extra":
        manifest["directories"].append(dict(
            path="/zzz", metadata=copy.deepcopy(manifest["directories"][0]["metadata"]),
        ))
    elif change == "directory-file-alias":
        manifest["directories"].append(dict(
            path=runtime["path"], metadata=copy.deepcopy(manifest["directories"][0]["metadata"]),
        ))
    elif change == "directory-type":
        manifest["directories"][0]["metadata"]["mode"] = stat.S_IFREG | 0o700
    elif change == "directory-mode":
        manifest["directories"][0]["metadata"]["mode"] |= 0o002
    elif change == "metadata-extra":
        runtime["metadata"]["approved"] = True
    elif change == "directory-metadata-extra":
        manifest["directories"][0]["metadata"]["approved"] = True
    elif change == "missing-ocean":
        manifest["members"] = [init]
    elif change == "decoded-profile-drift":
        worker.profile["tools"]["ocean"]["sha256"] = "f" * 64
    elif change == "decoded-registration-drift":
        worker.route["libraries"][0]["path"] = "/changed"
    else:
        pytest.fail(change)
    monkeypatch.setattr(observer.os, "open", lambda *a, **k: pytest.fail("filesystem opened"))
    monkeypatch.setattr(observer.os, "lstat", lambda *a, **k: pytest.fail("filesystem observed"))
    monkeypatch.setattr(worker, "_ocean_trust", lambda: pytest.fail("OCEAN read before validation"))
    reason = {
        "version-bool": "declared_manifest_shape", "scope": "declared_manifest_shape",
        "extra": "declared_manifest_shape", "profile": "declared_manifest_binding",
        "registration": "declared_manifest_binding", "worker": "declared_manifest_binding",
        "request": "declared_manifest_binding", "empty-members": "declared_member_bound",
        "too-many-members": "declared_member_bound",
        "too-many-directories": "declared_member_bound",
        "member-extra": "declared_member_shape", "role": "declared_member_scope",
        "file-bool": "declared_metadata_integer", "file-negative": "declared_metadata_integer",
        "file-overflow": "declared_metadata_integer", "file-hardlink": "declared_metadata_trust",
        "file-special": "declared_metadata_trust", "file-size": "declared_metadata_trust",
        "file-mode": "declared_metadata_trust", "time-nan": "declared_metadata_time",
        "time-noncanonical": "declared_metadata_time", "time-number": "declared_metadata_time",
        "digest": "token", "path-relative": "token", "path-dot": "declared_path",
        "path-parent": "declared_path", "path-empty": "declared_path", "path-newline": "token",
        "path-unicode": "token", "path-overlong": "token", "path-depth": "declared_path",
        "path-role-root": "declared_member_scope", "init-role-root": "declared_member_scope",
        "members-unsorted": "declared_member_order", "member-duplicate": "declared_member_order",
        "directory-duplicate": "declared_directory_order",
        "directory-unsorted": "declared_directory_order",
        "directory-missing": "declared_ancestor_union",
        "directory-extra": "declared_ancestor_union",
        "directory-file-alias": "declared_ancestor_union",
        "directory-type": "declared_metadata_trust", "directory-mode": "declared_metadata_trust",
        "metadata-extra": "declared_metadata_shape",
        "directory-metadata-extra": "declared_metadata_shape",
        "missing-ocean": "declared_ancestor_union",
        "decoded-profile-drift": "declared_manifest_binding",
        "decoded-registration-drift": "declared_manifest_binding",
    }[change]
    with pytest.raises(ValueError, match="^binding_observation_" + reason + "$"):
        check_declared(worker, manifest)


@pytest.mark.parametrize("raw_kind", [
    "hash", "noncanonical", "duplicate", "nonfinite", "nonascii", "deep", "large", "type",
])
def test_declared_document_rejects_before_filesystem(declared_case, monkeypatch, raw_kind):
    worker, manifest = declared_case
    raw = observer.canonical(manifest)
    expected = observer.digest(raw)
    if raw_kind == "hash":
        expected = "f" * 64
    elif raw_kind == "noncanonical":
        raw += b"\n"
    elif raw_kind == "duplicate":
        raw = b'{"schema_version":1,"schema_version":1}'
    elif raw_kind == "nonfinite":
        raw = b'{"schema_version":NaN}'
    elif raw_kind == "nonascii":
        raw = b'{"x":"\xff"}'
    elif raw_kind == "deep":
        raw = b"[" * 2000 + b"0" + b"]" * 2000
    elif raw_kind == "large":
        raw = b" " * 262145
    else:
        raw = json.loads(raw)
    if raw_kind != "hash" and isinstance(raw, bytes):
        expected = observer.digest(raw)
    monkeypatch.setattr(observer.os, "open", lambda *a, **k: pytest.fail("filesystem opened"))
    monkeypatch.setattr(observer.os, "lstat", lambda *a, **k: pytest.fail("filesystem observed"))
    monkeypatch.setattr(worker, "_ocean_trust", lambda: pytest.fail("OCEAN observed"))
    reason = {
        "hash": "digest", "noncanonical": "json", "duplicate": "json", "nonfinite": "json",
        "nonascii": "json", "deep": "json", "large": "bound", "type": "bound",
    }[raw_kind]
    with pytest.raises(ValueError, match="^binding_observation_declared_manifest_" + reason + "$"):
        worker._declared_code_members(raw, expected)


def test_declared_member_aggregate_bound_is_checked_before_content(declared_case, monkeypatch):
    worker, manifest = declared_case
    runtime = next(item for item in manifest["members"] if item["role"] == "runtime")
    for index in range(5):
        item = copy.deepcopy(runtime)
        item["path"] = f"/synthetic-runtime/library-{index}"
        item["metadata"]["size"] = 16 * 1024**2
        manifest["members"].append(item)
    manifest["members"].sort(key=lambda item: item["path"])
    monkeypatch.setattr(observer.os, "open", lambda *a, **k: pytest.fail("filesystem opened"))
    monkeypatch.setattr(worker, "_ocean_trust", lambda: pytest.fail("OCEAN observed"))
    with pytest.raises(ValueError, match="^binding_observation_declared_content_bound$"):
        check_declared(worker, manifest)


def test_declared_valid_schema_reaches_platform_gate_without_io(declared_case, monkeypatch):
    worker, manifest = declared_case
    monkeypatch.setattr(observer.platform, "system", lambda: "UnqualifiedPlatform")
    monkeypatch.setattr(observer.os, "open", lambda *a, **k: pytest.fail("filesystem opened"))
    monkeypatch.setattr(worker, "_ocean_trust", lambda: pytest.fail("OCEAN observed"))
    with pytest.raises(
        ValueError, match="^binding_observation_declared_normal_linux_user_required$",
    ):
        check_declared(worker, manifest)


def test_declared_real_success_stays_unqualified_and_read_only(declared_real_case, monkeypatch):
    worker, request, manifest, ocean, dependency, init = declared_real_case
    before = {path: (path.read_bytes(), physical.metadata(path.lstat()))
              for path in (ocean, dependency, init)}
    ledger_before = worker._ledger()
    descriptors = set(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(
        observer.subprocess, "Popen", lambda *a, **k: pytest.fail("process started"),
    )
    result = check_declared(worker, manifest)
    assert result["scope"] == "DECLARED_MEMBERS_ONLY"
    assert result["status"] == "EXACT_MEMBER_INTEGRITY_VERIFIED"
    assert result["member_count"] == 3
    assert result["directory_count"] == len(manifest["directories"])
    assert result["content_bytes"] == sum(m["metadata"]["size"] for m in manifest["members"])
    assert all(result[key] == 0 for key in (
        "new_eda_starts", "new_simulations", "new_extractions", "new_reservations", "new_claims",
    ))
    assert result["qualified"] is False and result["closure_trust"] == "NOT_ESTABLISHED"
    assert result["execution_authorized"] is False
    assert before == {path: (path.read_bytes(), physical.metadata(path.lstat()))
                      for path in (ocean, dependency, init)}
    assert descriptors == set(os.listdir("/proc/self/fd"))
    assert ledger_before == worker._ledger()
    assert worker.observe(request)["status"] == "CAPABILITY_NOT_QUALIFIED"


@pytest.mark.parametrize("change", [
    "content", "restored-mtime", "inode", "mode", "owner-baseline", "ancestor-mode",
    "symlink", "ancestor-symlink", "hardlink", "fifo", "digest",
])
def test_declared_real_file_and_ancestor_drift_reject(
    declared_real_case, tmp_path, monkeypatch, change,
):
    worker, _, manifest, _, dependency, init = declared_real_case
    if change == "content":
        dependency.write_bytes(b"changed")
    elif change == "restored-mtime":
        before = dependency.stat()
        dependency.write_bytes(b"x" * before.st_size)
        os.utime(dependency, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == "inode":
        before = dependency.stat()
        replacement = tmp_path / "replacement"
        replacement.write_bytes(dependency.read_bytes())
        replacement.chmod(stat.S_IMODE(before.st_mode))
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        replacement.replace(dependency)
    elif change == "mode":
        dependency.chmod(0o620)
    elif change == "owner-baseline":
        manifest["members"][0]["metadata"]["uid"] = 2**31 - 1
    elif change == "ancestor-mode":
        dependency.parent.chmod(0o720)
    elif change == "symlink":
        dependency.unlink()
        dependency.symlink_to(init)
    elif change == "ancestor-symlink":
        previous = tmp_path / "runtime-held"
        dependency.parent.rename(previous)
        dependency.parent.symlink_to(previous, target_is_directory=True)
    elif change == "hardlink":
        os.link(dependency, tmp_path / "duplicate")
    elif change == "fifo":
        dependency.unlink()
        os.mkfifo(dependency, 0o600)
    else:
        next(m for m in manifest["members"] if m["path"] == str(dependency))["sha256"] = "f" * 64
    if change != "digest":
        monkeypatch.setattr(
            worker.copying, "read_leaf", lambda *a, **k: pytest.fail("content before metadata"),
        )
    descriptors = set(os.listdir("/proc/self/fd"))
    with pytest.raises((ValueError, OSError)):
        check_declared(worker, manifest)
    assert descriptors == set(os.listdir("/proc/self/fd"))


@pytest.mark.parametrize("drift", ["bytes-restored-mtime", "ancestor-mode", "inode"])
def test_declared_final_union_rechecks_earlier_members_after_last_content(
    declared_real_case, monkeypatch, tmp_path, drift,
):
    worker, _, manifest, ocean, _, _ = declared_real_case
    first = Path(manifest["members"][0]["path"])
    read = worker.copying.read_leaf
    calls = []
    ocean_reads = [0]

    def late_drift(path, expected, limit, *args, **kwargs):
        raw = read(path, expected, limit, *args, **kwargs)
        calls.append(path)
        if path == str(ocean):
            ocean_reads[0] += 1
            if ocean_reads[0] == 2:
                before = first.stat()
                if drift == "bytes-restored-mtime":
                    first.write_bytes(b"x" * before.st_size)
                    os.utime(first, ns=(before.st_atime_ns, before.st_mtime_ns))
                elif drift == "ancestor-mode":
                    first.parent.chmod(0o720)
                else:
                    replacement = tmp_path / "late-replacement"
                    replacement.write_bytes(first.read_bytes())
                    replacement.chmod(stat.S_IMODE(before.st_mode))
                    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                    replacement.replace(first)
        return raw

    monkeypatch.setattr(worker.copying, "read_leaf", late_drift)
    with pytest.raises(ValueError, match="binding_observation_"):
        check_declared(worker, manifest)
    assert ocean_reads[0] == 2 and calls[-1] == str(ocean)


def test_declared_deadline_closes_descriptors_before_return(declared_real_case):
    worker, _, manifest, _, _, _ = declared_real_case
    worker._deadline = os.times()[4] - 1
    descriptors = set(os.listdir("/proc/self/fd"))
    with pytest.raises(ValueError, match="deadline"):
        check_declared(worker, manifest)
    assert descriptors == set(os.listdir("/proc/self/fd"))


def test_declared_missing_resolved_ocean_rejects_before_content(declared_real_case, monkeypatch):
    worker, _, manifest, ocean, _, _ = declared_real_case
    manifest["members"] = [member for member in manifest["members"]
                           if member["path"] != str(ocean)]
    # The second runtime file retains exactly the same ancestor union, so this
    # tests required-OCEAN membership rather than a structural union rejection.
    monkeypatch.setattr(
        worker.copying, "read_leaf", lambda *a, **k: pytest.fail("content before membership"),
    )
    with pytest.raises(ValueError, match="^binding_observation_declared_ocean_member$"):
        check_declared(worker, manifest)


@pytest.mark.parametrize("fault_call", [1, 3, 5])
@pytest.mark.parametrize("fault", ["fdopen", "read"])
def test_declared_stream_fault_closes_all_fds_and_restores_scoped_os(
    declared_real_case, monkeypatch, fault_call, fault,
):
    worker, _, manifest, _, _, _ = declared_real_case
    original_os = worker.copying.os
    facade = SimpleNamespace(**vars(original_os))
    calls = [0]

    class ReadFault:
        def __init__(self, stream):
            self.stream = stream

        def read(self, *args):
            raise OSError(errno.EIO, "synthetic read fault")

        def close(self):
            self.stream.close()

    def faulty_fdopen(*args, **kwargs):
        calls[0] += 1
        if calls[0] == fault_call:
            if fault == "fdopen":
                raise OSError(errno.ENOMEM, "synthetic fdopen fault")
            return ReadFault(original_os.fdopen(*args, **kwargs))
        return original_os.fdopen(*args, **kwargs)

    facade.fdopen = faulty_fdopen
    monkeypatch.setattr(worker.copying, "os", facade)
    descriptors = set(os.listdir("/proc/self/fd"))
    with pytest.raises(OSError, match="synthetic " + fault + " fault"):
        check_declared(worker, manifest)
    assert calls[0] == fault_call
    assert descriptors == set(os.listdir("/proc/self/fd"))
    assert worker.copying.os is facade and observer.os is original_os


def test_observe_is_unconditionally_blocked_and_never_writes_or_starts(selected, monkeypatch):
    worker, scan, _ = selected
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: pytest.fail("EDA start"))
    before = {p: p.read_bytes() for p in Path(worker.root).rglob("*") if p.is_file()}
    outcome = worker.observe(scan)
    assert outcome["status"] == "CAPABILITY_NOT_QUALIFIED"
    assert outcome["qualified"] is False and outcome["closure_trust"] == "NOT_ESTABLISHED"
    assert outcome["new_eda_starts"] == outcome["new_simulations"] == 0
    assert outcome["new_extractions"] == outcome["new_reservations"] == 0
    assert not (Path(worker.root) / "binding-observations").exists()
    assert before == {p: p.read_bytes() for p in Path(worker.root).rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="request_shape"):
        worker.observe({**scan, "closure_trust": "TRUSTED"})


@pytest.mark.parametrize("change", ["expression", "command", "view", "alias", "nonce", "bool"])
def test_fixed_renderer_rejects_untrusted_fields_and_expressions(selected, change):
    _, request, _ = selected
    scan = copy.deepcopy(request)
    if change == "expression":
        scan["variables"][0]["cadence_binding"] = "qa_vp+1"
    elif change == "command":
        scan["command"] = "anything"
    elif change == "view":
        scan["view"] = "layout"
    elif change == "alias":
        scan["variables"].append({"logical_id": "other", "cadence_binding": "qa_vp"})
    elif change == "nonce":
        scan["nonce"] = "a" * 32
    else:
        scan["schema_version"] = True
    with pytest.raises(ValueError):
        observer.render_collector(scan)


def test_rendering_is_fixed_and_bound_to_source_nonce_and_request(selected):
    _, scan, _ = selected
    raw = observer.render_collector(scan)
    assert b"@" not in raw and raw.isascii() and len(raw) < observer.FRAME_BYTES
    assert observer.digest(observer.canonical(scan)).encode() in raw
    assert scan["nonce"].encode() in raw and scan["observation_id"].encode() in raw
    assert b'dbOpenCellViewByType("Synthetic" "Cell" "schematic" "" "r")' in raw
    assert b'list(list("input-plus" "qa_vp"))' in raw
    assert b'outfile("binding-frame.txt")' in raw
    assert b"dbSave" not in raw and b"evalstring" not in raw and b"dbCreate" not in raw


@pytest.mark.parametrize("change", ["extra", "digest", "replacement-pins"])
def test_only_compiled_fixed_helpers_can_be_memory_loaded(selected, change, tmp_path):
    _, _, arguments = selected
    bundle, pins = assets(), dict(observer.HELPER_PINS)
    marker = tmp_path / "untrusted-module-executed"
    if change == "extra":
        bundle["anything.py"] = b"raise RuntimeError('must not execute')"
    else:
        bundle["copy.py"] = f"open({str(marker)!r}, 'w').write('bad')".encode()
        if change == "replacement-pins":
            pins["copy.py"] = observer.digest(bundle["copy.py"])
    with pytest.raises(ValueError, match="fixed_helper"):
        observer.BindingObservationWorker(*arguments, bundle, pins)
    assert not marker.exists()


def test_lower_copy_limits_are_private_and_combined_across_source_and_state(selected):
    worker, _, _ = selected
    assert copying.MAX_ENTRIES == 4096 and copying.MAX_BYTES == 67108864
    assert worker.copying.MAX_ENTRIES == 64 and worker.copying.MAX_BYTES == 1048576
    before = worker._snapshots()
    state = Path(worker.route["source_state"])
    for index in range(62):
        (state / str(index)).write_bytes(b"")
    with pytest.raises(ValueError, match="tree_bound|tree_or_link_bound"):
        worker._snapshots()
    assert copying.MAX_ENTRIES == 4096 and worker.copying.MAX_ENTRIES == 64
    assert before["source"]["bytes"] == len(b"synthetic OA placeholder")


def test_combined_byte_bound_and_original_content_metadata_drift_reject(selected):
    worker, _, _ = selected
    state = Path(worker.route["source_state"]) / "ADE_state.info"
    state.write_bytes(b"x" * observer.SNAPSHOT_BYTES)
    with pytest.raises(ValueError, match="drift_or_size"):
        worker._snapshots()
    state.write_bytes(b"changed")
    with pytest.raises(ValueError, match="original_registration_drift"):
        worker._snapshots()


def test_scan_must_match_registered_route_and_reviewed_digest(selected):
    worker, request, _ = selected
    scan = copy.deepcopy(request)
    scan["variables"][0]["cadence_binding"] = "Unregistered"
    with pytest.raises(ValueError, match="registered_request_binding"):
        worker.observe(scan)


def test_whole_registered_library_drift_is_separate_from_selected_cell(selected):
    worker, _, _ = selected
    before = worker._snapshots()
    library = Path(worker.route["libraries"][0]["path"])
    (library / "libInit.il").write_bytes(b"synthetic init placeholder")
    assert worker.copying.snapshot(worker.route["source_cell"]) == before["source"]
    with pytest.raises(ValueError, match="registered_dependency_drift"):
        worker._snapshots()
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES
    assert worker.copying.MAX_BYTES == observer.SNAPSHOT_BYTES


def test_dependency_budget_is_aggregate_and_always_restored(selected, tmp_path, monkeypatch):
    worker, _, _ = selected
    extra = tmp_path / "dependency"
    extra.mkdir()
    (extra / "code").write_bytes(b"synthetic dependency")
    snapshot = copying.dependency_snapshot(str(extra))
    worker.route["libraries"].append(dict(
        name="Other", path=str(extra), tree_sha256=snapshot["tree_sha256"],
    ))
    total = sum(s[2]["bytes"] for s in worker._dependencies())
    monkeypatch.setattr(observer, "DEPENDENCY_BYTES", total - 1)
    with pytest.raises(ValueError, match="drift_or_size|combined_dependency_bound"):
        worker._dependencies()
    assert (worker.copying.MAX_ENTRIES, worker.copying.MAX_BYTES) == (
        observer.SNAPSHOT_ENTRIES, observer.SNAPSHOT_BYTES,
    )


def test_dependency_scan_rechecks_earlier_library_after_later_read(selected, tmp_path, monkeypatch):
    worker, _, _ = selected
    extra = tmp_path / "dependency"
    extra.mkdir()
    tree_sha256 = copying.dependency_snapshot(str(extra))["tree_sha256"]
    worker.route["libraries"].append(dict(
        name="Other", path=str(extra), tree_sha256=tree_sha256,
    ))
    real_snapshot = worker.copying.dependency_snapshot

    def drifting(path):
        observed = real_snapshot(path)
        if path == str(extra):
            library = Path(worker.route["libraries"][0]["path"])
            (library / "late-init.il").write_bytes(b"synthetic late drift")
        return observed

    monkeypatch.setattr(worker.copying, "dependency_snapshot", drifting)
    with pytest.raises(ValueError, match="registered_dependency_drift"):
        worker._dependencies()


@pytest.mark.parametrize("change", ["new-leaf", "same-size-restored-mtime", "mode"])
def test_second_pass_late_dependency_drift_is_checked_over_whole_union(
    selected, tmp_path, monkeypatch, change,
):
    worker, _, _ = selected
    extra = tmp_path / "later-dependency"
    extra.mkdir()
    worker.route["libraries"].append(dict(
        name="Later", path=str(extra),
        tree_sha256=copying.dependency_snapshot(str(extra))["tree_sha256"],
    ))
    leaf = Path(worker.route["source_cell"]) / "sch.oa"
    original = leaf.stat()
    if change == "same-size-restored-mtime" and os.name != "posix":
        pytest.skip("POSIX change time, not Windows creation time")
    real_snapshot = worker.copying.dependency_snapshot
    later_reads = 0

    def late_drift(path):
        nonlocal later_reads
        snapshot = real_snapshot(path)
        if path == str(extra):
            later_reads += 1
            if later_reads == 2:
                if change == "new-leaf":
                    (leaf.parent.parent / "late-init.il").write_bytes(b"synthetic")
                elif change == "mode":
                    leaf.chmod(0o400)
                else:
                    leaf.write_bytes(b"x" * original.st_size)
                    os.utime(leaf, ns=(original.st_atime_ns, original.st_mtime_ns))
        return snapshot

    monkeypatch.setattr(worker.copying, "dependency_snapshot", late_drift)
    with pytest.raises(ValueError, match="dependency_scan_drift"):
        worker._dependencies()
    assert later_reads == 2
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES


@pytest.mark.parametrize("change", ["alias", "link", "missing", "count", "entries"])
def test_dependency_namespace_and_entry_bounds_reject(selected, tmp_path, monkeypatch, change):
    worker, _, _ = selected
    library = worker.route["libraries"][0]
    if change == "alias":
        worker.route["libraries"].append(dict(library))
    elif change == "link":
        if os.name == "nt":
            pytest.skip("symlink creation privilege is not required for Windows fixtures")
        (Path(library["path"]) / "linked").symlink_to(tmp_path / "state", target_is_directory=True)
    elif change == "missing":
        library["path"] = str(tmp_path / "nonexistent")
    elif change == "count":
        worker.route["libraries"] *= observer.DEPENDENCY_LIBRARIES + 1
    else:
        monkeypatch.setattr(observer, "DEPENDENCY_ENTRIES", 1)
    with pytest.raises((ValueError, OSError)):
        worker._dependencies()
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES


@pytest.mark.parametrize("operation", ["snapshot", "dependency_snapshot"])
def test_bounded_helper_retains_exact_snapshot_format_and_digest(
    selected, tmp_path, monkeypatch, operation,
):
    worker, _, _ = selected
    library = tmp_path / "digest-library"
    library.mkdir(mode=0o700)
    (library / "z-last").write_bytes(b"last")
    (library / "a-first").write_bytes(b"first")
    (library / "middle").mkdir(mode=0o700)
    (library / "middle" / "nested").write_bytes(b"nested")
    expected = getattr(worker.copying, operation)(str(library))
    original_os = worker.copying.os

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded helper listdir")

    monkeypatch.setattr(observer.os, "listdir", forbidden)
    monkeypatch.setattr(observer.os, "walk", forbidden)
    assert worker._bounded_copy_call(operation, str(library)) == expected
    assert worker.copying.os is original_os
    assert worker.copying.os is copying.os is os
    assert os.listdir is forbidden


def test_all_source_state_and_dependency_snapshots_use_bounded_enumeration(selected, monkeypatch):
    worker, _, _ = selected
    expected = worker._snapshots()

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded source/state/dependency enumeration")

    monkeypatch.setattr(observer.os, "listdir", forbidden)
    monkeypatch.setattr(observer.os, "walk", forbidden)
    assert worker._snapshots() == expected
    assert worker.copying.os is copying.os is os


@pytest.mark.parametrize("operation", ["snapshot", "dependency_snapshot", "copy_owned"])
@pytest.mark.parametrize("failure", [ValueError, KeyboardInterrupt])
def test_scoped_helper_os_is_restored_after_every_failure(
    selected, monkeypatch, operation, failure,
):
    worker, _, _ = selected
    original_os, original_listdir = worker.copying.os, os.listdir

    def failed(*args):
        assert worker.copying.os is not original_os
        assert worker.copying.os.listdir is not original_listdir
        assert os.listdir is original_listdir
        raise failure("synthetic helper failure")

    monkeypatch.setattr(worker.copying, operation, failed)
    arguments = ("/synthetic-source", "/synthetic-target", "a" * 64) if (
        operation == "copy_owned"
    ) else ("/synthetic-source",)
    with pytest.raises(failure, match="synthetic helper failure"):
        worker._bounded_copy_call(operation, *arguments)
    assert worker.copying.os is original_os
    assert os.listdir is original_listdir


@pytest.mark.parametrize("limit,expected_reads", [(9, 9), (observer.DEPENDENCY_ENTRIES, 4096)])
def test_dependency_namespace_stops_infinite_names_at_global_or_library_limit(
    selected, monkeypatch, limit, expected_reads,
):
    worker, _, _ = selected
    consumed, closed = [], []

    def infinite_entries(path):
        try:
            while True:
                consumed.append(True)
                assert len(consumed) <= expected_reads
                yield "synthetic-child"
        finally:
            closed.append(True)

    monkeypatch.setattr(observer, "DEPENDENCY_ENTRIES", limit)
    monkeypatch.setattr(worker, "_stage_directory_entries", infinite_entries)
    with pytest.raises(ValueError, match="dependency_namespace_bound"):
        worker._dependency_namespace(worker.route["libraries"])
    assert len(consumed) == expected_reads
    assert closed == [True]


@pytest.mark.parametrize("operation,limit", [("snapshot", 64), ("dependency_snapshot", 4096)])
def test_authenticated_helper_never_materializes_an_infinite_directory(
    selected, monkeypatch, operation, limit,
):
    worker, _, _ = selected
    consumed, closed = [], []
    original_os = worker.copying.os

    def infinite_entries(path):
        try:
            while True:
                consumed.append(True)
                assert len(consumed) <= limit
                yield "synthetic-child"
        finally:
            closed.append(True)

    monkeypatch.setattr(worker.copying, "MAX_ENTRIES", limit)
    monkeypatch.setattr(worker, "_stage_directory_entries", infinite_entries)
    with pytest.raises(ValueError, match="native_copy_tree_bound"):
        worker._bounded_copy_call(operation, worker.route["source_cell"])
    assert len(consumed) == limit
    assert closed == [True]
    assert worker.copying.os is original_os


@pytest.mark.parametrize("scan", ["namespace", "snapshot"])
def test_sibling_directory_names_share_the_remaining_discovery_budget(
    selected, tmp_path, monkeypatch, scan,
):
    worker, _, _ = selected
    library = tmp_path / "sibling-library"
    library.mkdir(mode=0o700)
    for name in ("left", "right"):
        (library / name).mkdir(mode=0o700)
        for index in range(2):
            (library / name / str(index)).write_bytes(b"")
    original_entries = worker._stage_directory_entries
    consumed, closed = {}, []

    def counted_entries(path):
        names = original_entries(path)
        try:
            for name in names:
                consumed[path] = consumed.get(path, 0) + 1
                yield name
        finally:
            names.close()
            closed.append(path)

    monkeypatch.setattr(worker, "_stage_directory_entries", counted_entries)
    if scan == "namespace":
        monkeypatch.setattr(observer, "DEPENDENCY_ENTRIES", 6)
    else:
        monkeypatch.setattr(worker.copying, "MAX_ENTRIES", 6)

    def action():
        if scan == "namespace":
            return worker._dependency_namespace([dict(path=str(library))])
        return worker._bounded_copy_call("snapshot", str(library))

    with pytest.raises(ValueError, match="bound"):
        action()
    # Root + two listed sibling directories + two left leaves already spend5.
    # The right directory may retain only one name and rejects its next name.
    assert consumed[str(library / "right")] == 2
    assert closed[-1] == str(library / "right")
    assert worker.copying.os is copying.os is os


def test_content_pass_after_namespace_still_rejects_unbounded_late_growth(selected, monkeypatch):
    worker, _, _ = selected
    library = worker.route["libraries"][0]["path"]
    original_entries = worker._stage_directory_entries
    visits, consumed, closed = [], [], []

    def late_growth(path):
        if path == library:
            visits.append(path)
        if path == library and len(visits) == 3:
            # The namespace's initial and membership reads already succeeded.
            # A later huge directory must also stop inside the content helper.
            try:
                while True:
                    consumed.append(True)
                    assert len(consumed) <= 4096
                    yield "synthetic-content-phase-growth"
            finally:
                closed.append(True)
        else:
            names = original_entries(path)
            try:
                yield from names
            finally:
                names.close()

    monkeypatch.setattr(worker, "_stage_directory_entries", late_growth)
    with pytest.raises(ValueError, match="native_copy_tree_bound"):
        worker._dependencies()
    assert len(visits) == 3
    assert len(consumed) == 4096
    assert closed == [True]
    assert worker.copying.os is copying.os is os
    assert worker.copying.MAX_ENTRIES == observer.SNAPSHOT_ENTRIES


def test_dependency_namespace_budget_is_shared_across_registered_library_roots(
    selected, tmp_path, monkeypatch,
):
    worker, _, _ = selected
    libraries = []
    for label in ("first", "second"):
        library = tmp_path / label
        library.mkdir(mode=0o700)
        for index in range(2):
            (library / str(index)).write_bytes(b"")
        libraries.append(dict(path=str(library)))
    monkeypatch.setattr(observer, "DEPENDENCY_ENTRIES", 5)
    with pytest.raises(ValueError, match="dependency_namespace_bound"):
        worker._dependency_namespace(libraries)


def test_helper_membership_recheck_has_its_own_bounded_prefix_and_restores_os(
    selected, monkeypatch,
):
    worker, _, _ = selected
    source = worker.route["source_cell"]
    original_entries = worker._stage_directory_entries
    visits, consumed, closed = [], [], []

    def growing_entries(path):
        visits.append(path)
        if len(visits) == 1:
            names = original_entries(path)
            try:
                yield from names
            finally:
                names.close()
        else:
            try:
                while True:
                    consumed.append(True)
                    assert len(consumed) <= 2
                    yield "synthetic-late-child"
            finally:
                closed.append(True)

    monkeypatch.setattr(worker, "_stage_directory_entries", growing_entries)
    with pytest.raises(ValueError, match="native_copy_tree_bound"):
        worker._bounded_copy_call("snapshot", source)
    assert len(consumed) == 2  # one original leaf plus first excess
    assert closed == [True]
    assert worker.copying.os is copying.os is os


@pytest.mark.skipif(os.name != "posix", reason="actual ordinary-user helper copy and rescan")
@pytest.mark.parametrize("growth", ["source-rescan", "target-scan", "none"])
def test_owned_copy_internal_rescans_are_bounded_and_restore_the_private_os(
    selected, tmp_path, monkeypatch, growth,
):
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    worker, _, _ = selected
    source = worker.route["source_cell"]
    target = str(tmp_path / "bounded-owned-copy")
    expected = worker.copying.snapshot(source)
    original_listdir = os.listdir
    original_entries = worker._stage_directory_entries
    visits, consumed, closed = {}, [], []

    def growing_entries(path):
        visits[path] = visits.get(path, 0) + 1
        growing = (growth == "source-rescan" and path == source and visits[path] == 3) or (
            growth == "target-scan" and path == target
        )
        if growing:
            try:
                while True:
                    consumed.append(True)
                    assert len(consumed) <= observer.SNAPSHOT_ENTRIES
                    yield "synthetic-late-child"
            finally:
                closed.append(True)
        else:
            names = original_entries(path)
            try:
                yield from names
            finally:
                names.close()

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded copy_owned enumeration")

    monkeypatch.setattr(worker, "_stage_directory_entries", growing_entries)
    monkeypatch.setattr(observer.os, "listdir", forbidden)
    if growth == "none":
        result = worker._bounded_copy_call("copy_owned", source, target, expected["tree_sha256"])
        # Inspect the tiny retained fixture with the untouched authenticated
        # helper after the bounded call; compare the complete copy receipt.
        monkeypatch.setattr(observer.os, "listdir", original_listdir)
        copied = worker.copying.snapshot(target)
        assert result == dict(
            schema_version=1, source_tree_sha256=expected["tree_sha256"],
            source_content_sha256=expected["content_sha256"],
            copy_content_sha256=copied["content_sha256"], copy_tree_sha256=copied["tree_sha256"],
            source_preserved=True, copy_owned=True,
            entries=copied["entries"], bytes=copied["bytes"],
        )
    else:
        with pytest.raises(ValueError, match="native_copy_tree_bound"):
            worker._bounded_copy_call("copy_owned", source, target, expected["tree_sha256"])
        assert len(consumed) == (2 if growth == "source-rescan" else observer.SNAPSHOT_ENTRIES)
        assert closed == [True]
    assert (Path(target) / "sch.oa").read_bytes() == b"synthetic OA placeholder"
    assert worker.copying.os is copying.os is os


@pytest.mark.skipif(
    platform.system() != "Linux" or platform.machine() not in ("i686", "x86_64"),
    reason="actual Linux dependency readdir64 prefix and cleanup",
)
def test_actual_linux_dependency_directory_rejects_first_excess_name_and_closes(
    selected, tmp_path, monkeypatch,
):
    worker, _, _ = selected
    library = tmp_path / "actual-dependency-limit"
    library.mkdir(mode=0o700)
    for index in range(4096):
        (library / f"leaf-{index:04d}").write_bytes(b"")
    original_entries = worker._stage_directory_entries
    consumed, closed = [], []

    def counted_entries(path):
        names = original_entries(path)
        try:
            for name in names:
                consumed.append(True)
                assert len(consumed) <= 4096
                yield name
        finally:
            names.close()
            closed.append(True)

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded dependency materialization")

    monkeypatch.setattr(worker, "_stage_directory_entries", counted_entries)
    monkeypatch.setattr(observer.os, "listdir", forbidden)
    monkeypatch.setattr(observer.os, "walk", forbidden)
    with pytest.raises(ValueError, match="dependency_namespace_bound"):
        worker._dependency_namespace([dict(path=str(library))])
    assert len(consumed) == 4096  # library root plus the 4,096th child is first excess
    assert closed == [True]


def test_library_map_is_reconstructed_from_registration_and_owned_stage(selected):
    worker, scan, _ = selected
    stage = "/synthetic-owned-stage/" + scan["observation_id"]
    expected = ("DEFINE Synthetic " + stage + "/library\n").encode("ascii")
    assert worker._cds_lib(scan, stage) == expected
    assert b"INCLUDE" not in expected and worker.route["source_cell"].encode() not in expected


@pytest.mark.skipif(os.name != "posix", reason="actual private owned stage and prelaunch guards")
@pytest.mark.parametrize("replacement", [
    b"DEFINE Synthetic /unregistered/other-library\n",
    b"INCLUDE /unregistered/cds.lib\n",
])
def test_staged_mapping_tamper_rejects_before_any_ocean_start(
    selected, controlled_inventory, monkeypatch, replacement,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")

    def forbidden(*args, **kwargs):
        pytest.fail("tampered library mapping must reject before OCEAN")

    monkeypatch.setattr(observer.subprocess, "Popen", forbidden)
    monkeypatch.setattr(worker, "_ocean_trust", forbidden)
    before = worker._ledger()
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        (Path(stage) / "cds.lib").write_bytes(replacement)
        with pytest.raises(ValueError, match="registered_library_mapping_drift"):
            worker._program(stage, session, scan)
        assert not (Path(stage) / "ocean-start-claimed.json").exists()
        assert (Path(stage) / "cds.lib").read_bytes() == replacement
    assert worker._ledger() == before


@pytest.mark.skipif(os.name != "posix", reason="actual ordinary-user resource flock and process")
@pytest.mark.parametrize("case", ["success", "nonzero", "timeout", "stdout", "stderr"])
def test_private_program_piece_bounds_own_synthetic_process_and_preserves_ledger(
    selected, controlled_inventory, monkeypatch, case,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("worker intentionally rejects root; hosted ordinary-user POSIX test required")
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    body = {
        "success": "open('binding-frame.txt','wb').write(b'synthetic complete frame\\n')",
        "nonzero": "raise SystemExit(3)",
        "timeout": "import time;time.sleep(30)",
        "stdout": "import os;os.write(1,b'x'*65537)",
        "stderr": "import os;os.write(2,b'x'*65537)",
    }[case]
    executable.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    launches = []
    real_popen = observer.subprocess.Popen

    def launch(argv, **options):
        launches.append((argv, options["env"]))
        return real_popen(argv, **options)

    monkeypatch.setattr(observer.subprocess, "Popen", launch)
    ledger = (Path(worker.root) / worker.accounting.LEDGER).read_bytes()
    original = worker._snapshots()
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 0.2 if case == "timeout" else 5)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, snapshots, copied = worker._stage(scan, session)
        assert snapshots == original and copied["source_preserved"]
        if case == "success":
            result = worker._program(stage, session, scan)
            assert result["frame"] == b"synthetic complete frame\n"
            assert result["qualified"] is False and result["closure_trust"] == "NOT_ESTABLISHED"
        else:
            reason = "program_failed" if case == "nonzero" else (
                "process_timeout" if case == "timeout" else "program_output_bound"
            )
            with pytest.raises(ValueError, match=reason):
                worker._program(stage, session, scan)
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)
        session.check()
        with pytest.raises(ValueError, match="attempt_already_exists"):
            worker._stage(scan, session)
    assert len(launches) == 1
    assert launches[0][0] == [
        str(executable), "-nograph", "-nocdsinit", "-log", stage + "/ocean.log",
        "-cdslib", stage + "/cds.lib", "-restore", stage + "/observer.ocn",
    ]
    assert launches[0][1]["HOME"] == stage + "/home"
    assert launches[0][1]["TMPDIR"] == stage + "/tmp"
    assert (Path(worker.root) / worker.accounting.LEDGER).read_bytes() == ledger
    assert worker._snapshots() == original
    assert all((Path(stage) / ("ocean." + stream)).stat().st_size <= observer.FRAME_BYTES
               for stream in ("stdout", "stderr"))


@pytest.mark.skipif(os.name != "posix", reason="owned POSIX runtime directories")
@pytest.mark.parametrize("case", ["clean", "content", "mode", "license"])
def test_private_environment_excludes_inherited_loader_and_init_inputs(
    selected, controlled_inventory, monkeypatch, case,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    for name in ("LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "CDS_SITE", "CDS_LOAD_ENV",
                 "CDS_LIB_PATH", "DISPLAY", "HOME", "PATH"):
        monkeypatch.setenv(name, "synthetic-untrusted-setting")
    monkeypatch.setenv("CDS_LIC_FILE", "synthetic-private-route")
    monkeypatch.delenv("LM_LICENSE_FILE", raising=False)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        if case == "content":
            (Path(stage) / "home" / ".cdsinit").write_bytes(b"synthetic")
        elif case == "mode":
            (Path(stage) / "tmp").chmod(0o750)
        elif case == "license":
            monkeypatch.setenv("CDS_LIC_FILE", "x" * 4097)
        if case == "clean":
            environment = worker._environment(stage)
            assert environment == dict(
                HOME=stage + "/home", TMPDIR=stage + "/tmp", TMP=stage + "/tmp",
                TEMP=stage + "/tmp", PATH="/usr/bin:/bin", LANG="C", LC_ALL="C",
                CDS_LIC_FILE="synthetic-private-route",
            )
        else:
            with pytest.raises(
                ValueError, match="runtime_directory|license_environment_bound|destination_trust",
            ):
                worker._environment(stage)


@pytest.mark.skipif(os.name != "posix", reason="actual dependency prelaunch guards")
def test_dependency_drift_prevents_private_program_start(
    selected, controlled_inventory, monkeypatch,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: pytest.fail("EDA start"))
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        library = Path(worker.route["libraries"][0]["path"])
        (library / "libInit.il").write_bytes(b"synthetic changed init")
        with pytest.raises(ValueError, match="registered_dependency_drift"):
            worker._program(stage, session, scan)
        assert not (Path(stage) / "ocean-start-claimed.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="actual synthetic child postfailure guards")
@pytest.mark.parametrize("exit_code", [0, 3])
def test_private_child_dependency_drift_is_retained_even_on_failure(
    selected, controlled_inventory, monkeypatch, exit_code,
):
    import json

    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    changed = Path(worker.route["libraries"][0]["path"]) / "libInit.il"
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    executable.write_text(
        f"#!{sys.executable}\nopen({str(changed)!r},'wb').write(b'synthetic drift')\n"
        f"raise SystemExit({exit_code})\n", encoding="utf-8",
    )
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 5)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        ledger = worker._ledger()
        reason = "registered_dependency_drift" if exit_code == 0 else "program_failed"
        with pytest.raises(ValueError, match=reason):
            worker._program(stage, session, scan)
        guard = json.loads((Path(stage) / "protection-check.json").read_bytes())
        assert guard["originals_preserved"] is False
        assert guard["owned_copy_preserved"] is guard["ledger_preserved"] is True
        assert changed.read_bytes() == b"synthetic drift"
        assert worker._ledger() == ledger
        assert (Path(stage) / "ocean-start-claimed.json").is_file()
        assert (Path(stage) / "ocean.stderr").is_file()
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)


@pytest.mark.skipif(os.name != "posix", reason="actual synthetic child evidence collisions")
@pytest.mark.parametrize("collision", [
    "stdout", "stderr", "both-stdout", "both-stderr", "protection", "both-protection",
])
@pytest.mark.parametrize("outcome", ["success", "nonzero", "drift"])
def test_child_evidence_collisions_never_skip_guards_or_replace_primary_failure(
    selected, controlled_inventory, monkeypatch, collision, outcome,
):
    import json

    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    names = {
        "stdout": ["ocean.stdout"], "stderr": ["ocean.stderr"],
        "both-stdout": ["ocean.stdout", "ocean.stdout-fallback"],
        "both-stderr": ["ocean.stderr", "ocean.stderr-fallback"],
        "protection": ["protection-check.json"],
        "both-protection": ["protection-check.json", "protection-check-fallback.json"],
    }[collision]
    changed = Path(worker.route["libraries"][0]["path"]) / "libInit.il"
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    body = [f"open({name!r},'wb').write(b'child-owned evidence')" for name in names]
    body.extend(["import os", "os.write(1,b'captured stdout')", "os.write(2,b'captured stderr')"])
    body.append("open('binding-frame.txt','wb').write(b'synthetic complete frame\\n')")
    if outcome == "drift":
        body.append(f"open({str(changed)!r},'wb').write(b'synthetic protected drift')")
    body.append(f"raise SystemExit({3 if outcome == 'nonzero' else 0})")
    executable.write_text(f"#!{sys.executable}\n" + "\n".join(body) + "\n", encoding="utf-8")
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 5)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        copied_path = stage + "/library/" + scan["cell"]
        ledger = worker._ledger()
        checked = dict(original=0, copied=0, ledger=0, config=0)
        real_snapshots, real_snapshot = worker._snapshots, worker.copying.snapshot
        real_ledger, real_read = worker._ledger, worker._read

        def snapshots():
            checked["original"] += 1
            return real_snapshots()

        def snapshot(path):
            if path == copied_path:
                checked["copied"] += 1
            return real_snapshot(path)

        def current_ledger():
            checked["ledger"] += 1
            return real_ledger()

        def read(path):
            if path == stage + "/cds.lib":
                checked["config"] += 1
            return real_read(path)

        monkeypatch.setattr(worker, "_snapshots", snapshots)
        monkeypatch.setattr(worker.copying, "snapshot", snapshot)
        monkeypatch.setattr(worker, "_ledger", current_ledger)
        monkeypatch.setattr(worker, "_read", read)
        reason = {
            "success": "evidence_publication_failed", "nonzero": "program_failed",
            "drift": "registered_dependency_drift",
        }[outcome]
        with pytest.raises(ValueError, match=reason):
            worker._program(stage, session, scan)
        # Prelaunch plus finalization must observe every protected category,
        # including when neither protection receipt can be published.
        assert all(count >= 2 for count in checked.values())
        assert all((Path(stage) / name).read_bytes() == b"child-owned evidence" for name in names)
        if collision != "both-protection":
            guard_name = ("protection-check-fallback.json" if collision == "protection"
                          else "protection-check.json")
            guard = json.loads((Path(stage) / guard_name).read_bytes())
            assert guard["originals_preserved"] is (outcome != "drift")
            assert guard["owned_copy_preserved"] is guard["ledger_preserved"] is True
            assert guard["cds_lib_preserved"] is True
            assert guard["failure_active"] is (outcome != "success")
            stream_name = collision.removeprefix("both-")
            if collision.startswith("both-"):
                assert guard["finalization_errors"] == [
                    "publish_" + stream_name, "publish_" + stream_name + "_fallback",
                ]
                assert guard["stream_publication"][stream_name] == "FAILED"
            elif collision == "protection":
                assert guard["finalization_errors"] == ["publish_protection"]
                assert guard["stream_publication"] == dict(stdout="PRIMARY", stderr="PRIMARY")
            else:
                assert guard["finalization_errors"] == ["publish_" + collision]
                assert guard["stream_publication"][collision] == "FALLBACK"
                assert (Path(stage) / ("ocean." + collision + "-fallback")).read_bytes() == (
                    "captured " + collision
                ).encode()
            assert guard["protection_record"] == (
                "FALLBACK" if collision == "protection" else "PRIMARY"
            )
        assert real_ledger() == ledger
        assert (Path(stage) / "ocean-start-claimed.json").is_file()
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)


@pytest.mark.parametrize("case", [
    "stdout", "stderr", "both-stdout", "both-stderr", "protection", "both-protection",
    "close",
])
@pytest.mark.parametrize("failure_active", [False, True])
def test_finalization_file_collisions_and_close_faults_are_independent(
    selected, tmp_path, monkeypatch, case, failure_active,
):
    import json

    worker, _, _ = selected
    stage = tmp_path / "finalization"
    stage.mkdir(mode=0o700)
    names = {
        "stdout": ["ocean.stdout"], "stderr": ["ocean.stderr"],
        "both-stdout": ["ocean.stdout", "ocean.stdout-fallback"],
        "both-stderr": ["ocean.stderr", "ocean.stderr-fallback"],
        "protection": ["protection-check.json"],
        "both-protection": ["protection-check.json", "protection-check-fallback.json"],
    }.get(case, [])
    for name in names:
        (stage / name).write_bytes(b"retained collision")
    checked = []

    def record(name, value):
        checked.append(name)
        return value

    monkeypatch.setattr(worker, "_snapshots", lambda: record("original", "original"))
    monkeypatch.setattr(worker.copying, "snapshot", lambda path: record("copy", "copy"))
    monkeypatch.setattr(worker, "_ledger", lambda: record("ledger", "ledger"))
    monkeypatch.setattr(worker, "_read", lambda path: record("config", b"config"))

    class CloseFault:
        def close(self):
            raise OSError("synthetic close fault")

    def finish():
        worker._finalize_evidence(
            str(stage), [CloseFault()] if case == "close" else [], None,
            [b"captured stdout", b"captured stderr"], "original", "synthetic-copy", "copy",
            "ledger", b"config", failure_active, False,
        )

    if failure_active:
        with pytest.raises(ValueError, match="original_child_failure"):
            try:
                raise ValueError("original_child_failure")
            finally:
                finish()
    else:
        with pytest.raises(ValueError, match="evidence_publication_failed"):
            finish()
    assert checked == ["original", "copy", "ledger", "config"]
    assert all((stage / name).read_bytes() == b"retained collision" for name in names)
    if case != "both-protection":
        guard_name = ("protection-check-fallback.json" if case == "protection"
                      else "protection-check.json")
        guard = json.loads((stage / guard_name).read_bytes())
        assert all(guard[name] for name in (
            "originals_preserved", "owned_copy_preserved", "ledger_preserved", "cds_lib_preserved",
        ))
        assert guard["failure_active"] is failure_active
        assert guard["cleanup_failed"] is False
        if case == "close":
            assert guard["finalization_errors"] == ["close_stream_0"]


@pytest.mark.parametrize("bound", ["logical", "allocated", "entries", "directory", "walk"])
@pytest.mark.parametrize("failure_active", [False, True])
def test_full_stage_skips_every_evidence_write_but_attempts_all_conservation_checks(
    selected, tmp_path, monkeypatch, bound, failure_active,
):
    worker, _, _ = selected
    stage = tmp_path / "full-finalization"
    stage.mkdir(mode=0o700)
    retained = stage / "retained-child-file"
    retained.write_bytes(b"retained child bytes")
    if bound == "entries":
        for index in range(254):
            (stage / f"retained-{index:03d}").write_bytes(b"")
    elif bound in ("logical", "allocated"):
        real_lstat = observer.os.lstat

        def observed_lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if os.path.normpath(path) == str(retained):
                # Synthetic metadata isolates the two independent size axes;
                # actual sparse-file behavior is exercised by the POSIX child.
                values = {name: getattr(info, name) for name in dir(info)
                          if name.startswith("st_")}
                values.update(st_size=observer.STAGE_BYTES if bound == "logical" else 1,
                              st_blocks=0 if bound == "logical" else observer.STAGE_BYTES // 512)
                return SimpleNamespace(**values)
            return info

        monkeypatch.setattr(observer.os, "lstat", observed_lstat)
    elif bound == "directory":
        logical, allocated = worker._stage_size(str(stage))
        unit = max(512, getattr(stage.stat(), "st_blksize", 4096))
        if hasattr(os, "statvfs"):
            fs = os.statvfs(stage)
            unit = max(unit, fs.f_bsize, fs.f_frsize)
        # Content allocation fits, but the directory-growth allowance does not.
        monkeypatch.setattr(observer, "STAGE_BYTES", max(logical, allocated) + unit)
    else:
        def unavailable_names(path):
            raise OSError(errno.EACCES, "synthetic unreadable subtree")

        monkeypatch.setattr(worker, "_stage_directory_entries", unavailable_names)
    before = {p.name: p.read_bytes() for p in stage.iterdir()}
    checked, closed = [], []

    def record(name, value):
        checked.append(name)
        return value

    class Closed:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(worker, "_snapshots", lambda: record("original", "original"))
    monkeypatch.setattr(worker.copying, "snapshot", lambda path: record("copy", "copy"))
    monkeypatch.setattr(worker, "_ledger", lambda: record("ledger", "ledger"))
    monkeypatch.setattr(worker, "_read", lambda path: record("config", b"config"))
    monkeypatch.setattr(worker, "_write", lambda *args: pytest.fail("unbudgeted evidence write"))

    def finish():
        worker._finalize_evidence(
            str(stage), [Closed()], Closed(), [b"captured stdout", b"captured stderr"],
            "original", "synthetic-copy", "copy", "ledger", b"config", failure_active, False,
        )

    if failure_active:
        with pytest.raises(ValueError, match="original_child_failure"):
            try:
                raise ValueError("original_child_failure")
            finally:
                finish()
    else:
        with pytest.raises(ValueError, match="evidence_publication_failed"):
            finish()
    assert checked == ["original", "copy", "ledger", "config"]
    assert closed == [True, True]
    assert {p.name: p.read_bytes() for p in stage.iterdir()} == before


@pytest.mark.parametrize("reserved", [0, 1])
def test_stage_limit_stops_an_infinite_name_stream_without_materializing_it(
    selected, tmp_path, monkeypatch, reserved,
):
    worker, _, _ = selected
    stage = tmp_path / "stream-bound"
    stage.mkdir(mode=0o700)
    (stage / "retained").write_bytes(b"")
    consumed, closed = [], []

    def infinite_entries(path):
        try:
            while True:
                consumed.append(True)
                assert len(consumed) <= 256 - reserved
                yield "retained"
        finally:
            closed.append(True)

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded directory materialization")

    monkeypatch.setattr(worker, "_stage_directory_entries", infinite_entries)
    monkeypatch.setattr(observer.os, "listdir", forbidden)
    monkeypatch.setattr(observer.os, "walk", forbidden)
    with pytest.raises(ValueError, match="stage_capacity"):
        worker._stage_size(str(stage), reserved_entries=reserved)
    # The root itself is charged first. Reject the next child immediately when
    # existing plus reserved entries would become 257; never request another.
    assert len(consumed) == 256 - reserved
    assert closed == [True]


@pytest.mark.parametrize("files,reserved,accepted", [
    (250, 1, True), (251, 0, True), (251, 1, False), (252, 0, False),
])
def test_stage_streaming_keeps_one_shared_tree_budget_and_directory_double_count(
    selected, tmp_path, monkeypatch, files, reserved, accepted,
):
    worker, _, _ = selected
    stage = tmp_path / "tree-bound"
    stage.mkdir(mode=0o700)
    directories = [stage / "left", stage / "right"]
    for directory in directories:
        directory.mkdir(mode=0o700)
    leaves = [directories[index % 2] / f"leaf-{index:03d}" for index in range(files)]
    for leaf in leaves:
        leaf.write_bytes(b"")
    expected_allocated = sum(
        getattr(path.stat(), "st_blocks", (path.stat().st_size + 511) // 512) * 512
        for path in [stage] + directories * 2 + leaves
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unbounded directory materialization")

    monkeypatch.setattr(observer.os, "listdir", forbidden)
    monkeypatch.setattr(observer.os, "walk", forbidden)
    if accepted:
        assert worker._stage_size(str(stage), reserved_entries=reserved) == (0, expected_allocated)
    else:
        with pytest.raises(ValueError, match="stage_capacity"):
            worker._stage_size(str(stage), reserved_entries=reserved)


@pytest.mark.parametrize("fault", ["read", "stat"])
def test_stage_stream_closes_on_read_or_stat_failure(selected, tmp_path, monkeypatch, fault):
    worker, _, _ = selected
    stage = tmp_path / "stream-fault"
    stage.mkdir(mode=0o700)
    (stage / "retained").write_bytes(b"")
    closed = []

    def entries(path):
        try:
            yield "retained"
            if fault == "read":
                raise OSError(errno.EACCES, "synthetic incremental read failure")
            yield "missing"
        finally:
            closed.append(True)

    monkeypatch.setattr(worker, "_stage_directory_entries", entries)
    with pytest.raises(OSError):
        worker._stage_size(str(stage))
    assert closed == [True]


@pytest.mark.parametrize("fault", [
    "configure", "identity", "fdopendir", "read", "record", "close", "close-error",
])
def test_linux_directory_stream_cleans_up_opened_handles_on_every_exit(
    selected, tmp_path, monkeypatch, fault,
):
    import ctypes

    worker, _, _ = selected
    stage = tmp_path / "libc-stream"
    stage.mkdir(mode=0o700)
    info = stage.stat()
    opened, descriptors_closed, streams_closed = [], [], []
    buffer = ctypes.create_string_buffer(32)
    ctypes.c_ushort.from_buffer(buffer, 16).value = 19 if fault == "record" else 32
    buffer[19:24] = b"leaf\x00"

    def fdopendir(fd):
        return 0 if fault == "fdopendir" else 456

    def readdir(stream):
        if fault == "read":
            ctypes.set_errno(errno.EACCES)
            return None
        return ctypes.addressof(buffer)

    def closedir(stream):
        streams_closed.append(stream)
        return -1 if fault == "close-error" else 0

    libc = SimpleNamespace(fdopendir=fdopendir, readdir64=readdir, closedir=closedir)
    if fault == "configure":
        del libc.readdir64

    def opened_fd(*args):
        opened.append(args)
        return 123

    def fstat(fd):
        if fault == "identity":
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            values["st_ino"] += 1
            return SimpleNamespace(**values)
        return info

    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: libc)
    monkeypatch.setattr(observer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(observer.platform, "machine", lambda: "i686")
    # A local os facade exercises the fixed Linux branch on Windows without
    # changing the process-wide platform used by pathlib or the test runner.
    monkeypatch.setattr(observer, "os", SimpleNamespace(
        name="posix", O_RDONLY=os.O_RDONLY, O_DIRECTORY=0, O_NOFOLLOW=0,
        lstat=os.lstat, open=opened_fd, close=lambda fd: descriptors_closed.append(fd), fstat=fstat,
    ))
    names = worker._stage_directory_entries(str(stage))
    if fault in ("close", "close-error"):
        assert next(names) == "leaf"
        if fault == "close-error":
            with pytest.raises(OSError, match="directory_close"):
                names.close()
        else:
            names.close()
    else:
        with pytest.raises((AttributeError, ValueError, OSError)):
            next(names)
    assert len(opened) == (0 if fault == "configure" else 1)
    assert descriptors_closed == ([123] if fault in ("identity", "fdopendir") else [])
    assert streams_closed == ([456] if fault in ("read", "record", "close", "close-error") else [])


@pytest.mark.skipif(
    platform.system() != "Linux" or platform.machine() not in ("i686", "x86_64"),
    reason="actual supported Linux readdir64 ABI and handle cleanup",
)
@pytest.mark.parametrize("count,reserved,accepted", [
    (255, 0, True), (256, 0, False), (257, 0, False), (254, 1, True), (255, 1, False),
])
def test_actual_linux_directory_stream_stops_at_the_global_entry_bound_and_closes(
    selected, tmp_path, monkeypatch, count, reserved, accepted,
):
    import ctypes

    worker, _, _ = selected
    stage = tmp_path / "actual-libc-stream"
    stage.mkdir(mode=0o700)
    for index in range(count):
        (stage / f"leaf-{index:03d}").write_bytes(b"")
    real_cdll = ctypes.CDLL
    reads, closes = [], []

    def library(*args, **kwargs):
        libc = real_cdll(*args, **kwargs)
        read, close = libc.readdir64, libc.closedir
        read.argtypes, read.restype = [ctypes.c_void_p], ctypes.c_void_p
        close.argtypes, close.restype = [ctypes.c_void_p], ctypes.c_int

        def readdir(stream):
            reads.append(True)
            assert len(reads) <= 259
            return read(stream)

        def closedir(stream):
            closes.append(True)
            return close(stream)

        return SimpleNamespace(fdopendir=libc.fdopendir, readdir64=readdir, closedir=closedir)

    monkeypatch.setattr(ctypes, "CDLL", library)
    if accepted:
        worker._stage_size(str(stage), reserved_entries=reserved)
        assert len(reads) == count + 3  # two dot entries and one EOF read
    else:
        with pytest.raises(ValueError, match="stage_capacity"):
            worker._stage_size(str(stage), reserved_entries=reserved)
        assert len(reads) == 258 - reserved
    assert closes == [True]
    assert sum(1 for _ in stage.iterdir()) == count


@pytest.mark.skipif(os.name != "posix", reason="actual unreadable owned directory")
@pytest.mark.parametrize("failure_active", [False, True])
def test_unreadable_child_subtree_denies_evidence_growth_and_preserves_all_guards(
    selected, tmp_path, monkeypatch, failure_active,
):
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    worker, _, _ = selected
    stage = tmp_path / "unreadable-finalization"
    stage.mkdir(mode=0o700)
    hidden = stage / "hidden-child-directory"
    hidden.mkdir(mode=0o700)
    retained = hidden / "retained-child-file"
    content = b"retained child content" * 1024
    retained.write_bytes(content)
    retained_info = retained.stat()
    hidden.chmod(0)
    hidden_info = hidden.stat()
    checked, writes = [], []

    def record(name, value):
        checked.append(name)
        return value

    monkeypatch.setattr(worker, "_snapshots", lambda: record("original", "original"))
    monkeypatch.setattr(worker.copying, "snapshot", lambda path: record("copy", "copy"))
    monkeypatch.setattr(worker, "_ledger", lambda: record("ledger", "ledger"))
    monkeypatch.setattr(worker, "_read", lambda path: record("config", b"config"))
    monkeypatch.setattr(worker, "_write", lambda *args: writes.append(args))

    def finish():
        worker._finalize_evidence(
            str(stage), [], None, [b"captured stdout", b"captured stderr"],
            "original", "synthetic-copy", "copy", "ledger", b"config", failure_active, False,
        )

    try:
        if failure_active:
            with pytest.raises(ValueError, match="original_child_failure"):
                try:
                    raise ValueError("original_child_failure")
                finally:
                    finish()
        else:
            with pytest.raises(ValueError, match="evidence_publication_failed"):
                finish()
        assert checked == ["original", "copy", "ledger", "config"]
        assert writes == []
        assert list(stage.iterdir()) == [hidden]
        assert hidden.stat() == hidden_info
    finally:
        # Disposable fixture restoration only; the worker never repairs or
        # deletes the child's unreadable directory to make an observation pass.
        hidden.chmod(0o700)
    assert retained.stat() == retained_info
    assert retained.read_bytes() == content


@pytest.mark.parametrize("publication", ["stdout", "protection"])
@pytest.mark.parametrize("failure_active", [False, True])
def test_partial_primary_is_preserved_and_fallback_rechecks_remaining_capacity(
    selected, tmp_path, monkeypatch, publication, failure_active,
):
    import json

    worker, _, _ = selected
    stage = tmp_path / "partial-finalization"
    stage.mkdir(mode=0o700)
    unit = max(512, getattr(stage.stat(), "st_blksize", 4096))
    if hasattr(os, "statvfs"):
        fs = os.statvfs(stage)
        unit = max(unit, fs.f_bsize, fs.f_frsize)
    logical, allocated = worker._stage_size(str(stage))
    data = [b"x" * observer.FRAME_BYTES, b""] if publication == "stdout" else [b"", b""]
    content_blocks = (len(data[0]) + unit - 1) // unit if publication == "stdout" else 1
    limit = max(logical, allocated) + (content_blocks + 2) * unit
    monkeypatch.setattr(observer, "STAGE_BYTES", limit)
    checked, writes = [], []
    real_write = worker._write
    leaf = "ocean.stdout" if publication == "stdout" else "protection-check.json"
    partial = []

    def write(path, raw):
        writes.append(Path(path).name)
        if Path(path).name == leaf:
            partial.append(raw[:max(1, len(raw) // 2)])
            real_write(path, partial[-1])
            raise OSError("synthetic partial publication")
        real_write(path, raw)

    def record(name, value):
        checked.append(name)
        return value

    monkeypatch.setattr(worker, "_write", write)
    monkeypatch.setattr(worker, "_snapshots", lambda: record("original", "original"))
    monkeypatch.setattr(worker.copying, "snapshot", lambda path: record("copy", "copy"))
    monkeypatch.setattr(worker, "_ledger", lambda: record("ledger", "ledger"))
    monkeypatch.setattr(worker, "_read", lambda path: record("config", b"config"))

    def finish():
        worker._finalize_evidence(
            str(stage), [], None, data, "original", "synthetic-copy", "copy", "ledger",
            b"config", failure_active, False,
        )

    if failure_active:
        with pytest.raises(ValueError, match="original_child_failure"):
            try:
                raise ValueError("original_child_failure")
            finally:
                finish()
    else:
        with pytest.raises(ValueError, match="evidence_publication_failed"):
            finish()
    assert checked == ["original", "copy", "ledger", "config"]
    assert (stage / leaf).read_bytes() == partial[0]
    assert not (stage / ("ocean.stdout-fallback" if publication == "stdout"
                         else "protection-check-fallback.json")).exists()
    assert not any(name.endswith("fallback") or name.endswith("fallback.json") for name in writes)
    assert max(worker._stage_size(str(stage))) <= limit
    if publication == "stdout":
        guard = json.loads((stage / "protection-check.json").read_bytes())
        assert guard["stream_publication"]["stdout"] == "FAILED"
        assert guard["finalization_errors"] == ["publish_stdout", "publish_stdout_fallback"]


@pytest.mark.skipif(os.name != "posix", reason="actual sparse child stage and allocated blocks")
@pytest.mark.parametrize("exit_code", [0, 3])
def test_sparse_child_near_logical_bound_prevents_unbudgeted_final_evidence(
    selected, controlled_inventory, monkeypatch, request, exit_code,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    ready_read, ready_write = os.pipe()
    ready_reader = os.fdopen(ready_read, "rb", buffering=0)
    request.addfinalizer(ready_reader.close)
    ready_writer = os.fdopen(ready_write, "wb", buffering=0)
    request.addfinalizer(ready_writer.close)
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    executable.write_text(
        f"#!{sys.executable}\nimport os\n"
        "with open('binding-frame.txt','wb') as frame:\n frame.write(b'synthetic frame')\n"
        "os.write(1,b'captured stdout')\nos.write(2,b'captured stderr')\n"
        "size=sum(os.lstat(os.path.join(p,n)).st_size for p,ds,ns in os.walk('.') for n in ns)\n"
        "with open('retained-sparse','wb') as sparse:\n"
        f" sparse.truncate({observer.STAGE_BYTES}-size-1)\n"
        f"os.write({ready_write},b'R')\nos.close({ready_write})\n"
        f"raise SystemExit({exit_code})\n", encoding="utf-8",
    )
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 5)
    real_popen = observer.subprocess.Popen

    def coordinated_launch(*args, **kwargs):
        # This fixture targets final evidence capacity after stable child output.
        # Wait for explicit completion of every stage write before the worker's
        # first directory scan; otherwise a legitimate transient drift guard can
        # fire while the child creates its frame/sparse file. Do not reap the
        # leader: real /proc identity, group, exit status and all scans still run.
        kwargs["pass_fds"] = (ready_writer.fileno(),)
        process = real_popen(*args, **kwargs)
        try:
            assert observer.select.select([ready_reader], [], [], 5)[0], "child readiness timeout"
            assert ready_reader.read(1) == b"R"
        except BaseException:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            finally:
                try:
                    process.stdout.close()
                finally:
                    process.stderr.close()
            raise
        return process

    monkeypatch.setattr(observer.subprocess, "Popen", coordinated_launch)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        writes, checked = [], []
        real_write = worker._write
        real_snapshots, real_snapshot = worker._snapshots, worker.copying.snapshot
        real_ledger, real_read = worker._ledger, worker._read
        copied_path = stage + "/library/" + scan["cell"]

        def write(path, raw):
            writes.append(Path(path).name)
            return real_write(path, raw)

        def snapshots():
            checked.append("original")
            return real_snapshots()

        def snapshot(path):
            if path == copied_path:
                checked.append("copy")
            return real_snapshot(path)

        def ledger():
            checked.append("ledger")
            return real_ledger()

        def read(path):
            if path == stage + "/cds.lib":
                checked.append("config")
            return real_read(path)

        monkeypatch.setattr(worker, "_write", write)
        monkeypatch.setattr(worker, "_snapshots", snapshots)
        monkeypatch.setattr(worker.copying, "snapshot", snapshot)
        monkeypatch.setattr(worker, "_ledger", ledger)
        monkeypatch.setattr(worker, "_read", read)
        reason = "evidence_publication_failed" if exit_code == 0 else "program_failed"
        with pytest.raises(ValueError, match=reason):
            worker._program(stage, session, scan)
        assert writes == ["ocean-start-claimed.json"]
        assert all(checked.count(name) >= 2 for name in ("original", "copy", "ledger", "config"))
        sparse = Path(stage) / "retained-sparse"
        logical, allocated = worker._stage_size(stage)
        assert sparse.stat().st_size > observer.STAGE_BYTES // 2
        assert allocated < logical < observer.STAGE_BYTES
        assert not (Path(stage) / "protection-check.json").exists()
        assert not (Path(stage) / "protection-check-fallback.json").exists()
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)


@pytest.mark.skipif(os.name != "posix", reason="actual synthetic child stream-close failure")
@pytest.mark.parametrize("exit_code", [0, 3])
def test_stream_close_failure_keeps_conservation_and_primary_child_failure(
    selected, controlled_inventory, monkeypatch, exit_code,
):
    import json

    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    executable.write_text(
        f"#!{sys.executable}\nopen('binding-frame.txt','wb').write(b'synthetic frame')\n"
        f"raise SystemExit({exit_code})\n", encoding="utf-8",
    )
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 5)
    real_popen = observer.subprocess.Popen

    class CloseFault:
        def __init__(self, stream):
            self.stream = stream

        def fileno(self):
            return self.stream.fileno()

        def close(self):
            self.stream.close()
            raise OSError("synthetic close failure")

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        process.stdout = CloseFault(process.stdout)
        return process

    monkeypatch.setattr(observer.subprocess, "Popen", launch)
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        reason = "evidence_publication_failed" if exit_code == 0 else "program_failed"
        with pytest.raises(ValueError, match=reason):
            worker._program(stage, session, scan)
        guard = json.loads((Path(stage) / "protection-check.json").read_bytes())
        assert all(guard[name] for name in (
            "originals_preserved", "owned_copy_preserved", "ledger_preserved", "cds_lib_preserved",
        ))
        assert guard["finalization_errors"] == ["close_stream_0"]
        assert guard["failure_active"] is (exit_code != 0)
        assert (Path(stage) / "ocean.stdout").is_file()
        assert (Path(stage) / "ocean.stderr").is_file()
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)


@pytest.mark.skipif(os.name != "posix", reason="actual permissions and ordinary-user preflight")
def test_preflight_rejects_active_work_and_disk_floor_without_start(
    selected, controlled_inventory, monkeypatch,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    before = worker._ledger()
    with worker.accounting.ReservationSession(worker.root) as session:
        marker = Path(worker.root) / worker.accounting.JOBS / "active"
        marker.write_bytes(b"retained active evidence")
        with pytest.raises(ValueError, match="active_work"):
            worker._stage(scan, session)
        assert not (Path(worker.root) / "binding-observations").exists()
        # Synthetic fixture action only; actual observer never removes markers.
        marker.unlink()
        worker.profile["limits"]["disk_floor_bytes"] = 10**30
        with pytest.raises(ValueError, match="disk_floor"):
            worker._stage(scan, session)
    assert worker._ledger() == before


@pytest.mark.parametrize("case", ["eda", "benign", "other-uid", "denied", "vanished", "gone"])
def test_conflicting_process_inventory_is_fail_closed(selected, monkeypatch, case):
    worker, _, _ = selected
    uid = 12345
    with monkeypatch.context() as patch:
        patch.setattr(observer.os, "getuid", lambda: uid, raising=False)
        patch.setattr(observer.os, "getpid", lambda: 98764)
        patch.setattr(observer.os, "listdir", lambda path: ["self", "98764", "98765"])
        patch.setattr(observer.os, "stat", lambda path: SimpleNamespace(
            st_uid=uid + (case == "other-uid")))

        def target(path):
            assert path == "/proc/98765/exe"
            if case in ("denied", "vanished", "gone"):
                code = {"denied": errno.EACCES, "vanished": errno.ENOENT,
                        "gone": errno.ESRCH}[case]
                raise OSError(code, "synthetic process visibility")
            assert case != "other-uid"
            return "/synthetic/Spectre" if case == "eda" else "/synthetic/python"

        patch.setattr(observer.os, "readlink", target)
        if case == "eda":
            with pytest.raises(ValueError, match="active_eda_process"):
                worker._check_conflicting_processes()
        elif case == "denied":
            with pytest.raises(PermissionError) as raised:
                worker._check_conflicting_processes()
            assert raised.value.errno == errno.EACCES
        else:
            worker._check_conflicting_processes()


@pytest.mark.skipif(os.name != "posix", reason="ordinary-user POSIX prelaunch failure")
def test_unknown_same_uid_process_prevents_stage_and_start(selected, monkeypatch):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    before = worker._ledger()

    def denied():
        raise OSError(errno.EACCES, "synthetic protected same-UID process")

    monkeypatch.setattr(worker, "_check_conflicting_processes", denied)
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: pytest.fail("EDA start"))
    with (
        worker.accounting.ReservationSession(worker.root) as session,
        pytest.raises(PermissionError),
    ):
        worker._stage(scan, session)
    assert not (Path(worker.root) / "binding-observations").exists()
    assert worker._ledger() == before
