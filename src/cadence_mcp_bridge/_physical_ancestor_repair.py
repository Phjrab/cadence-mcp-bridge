"""Fixed registered-library ancestor recipe; no vendor reads or EDA calls.

Compose with a fresh authenticated installation-repair module. Never modify the
active native modeltrust source or expose arbitrary targets through MCP.
"""

# mypy: ignore-errors
import os
import stat

RECIPE = "standard-vm-registered-library-ancestors-v1"
MAX_ANCESTORS = 64


def directory_paths(profile, registration, collector, core):
    roots, tools = collector.targets(profile, registration)
    installations = [root for root in roots if any(core.inside(tool, root) for tool in tools)]
    selected = set()
    for route in registration["routes"]:
        for library in route["libraries"]:
            leaf = library["path"]
            containers = [root for root in installations if core.inside(leaf, root)]
            if not containers:
                continue
            root = max(containers, key=len)
            # OA library leaves, cells, model contents and user work are excluded.
            current = os.path.dirname(leaf)
            while core.inside(current, root):
                core.valid_path(current)
                if os.path.realpath(current) != current:
                    raise ValueError("ancestor_recipe_alias")
                selected.add(current)
                if len(selected) > MAX_ANCESTORS:
                    raise ValueError("ancestor_recipe_bound")
                if current == root:
                    break
                current = os.path.dirname(current)
    if not selected:
        raise ValueError("ancestor_recipe_empty")
    return sorted(set(installations)), sorted(selected)


def inventory(profile, registration, collector, core):
    roots, paths = directory_paths(profile, registration, collector, core)
    if not hasattr(core, "_ancestor_snapshot_original"):
        core._ancestor_snapshot_original = core.snapshot_descriptor

        def directory_snapshot(path, fd):
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise ValueError("ancestor_recipe_directory_identity")
            return core._ancestor_snapshot_original(path, fd)

        core.snapshot_descriptor = directory_snapshot
    # Check roles BEFORE core.snapshot, which hashes regular files by design.
    directory_metadata = {}
    for path in paths:
        info = os.lstat(path)
        directory_metadata[path] = collector.metadata(info)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.getuid())
            or info.st_mode & 3584
        ):
            raise ValueError("ancestor_recipe_directory_identity")
    core.verify_unlisted_ancestors(roots)
    result = core.plan(
        {
            "installation_roots": roots,
            "paths": paths,
            "links": [],
            "profile_sha256": core.digest(profile),
            "resource_lock": profile["paths"]["managed_root"] + "/run.lock",
        }
    )
    for record in result["plan"]["records"]:
        if record["kind"] != "directory" or record["sha256"] is not None:
            raise ValueError("ancestor_recipe_directory_identity")
        # This first recipe preserves ACL semantics by accepting basic ACLs only.
        # Extended/default/named-user ACLs need a separately reviewed recipe.
        lines = core.normalize_acl(record["acl"])
        if len(lines) != 3 or set(line.rsplit(":", 1)[0] for line in lines) != set(
            ("user:", "group:", "other:")
        ):
            raise ValueError("ancestor_recipe_extended_acl")
    original = result["plan"]
    if any(
        collector.metadata(os.lstat(path)) != value for path, value in directory_metadata.items()
    ):
        raise ValueError("ancestor_recipe_inventory_drift")
    original.update(
        schema_version=2,
        recipe_id=RECIPE,
        profile=profile,
        registration=registration,
        directory_metadata=directory_metadata,
    )
    result["plan_sha256"] = core.digest(original)
    return core.bounded_inventory(result)


def mutate(request, collector, core, rollback=False):
    """Existing receipts, fixed resource flock and held-inode mutation guards."""
    if set(request) != set(("plan", "expected_plan_sha256", "operator_authority")):
        raise ValueError("mutation_shape")
    original = request["plan"]
    if (
        original.get("schema_version") != 2
        or original.get("recipe_id") != RECIPE
        or core.digest(original) != request["expected_plan_sha256"]
        or not isinstance(request["operator_authority"], core.TEXT)
        or not 1 <= len(request["operator_authority"]) <= 512
        or len(core.canonical(request)) + 1 > core.LIMIT
    ):
        raise ValueError("ancestor_recipe_binding")

    def completion(value):
        if value.get("recipe_id") != RECIPE:
            raise ValueError("ancestor_recipe_required")
        return inventory(value["profile"], value["registration"], collector, core)["plan"]

    # The caller supplies a fresh private core module, never the active runtime.
    core.completion_inventory = completion
    if completion(original)["scope"] != original["scope"]:
        raise ValueError("ancestor_recipe_scope")
    import fcntl

    lock = original["scope"]["resource_lock"]
    fd = core.open_fixed(lock)
    try:
        info = os.fstat(fd)
        parent_fd = core.open_fixed(os.path.dirname(lock))
        try:
            parent = os.fstat(parent_fd)
            administrator_for_owner = os.getuid() == 0 and info.st_uid == parent.st_uid
            if (
                not stat.S_ISDIR(parent.st_mode)
                or parent.st_mode & 18
                or not stat.S_ISREG(info.st_mode)
                or info.st_mode & 18
                or (info.st_uid not in (0, os.getuid()) and not administrator_for_owner)
                or info.st_nlink != 1
            ):
                raise ValueError("resource_lock_trust")

            def resource_guard():
                core.verify_resource_lock(lock, fd, parent_fd, info, parent)

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            resource_guard()
            core.authenticate_applied_plan(request, rollback)
            resource_guard()
            core._mutate_locked(request, rollback, True, resource_guard)
        finally:
            os.close(parent_fd)
    finally:
        os.close(fd)


def run(request, setup, assets, known, collector, core):
    """Only authenticated installed profiles can select registered ancestors."""
    if (
        os.name != "posix"
        or os.getuid() == 0
        or set(request) != set(("operation", "manifest_sha256", "files", "mutation"))
        or request["operation"] not in ("plan", "apply", "rollback")
    ):
        raise ValueError("ancestor_recipe_request")
    expected = request["manifest_sha256"]
    manifest, profile, registration = setup.inventory(assets, expected, known)
    accounting, installer, probe, confirmation = setup.modules(assets)
    probe.validate_profile(profile)
    root, binding, username, uid = confirmation.domain(
        profile, registration["identity_manifest_sha256"]
    )

    # Planning is read-only. Mutation acquires the SAME existing resource flock
    # itself, so do not recursively acquire ReservationSession for apply/rollback.
    def verify_runtime():
        directory = root + "/runtime/" + expected
        setup.private(directory, True)
        if (
            set(os.listdir(directory)) != set(assets)
            or any(setup.read(directory + "/" + name) != raw for name, raw in assets.items())
            or setup.closed(setup.read(root + "/active-native-provider.json"))["manifest_sha256"]
            != expected
        ):
            raise ValueError("ancestor_recipe_runtime_drift")

    verify_runtime()
    if request["operation"] == "plan":
        if request["mutation"] is not None:
            raise ValueError("ancestor_recipe_plan_shape")
        with accounting.ReservationSession(root) as session:
            before, records = session.observe(binding)
            result = inventory(profile, registration, collector, core)
            verify_runtime()
            after, records = session.observe(binding)
            if after != before:
                raise ValueError("ancestor_recipe_ledger_drift")
            return result
    mutation = request["mutation"]
    if mutation["plan"]["profile"] != profile or mutation["plan"]["registration"] != registration:
        raise ValueError("ancestor_recipe_registration_binding")
    # Revalidate the installed runtime at every existing fixed resource guard.
    old_guard = core.verify_resource_lock

    def guard(*args):
        old_guard(*args)
        verify_runtime()

    core.verify_resource_lock = guard
    mutate(mutation, collector, core, request["operation"] == "rollback")
    return {"status": "PHYSICAL_ANCESTOR_METADATA_COMPLETE", "execution_authorized": False}
