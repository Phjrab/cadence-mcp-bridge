"""Fixed hash-bound native runtime entry. Python2.6, strict closed stdin.

No registration/confirmation/admin command exists here. The separately installed
operator activation record is mandatory for admission; lookup cannot dispatch.
"""

# mypy: ignore-errors
import hashlib
import json
import os
import stat
import sys

LIMIT = 262144
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
    "profile.json",
    "registration.json",
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or os.path.realpath(path) != path:
        raise ValueError("native_runtime_file_type")
    if os.name != "posix" or info.st_uid != os.getuid() or info.st_mode & 63:
        raise ValueError("native_runtime_file_permissions")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, "rb")
    try:
        before = os.fstat(fd)
        data = stream.read(LIMIT + 1)
        after = os.lstat(path)
        expected = (info.st_dev, info.st_ino, info.st_size, info.st_mtime)
        if (
            len(data) > LIMIT
            or expected != (before.st_dev, before.st_ino, before.st_size, before.st_mtime)
            or expected != (after.st_dev, after.st_ino, after.st_size, after.st_mtime)
        ):
            raise ValueError("native_runtime_file_drift")
        return data
    finally:
        stream.close()


def closed(raw):
    value = json.loads(raw.decode("ascii"))
    if len(raw) > LIMIT or canonical(value) != raw:
        raise ValueError("native_runtime_noncanonical")
    return value


def validate(expected):
    if os.name != "posix" or os.getuid() == 0 or len(expected) != 64:
        raise ValueError("native_runtime_normal_posix_user_required")
    here = os.path.dirname(os.path.abspath(__file__))
    current = here
    while True:
        info = os.lstat(current)
        if (
            not stat.S_ISDIR(info.st_mode)
            or os.path.realpath(current) != current
            or info.st_uid not in (0, os.getuid())
            or info.st_mode & (63 if current == here else 18)
        ):
            raise ValueError("native_runtime_ancestor_permissions")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    raw = read(here + "/manifest.json")
    manifest = closed(raw)
    if (
        digest(raw) != expected
        or os.path.basename(here) != expected
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
    ):
        raise ValueError("native_runtime_manifest_binding")
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 3
        or manifest["kind"] != "STANDARD_VM_CONFIRMED_NATIVE_RUNTIME"
    ):
        raise ValueError("native_runtime_manifest_kind")
    if set(manifest["files"]) != set(FILES) or set(os.listdir(here)) != set(
        FILES + ("manifest.json",)
    ):
        raise ValueError("native_runtime_inventory")
    assets = {}
    for name in FILES:
        data = read(here + "/" + name)
        if manifest["files"][name] != {"sha256": digest(data), "bytes": len(data)}:
            raise ValueError("native_runtime_asset_drift")
        assets[name] = data
    profile = json.loads(assets["profile.json"].decode("ascii"))
    if (
        digest(assets["profile.json"]) != manifest["profile_sha256"]
        or digest(assets["registration.json"]) != manifest["registration_sha256"]
        or profile["environment_id"] != manifest["environment_id"]
    ):
        raise ValueError("native_runtime_configuration_binding")
    if here != profile["paths"]["managed_root"] + "/runtime/" + expected:
        raise ValueError("native_runtime_root_binding")
    return here, manifest, assets, profile


def activation(profile, expected):
    # Caller holds the same existing run.lock used by operator activation.
    root = profile["paths"]["managed_root"]
    pointer = closed(read(root + "/active-native-provider.json"))
    if (
        pointer != {"schema_version": 1, "manifest_sha256": expected}
        or type(pointer["schema_version"]) is not int
    ):
        raise ValueError("native_runtime_activation_mismatch")
    if os.path.lexists(root + "/native-provider-revoked.json"):
        raise ValueError("native_runtime_revoked")


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in ("authorize", "accept", "lookup", "cancel_pending"):
        raise ValueError("native_runtime_fixed_action")
    expected, action = sys.argv[1:]
    here, manifest, assets, profile = validate(expected)
    request = closed(sys.stdin.read(LIMIT + 1).encode("ascii"))
    if (
        set(request)
        != set(
            (
                "schema_version",
                "action",
                "operation_id",
                "plan",
                "plan_sha256",
                "identity_manifest_sha256",
            )
        )
        or type(request["schema_version"]) is not int
        or request["schema_version"] != 1
        or request["action"] != action
        or digest(canonical(request["plan"])) != request["plan_sha256"]
    ):
        raise ValueError("native_runtime_request_binding")
    registration = closed(assets["registration.json"])
    if request["identity_manifest_sha256"] != registration["identity_manifest_sha256"]:
        raise ValueError("native_runtime_accounting_anchor")
    # Import only verified fixed members; Python -B forbids extra bytecode files.
    sys.path.insert(0, here)
    import reservations
    import confirmation
    import probe
    import storage
    import copying
    import rendering
    import installer
    import operations
    import gate
    import worker

    bound_gate = gate.ConfirmedGate(
        profile,
        assets["profile.json"],
        registration,
        expected,
        manifest["files"]["probe.py"]["sha256"],
        (reservations, confirmation, probe, storage, copying),
        lambda: activation(profile, expected),
    )
    history = closed(
        read(profile["paths"]["managed_root"] + "/native-provider-history/" + expected + ".json")
    )
    if (
        set(history)
        != set(
            ("schema_version", "manifest_sha256", "identity_manifest_sha256", "operator_authority")
        )
        or type(history["schema_version"]) is not int
        or history["schema_version"] != 1
        or history["manifest_sha256"] != expected
        or history["identity_manifest_sha256"] != registration["identity_manifest_sha256"]
    ):
        raise ValueError("native_runtime_activation_history")
    confirmation.authority_reference(history["operator_authority"])
    eda = worker.EdaWorker(bound_gate, operations, rendering, copying, installer)
    coordinator = operations.NativeCoordinator(
        profile["paths"]["managed_root"], reservations, bound_gate, operations.ForkWorker(eda.run)
    )
    if action == "authorize":
        if request["operation_id"] is not None:
            raise ValueError("native_runtime_authorize_identity")
        result = coordinator.authorize(None, request["plan"])
    else:
        operations.uuid(request["operation_id"])
        if action == "accept":
            result = coordinator.accept(request["operation_id"], request["plan"])
        elif action == "lookup":
            result = coordinator.lookup(request["operation_id"], request["plan"])
        else:
            result = coordinator.cancel_pending(request["operation_id"], request["plan"])
    reply = {
        "schema_version": 1,
        "runtime_manifest_sha256": expected,
        "identity_manifest_sha256": registration["identity_manifest_sha256"],
        "action": action,
        "payload": result,
    }
    raw = canonical(reply)
    if len(raw) > LIMIT:
        raise ValueError("native_runtime_response_size")
    sys.stdout.write(raw.decode("ascii") + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("NATIVE_PROVIDER_REJECTED\n")
        sys.exit(65)
