"""Explicit fixed native runtime setup; Python2.6, no import side effects.

Only the operator CLI invokes main with its compiled package hash allowlist.
No MCP caller can choose code, paths, sudo or a launcher. Existing accounting,
preflight and legacy runtime controls are never replaced.
"""

# mypy: ignore-errors
import base64
import hashlib
import json
import os
import stat
import sys
import types

LIMIT = 1048576
ASSET_LIMIT = 262144
FILES = (
    "provider.py",
    "operations.py",
    "gate.py",
    "worker.py",
    "rendering.py",
    "copying.py",
    "confirmation.py",
    "reservations.py",
    "installer.py",
    "probe.py",
    "storage.py",
    "modeltrust.py",
    "profile.json",
    "registration.json",
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def metadata(path):
    info = private(path)
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "nlink": info.st_nlink,
        "size": info.st_size,
        "mtime": info.st_mtime,
    }


def closed(raw):
    value = json.loads(raw.decode("ascii"))
    if len(raw) > LIMIT or canonical(value) != raw:
        raise ValueError("native_setup_canonical")
    return value


def private(path, directory=False, ancestor=False):
    info = os.lstat(path)
    if (
        os.path.realpath(path) != os.path.abspath(path)
        or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
        or info.st_uid not in ((0, os.getuid()) if ancestor else (os.getuid(),))
        or info.st_mode & (18 if ancestor else 63)
    ):
        raise ValueError("native_setup_private_path")
    return info


def read(path):
    before = private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, "rb")
    try:
        opened = os.fstat(fd)
        data = stream.read(ASSET_LIMIT + 1)
        after = private(path)
        expected = (before.st_dev, before.st_ino, before.st_size, before.st_mtime)
        if (
            len(data) > ASSET_LIMIT
            or expected != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime)
            or expected != (after.st_dev, after.st_ino, after.st_size, after.st_mtime)
        ):
            raise ValueError("native_setup_read_drift")
        return data
    finally:
        stream.close()


def write_atomic_record(path, value, accounting):
    """Publish only complete/fsynced records under the existing lifetime flock.

    Interrupted private candidates remain evidence. Retry creates another bounded
    candidate instead of deleting or parsing a truncated final-path authority record.
    """
    raw = canonical(value)
    if len(raw) > ASSET_LIMIT:
        raise ValueError("native_setup_record_size")
    parent = os.path.dirname(path)
    private(parent, directory=True)
    if os.path.lexists(path):
        if read(path) != raw:
            raise ValueError("native_setup_record_conflict")
        return
    name = ".native-record-" + hashlib.sha256(os.urandom(32)).hexdigest()
    candidate = os.path.join(parent, name)
    fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384)
    try:
        offset = 0
        while offset < len(raw):
            wrote = os.write(fd, raw[offset:])
            if wrote <= 0:
                raise ValueError("native_setup_record_short_write")
            offset += wrote
        os.fsync(fd)
    finally:
        os.close(fd)
    accounting.sync_directory(parent)
    if read(candidate) != raw or os.path.lexists(path):
        raise ValueError("native_setup_record_publish_conflict")
    os.rename(candidate, path)
    accounting.sync_directory(parent)


def modules(assets):
    if __package__:
        from cadence_mcp_bridge import _shared_reservations as accounting
        from cadence_mcp_bridge import _runner_bootstrap as installer
        from cadence_mcp_bridge import _environment_probe as probe
        from cadence_mcp_bridge import _operator_confirmation as confirmation

        return accounting, installer, probe, confirmation
    # Only fixed code hashes from the installed operator package are accepted
    # before memory loading. Nothing supplies an unbound script/module name.
    loaded = {}
    for name in ("installer", "probe", "reservations", "confirmation"):
        module = types.ModuleType(name)
        module.__dict__["__package__"] = None
        sys.modules[name] = module
        eval(compile(assets[name + ".py"], name + ".py", "exec"), module.__dict__)
        loaded[name] = module
    return loaded["reservations"], loaded["installer"], loaded["probe"], loaded["confirmation"]


def inventory(assets, expected, known):
    if set(assets) != set(FILES + ("manifest.json",)) or set(known) != set(FILES) - set(
        ("profile.json", "registration.json")
    ):
        raise ValueError("native_setup_inventory")
    raw = assets["manifest.json"]
    manifest = closed(raw)
    if (
        digest(raw) != expected
        or set(manifest)
        != set(
            (
                "schema_version",
                "kind",
                "environment_id",
                "profile_sha256",
                "registration_sha256",
                "files",
            )
        )
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 3
        or manifest["kind"] != "STANDARD_VM_CONFIRMED_NATIVE_RUNTIME"
        or set(manifest["files"]) != set(FILES)
    ):
        raise ValueError("native_setup_manifest")
    for name in FILES:
        data = assets[name]
        if (
            len(data) > ASSET_LIMIT
            or manifest["files"][name] != {"sha256": digest(data), "bytes": len(data)}
            or (name in known and digest(data) != known[name])
        ):
            raise ValueError("native_setup_package_asset")
    profile = json.loads(assets["profile.json"].decode("ascii"))
    registration = closed(assets["registration.json"])
    if (
        digest(assets["profile.json"]) != manifest["profile_sha256"]
        or digest(assets["registration.json"]) != manifest["registration_sha256"]
        or profile["environment_id"] != manifest["environment_id"]
        or registration["environment_sha256"] != manifest["profile_sha256"]
    ):
        raise ValueError("native_setup_configuration")
    return manifest, profile, registration


def directory(path, accounting):
    if not os.path.lexists(path):
        private(os.path.dirname(path), True)
        os.mkdir(path, 448)
        accounting.sync_directory(os.path.dirname(path))
    private(path, True)


def apply(request, expected, known):
    if os.name != "posix" or os.getuid() == 0:
        raise ValueError("native_setup_normal_linux_user")
    if (
        set(request)
        != set(
            ("schema_version", "action", "manifest_sha256", "files", "operator_authority")
            + (("previous_manifest_sha256",) if request.get("action") == "update" else ())
            + (("nonce",) if request.get("action") == "preflight" else ())
        )
        or type(request["schema_version"]) is not int
        or request["schema_version"] != 1
        or request["manifest_sha256"] != expected
        or len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)
        or request["action"]
        not in ("stage", "activate", "inspect", "revoke", "update", "preflight")
        or set(request["files"]) != set(FILES + ("manifest.json",))
    ):
        raise ValueError("native_setup_request")
    assets = {}
    for name, value in request["files"].items():
        data = base64.b64decode(value)
        if base64.b64encode(data).decode("ascii") != value:
            raise ValueError("native_setup_base64")
        assets[name] = data
    manifest, profile, registration = inventory(assets, expected, known)
    accounting, installer, probe, confirmation = modules(assets)
    probe.validate_profile(profile)
    root, binding, username, uid = confirmation.domain(
        profile, registration["identity_manifest_sha256"]
    )
    reference = request["operator_authority"]
    if request["action"] in ("inspect", "preflight"):
        if reference is not None:
            raise ValueError("native_setup_inspection_authority")
    else:
        confirmation.authority_reference(reference)
    target = root + "/runtime/" + expected
    changed = 0
    observation = None
    if request["action"] == "preflight" and not confirmation.matches(
        r"^[0-9a-f]{32}$", request["nonce"]
    ):
        raise ValueError("native_setup_preflight_nonce")
    with accounting.ReservationSession(root) as session:
        confirmation.domain(profile, registration["identity_manifest_sha256"])
        before, records = session.observe(binding)
        if request["action"] == "stage":
            directory(root + "/runtime", accounting)
            directory(target, accounting)
            if set(os.listdir(target)) - set(assets):
                raise ValueError("native_setup_partial_inventory")
            # Validate every retained item before creating a missing member.
            for name, data in assets.items():
                if os.path.lexists(target + "/" + name) and read(target + "/" + name) != data:
                    raise ValueError("native_setup_retained_conflict")
            for name, data in sorted(assets.items()):
                if not os.path.lexists(target + "/" + name):
                    installer.exclusive(target + "/" + name, data)
                    accounting.sync_directory(target)
                    changed += 1
        private(target, True)
        if set(os.listdir(target)) != set(assets):
            raise ValueError("native_setup_installed_inventory")
        for name, data in assets.items():
            if read(target + "/" + name) != data:
                raise ValueError("native_setup_installed_drift")
        history_dir = root + "/native-provider-history"
        history_path = history_dir + "/" + expected + ".json"
        revoked = history_dir + "/" + expected + ".revoked.json"
        pointer_path = root + "/active-native-provider.json"
        pointer = {"schema_version": 1, "manifest_sha256": expected}
        history = None
        if os.path.lexists(history_path):
            private(history_dir, True)
            history = closed(read(history_path))
            if (
                set(history)
                != set(
                    (
                        "schema_version",
                        "manifest_sha256",
                        "identity_manifest_sha256",
                        "operator_authority",
                    )
                )
                or type(history["schema_version"]) is not int
                or history["schema_version"] != 1
                or history["manifest_sha256"] != expected
                or history["identity_manifest_sha256"] != registration["identity_manifest_sha256"]
            ):
                raise ValueError("native_setup_activation_history")
            confirmation.authority_reference(history["operator_authority"])
        active = False
        if os.path.lexists(pointer_path):
            actual_pointer = closed(read(pointer_path))
            if (
                set(actual_pointer) != set(("schema_version", "manifest_sha256"))
                or type(actual_pointer["schema_version"]) is not int
                or actual_pointer["schema_version"] != 1
                or not confirmation.matches(r"^[0-9a-f]{64}$", actual_pointer["manifest_sha256"])
            ):
                raise ValueError("native_setup_pointer_shape")
            active = actual_pointer == pointer
            if active and history is None:
                raise ValueError("native_setup_pointer_without_history")
        if request["action"] == "preflight":
            observation = probe.observe(
                profile,
                digest(assets["profile.json"]),
                digest(assets["probe.py"]),
                request["nonce"],
            )
        if request["action"] in ("activate", "update"):
            if os.path.lexists(revoked) or os.path.lexists(root + "/native-provider-revoked.json"):
                raise ValueError("native_setup_revoked")
            if os.path.lexists(pointer_path) and not active and request["action"] != "update":
                raise ValueError("native_setup_other_active_runtime")
            probe.observe(
                profile,
                manifest["profile_sha256"],
                digest(assets["probe.py"]),
                __import__("binascii").hexlify(os.urandom(16)).decode("ascii"),
            )
            previous = None
            update_path = None
            if request["action"] == "update":
                previous = request["previous_manifest_sha256"]
                if (
                    not confirmation.matches(r"^[0-9a-f]{64}$", previous)
                    or previous == expected
                    or not os.path.lexists(pointer_path)
                ):
                    raise ValueError("native_setup_update_predecessor")
                old_target = root + "/runtime/" + previous
                private(old_target, True)
                old_raw = read(old_target + "/manifest.json")
                old_manifest = closed(old_raw)
                if (
                    digest(old_raw) != previous
                    or old_manifest.get("schema_version") != 3
                    or old_manifest.get("kind") != manifest["kind"]
                    or set(old_manifest.get("files", {})) != set(FILES)
                    or set(os.listdir(old_target)) != set(FILES + ("manifest.json",))
                ):
                    raise ValueError("native_setup_update_prior_manifest")
                for name in FILES:
                    old_data = read(old_target + "/" + name)
                    if old_manifest["files"][name] != {
                        "sha256": digest(old_data),
                        "bytes": len(old_data),
                    }:
                        raise ValueError("native_setup_update_prior_asset_drift")
                old_registration = closed(read(old_target + "/registration.json"))
                old_history = closed(read(history_dir + "/" + previous + ".json"))
                if (
                    old_registration["identity_manifest_sha256"]
                    != registration["identity_manifest_sha256"]
                    or old_history["manifest_sha256"] != previous
                    or old_history["identity_manifest_sha256"]
                    != registration["identity_manifest_sha256"]
                    or os.path.lexists(history_dir + "/" + previous + ".revoked.json")
                ):
                    raise ValueError("native_setup_update_prior_identity_or_revocation")
                confirmation.authority_reference(old_history["operator_authority"])
                previous_pointer = {"schema_version": 1, "manifest_sha256": previous}
                if actual_pointer not in (previous_pointer, pointer):
                    raise ValueError("native_setup_update_pointer_moved")
                update_dir = root + "/native-provider-updates"
                directory(update_dir, accounting)
                update_path = update_dir + "/" + previous + "-" + expected + ".json"
                pending = root + "/active-native-provider.pending-" + expected
                raw_pointer = canonical(pointer)
                update_record = {
                    "schema_version": 1,
                    "previous_manifest_sha256": previous,
                    "manifest_sha256": expected,
                    "identity_manifest_sha256": registration["identity_manifest_sha256"],
                    "operator_authority": reference,
                    "previous_pointer": previous_pointer,
                }
                if os.path.lexists(update_path):
                    old_update = closed(read(update_path))
                    if set(old_update) != set(update_record) | set(
                        ("previous_metadata", "replacement_metadata")
                    ) or any(old_update[key] != value for key, value in update_record.items()):
                        raise ValueError("native_setup_update_history_conflict")
                    update_record = old_update
                    if active:
                        if metadata(pointer_path) != update_record["replacement_metadata"]:
                            raise ValueError("native_setup_update_pointer_metadata_drift")
                    elif metadata(pointer_path) != update_record["previous_metadata"]:
                        raise ValueError("native_setup_update_prior_metadata_drift")
                elif active:
                    raise ValueError("native_setup_update_pointer_without_history")
                else:
                    update_record["previous_metadata"] = metadata(pointer_path)
                if not active:
                    if os.path.lexists(pending):
                        if read(pending) != raw_pointer:
                            raise ValueError("native_setup_update_pending_conflict")
                    else:
                        write_atomic_record(pending, pointer, accounting)
                        accounting.sync_directory(root)
                    if "replacement_metadata" in update_record:
                        if metadata(pending) != update_record["replacement_metadata"]:
                            raise ValueError("native_setup_update_pending_metadata_drift")
                    else:
                        update_record["replacement_metadata"] = metadata(pending)
                if not os.path.lexists(update_path):
                    write_atomic_record(update_path, update_record, accounting)
                    changed += 1
            wanted = {
                "schema_version": 1,
                "manifest_sha256": expected,
                "identity_manifest_sha256": registration["identity_manifest_sha256"],
                "operator_authority": reference,
            }
            if history is not None and history != wanted:
                raise ValueError("native_setup_authority_conflict")
            directory(history_dir, accounting)
            if history is None:
                write_atomic_record(history_path, wanted, accounting)
                changed += 1
                history = wanted
            if not active:
                if request["action"] == "update":
                    # Same existing flock; never replace a live worker's pointer.
                    # Old immutable runtime/history/grants/jobs remain untouched.
                    if closed(read(pointer_path)) != previous_pointer:
                        raise ValueError("native_setup_update_pointer_race")
                    os.rename(pending, pointer_path)
                    accounting.sync_directory(root)
                    if metadata(pointer_path) != update_record["replacement_metadata"]:
                        raise ValueError("native_setup_update_replacement_metadata_drift")
                else:
                    write_atomic_record(pointer_path, pointer, accounting)
                changed += 1
                active = True
        if request["action"] == "revoke":
            if history is None:
                raise ValueError("native_setup_revoke_without_history")
            value = {
                "schema_version": 1,
                "manifest_sha256": expected,
                "activation_sha256": digest(canonical(history)),
                "operator_authority": reference,
            }
            if os.path.lexists(revoked):
                if closed(read(revoked)) != value:
                    raise ValueError("native_setup_revocation_conflict")
            else:
                write_atomic_record(revoked, value, accounting)
                changed += 1
        if os.path.lexists(revoked):
            value = closed(read(revoked))
            if (
                history is None
                or set(value)
                != set(
                    ("schema_version", "manifest_sha256", "activation_sha256", "operator_authority")
                )
                or type(value["schema_version"]) is not int
                or value["schema_version"] != 1
                or value["manifest_sha256"] != expected
                or value["activation_sha256"] != digest(canonical(history))
            ):
                raise ValueError("native_setup_revocation_binding")
            confirmation.authority_reference(value["operator_authority"])
            active = False
        after, records = session.observe(binding)
        if before != after:
            raise ValueError("native_setup_accounting_drift")
    result = {
        "schema_version": 1,
        "status": "NATIVE_RUNTIME_" + request["action"].upper(),
        "manifest_sha256": expected,
        "identity_manifest_sha256": registration["identity_manifest_sha256"],
        "changed_files": changed,
        "active": active,
        "counter": after,
        "operator_uid": uid,
        "execution_authorized": False,
        "new_reservations": 0,
        "new_simulations": 0,
    }
    if request["action"] == "preflight":
        result["environment_observation"] = observation
    return result


def main(known):
    try:
        if len(sys.argv) != 2:
            raise ValueError("native_setup_fixed_identity")
        raw = sys.stdin.read(LIMIT + 1).encode("ascii")
        reply = apply(closed(raw), sys.argv[1], known)
        sys.stdout.write(canonical(reply).decode("ascii") + "\n")
    except Exception:
        sys.stderr.write("NATIVE_SETUP_REJECTED\n")
        sys.exit(65)
