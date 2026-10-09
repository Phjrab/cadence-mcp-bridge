"""Explicit normal-user domain provisioning; no import/startup effects or dispatch."""

# mypy: ignore-errors
import hashlib
import json
import os
import stat
import sys
import uuid

LIMIT = 262144
MEMBERS = ("setup.py", "migration.py", "reservations.py", "installer.py", "probe.py")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(value).hexdigest()


def closed(data):
    if len(data) > LIMIT:
        raise ValueError("setup_input_limit")
    value = json.loads(data.decode("ascii"))
    if canonical(value) != data:
        raise ValueError("setup_canonical_required")
    return value


def helpers():
    if __package__:
        from cadence_mcp_bridge import _shared_reservations as accounting
        from cadence_mcp_bridge import _runner_bootstrap as installer
        from cadence_mcp_bridge import _environment_probe as probe
        from cadence_mcp_bridge import _domain_migration as migration
    else:
        import reservations as accounting
        import installer
        import probe
        import migration
    return accounting, installer, probe, migration


def home():
    import pwd

    return pwd.getpwuid(os.getuid()).pw_dir


def validate_assets(expected):
    # Verify ALL fixed source files before any helper import; no caller code/name.
    directory = os.path.dirname(os.path.abspath(__file__))
    if os.path.realpath(directory) != directory or len(expected) != 64:
        raise ValueError("migration_asset_location")
    info = os.stat(directory)
    if info.st_uid != os.getuid() or info.st_mode & 18:
        raise ValueError("migration_asset_directory_trust")
    ancestor = directory
    while True:
        observed = os.lstat(ancestor)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid not in (0, os.getuid())
            or observed.st_mode & 18
        ):
            raise ValueError("migration_asset_ancestor_trust")
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    values = {}
    for name in MEMBERS + ("manifest.json",):
        path = directory + "/" + name
        info = os.lstat(path)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or os.path.realpath(path) != path
            or info.st_uid != os.getuid()
            or info.st_mode & 18
        ):
            raise ValueError("migration_asset_trust")
        stream = open(path, "rb")
        try:
            before = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError("migration_asset_open_drift")
            values[name] = stream.read(LIMIT + 1)
        finally:
            stream.close()
        if len(values[name]) > LIMIT:
            raise ValueError("migration_asset_limit")
    if digest(values["manifest.json"]) != expected:
        raise ValueError("migration_asset_binding")
    manifest = closed(values["manifest.json"])
    if (
        set(manifest) != set(("schema_version", "kind", "files"))
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["kind"] != "STANDARD_VM_DOMAIN_SETUP_HELPER"
        or set(manifest["files"]) != set(MEMBERS)
        or set(os.listdir(directory)) != set(MEMBERS + ("manifest.json",))
    ):
        raise ValueError("migration_asset_inventory")
    for name in MEMBERS:
        if manifest["files"][name] != {"sha256": digest(values[name]), "bytes": len(values[name])}:
            raise ValueError("migration_asset_content_drift")
    return expected


def profile(value):
    accounting, installer, probe, migration = helpers()
    value = probe.validate_profile(value)
    migration.identity(value)
    root = value["paths"]["managed_root"]
    if (
        not root.startswith(home() + "/")
        or value["paths"]["job_root"] != root + "/" + accounting.JOBS
        or value["paths"]["result_root"] != root + "/" + accounting.JOBS
        or not 1 <= value["limits"]["spectre_attempts"] <= accounting.CEILING_COUNT
        or not 1 <= value["limits"]["result_reserved_bytes"] <= accounting.MAX_POLICY_BYTES
    ):
        raise ValueError("setup_profile_scope")
    installer.directory(home())
    installer.directory(value["paths"]["workspace_root"])
    return root, home() + "/.cadence_mcp-domain"


def histories(value, ignored=None):
    # Do not inspect vendor/PDK contents. Valid managed roots cannot overlap those.
    accounting, installer, probe, migration = helpers()
    protected = value["paths"]["protected_roots"]
    count = 0

    def denied(error):
        raise ValueError("setup_history_unreadable")

    for directory, directories, names in os.walk(
        home(), topdown=True, onerror=denied, followlinks=False
    ):
        count += 1
        if count > 50000 or directory.count("/") - home().count("/") > 32:
            raise ValueError("setup_history_inventory_limit")
        directories[:] = [
            name
            for name in directories
            if not os.path.islink(directory + "/" + name)
            and os.path.normpath(os.path.join(directory, name))
            not in [os.path.normpath(p) for p in protected]
            and os.path.normpath(os.path.join(directory, name))
            != (os.path.normpath(ignored) if ignored else None)
        ]
        if ignored and os.path.normpath(directory) == os.path.normpath(ignored):
            directories[:] = []
            continue
        if ("counter.json" in names and os.path.basename(directory) == "sim-mcp-v2-jobs") or (
            "manifest.json" in names and os.path.basename(directory) == "reservation-identity"
        ):
            raise ValueError("setup_existing_history_use_registered_domain")


def make_anchor(value, root, campaign):
    accounting, installer, probe, migration = helpers()
    return {
        "schema_version": 2,
        "root_sha256": digest(root.encode("utf-8")),
        "resource_domain_sha256": digest(
            canonical(
                {
                    "hostname": value["host"]["hostname"].lower().rstrip("."),
                    "architecture": value["host"]["architecture"],
                }
            )
        ),
        "ledger_ref": accounting.LEDGER,
        "baseline": {"campaign_id": campaign, "count": 0, "result_reserved_bytes": 0},
        "legacy_operation_ids": [],
        "policy": {
            "campaign_id": campaign,
            "attempt_ceiling": value["limits"]["spectre_attempts"],
            "result_ceiling_bytes": value["limits"]["result_reserved_bytes"],
        },
    }


def plan_fresh(value, assets):
    accounting, installer, probe, migration = helpers()
    root, domain = profile(value)
    if os.path.lexists(domain + "/manifest.json") or os.path.lexists(domain + "/intent.json"):
        raise ValueError("setup_domain_already_registered_or_pending")
    if os.path.lexists(root):
        raise ValueError("setup_fresh_root_must_be_absent")
    histories(value)
    anchor = make_anchor(value, root, str(uuid.uuid4()))
    result = {
        "schema_version": 1,
        "recipe_id": "fresh-standard-vm-domain-v1",
        "profile": value,
        "helper_manifest_sha256": assets,
        "profile_sha256": digest(canonical(value)),
        "anchor": anchor,
        "authority": "PLAN_IS_NOT_OPERATOR_APPROVAL",
    }
    return {
        "plan": result,
        "plan_sha256": digest(canonical(result)),
        "execution_authorized": False,
        "ledger_initialized": False,
    }


def retain(path, value):
    accounting, installer, probe, migration = helpers()
    if os.path.lexists(path):
        if canonical(accounting.read(path)) != canonical(value):
            raise ValueError("setup_retained_record_conflict")
        return False
    accounting.write_new(path, value)
    return True


def directory(path):
    accounting, installer, probe, migration = helpers()
    if not os.path.lexists(path):
        os.mkdir(path, 448)
        accounting.sync_directory(os.path.dirname(path))
    accounting.safe(path, True)


def index_lock(domain):
    accounting, installer, probe, migration = helpers()
    directory(domain)
    lock = domain + "/run.lock"
    if not os.path.lexists(lock):
        installer.exclusive(lock, b"")
        accounting.sync_directory(domain)
    return installer._operator_lock(domain)


def authority(request):
    accounting, installer, probe, migration = helpers()
    if (
        not isinstance(request, dict)
        or set(request) != set(("plan", "expected_plan_sha256", "operator_authority"))
        or not accounting.matches(accounting.HASH, request["expected_plan_sha256"])
        or not isinstance(request["operator_authority"], accounting.STRING_TYPES)
        or not 1 <= len(request["operator_authority"]) <= 512
        or any(ord(c) < 32 for c in request["operator_authority"])
        or digest(canonical(request["plan"])) != request["expected_plan_sha256"]
    ):
        raise ValueError("setup_actual_instruction_binding_required")


def apply_fresh(request, assets):
    accounting, installer, probe, migration = helpers()
    authority(request)
    value = request["plan"]
    if (
        not isinstance(value, dict)
        or set(value)
        != set(
            (
                "schema_version",
                "recipe_id",
                "profile",
                "helper_manifest_sha256",
                "profile_sha256",
                "anchor",
                "authority",
            )
        )
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["recipe_id"] != "fresh-standard-vm-domain-v1"
        or value["authority"] != "PLAN_IS_NOT_OPERATOR_APPROVAL"
        or value["helper_manifest_sha256"] != assets
        or value["profile_sha256"] != digest(canonical(value["profile"]))
    ):
        raise ValueError("setup_plan_binding")
    root, domain = profile(value["profile"])
    campaign = value["anchor"]["policy"]["campaign_id"]
    if not accounting.matches(accounting.ID, campaign) or canonical(
        make_anchor(value["profile"], root, campaign)
    ) != canonical(value["anchor"]):
        raise ValueError("setup_anchor_binding")
    key = request["expected_plan_sha256"]
    anchor = value["anchor"]
    index = {
        "schema_version": 1,
        "root": root,
        "resource_domain_sha256": anchor["resource_domain_sha256"],
        "identity_manifest_sha256": digest(canonical(anchor)),
        "plan_sha256": key,
    }
    intent = {
        "schema_version": 1,
        "plan_sha256": key,
        "root": root,
        "helper_manifest_sha256": assets,
        "operator_authority": request["operator_authority"],
    }
    fd = index_lock(domain)
    try:
        if set(os.listdir(domain)) - set(
            ("run.lock", "intent.json", "manifest.json", "complete.json")
        ):
            raise ValueError("setup_domain_index_inventory")
        pending = os.path.lexists(domain + "/intent.json")
        if pending and canonical(accounting.read(domain + "/intent.json")) != canonical(intent):
            raise ValueError("setup_other_initialization_pending")
        if os.path.lexists(domain + "/manifest.json"):
            if not pending or canonical(accounting.read(domain + "/manifest.json")) != canonical(
                index
            ):
                raise ValueError("setup_existing_domain_conflict")
            binding = dict(anchor)
            binding["identity_manifest_sha256"] = index["identity_manifest_sha256"]
            # Validate current consumption; repeating setup never rewrites it to zero.
            checkfd = accounting.open_lock(root)
            try:
                accounting.state(root, binding)
            finally:
                if checkfd is not None:
                    os.close(checkfd)
            retain(domain + "/complete.json", index)
            return {
                "status": "EXISTING_FRESH_DOMAIN_REUSED",
                "ledger_initialized": False,
                "ledger_modified": False,
                "execution_authorized": False,
                "identity_manifest_sha256": index["identity_manifest_sha256"],
            }
        if os.path.lexists(root) and not pending:
            raise ValueError("setup_existing_root_never_reinitialize")
        histories(value["profile"], root if pending else None)
        retain(domain + "/intent.json", intent)
        directory(root)
        if set(os.listdir(root)) - set(
            ("run.lock", "sim-mcp-v2-jobs", accounting.JOBS, accounting.REGISTRY)
        ):
            raise ValueError("setup_partial_root_inventory")
        for leaf in ("sim-mcp-v2-jobs", accounting.JOBS, accounting.REGISTRY):
            directory(root + "/" + leaf)
        if not os.path.lexists(root + "/run.lock"):
            installer.exclusive(root + "/run.lock", b"")
            accounting.sync_directory(root)
        rootfd = installer._operator_lock(root)
        try:
            if (
                os.listdir(root + "/" + accounting.JOBS)
                or set(os.listdir(root + "/sim-mcp-v2-jobs")) - set(("counter.json",))
                or set(os.listdir(root + "/" + accounting.REGISTRY)) - set(("manifest.json",))
            ):
                raise ValueError("setup_partial_history_conflict")
            retain(root + "/" + accounting.LEDGER, anchor["baseline"])
            retain(root + "/" + accounting.REGISTRY + "/manifest.json", anchor)
            binding = dict(anchor)
            binding["identity_manifest_sha256"] = index["identity_manifest_sha256"]
            accounting.state(root, binding)
            retain(domain + "/manifest.json", index)
            retain(domain + "/complete.json", index)
        finally:
            if rootfd is not None:
                os.close(rootfd)
        return {
            "status": "FRESH_DOMAIN_INITIALIZED_NOT_EXECUTION_AUTHORITY",
            "ledger_initialized": True,
            "ledger_modified": False,
            "execution_authorized": False,
            "identity_manifest_sha256": index["identity_manifest_sha256"],
        }
    finally:
        if fd is not None:
            os.close(fd)


def register_existing(request, assets):
    accounting, installer, probe, migration = helpers()
    authority(request)
    value = request["plan"]
    # Registration records an already-provisioned anchor. It never migrates/rebaselines a ledger.
    if (
        not isinstance(value, dict)
        or set(value)
        != set(("schema_version", "profile", "identity_manifest_sha256", "helper_manifest_sha256"))
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["helper_manifest_sha256"] != assets
        or not accounting.matches(accounting.HASH, value["identity_manifest_sha256"])
    ):
        raise ValueError("setup_existing_registration_binding")
    root, domain = profile(value["profile"])
    fd = index_lock(domain)
    try:
        rootfd = accounting.open_lock(root)
        try:
            binding = {
                "root_sha256": digest(root.encode("utf-8")),
                "resource_domain_sha256": digest(
                    canonical(
                        {
                            "hostname": value["profile"]["host"]["hostname"].lower().rstrip("."),
                            "architecture": value["profile"]["host"]["architecture"],
                        }
                    )
                ),
                "ledger_ref": accounting.LEDGER,
                "identity_manifest_sha256": value["identity_manifest_sha256"],
            }
            anchor = accounting.identity_manifest(root, binding)
            expected_policy = accounting.effective_policy(root, anchor)
            if (
                value["profile"]["limits"]["spectre_attempts"],
                value["profile"]["limits"]["result_reserved_bytes"],
            ) != (expected_policy["attempt_ceiling"], expected_policy["result_ceiling_bytes"]):
                raise ValueError("setup_existing_policy_mismatch")
            accounting.state(root, binding)
            index = {
                "schema_version": 1,
                "root": root,
                "resource_domain_sha256": binding["resource_domain_sha256"],
                "identity_manifest_sha256": binding["identity_manifest_sha256"],
                "plan_sha256": request["expected_plan_sha256"],
            }
            if os.path.lexists(domain + "/intent.json") or set(os.listdir(domain)) - set(
                ("run.lock", "manifest.json", "existing-registration.json")
            ):
                raise ValueError("setup_existing_index_conflict")
            intent = {
                "schema_version": 1,
                "plan_sha256": request["expected_plan_sha256"],
                "operator_authority": request["operator_authority"],
            }
            if os.path.lexists(domain + "/manifest.json") and canonical(
                accounting.read(domain + "/manifest.json")
            ) != canonical(index):
                raise ValueError("setup_existing_domain_conflict")
            retain(domain + "/existing-registration.json", intent)
            retain(domain + "/manifest.json", index)
            return {
                "status": "EXISTING_DOMAIN_REGISTERED_NO_LEDGER_CHANGE",
                "ledger_initialized": False,
                "ledger_modified": False,
                "execution_authorized": False,
                "identity_manifest_sha256": binding["identity_manifest_sha256"],
            }
        finally:
            if rootfd is not None:
                os.close(rootfd)
    finally:
        if fd is not None:
            os.close(fd)


def main():
    if (
        len(sys.argv) != 3
        or sys.argv[1] not in ("plan-fresh", "apply-fresh", "register-existing")
        or os.name != "posix"
    ):
        raise ValueError("fixed_setup_command_required")
    assets = validate_assets(sys.argv[2])
    data = closed(sys.stdin.read(LIMIT + 1).encode("ascii"))
    if sys.argv[1] == "plan-fresh":
        result = plan_fresh(data, assets)
    elif sys.argv[1] == "apply-fresh":
        result = apply_fresh(data, assets)
    else:
        result = register_existing(data, assets)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("STANDARD_VM_DOMAIN_SETUP_REJECTED\n")
        sys.exit(1)
