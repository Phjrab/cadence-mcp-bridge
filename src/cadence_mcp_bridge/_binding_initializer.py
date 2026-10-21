"""Closed registered-library metadata recipe; no discovery or execution authority.

Only root and top-level .il/.ils/.cxt metadata in registered installation
libraries can change. Whole original trees remain bound; new pins are linked
evidence, never an automatic registration update or runtime attestation.
"""
# mypy: ignore-errors
# ruff: noqa: UP031, B905
import copy
import os
import stat
import types

RECIPE = "standard-vm-registered-initializers-v1"
LIBRARIES = 8
ENTRIES = 8192
BYTES = 67108864
TARGETS = 128


def build_accounting(profile, registration, storage):
    """Reuse existing exact accounting guards without formatter/trust assertions."""
    class InitializerAccounting(storage.StorageAdmin):
        def __init__(self):
            self.config = dict(
                hostname=profile["host"]["hostname"],
                architecture=profile["host"]["architecture"],
                user=profile["host"]["user"], managed_root=profile["paths"]["managed_root"],
                identity_manifest_sha256=registration["identity_manifest_sha256"],
            )
            self.root = self.config["managed_root"]
            self.domain = storage.digest(storage.canonical(dict(
                hostname=self.config["hostname"].lower().rstrip("."),
                architecture=self.config["architecture"],
            )))
            self.directories, self.fds = {}, []
            self.deadline = os.times()[4] + 60
            self.cancelled, self.lock = False, None
            self.protected, self.absent_protected = {}, []

    return InitializerAccounting()


def _libraries(profile, registration, core):
    names, locations = {}, {}
    roots = profile["paths"]["protected_roots"]
    workspace, managed = profile["paths"]["workspace_root"], profile["paths"]["managed_root"]
    for route in registration["routes"]:
        for row in route["libraries"]:
            if set(row) != set(("name", "path", "tree_sha256")):
                raise ValueError("initializer_library_shape")
            path = core.valid_path(row["path"])
            if core.inside(path, managed) or not any(
                core.inside(path, root) for root in [workspace] + list(roots)
            ):
                raise ValueError("initializer_library_scope")
            name = row["name"]
            if name in names and names[name] != row or (
                path in locations and locations[path] != name
            ):
                raise ValueError("initializer_library_alias")
            names[name], locations[path] = row, name
    if not 1 <= len(names) <= LIBRARIES:
        raise ValueError("initializer_library_bound")
    paths = sorted(locations)
    if any(core.inside(right, left) for index, left in enumerate(paths)
           for right in paths[index + 1:]):
        raise ValueError("initializer_overlapping_library_roots")
    return [copy.deepcopy(names[name]) for name in sorted(names)]


def _operator_uid(profile):
    import pwd
    uid = pwd.getpwnam(profile["host"]["user"]).pw_uid
    if uid == 0:
        raise ValueError("initializer_ordinary_operator_required")
    return uid


def _installation_libraries(profile, libraries, core):
    protected = [root for root in profile["paths"]["protected_roots"]
                 if any(core.inside(tool["path"], root) for tool in profile["tools"].values())]
    return [row for row in libraries if any(core.inside(row["path"], root)
                                            for root in protected)]


def _ancestors(profile, libraries, core):
    uid, paths = _operator_uid(profile), set()
    for library in _installation_libraries(profile, libraries, core):
        path = os.path.dirname(library["path"])
        for _unused in range(128):
            paths.add(path)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        else:
            raise ValueError("initializer_ancestor_bound")
    records = []
    for path in sorted(paths, reverse=True):
        if path == "/":
            fd = os.open("/", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_DIRECTORY)
            try:
                observed = core.snapshot_descriptor(path, fd)
            finally:
                os.close(fd)
        else:
            observed = core.snapshot(path)
        if observed["kind"] != "directory" or observed["uid"] not in (0, uid) or (
            observed["mode"] & 18
        ):
            raise ValueError("initializer_ancestor_trust")
        records.append(observed)
    return sorted(records, key=lambda row: row["path"])


def _namespace(snapshots):
    result = []
    seen = set()

    def record(path):
        if path in seen:
            return
        seen.add(path)
        if len(seen) > ENTRIES + LIBRARIES * 128:
            raise ValueError("initializer_namespace_bound")
        info = os.lstat(path)
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or (
            os.path.realpath(path) != path
        ):
            raise ValueError("initializer_namespace_type")
        result.append([path, info.st_dev, info.st_ino, info.st_mode,
                       info.st_uid, info.st_gid, info.st_nlink, info.st_size,
                       "%.17g" % info.st_mtime, "%.17g" % info.st_ctime])

    for library, observed in snapshots:
        for row in observed["metadata"]:
            record(library["path"] + ("/" + row[1] if row[1] else ""))
        ancestor = os.path.dirname(library["path"])
        for _unused in range(128):
            record(ancestor)
            parent = os.path.dirname(ancestor)
            if parent == ancestor:
                break
            ancestor = parent
        else:
            raise ValueError("initializer_ancestor_bound")
    return sorted(result)


def _observe(libraries, copying, core):
    before_limits = copying.MAX_ENTRIES, copying.MAX_BYTES
    original_os = copying.os
    bounded_os = types.ModuleType("initializer_copy_os")
    bounded_os.__dict__.update(original_os.__dict__)

    def bounded_names(path):
        fd = core.open_fixed(path)
        try:
            return core.bounded_directory_names(fd)
        finally:
            os.close(fd)

    bounded_os.listdir = bounded_names
    copying.os = bounded_os
    snapshots, remaining_entries, remaining_bytes = [], ENTRIES, BYTES
    try:
        for library in libraries:
            if remaining_entries < 1 or remaining_bytes < 0:
                raise ValueError("initializer_combined_bound")
            copying.MAX_ENTRIES, copying.MAX_BYTES = min(4096, remaining_entries), remaining_bytes
            observed = copying.dependency_snapshot(library["path"])
            remaining_entries -= observed["entries"]
            remaining_bytes -= observed["bytes"]
            snapshots.append([copy.deepcopy(library), observed])
        namespace = _namespace(snapshots)
        # A later library/read must not invalidate any earlier member. The
        # existing helper additionally checks held regular descriptors.
        for library, first in snapshots:
            copying.MAX_ENTRIES, copying.MAX_BYTES = first["entries"], first["bytes"]
            if copying.dependency_snapshot(library["path"]) != first:
                raise ValueError("initializer_tree_scan_drift")
        if _namespace(snapshots) != namespace:
            raise ValueError("initializer_namespace_scan_drift")
        return snapshots, namespace
    finally:
        copying.MAX_ENTRIES, copying.MAX_BYTES = before_limits
        copying.os = original_os


def _selected(profile, snapshots, core):
    roots, paths = [], []
    eligible = set(row["path"] for row in _installation_libraries(
        profile, [library for library, snap in snapshots], core))
    for library, observed in snapshots:
        # Workspace libraries are conserved but cannot expand the installation
        # administrator recipe. Their behavior remains a separate trust gate.
        if library["path"] not in eligible:
            continue
        code = [row for row in observed["metadata"] if row[0] == "file" and
                "/" not in row[1] and row[1].endswith((".il", ".ils", ".cxt"))]
        if not code:
            continue
        roots.append(library["path"])
        paths.append(library["path"])
        paths.extend(library["path"] + "/" + row[1] for row in code)
    if not 1 <= len(roots) <= 3 or not 1 <= len(set(paths)) <= TARGETS:
        raise ValueError("initializer_fixed_target_bound")
    return sorted(set(roots)), sorted(set(paths))


def inventory(profile, registration, copying, core, enforce_registered=True):
    libraries = _libraries(profile, registration, core)
    core.verify_unlisted_ancestors([row["path"] for row in
        _installation_libraries(profile, libraries, core)])
    snapshots, namespace = _observe(libraries, copying, core)
    ancestors = _ancestors(profile, libraries, core)
    if enforce_registered and any(
        snap["tree_sha256"] != library["tree_sha256"] for library, snap in snapshots
    ):
        raise ValueError("initializer_registered_tree_drift")
    roots, paths = _selected(profile, snapshots, core)
    result = core.plan(dict(installation_roots=roots, paths=paths, links=[],
        profile_sha256=core.digest(profile),
        resource_lock=profile["paths"]["managed_root"] + "/run.lock"))
    uid = _operator_uid(profile)
    if any(row["uid"] not in (0, uid) for row in result["plan"]["records"]):
        raise ValueError("initializer_target_owner_trust")
    if _namespace(snapshots) != namespace:
        raise ValueError("initializer_inventory_read_drift")
    plan = result["plan"]
    plan.update(schema_version=2, recipe_id=RECIPE, profile=copy.deepcopy(profile),
                registration=copy.deepcopy(registration), library_snapshots=snapshots,
                library_namespace=namespace, ancestor_acl_records=ancestors,
                runtime_trust_assessed=False, registration_updated=False)
    result["plan_sha256"] = core.digest(plan)
    return core.bounded_inventory(result)


def verify_delta(original, copying, core, rollback=False, partial=False, final_guard=None):
    if original.get("recipe_id") != RECIPE or original.get("schema_version") != 2:
        raise ValueError("initializer_fixed_recipe_required")
    libraries = _libraries(original["profile"], original["registration"], core)
    core.verify_unlisted_ancestors([row["path"] for row in
        _installation_libraries(original["profile"], libraries, core)])
    observed, namespace = _observe(libraries, copying, core)
    roots, paths = _selected(original["profile"], observed, core)
    if roots != original["scope"]["installation_roots"] or paths != original["scope"]["paths"]:
        raise ValueError("initializer_fixed_scope_drift")
    expected_selected = dict((row["path"], row) for row in original["records"])
    if sorted(expected_selected) != paths:
        raise ValueError("initializer_target_record_binding")
    uid = _operator_uid(original["profile"])
    if any(row["uid"] not in (0, uid) for row in expected_selected.values()):
        raise ValueError("initializer_target_owner_trust")
    transitions = []
    if len(observed) != len(original["library_snapshots"]):
        raise ValueError("initializer_library_count_drift")
    for (library, before), (current_library, after) in zip(original["library_snapshots"], observed):
        if before["tree_sha256"] != library["tree_sha256"] or (
            copying.digest(copying.canonical(before["metadata"])) != before["tree_sha256"]
        ):
            raise ValueError("initializer_original_registration_binding")
        if library != current_library or before["content_sha256"] != after["content_sha256"] or (
            before["entries"] != after["entries"] or before["bytes"] != after["bytes"]
            or len(before["metadata"]) != len(after["metadata"])
        ):
            raise ValueError("initializer_library_content_drift")
        for old, now in zip(before["metadata"], after["metadata"]):
            selected_path = library["path"] + ("/" + old[1] if old[1] else "")
            expected = list(old)
            if selected_path in expected_selected:
                target = expected_selected[selected_path]
                if old[2] != target["mode"] or target["after_mode"] != old[2] & ~18:
                    raise ValueError("initializer_original_mode_binding")
                expected[2] = old[2] if rollback else target["after_mode"]
                if partial and now[2] in (old[2], target["after_mode"]):
                    expected[2] = now[2]
            if now != expected:
                raise ValueError("initializer_unapproved_tree_metadata_drift")
        transitions.append(dict(name=library["name"], path=library["path"],
            original_tree_sha256=before["tree_sha256"], current_tree_sha256=after["tree_sha256"],
            content_sha256=before["content_sha256"]))
    if len(namespace) != len(original["library_namespace"]):
        raise ValueError("initializer_namespace_membership_drift")
    for old, now in zip(original["library_namespace"], namespace):
        expected = list(old)
        selected = expected_selected.get(old[0])
        if selected is not None:
            target = selected["mode"] if rollback else selected["after_mode"]
            if partial and stat.S_IMODE(now[3]) in (selected["mode"], selected["after_mode"]):
                target = stat.S_IMODE(now[3])
            expected[3] = stat.S_IFMT(old[3]) | target
            # fchmod/setfacl legitimately change selected ctime, including a
            # partial apply or restoration. No other inode/security field moves.
            if selected["mode"] != selected["after_mode"] or (
                core.normalize_acl(selected["acl"]) != core.normalize_acl(selected["after_acl"])
            ):
                expected[9] = now[9]
        if expected != now:
            raise ValueError("initializer_unapproved_identity_drift")
    ancestors = _ancestors(original["profile"], libraries, core)
    if len(ancestors) != len(original["ancestor_acl_records"]):
        raise ValueError("initializer_ancestor_acl_scope_drift")
    for old, now in zip(original["ancestor_acl_records"], ancestors):
        if set(old) != set(now) or any(
            (core.normalize_acl(old[key]) != core.normalize_acl(now[key])
             if key == "acl" else not core.metadata_equal(key, old[key], now[key]))
            for key in old
        ):
            raise ValueError("initializer_ancestor_acl_drift")
    for selected_path in paths:
        old = expected_selected[selected_path]
        now = core.snapshot(selected_path)
        if any(not core.metadata_equal(key, old[key], now[key]) for key in
               ("path", "dev", "ino", "uid", "gid", "kind", "size", "mtime", "sha256")):
            raise ValueError("initializer_selected_protected_drift")
        if old["after_mode"] != old["mode"] & ~18 or (
            core.normalize_acl(old["after_acl"]) !=
            core.normalize_acl(core.restricted_acl(old["acl"]))
        ):
            raise ValueError("initializer_selected_plan_drift")
        mode, acl = ((old["mode"], old["acl"]) if rollback else
                     (old["after_mode"], old["after_acl"]))
        candidates = [(mode, acl)]
        if partial:
            candidates = [(old["mode"], old["acl"]), (old["after_mode"], old["after_acl"]),
                (old["after_mode"], core.chmod_acl(old["acl"], old["after_mode"])),
                (old["mode"], core.chmod_acl(old["after_acl"], old["mode"]))]
        if not any(now["mode"] == mode and
                   core.normalize_acl(now["acl"]) == core.normalize_acl(acl)
                   for mode, acl in candidates):
            raise ValueError("initializer_selected_acl_drift")
    if final_guard is not None:
        final_guard()
    # No content/ACL/accounting read follows this complete namespace witness.
    # In particular, the last accounting read cannot revert selected metadata
    # after strict comparison and still yield a successful terminal response.
    if _namespace(observed) != namespace:
        raise ValueError("initializer_selected_read_union_drift")
    return dict(schema_version=1, kind="INITIALIZER_ALLOWED_METADATA_DELTA",
        plan_sha256=core.digest(original), rollback=rollback,
        selected_targets=len(paths), libraries=transitions, content_preserved=True,
        owner_group_preserved=True, registration_updated=False,
        runtime_trust_assessed=False, execution_authorized=False,
        receipt_provenance_assessed=False)


def mutate(request, copying, core, rollback=False, accounting=None):
    if accounting is None or accounting.lock is None:
        raise ValueError("initializer_entered_accounting_guard_required")
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError("initializer_administrator_required")
    if set(request) != set(("plan", "expected_plan_sha256", "operator_authority")):
        raise ValueError("initializer_mutation_shape")
    authority = request["operator_authority"]
    if not isinstance(authority, core.TEXT) or not 1 <= len(authority) <= 512:
        raise ValueError("initializer_operator_authority_required")
    if len(core.canonical(request)) + 1 > core.LIMIT:
        raise ValueError("initializer_mutation_bound")
    original = request["plan"]
    if core.digest(original) != request["expected_plan_sha256"]:
        raise ValueError("initializer_plan_binding")
    if original["scope"]["resource_lock"] != accounting.root + "/run.lock" or (
        original["registration"]["identity_manifest_sha256"] !=
        accounting.config["identity_manifest_sha256"]
    ):
        raise ValueError("initializer_accounting_binding")
    for field in ("hostname", "architecture", "user"):
        if accounting.config[field] != original["profile"]["host"][field]:
            raise ValueError("initializer_accounting_host_binding")

    def guard():
        accounting.guard()
        verify_delta(original, copying, core, rollback, True)
        accounting.guard()

    guard()
    # Use only a fresh authenticated private core module. Neither the global
    # product module nor its fixed installation recipe is widened.
    saved_completion, saved_emit = core.completion_inventory, core.emit
    events = []
    try:
        core.completion_inventory = lambda plan: inventory(
            plan["profile"], plan["registration"], copying, core, False)["plan"]
        core.emit = lambda event: events.append(event)
        core.authenticate_applied_plan(request, rollback)
        guard()
        core._mutate_locked(request, rollback, True, guard)
        # Recheck selected final ACLs as well as every tree metadata row. The
        # generic completion already conserves each selected content/owner.
        core.verify_completed_targets(original, rollback, True)
        guard()
        core.verify_applied_receipt(request)
        accounting.guard()
        # Finish with a strict projection. A later receipt/completion read must
        # not restore a selected before-state and still yield apply success.
        delta = verify_delta(original, copying, core, rollback,
                             final_guard=accounting.guard)
        delta["changed"] = sum(1 for event in events if event.get("event") == "changed")
        delta["metadata_changes_explicit"] = True
        delta["observed_plan_sha256"] = core.digest(original)
        delta["applied_plan_receipt_sha256"] = copying.digest(core.receipt_bytes(original))
        delta["receipt_provenance_assessed"] = True
        return delta
    finally:
        core.completion_inventory, core.emit = saved_completion, saved_emit
