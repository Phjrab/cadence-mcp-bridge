"""Fixed existing-ledger migration. Python2.6; no grant, fresh ledger or dispatch."""

# mypy: ignore-errors
import hashlib
import json
import os
import stat
import sys

LIMIT = 262144
MEMBERS = ("migration.py", "reservations.py", "installer.py", "probe.py")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(value).hexdigest()


def closed(data):
    if len(data) > LIMIT:
        raise ValueError("migration_input_limit")
    result = json.loads(data.decode("ascii"))
    if canonical(result) != data:
        raise ValueError("migration_canonical_document_required")
    return result


def helpers():
    if __package__:
        from cadence_mcp_bridge import _shared_reservations as accounting
        from cadence_mcp_bridge import _runner_bootstrap as installer
        from cadence_mcp_bridge import _environment_probe as probe
    else:
        import reservations as accounting
        import installer
        import probe
    return accounting, installer, probe


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
        or manifest["kind"] != "EXISTING_DOMAIN_OPERATOR_HELPER"
        or set(manifest["files"]) != set(MEMBERS)
        or set(os.listdir(directory)) != set(MEMBERS + ("manifest.json",))
    ):
        raise ValueError("migration_asset_inventory")
    for name in MEMBERS:
        if manifest["files"][name] != {"sha256": digest(values[name]), "bytes": len(values[name])}:
            raise ValueError("migration_asset_content_drift")
    return expected


def identity(value):
    import pwd

    actual = os.uname()
    host = value["host"]
    if (actual[0], actual[1], actual[4], pwd.getpwuid(os.getuid()).pw_name) != (
        host["os"],
        host["hostname"],
        host["architecture"],
        host["user"],
    ):
        raise ValueError("migration_host_identity")


def profile(value):
    accounting, installer, probe = helpers()
    value = probe.validate_profile(value)
    identity(value)
    limits = value["limits"]
    if (
        limits["spectre_attempts"] != accounting.CEILING_COUNT
        or limits["result_reserved_bytes"] != accounting.CEILING_BYTES
    ):
        raise ValueError("existing_legacy_policy_required")
    root = value["paths"]["managed_root"]
    if (
        value["paths"]["job_root"] != root + "/" + accounting.JOBS
        or value["paths"]["result_root"] != root + "/" + accounting.JOBS
    ):
        raise ValueError("existing_legacy_job_root_required")
    installer.directory(root)
    return root


def file_metadata(value):
    accounting, installer, probe = helpers()
    info = accounting.safe(value)
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "bytes": info.st_size,
        "mtime": "%.9f" % info.st_mtime,
    }


def snapshot(root):
    accounting, installer, probe = helpers()
    counter_path = root + "/" + accounting.LEDGER
    accounting.safe(os.path.dirname(counter_path), True)
    if os.path.lexists(counter_path + ".ade-tmp"):
        raise ValueError("migration_ambiguous_counter")
    counter = accounting.read(counter_path)
    accounting.counter_shape(counter)
    if counter["result_reserved_bytes"] != accounting.expected_bytes(counter["count"], []):
        raise ValueError("migration_legacy_counter_conservation")
    data = installer.regular(counter_path)
    jobs = root + "/" + accounting.JOBS
    accounting.safe(jobs, True)
    if os.path.lexists(jobs + "/active") or os.path.lexists(root + "/execution.lock"):
        raise ValueError("migration_active_or_unresolved")
    names = sorted(os.listdir(jobs))
    if len(names) > 2048:
        raise ValueError("migration_inventory_limit")
    records, slots = [], set()
    for name in names:
        if name == "control.lock":
            accounting.safe(jobs + "/" + name)
            continue
        if not accounting.matches(accounting.ID, name):
            raise ValueError("migration_job_identity")
        accounting.safe(jobs + "/" + name, True)
        work = jobs + "/" + name + "/work"
        record = {"operation_id": name, "marker_sha256": None, "marker_metadata": None}
        if os.path.lexists(work):
            accounting.safe(work, True)
            if any(
                os.path.lexists(work + "/" + leaf)
                for leaf in ("reservation-intent.json", "reservation-receipt.json")
            ):
                raise ValueError("migration_already_has_generic_records")
            marker = work + "/attempt-reserved"
            if os.path.lexists(marker):
                value = accounting.read(marker)
                accounting.marker_shape(value)
                if (
                    value["count"] > counter["count"]
                    or value["count"] in slots
                    or value["result_reserved_bytes"]
                    != accounting.expected_bytes(value["count"], [])
                ):
                    raise ValueError("migration_legacy_marker_conservation")
                slots.add(value["count"])
                record["marker_sha256"] = digest(installer.regular(marker))
                record["marker_metadata"] = file_metadata(marker)
        records.append(record)
    lock = accounting.safe(root + "/run.lock")
    return {
        "baseline": counter,
        "ledger_sha256": digest(data),
        "ledger_inode": accounting.identity(accounting.safe(counter_path)),
        "ledger_metadata": file_metadata(counter_path),
        "native_jobs": records,
        "lock_inode": accounting.identity(lock),
        "lock_sha256": digest(installer.regular(root + "/run.lock")),
    }


def anchor_for(value, root, current):
    accounting, installer, probe = helpers()
    return {
        "schema_version": 1,
        "root_sha256": digest(root.encode("utf-8")),
        "resource_domain_sha256": digest(
            canonical(
                {
                    "hostname": value["host"]["hostname"],
                    "architecture": value["host"]["architecture"],
                }
            )
        ),
        "ledger_ref": accounting.LEDGER,
        "baseline": current["baseline"],
        "legacy_operation_ids": [],
    }


def plan(value, assets_sha256):
    accounting, installer, probe = helpers()
    root = profile(value)
    fd = installer._operator_lock(root)
    try:
        current = snapshot(root)
        if os.path.lexists(root + "/" + accounting.REGISTRY):
            raise ValueError("migration_already_present_use_established_provider")
        result = {
            "schema_version": 1,
            "recipe_id": "existing-legacy-domain-v1",
            "helper_manifest_sha256": assets_sha256,
            "profile": value,
            "profile_sha256": digest(canonical(value)),
            "snapshot": current,
            "anchor": anchor_for(value, root, current),
            "authority": "PLAN_IS_NOT_OPERATOR_APPROVAL",
        }
        return {
            "plan": result,
            "plan_sha256": digest(canonical(result)),
            "execution_authorized": False,
            "ledger_initialized": False,
        }
    finally:
        if fd is not None:
            os.close(fd)


def apply(request, assets_sha256):
    accounting, installer, probe = helpers()
    if (
        not isinstance(request, dict)
        or set(request) != set(("plan", "expected_plan_sha256", "operator_authority"))
        or not accounting.matches(accounting.HASH, request["expected_plan_sha256"])
        or not isinstance(request["operator_authority"], accounting.STRING_TYPES)
        or not 1 <= len(request["operator_authority"]) <= 512
        or any(ord(c) < 32 for c in request["operator_authority"])
    ):
        raise ValueError("migration_request_shape")
    value = request["plan"]
    if (
        not isinstance(value, dict)
        or set(value)
        != set(
            (
                "schema_version",
                "recipe_id",
                "profile",
                "profile_sha256",
                "snapshot",
                "anchor",
                "authority",
                "helper_manifest_sha256",
            )
        )
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["recipe_id"] != "existing-legacy-domain-v1"
        or value["helper_manifest_sha256"] != assets_sha256
        or value["authority"] != "PLAN_IS_NOT_OPERATOR_APPROVAL"
        or digest(canonical(value)) != request["expected_plan_sha256"]
        or digest(canonical(value["profile"])) != value["profile_sha256"]
    ):
        raise ValueError("migration_plan_binding")
    root = profile(value["profile"])
    fd = installer._operator_lock(root)
    try:
        current = snapshot(root)
        anchor = anchor_for(value["profile"], root, current)
        if canonical(current) != canonical(value["snapshot"]) or canonical(anchor) != canonical(
            value["anchor"]
        ):
            raise ValueError("migration_snapshot_drift")
        receipts = root + "/operator-domain-migration"
        registry = root + "/" + accounting.REGISTRY
        key = request["expected_plan_sha256"]
        intent = receipts + "/" + key + ".intent.json"
        if os.path.lexists(registry):
            accounting.safe(registry, True)
            if sorted(os.listdir(registry)) not in ([], ["manifest.json"]):
                raise ValueError("migration_registry_conflict")
            if not os.path.lexists(intent):
                raise ValueError("migration_unrecorded_partial_state")
        if not os.path.lexists(receipts):
            os.mkdir(receipts, 448)
            accounting.sync_directory(root)
        accounting.safe(receipts, True)

        def retain(path, record):
            if os.path.lexists(path):
                if canonical(accounting.read(path)) != canonical(record):
                    raise ValueError("migration_retained_record_conflict")
                return False
            accounting.write_new(path, record)
            return True

        # Existing read() has an8KiB record bound; keep large plan in a bounded
        # hash-indexed receipt instead. The actual human instruction is authority.
        request_record = {
            "schema_version": 1,
            "plan_sha256": key,
            "helper_manifest_sha256": assets_sha256,
            "snapshot_sha256": digest(canonical(current)),
            "operator_authority": request["operator_authority"],
        }
        retain(intent, request_record)
        if not os.path.lexists(registry):
            os.mkdir(registry, 448)
            accounting.sync_directory(root)
        accounting.safe(registry, True)
        created = retain(registry + "/manifest.json", anchor)
        if canonical(snapshot(root)) != canonical(current):
            raise ValueError("migration_post_snapshot_drift")
        result = {
            "schema_version": 1,
            "plan_sha256": key,
            "identity_manifest_sha256": digest(canonical(anchor)),
            "snapshot_sha256": digest(canonical(current)),
            "ledger_sha256": current["ledger_sha256"],
            "status": "EXISTING_DOMAIN_ANCHORED_NOT_EXECUTION_AUTHORITY",
            "execution_authorized": False,
            "ledger_initialized": False,
            "ledger_modified": False,
            "reservation_cost": 0,
        }
        retain(receipts + "/" + key + ".complete.json", result)
        result["anchor_created"] = created
        return result
    finally:
        if fd is not None:
            os.close(fd)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("inventory-existing", "apply-existing"):
        raise ValueError("fixed_existing_migration_command_required")
    if os.name != "posix":
        raise ValueError("native_linux_required")
    assets = validate_assets(sys.argv[2])
    data = closed(sys.stdin.read(LIMIT + 1).encode("ascii"))
    result = plan(data, assets) if sys.argv[1] == "inventory-existing" else apply(data, assets)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        reason = str(failure)
        allowed = (
            "migration_active_or_unresolved",
            "migration_snapshot_drift",
            "migration_already_present_use_established_provider",
        )
        sys.stderr.write(
            (reason if reason in allowed else "OPERATOR_DOMAIN_MIGRATION_REJECTED") + "\n"
        )
        sys.exit(1)
