"""Synthetic invariant cases and separately labeled owned Linux metadata work."""

import base64
import copy
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from importlib.resources import files
from types import SimpleNamespace

import pytest

from cadence_mcp_bridge import _binding_initializer as recipe
from cadence_mcp_bridge import _installation_repair as repair
from cadence_mcp_bridge import _native_copy as native_copy


def _acl(mode):
    return "".join(
        role + "::" + "".join(flag if (mode >> shift) & bit else "-"
                             for flag, bit in (("r", 4), ("w", 2), ("x", 1))) + "\n"
        for role, shift in (("user", 6), ("group", 3), ("other", 0))
    )


def _snapshot(metadata):
    content = [["directory", row[1]] if row[0] == "directory" else
               ["file", row[1], row[6], row[7]] for row in metadata]
    return dict(schema_version=2, tree_sha256=native_copy.digest(native_copy.canonical(metadata)),
                content_sha256=native_copy.digest(native_copy.canonical(content)),
                entries=len(metadata), bytes=sum(row[6] for row in metadata if row[0] == "file"),
                metadata=metadata)


@pytest.fixture
def fixture(monkeypatch):
    profile = dict(host=dict(hostname="standard-vm", architecture="i686", user="operator"),
        tools=dict(ocean=dict(path="/opt/eda/IC/tools/bin/ocean")),
        paths=dict(protected_roots=["/opt/eda"], workspace_root="/home/operator/work",
                   managed_root="/home/operator/work/.cadence_mcp"))
    metadata = [["directory", "", 0o775, 0, 0, "100.000000000"],
                ["file", "libInit.il", 0o664, 0, 0, "100.000000000", 3, "a" * 64, 1],
                ["file", "context.cxt", 0o644, 0, 0, "100.000000000", 3, "b" * 64, 1],
                ["directory", "cell", 0o755, 0, 0, "100.000000000"],
                ["file", "cell/sch.oa", 0o644, 0, 0, "100.000000000", 3, "c" * 64, 1]]
    initial = _snapshot(metadata)
    library = dict(name="ReferenceLib", path="/opt/eda/lib", tree_sha256=initial["tree_sha256"])
    registration = dict(identity_manifest_sha256="d" * 64, routes=[dict(libraries=[library])])
    namespace = [["/opt/eda/lib" + ("/" + row[1] if row[1] else ""), 1, i + 10,
                  (stat.S_IFDIR if row[0] == "directory" else stat.S_IFREG) | row[2],
                  row[3], row[4], 2 if row[0] == "directory" else 1,
                  64 if row[0] == "directory" else row[6], "100", "100"]
                 for i, row in enumerate(metadata)]
    state = dict(snapshots=[[library, initial]], namespace=sorted(namespace), acls={})
    fake_core = SimpleNamespace(**{name: getattr(repair, name) for name in dir(repair)
                                  if not name.startswith("__")})

    def core_snapshot(path):
        row = next(row for row in state["snapshots"][0][1]["metadata"]
                   if path == "/opt/eda/lib" + ("/" + row[1] if row[1] else ""))
        identity = next(item for item in state["namespace"] if item[0] == path)
        return dict(path=path, dev=identity[1], ino=identity[2], mode=row[2], uid=row[3],
                    gid=row[4], kind="file" if row[0] == "file" else "directory",
                    size=row[6] if row[0] == "file" else None,
                    mtime=row[5] if row[0] == "file" else None,
                    sha256=row[7] if row[0] == "file" else None,
                    acl=state["acls"].get(path, _acl(row[2])))

    def core_plan(scope):
        records = []
        for path in scope["paths"]:
            row = core_snapshot(path)
            row.update(after_mode=row["mode"] & ~0o022,
                after_acl=repair.restricted_acl(row["acl"]),
                reason="remove_shared_code_write_preserve_content_owner_rx")
            records.append(row)
        plan = dict(schema_version=1, scope=copy.deepcopy(scope), records=records)
        return dict(plan=plan, plan_sha256=repair.digest(plan))

    fake_core.snapshot, fake_core.plan = core_snapshot, core_plan
    fake_core.verify_unlisted_ancestors = lambda *_: None
    monkeypatch.setattr(recipe, "_operator_uid", lambda _: 500)
    monkeypatch.setattr(recipe, "_ancestors", lambda *_: [])
    monkeypatch.setattr(recipe, "_observe", lambda *_: copy.deepcopy(
        (state["snapshots"], state["namespace"])))
    monkeypatch.setattr(recipe, "_namespace", lambda *_: copy.deepcopy(state["namespace"]))
    result = recipe.inventory(profile, registration, native_copy, fake_core)
    return profile, registration, state, fake_core, result["plan"]


def _apply(state, original):
    selected = {row["path"]: row for row in original["records"]}
    for library, snap in state["snapshots"]:
        for row in snap["metadata"]:
            path = library["path"] + ("/" + row[1] if row[1] else "")
            if path in selected:
                row[2] = selected[path]["after_mode"]
        snap.update(_snapshot(snap["metadata"]))
    for row in state["namespace"]:
        if row[0] in selected:
            old = selected[row[0]]
            row[3] = stat.S_IFMT(row[3]) | old["after_mode"]
            if old["mode"] != old["after_mode"]:
                row[9] = "101"


def test_inventory_selects_only_exact_top_level_code_and_preserves_original_pins(fixture):
    _, registration, _, _, plan = fixture
    assert plan["scope"]["paths"] == ["/opt/eda/lib", "/opt/eda/lib/context.cxt",
                                         "/opt/eda/lib/libInit.il"]
    assert plan["registration"] == registration
    assert not plan["runtime_trust_assessed"] and not plan["registration_updated"]
    assert all("cell" not in row["path"] for row in plan["records"])


def test_exact_apply_projection_links_new_pin_without_rebaseline(fixture):
    _, registration, state, core, plan = fixture
    retained = copy.deepcopy(plan)
    _apply(state, plan)
    delta = recipe.verify_delta(plan, native_copy, core)
    assert delta["libraries"][0]["original_tree_sha256"] != delta["libraries"][0][
        "current_tree_sha256"]
    assert delta["libraries"][0]["original_tree_sha256"] == registration["routes"][0][
        "libraries"][0]["tree_sha256"]
    assert delta["content_preserved"] and not delta["registration_updated"]
    assert not delta["runtime_trust_assessed"] and plan == retained


@pytest.mark.parametrize("change", ["content", "nonselected-mode", "owner", "mtime", "inode",
    "nonselected-ctime", "link", "extra", "missing", "selected-execute", "acl", "fake-baseline"])
def test_unapproved_delta_never_becomes_a_new_baseline(fixture, change):
    _, _, state, core, plan = fixture
    _apply(state, plan)
    snap = state["snapshots"][0][1]
    if change == "content":
        snap["metadata"][-1][7] = "f" * 64
    elif change == "nonselected-mode":
        snap["metadata"][-1][2] = 0o600
    elif change == "owner":
        snap["metadata"][-1][3] = 501
    elif change == "mtime":
        snap["metadata"][-1][5] = "101.000000000"
    elif change == "inode":
        state["namespace"][-1][2] += 1
    elif change == "nonselected-ctime":
        next(row for row in state["namespace"] if row[0].endswith("sch.oa"))[9] = "101"
    elif change == "link":
        snap["metadata"][-1][-1] = 2
    elif change == "extra":
        snap["metadata"].append(["file", "new.il", 0o644, 0, 0, "100", 0, "e" * 64, 1])
    elif change == "missing":
        snap["metadata"].pop()
    elif change == "selected-execute":
        snap["metadata"][1][2] |= 0o100
    elif change == "acl":
        state["acls"]["/opt/eda/lib/libInit.il"] = "user::rw-\ngroup::r--\nother::---\n"
    else:
        plan["library_snapshots"][0][1]["metadata"][-1][2] = 0o600
    snap.update(_snapshot(snap["metadata"]))
    with pytest.raises(ValueError, match="initializer_"):
        recipe.verify_delta(plan, native_copy, core)


def test_partial_projection_accepts_only_original_or_planned_state(fixture):
    _, _, state, core, plan = fixture
    assert recipe.verify_delta(plan, native_copy, core, partial=True)["content_preserved"]
    with pytest.raises(ValueError):
        recipe.verify_delta(plan, native_copy, core)
    _apply(state, plan)
    assert recipe.verify_delta(plan, native_copy, core, partial=True)["content_preserved"]


def test_last_accounting_read_cannot_invalidate_strict_selected_metadata(fixture):
    _, _, state, core, plan = fixture
    _apply(state, plan)

    def last_accounting_read():
        state["snapshots"] = copy.deepcopy(plan["library_snapshots"])
        state["namespace"] = copy.deepcopy(plan["library_namespace"])

    with pytest.raises(ValueError, match="selected_read_union_drift"):
        recipe.verify_delta(plan, native_copy, core, final_guard=last_accounting_read)


def test_rollback_preserves_the_original_pin_and_reports_metadata_scope(fixture):
    _, _, _, core, plan = fixture
    delta = recipe.verify_delta(plan, native_copy, core, rollback=True)
    assert delta["rollback"] and delta["content_preserved"]
    assert delta["libraries"][0]["current_tree_sha256"] == delta["libraries"][0][
        "original_tree_sha256"]


def test_mutation_has_no_guardless_entry(fixture):
    _, _, _, core, plan = fixture
    with pytest.raises(ValueError, match="entered_accounting_guard_required"):
        recipe.mutate(dict(plan=plan, expected_plan_sha256=repair.digest(plan),
                           operator_authority="synthetic"), native_copy, core)


def test_accounting_reuses_existing_guards_without_formatter_assertions(fixture):
    from cadence_mcp_bridge import _binding_storage_admin as storage

    profile, registration, _, _, _ = fixture
    accounting = recipe.build_accounting(profile, registration, storage)
    assert isinstance(accounting, storage.StorageAdmin)
    assert accounting.guard.__func__ is storage.StorageAdmin.guard
    assert accounting.enter.__func__ is storage.StorageAdmin.enter
    assert not any("formatter" in key or "runtime" in key for key in accounting.config)
    assert accounting.protected == {} and accounting.lock is None


def _accounting(profile, registration):
    return SimpleNamespace(lock=7, root=profile["paths"]["managed_root"],
        config=dict(profile["host"], identity_manifest_sha256=registration[
            "identity_manifest_sha256"]), guard=lambda: None)


@pytest.mark.parametrize("authority", ["", None, 42, [], "x" * 513])
def test_authority_rejection_precedes_receipt_or_mutation(fixture, monkeypatch, authority):
    profile, registration, _, core, plan = fixture
    monkeypatch.setattr(recipe, "os", SimpleNamespace(getuid=lambda: 0, geteuid=lambda: 0))

    def denied(*_):
        raise AssertionError("invalid authority reached a mutating core path")

    core.authenticate_applied_plan, core._mutate_locked = denied, denied
    with pytest.raises(ValueError, match="operator_authority_required"):
        recipe.mutate(dict(plan=plan, expected_plan_sha256=repair.digest(plan),
                           operator_authority=authority), native_copy, core,
                      accounting=_accounting(profile, registration))


@pytest.mark.parametrize("late_drift", [False, True])
def test_final_strict_projection_follows_receipt_and_completion_reads(
    fixture, monkeypatch, late_drift,
):
    profile, registration, state, core, plan = fixture
    monkeypatch.setattr(recipe, "os", SimpleNamespace(getuid=lambda: 0, geteuid=lambda: 0))
    core.authenticate_applied_plan = lambda *_: None
    core.verify_completed_targets = lambda *_: None

    def perform(*args):
        _apply(state, plan)
        core.emit(dict(event="changed"))
        core.emit(dict(event="complete"))

    def receipt(*args):
        if late_drift:
            state["snapshots"] = copy.deepcopy(plan["library_snapshots"])
            state["namespace"] = copy.deepcopy(plan["library_namespace"])

    core._mutate_locked, core.verify_applied_receipt = perform, receipt
    core.receipt_bytes = lambda *_: b"retained synthetic observed-before receipt\n"
    request = dict(plan=plan, expected_plan_sha256=repair.digest(plan),
                   operator_authority="synthetic explicit test authority")
    accounting = _accounting(profile, registration)
    if late_drift:
        with pytest.raises(ValueError, match="unapproved_tree_metadata_drift"):
            recipe.mutate(request, native_copy, core, accounting=accounting)
    else:
        delta = recipe.mutate(request, native_copy, core, accounting=accounting)
        assert delta["receipt_provenance_assessed"] and delta["changed"] == 1
        assert delta["applied_plan_receipt_sha256"] == native_copy.digest(core.receipt_bytes(plan))
        assert delta["applied_plan_receipt_sha256"] != delta["observed_plan_sha256"]


def test_protected_user_library_is_conserved_but_excluded_from_admin_targets(fixture):
    profile, registration, state, core, _ = fixture
    profile["paths"]["protected_roots"].append("/home/operator/protected-design")
    first = copy.deepcopy(state["snapshots"][0])
    first[0].update(name="UserProtected", path="/home/operator/protected-design/lib")
    registration["routes"][0]["libraries"].append(first[0])
    selected = recipe._selected(profile, state["snapshots"] + [first], core)
    assert all(path.startswith("/opt/eda/") for path in selected[1])


def test_overlapping_registered_libraries_are_rejected(fixture):
    profile, registration, _, core, _ = fixture
    registration["routes"][0]["libraries"].append(dict(
        name="Nested", path="/opt/eda/lib/nested", tree_sha256="e" * 64))
    with pytest.raises(ValueError, match="overlapping_library_roots"):
        recipe._libraries(profile, registration, core)


def test_inventory_rejects_untrusted_selected_owner(fixture):
    profile, registration, state, core, _ = fixture
    state["snapshots"][0][1]["metadata"][1][3] = 501
    state["snapshots"][0][1].update(_snapshot(state["snapshots"][0][1]["metadata"]))
    registration["routes"][0]["libraries"][0]["tree_sha256"] = state["snapshots"][0][1][
        "tree_sha256"]
    with pytest.raises(ValueError, match="target_owner_trust"):
        recipe.inventory(profile, registration, native_copy, core)


def test_ancestor_conservation_cannot_substitute_for_ancestor_owner_trust(fixture, monkeypatch):
    profile, registration, _, core, _ = fixture
    resource = _fresh("_binding_initializer")
    monkeypatch.setattr(resource, "_operator_uid", lambda _: 500)
    core.snapshot = lambda path: dict(path=path, kind="directory", mode=0o755,
                                      uid=501, acl=_acl(0o755))
    with pytest.raises(ValueError, match="ancestor_trust"):
        resource._ancestors(profile, registration["routes"][0]["libraries"], core)


def _fresh(name):
    path = str(files("cadence_mcp_bridge").joinpath(name + ".py"))
    spec = importlib.util.spec_from_file_location("isolated_initializer_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(os.name != "posix", reason="owned Linux dirfd/chmod/ACL metadata evidence")
def test_owned_library_inventory_and_metadata_projection(tmp_path, monkeypatch):
    if shutil.which("getfacl") is None:
        pytest.skip("actual ACL inventory requires getfacl")
    copying, core = _fresh("_native_copy"), _fresh("_installation_repair")
    # This owned temporary tree is not an installed system hierarchy. The real
    # core ancestor trust behavior is covered by its dedicated POSIX cases.
    monkeypatch.setattr(core, "verify_unlisted_ancestors", lambda *_: None)
    monkeypatch.setattr(recipe, "_operator_uid", lambda _: os.getuid() or 65534)
    monkeypatch.setattr(recipe, "_ancestors", lambda *_: [])
    library = tmp_path / "library"
    library.mkdir(mode=0o775)
    code = library / "libInit.il"
    code.write_bytes(b"; synthetic initializer, never executed\n")
    original_oa = library / "preserved.oa"
    original_oa.write_bytes(b"owned synthetic OA bytes")
    code.chmod(0o664)
    library.chmod(0o775)
    before = copying.dependency_snapshot(str(library))
    profile = dict(tools=dict(ocean=dict(path=str(tmp_path / "tools" / "ocean"))),
                   paths=dict(workspace_root=str(tmp_path), managed_root=str(tmp_path / "managed"),
                             protected_roots=[str(tmp_path)]))
    registration = dict(routes=[dict(libraries=[dict(name="Synthetic", path=str(library),
                                                    tree_sha256=before["tree_sha256"])])])
    result = recipe.inventory(profile, registration, copying, core)
    code.chmod(0o644)
    library.chmod(0o755)
    delta = recipe.verify_delta(result["plan"], copying, core)
    assert delta["content_preserved"] and original_oa.read_bytes() == b"owned synthetic OA bytes"
    assert json.dumps(delta) and not delta["runtime_trust_assessed"]


@pytest.mark.skipif(os.name != "posix", reason="owned Linux core receipt/flock/ACL integration")
def test_owned_glue_reuses_core_receipt_apply_repeat_and_rollback(tmp_path, monkeypatch):
    if shutil.which("getfacl") is None or shutil.which("setfacl") is None:
        pytest.skip("actual core mutation requires ACL tools")
    import fcntl

    copying, core = _fresh("_native_copy"), _fresh("_installation_repair")
    library, managed = tmp_path / "library", tmp_path / "managed"
    library.mkdir()
    managed.mkdir(mode=0o700)
    code = library / "libInit.il"
    code.write_bytes(b"; synthetic owned code, never executed\n")
    code.chmod(0o664)
    library.chmod(0o775)
    lock = managed / "run.lock"
    lock.write_bytes(b"retained-owned-resource-lock")
    lock.chmod(0o600)
    profile = dict(host=dict(user="synthetic", hostname="synthetic", architecture="x86_64"),
        tools=dict(ocean=dict(path=str(tmp_path / "tools" / "ocean"))),
        paths=dict(workspace_root=str(tmp_path), managed_root=str(managed),
                   protected_roots=[str(tmp_path)]))
    registration = dict(identity_manifest_sha256="d" * 64,
        routes=[dict(libraries=[dict(name="Synthetic", path=str(library),
            tree_sha256=copying.dependency_snapshot(str(library))["tree_sha256"])])])
    # A disposable temp hierarchy and ordinary test identity do not prove the
    # actual administrator/ancestor gates. Their established core tests and
    # actual managed-VM qualification remain separate requirements.
    monkeypatch.setattr(core, "verify_unlisted_ancestors", lambda *_: None)
    monkeypatch.setattr(core, "verify_receipt_parent_chain", lambda *_: None)
    monkeypatch.setattr(recipe, "_ancestors", lambda *_: [])
    monkeypatch.setattr(recipe, "_operator_uid", lambda _: os.getuid() or 65534)
    result = recipe.inventory(profile, registration, copying, core)
    proxy = SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})
    proxy.getuid, proxy.geteuid = lambda: 0, lambda: 0
    monkeypatch.setattr(recipe, "os", proxy)
    fd, parentfd = core.open_fixed(str(lock)), core.open_fixed(str(managed))
    before, parent_before = os.fstat(fd), os.fstat(parentfd)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        accounting = _accounting(profile, registration)
        accounting.lock = fd
        accounting.guard = lambda: core.verify_resource_lock(
            str(lock), fd, parentfd, before, parent_before)
        request = dict(plan=result["plan"], expected_plan_sha256=result["plan_sha256"],
                       operator_authority="SYNTHETIC_OWNED_TEST_ONLY")
        applied = recipe.mutate(request, copying, core, accounting=accounting)
        assert applied["changed"] == 2 and code.stat().st_mode & 0o777 == 0o644
        assert applied["receipt_provenance_assessed"] and not applied["runtime_trust_assessed"]
        assert recipe.mutate(request, copying, core, accounting=accounting)["changed"] == 0
        restored = recipe.mutate(request, copying, core, rollback=True, accounting=accounting)
        assert restored["changed"] == 2 and code.stat().st_mode & 0o777 == 0o664
        assert restored["libraries"][0]["current_tree_sha256"] == result["plan"][
            "library_snapshots"][0][1]["tree_sha256"]
        assert code.read_bytes() == b"; synthetic owned code, never executed\n"
        assert lock.read_bytes() == b"retained-owned-resource-lock"
    finally:
        os.close(parentfd)
        os.close(fd)


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("CADENCE_TEST_INITIALIZER_ADMIN") != "1",
    reason="explicit disposable hosted administrator fixture only; no configured VM",
)
def test_actual_disposable_initializer_admin_partial_resume_repeat_rollback(tmp_path):
    """Real root/ordinary-user boundary and existing accounting, disposable only."""
    import pwd

    assert os.getuid() != 0
    assert str(tmp_path).startswith(pwd.getpwuid(os.getuid()).pw_dir + "/")
    library, managed = tmp_path / "library", tmp_path / ".cadence_mcp"
    library.mkdir()
    managed.mkdir(mode=0o700)
    code = library / "libInit.il"
    code.write_bytes(b"; owned hosted initializer fixture; never evaluated\n")
    code.chmod(0o664)
    library.chmod(0o775)
    oa = library / "preserved.oa"
    oa.write_bytes(b"owned synthetic protected OA\n")
    oa.chmod(0o644)
    for name in ("sim-mcp-v2-jobs", "reservation-identity"):
        (managed / name).mkdir(mode=0o700)
    profile = dict(host=dict(hostname=os.uname().nodename, architecture=os.uname().machine,
                            user=pwd.getpwuid(os.getuid()).pw_name),
        tools=dict(ocean=dict(path=str(tmp_path / "fixed-tools" / "ocean"))),
        paths=dict(workspace_root=str(tmp_path), managed_root=str(managed),
                   protected_roots=[str(tmp_path)]))
    domain = native_copy.digest(native_copy.canonical(dict(
        hostname=profile["host"]["hostname"].lower().rstrip("."),
        architecture=profile["host"]["architecture"])))
    anchor = dict(root_sha256=native_copy.digest(str(managed).encode()),
                  resource_domain_sha256=domain, ledger_ref="sim-mcp-v2-jobs/counter.json")
    registration = dict(identity_manifest_sha256=native_copy.digest(native_copy.canonical(anchor)),
        routes=[dict(libraries=[dict(name="OwnedHosted", path=str(library),
            tree_sha256=native_copy.dependency_snapshot(str(library))["tree_sha256"])])])
    protected = {"run.lock": b"retained lifecycle lock",
        "reservation-identity/manifest.json": native_copy.canonical(anchor),
        "sim-mcp-v2-jobs/counter.json": b'{"count":7,"result_reserved_bytes":1024}',
        "preserved-journal": b"owned synthetic journal, never reset"}
    for name, raw in protected.items():
        (managed / name).write_bytes(raw)
        (managed / name).chmod(0o600)

    def metadata(path):
        info = path.stat()
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    before = {name: metadata(managed / name) for name in protected}
    source_pins = {}
    for name in ("_installation_repair", "_native_copy", "_binding_storage_admin",
                 "_binding_initializer"):
        source_pins[name] = files("cadence_mcp_bridge").joinpath(name + ".py").read_bytes().replace(
            b"\r\n", b"\n")
    config = dict(profile=profile, registration=registration)
    # This test-only child embeds only exact installed resources and frozen
    # disposable configuration. It has no arbitrary path/source/command input.
    child = '''import sys
first = sys.path[0] if sys.path else None
sys.path[:] = [p for p in sys.path if p and p != first]
import os
sys.path[:] = [p for p in sys.path if os.path.isabs(p) and os.path.realpath(p) != os.getcwd()]
import base64, hashlib, json, types
CONFIG = json.loads(base64.b64decode(__CONFIG__).decode("ascii"))
SOURCES = __SOURCES__
PINS = __PINS__
loaded = {}
for name in sorted(SOURCES):
    raw = base64.b64decode(SOURCES[name])
    assert hashlib.sha256(raw).hexdigest() == PINS[name]
    module = types.ModuleType("owned_hosted_" + name)
    eval(compile(raw, "<fixed-owned-test-resource>", "exec"), module.__dict__)
    loaded[name] = module
core, copying = loaded["_installation_repair"], loaded["_native_copy"]
recipe, storage = loaded["_binding_initializer"], loaded["_binding_storage_admin"]
operation = sys.argv[1]
assert operation in ("plan", "partial", "apply", "rollback", "check")
if operation == "plan":
    result = recipe.inventory(CONFIG["profile"], CONFIG["registration"], copying, core)
else:
    request = json.loads(sys.stdin.read(core.LIMIT + 1))
    assert core.digest(request["plan"]) == request["expected_plan_sha256"] == sys.argv[2]
    assert request["plan"]["profile"] == CONFIG["profile"]
    assert request["plan"]["registration"] == CONFIG["registration"]
    if operation == "check":
        assert os.getuid() != 0
        result = recipe.verify_delta(request["plan"], copying, core)
    else:
        accounting = recipe.build_accounting(CONFIG["profile"], CONFIG["registration"], storage)
        try:
            accounting.enter()
            if operation == "partial":
                original_os = core.os
                proxy = types.ModuleType("owned_injected_partial_os")
                proxy.__dict__.update(original_os.__dict__)
                def partial(fd, mode):
                    original_os.fchmod(fd, mode)
                    raise ValueError("INTENTIONAL_OWNED_TEST_PARTIAL_AFTER_ONE_FCHMOD")
                proxy.fchmod = partial
                core.os = proxy
            result = recipe.mutate(request, copying, core, operation == "rollback", accounting)
        finally:
            accounting.close()
sys.stdout.write(core.canonical(result).decode("ascii") + chr(10))
'''.replace("__CONFIG__", repr(base64.b64encode(native_copy.canonical(config)).decode()))
    child = child.replace("__SOURCES__", repr({name: base64.b64encode(raw).decode()
                                             for name, raw in source_pins.items()}))
    child = child.replace("__PINS__", repr({name: native_copy.digest(raw)
                                          for name, raw in source_pins.items()}))
    helper = tmp_path / "fixed-owned-initializer-test.py"
    helper.write_bytes(child.encode("ascii"))
    helper.chmod(0o600)

    def invoke(operation, request=None, administrator=True):
        argv = [sys.executable, "-E", "-s", "-B", str(helper), operation]
        if administrator:
            argv = ["sudo", "-n"] + argv
        raw = None
        if request is not None:
            raw = native_copy.canonical(request)
            argv.append(request["expected_plan_sha256"])
        return subprocess.run(argv, input=raw, capture_output=True, timeout=90)

    planned = invoke("plan", administrator=False)
    assert planned.returncode == 0, planned.stderr.decode(errors="replace")
    observed = json.loads(planned.stdout)
    request = dict(plan=observed["plan"], expected_plan_sha256=observed["plan_sha256"],
                   operator_authority="EXPLICIT_DISPOSABLE_HOSTED_TEST_ONLY")
    partial = invoke("partial", request)
    assert partial.returncode != 0
    assert b"INTENTIONAL_OWNED_TEST_PARTIAL_AFTER_ONE_FCHMOD" in partial.stderr
    assert stat.S_IMODE(library.stat().st_mode) == 0o755
    assert stat.S_IMODE(code.stat().st_mode) == 0o664
    applied = invoke("apply", request)
    assert applied.returncode == 0, applied.stderr.decode(errors="replace")
    terminal = json.loads(applied.stdout)
    assert terminal["changed"] == 1 and terminal["receipt_provenance_assessed"]
    repeated = invoke("apply", request)
    assert repeated.returncode == 0, repeated.stderr.decode(errors="replace")
    assert json.loads(repeated.stdout)["changed"] == 0
    postcheck = invoke("check", request, administrator=False)
    assert postcheck.returncode == 0, postcheck.stderr.decode(errors="replace")
    assert not json.loads(postcheck.stdout)["receipt_provenance_assessed"]
    rolled_back = invoke("rollback", request)
    assert rolled_back.returncode == 0, rolled_back.stderr.decode(errors="replace")
    assert json.loads(rolled_back.stdout)["libraries"][0]["current_tree_sha256"] == registration[
        "routes"][0]["libraries"][0]["tree_sha256"]
    for name, raw in protected.items():
        assert metadata(managed / name) == before[name]
        assert (managed / name).read_bytes() == raw
    assert code.read_bytes() == b"; owned hosted initializer fixture; never evaluated\n"
    assert oa.read_bytes() == b"owned synthetic protected OA\n"
    assert not (managed / "reservation-identity" / "legacy-seal.json").exists()
    # Root-owned before receipts intentionally remain on the disposable hosted
    # runner. This test does not contact the registered Cadence VM or run EDA.
