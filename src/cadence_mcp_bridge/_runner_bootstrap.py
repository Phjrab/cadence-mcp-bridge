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


def _operator_lock(target):
    # Existing-domain provisioning is separate. Never create a substitute lock.
    if os.name == "nt":
        return None  # Disposable local staging tests only.
    import fcntl

    current = target
    while True:
        info = os.lstat(current)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.getuid())
            or info.st_mode & 18
        ):
            raise ValueError("operator_ancestor_permissions")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    path = os.path.join(target, "run.lock")
    info = os.lstat(path)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & 18
    ):
        raise ValueError("operator_lock_permissions")
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    held = os.fstat(fd)
    if (info.st_dev, info.st_ino) != (held.st_dev, held.st_ino):
        os.close(fd)
        raise ValueError("operator_lock_drift")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        os.close(fd)
        raise ValueError("operator_domain_busy")
    try:
        after = os.lstat(path)
        if (
            not stat.S_ISREG(after.st_mode)
            or after.st_nlink != 1
            or after.st_uid != os.getuid()
            or after.st_mode & 18
            or (after.st_dev, after.st_ino) != (held.st_dev, held.st_ino)
        ):
            raise ValueError("operator_lock_drift")
    except Exception:
        os.close(fd)
        raise ValueError("operator_lock_drift")
    return fd


def _operator_state(path):
    value = closed(regular(path))
    if (
        not isinstance(value, dict)
        or set(value) != set(("schema_version", "manifest_sha256"))
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or (os.name != "nt" and os.stat(path).st_mode & 63)
    ):
        raise ValueError("operator_state_shape_or_permissions")
    return value


def operator_activation(target, expected):
    target = directory(target)
    fd = _operator_lock(target)
    try:
        version = os.path.join(target, "runtime", expected)
        manifest, contents, raw = validate(version, expected)
        target_binding(manifest, contents, target)
        if manifest["schema_version"] != 2:
            raise ValueError("operator_manifest_version")
        if os.path.lexists(os.path.join(target, "execution.lock")):
            raise ValueError("active_or_unresolved_jobs")
        if os.path.lexists(os.path.join(target, "operator-runner-revoked.json")):
            raise ValueError("operator_runner_revoked")
        state = os.path.join(target, "active-operator-runner.json")
        value = {"schema_version": 1, "manifest_sha256": expected}
        if os.path.lexists(state) and _operator_state(state) != value:
            raise ValueError("update_requires_lifecycle_gate")
        binary = os.path.join(target, "bin")
        if not os.path.exists(binary):
            os.mkdir(binary, 448)
        directory(binary)
        path = os.path.join(binary, "cadence-operator-runner")
        launcher = contents["launcher.py"]
        # Exact partial initial activation is resumable; unrelated bytes stay untouched.
        if os.path.lexists(path):
            if regular(path) != launcher or (
                os.name != "nt" and stat.S_IMODE(os.stat(path).st_mode) != 448
            ):
                raise ValueError("operator_launcher_collision")
        else:
            exclusive(path, launcher, 448)
        existed = os.path.lexists(state)
        if not existed:
            exclusive(state, canonical(value))
        return {
            "status": "EXISTING_EXACT_OPERATOR_ACTIVATION"
            if existed
            else "OPERATOR_ACTIVATION_RECORDED_NOT_QUALIFIED",
            "manifest_sha256": expected,
            "execution_authorized": False,
        }
    finally:
        if fd is not None:
            os.close(fd)


def operator_deactivate(target, expected):
    target = directory(target)
    fd = _operator_lock(target)
    try:
        manifest, contents, raw = validate(os.path.join(target, "runtime", expected), expected)
        target_binding(manifest, contents, target)
        active = _operator_state(os.path.join(target, "active-operator-runner.json"))
        if active != {"schema_version": 1, "manifest_sha256": expected}:
            raise ValueError("activation_previous_mismatch")
        revoked = os.path.join(target, "operator-runner-revoked.json")
        if os.path.lexists(revoked):
            if _operator_state(revoked) != active:
                raise ValueError("operator_revocation_drift")
        else:
            exclusive(revoked, canonical(active))
        return {"status": "OPERATOR_DEACTIVATED_HISTORY_RETAINED", "execution_authorized": False}
    finally:
        if fd is not None:
            os.close(fd)


def _sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _retain_exact(path, data, mode=384):
    if os.path.lexists(path):
        if regular(path) != data:
            raise ValueError("operator_update_history_drift")
    else:
        exclusive(path, data, mode)
        _sync_directory(os.path.dirname(path))


def _replace_operator_file(source, target):
    if os.name == "nt":
        os.replace(source, target)  # Modern Python disposable staging only.
    else:
        os.rename(source, target)


def operator_preflight_update(target, expected, previous):
    # This is ONLY a same-profile preflight-launcher update. Native worker upgrades
    # require a later lifecycle gate; equal arbitrary runner bytes do not suffice.
    target = directory(target)
    fd = _operator_lock(target)
    try:
        old, old_files, old_raw = validate(os.path.join(target, "runtime", previous), previous)
        new, new_files, new_raw = validate(os.path.join(target, "runtime", expected), expected)
        target_binding(old, old_files, target)
        target_binding(new, new_files, target)
        known_preflight = "aa3e40fdbce271940545bc7cd62883cb454d7c6712d229c9aa991434237bf9db"
        if (
            old["schema_version"] != 2
            or new["schema_version"] != 2
            or digest(old_files["runner.py"].replace(b"\r\n", b"\n")) != known_preflight
            or any(old_files[name] != new_files[name] for name in FILES if name != "launcher.py")
            or previous == expected
        ):
            raise ValueError("preflight_only_update_required")
        if os.path.lexists(os.path.join(target, "execution.lock")) or os.path.lexists(
            os.path.join(target, "operator-runner-revoked.json")
        ):
            raise ValueError("active_or_revoked_operator_runner")
        before = {"schema_version": 1, "manifest_sha256": previous}
        after = {"schema_version": 1, "manifest_sha256": expected}
        state = os.path.join(target, "active-operator-runner.json")
        current = _operator_state(state)
        launcher = os.path.join(directory(os.path.join(target, "bin")), "cadence-operator-runner")
        actual = regular(launcher)
        if (
            current not in (before, after)
            or actual not in (old_files["launcher.py"], new_files["launcher.py"])
            or (os.name != "nt" and stat.S_IMODE(os.stat(launcher).st_mode) != 448)
        ):
            raise ValueError("operator_update_state_drift")
        if current == after and actual != new_files["launcher.py"]:
            raise ValueError("operator_update_state_drift")
        history = os.path.join(target, "operator-activation-history")
        if not os.path.exists(history):
            os.mkdir(history, 448)
            _sync_directory(target)
        directory(history)
        key = digest((previous + "-" + expected).encode("ascii"))
        record = {
            "schema_version": 1,
            "scope": "PREFLIGHT_ONLY_SAME_PROFILE",
            "previous": before,
            "next": after,
            "old_launcher_sha256": digest(old_files["launcher.py"]),
            "new_launcher_sha256": digest(new_files["launcher.py"]),
        }
        evidence = os.path.join(history, key + ".json")
        # A partial or complete pair is recoverable only with the preexisting exact
        # history. A substituted new pointer cannot create its own authorization.
        if (current == after or actual == new_files["launcher.py"]) and not os.path.lexists(
            evidence
        ):
            raise ValueError("operator_update_history_missing")
        _retain_exact(evidence, canonical(record))
        if actual != new_files["launcher.py"]:
            pending = os.path.join(target, "bin", "operator-launcher-update.pending")
            _retain_exact(pending, new_files["launcher.py"], 448)
            if os.name != "nt" and stat.S_IMODE(os.stat(pending).st_mode) != 448:
                raise ValueError("operator_update_pending_permissions")
            _replace_operator_file(pending, launcher)
            _sync_directory(os.path.dirname(launcher))
        if current != after:
            pending = os.path.join(target, "operator-pointer-update.pending")
            _retain_exact(pending, canonical(after))
            _replace_operator_file(pending, state)
            _sync_directory(target)
        _retain_exact(os.path.join(history, key + ".complete.json"), canonical(record))
        return {
            "status": "OPERATOR_PREFLIGHT_UPDATE_RECORDED",
            "manifest_sha256": expected,
            "previous_manifest_sha256": previous,
            "execution_authorized": False,
        }
    finally:
        if fd is not None:
            os.close(fd)


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "install":
        result = install(sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) == 4 and sys.argv[1] == "verify":
        validate(os.path.join(directory(sys.argv[2]), "runtime", sys.argv[3]), sys.argv[3])
        result = {"status": "INSTALL_CONTENT_VERIFIED", "execution_authorized": False}
    elif len(sys.argv) == 4 and sys.argv[1] == "activate":
        result = activation(sys.argv[2], sys.argv[3], None)
    elif len(sys.argv) == 5 and sys.argv[1] == "update-operator-preflight":
        result = operator_preflight_update(sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) == 4 and sys.argv[1] == "activate-operator":
        result = operator_activation(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == "deactivate-operator":
        result = operator_deactivate(sys.argv[2], sys.argv[3])
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
