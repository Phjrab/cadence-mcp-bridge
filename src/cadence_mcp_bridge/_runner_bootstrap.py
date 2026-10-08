"""Fixed runner content installer; standalone Python 2.6-compatible stdlib asset."""

# mypy: ignore-errors
import hashlib
import json
import os
import stat
import sys

LEGACY_FILES = ("profile.json", "probe.py", "runner.py", "launcher.py")
FILES = LEGACY_FILES + ("reservations.py",)
LIMIT = 262144


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(data):
    return hashlib.sha256(data).hexdigest()


def closed(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_field")
            result[key] = value
        return result

    if len(data) > LIMIT:
        raise ValueError("input_limit")
    # Python2.6 has no object_pairs_hook; generated manifests use exact canonical bytes.
    try:
        value = json.loads(data.decode("ascii"), object_pairs_hook=pairs)
    except TypeError:
        value = json.loads(data.decode("ascii"))
    if canonical(value) != data:
        raise ValueError("noncanonical_document")
    return value


def regular(path):
    if os.path.realpath(path) != os.path.abspath(path):
        raise ValueError("linked_path")
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("unsafe_file")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 18):
        raise ValueError("unsafe_owner_or_mode")
    stream = open(path, "rb")
    try:
        before = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("file_open_drift")
        data = stream.read(LIMIT + 1)
        after = os.lstat(path)
        if len(data) > LIMIT or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("file_drift_or_size")
        return data
    finally:
        stream.close()


def directory(path):
    path = os.path.abspath(path)
    if os.path.realpath(path) != path or not os.path.isdir(path):
        raise ValueError("unsafe_directory")
    info = os.stat(path)
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 18):
        raise ValueError("unsafe_directory_owner_or_mode")
    return path


def validate(bundle, expected):
    directory(bundle)
    raw = regular(os.path.join(bundle, "manifest.json"))
    if digest(raw) != expected or len(expected) != 64:
        raise ValueError("plan_hash_mismatch")
    manifest = closed(raw)
    if set(manifest) != set(("schema_version", "files", "environment_id", "profile_sha256")):
        raise ValueError("manifest_shape")
    if manifest["schema_version"] not in (1, 2) or type(manifest["schema_version"]) is not int:
        raise ValueError("manifest_version")
    members = LEGACY_FILES if manifest["schema_version"] == 1 else FILES
    if set(manifest["files"]) != set(members) or set(os.listdir(bundle)) != set(
        members + ("manifest.json",)
    ):
        raise ValueError("bundle_inventory")
    contents = {}
    for name in members:
        value = regular(os.path.join(bundle, name))
        entry = manifest["files"][name]
        if set(entry) != set(("sha256", "bytes")) or entry != {
            "sha256": digest(value),
            "bytes": len(value),
        }:
            raise ValueError("asset_drift")
        contents[name] = value
    if digest(contents["profile.json"]) != manifest["profile_sha256"]:
        raise ValueError("profile_drift")
    return manifest, contents, raw


def exclusive(path, content, mode=384):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    stream = os.fdopen(descriptor, "wb")
    try:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    finally:
        stream.close()


def target_binding(manifest, contents, target):
    profile = json.loads(contents["profile.json"].decode("utf-8"))
    if (
        not isinstance(profile, dict)
        or profile.get("environment_id") != manifest["environment_id"]
        or not isinstance(profile.get("paths"), dict)
        or profile["paths"].get("managed_root") != target
    ):
        raise ValueError("installation_target_binding")


def install(bundle, target, expected):
    # Native installation always binds to the hash-verified operator managed root.
    manifest, contents, raw = validate(bundle, expected)
    target_binding(manifest, contents, os.path.abspath(target))
    return _install_content(bundle, target, expected, False)


def stage_windows(bundle, target, expected):
    # Windows cannot host this Linux runner. This is explicit local content staging,
    # never exposed by the standalone command and never usable on a Linux target.
    if os.name != "nt":
        raise ValueError("windows_local_staging_only")
    result = _install_content(bundle, target, expected, True)
    result["installation_scope"] = "WINDOWS_LOCAL_CONTENT_STAGING_ONLY"
    result["native_installation_verified"] = False
    return result


def _install_content(bundle, target, expected, staging):
    manifest, contents, raw = validate(bundle, expected)
    target = directory(target)
    if staging:
        if os.name != "nt":
            raise ValueError("windows_local_staging_only")
    else:
        target_binding(manifest, contents, target)
    versions = os.path.join(target, "runtime")
    if not os.path.exists(versions):
        os.mkdir(versions, 448)
    directory(versions)
    version = os.path.join(versions, expected)
    if os.path.exists(version):
        validate(version, expected)
        return {
            "status": "EXISTING_EXACT_INSTALL",
            "manifest_sha256": expected,
            "execution_authorized": False,
        }
    os.mkdir(version, 448)
    # A crash leaves a visible incomplete exclusive directory. It is never overwritten/deleted.
    for name in manifest["files"]:
        exclusive(os.path.join(version, name), contents[name])
    exclusive(os.path.join(version, "manifest.json"), raw)
    validate(version, expected)
    return {
        "status": "INSTALL_CONTENT_VERIFIED",
        "manifest_sha256": expected,
        "execution_authorized": False,
    }


def activation(target, expected, previous):
    target = directory(target)
    version = os.path.join(target, "runtime", expected)
    manifest, contents, raw = validate(version, expected)
    target_binding(manifest, contents, target)
    state = os.path.join(target, "active-runner.json")
    if os.path.exists(os.path.join(target, "execution.lock")):
        raise ValueError("active_or_unresolved_jobs")
    current = None
    if os.path.exists(state):
        current = closed(regular(state))
    if current != previous:
        raise ValueError("activation_previous_mismatch")
    # Initial activation is exclusive. Updates append a reviewed immutable record;
    # replacing an active pointer is deliberately unavailable until lifecycle lock provisioning.
    if current is not None:
        raise ValueError("update_requires_lifecycle_gate")
    binary = os.path.join(target, "bin")
    if not os.path.exists(binary):
        os.mkdir(binary, 448)
    directory(binary)
    launcher = regular(os.path.join(version, "launcher.py"))
    exclusive(os.path.join(binary, "cadence-runner"), launcher, 448)
    value = {"schema_version": 1, "manifest_sha256": expected}
    exclusive(state, canonical(value))
    return {
        "status": "ACTIVATION_RECORDED_NOT_QUALIFIED",
        "manifest_sha256": expected,
        "execution_authorized": False,
    }


def deactivate(target, expected):
    target = directory(target)
    version = os.path.join(target, "runtime", expected)
    manifest, contents, raw = validate(version, expected)
    target_binding(manifest, contents, target)
    active = closed(regular(os.path.join(target, "active-runner.json")))
    if active != {"schema_version": 1, "manifest_sha256": expected}:
        raise ValueError("activation_previous_mismatch")
    exclusive(os.path.join(target, "runner-revoked.json"), canonical(active))
    return {"status": "DEACTIVATED_HISTORY_RETAINED", "execution_authorized": False}


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "install":
        result = install(sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) == 4 and sys.argv[1] == "verify":
        validate(os.path.join(directory(sys.argv[2]), "runtime", sys.argv[3]), sys.argv[3])
        result = {"status": "INSTALL_CONTENT_VERIFIED", "execution_authorized": False}
    elif len(sys.argv) == 4 and sys.argv[1] == "activate":
        result = activation(sys.argv[2], sys.argv[3], None)
    elif len(sys.argv) == 4 and sys.argv[1] == "deactivate":
        result = deactivate(sys.argv[2], sys.argv[3])
    else:
        raise ValueError("fixed_install_command_required")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write(
            "RUNNER_INSTALL_REJECTED: verify plan, paths, owner, files and activation state\n"
        )
        sys.exit(1)
