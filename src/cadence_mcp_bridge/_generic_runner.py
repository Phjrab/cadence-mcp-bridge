"""Immutable generic runner preflight asset; standalone Python2.6, no eval."""

# mypy: ignore-errors
import hashlib
import json
import os
import stat
import sys


def trusted_directory_chain(path):
    if os.name == "nt":
        return  # Windows staging is never native runner qualification.
    current = os.path.abspath(path)
    while True:
        info = os.lstat(current)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.getuid())
            or info.st_mode & 18
        ):
            raise ValueError("runner_directory_permissions")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ("identity", "preflight"):
        raise ValueError("runner_command_not_qualified")
    directory = os.path.dirname(os.path.abspath(__file__))
    if os.path.realpath(directory) != directory or os.path.basename(directory) != sys.argv[2]:
        raise ValueError("runner_location")
    trusted_directory_chain(directory)
    # The installed bootstrap verifier is intentionally kept outside the version
    # tree. Import only the hash-verified fixed probe from this private version.
    info = os.lstat(directory + "/manifest.json")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("runner_manifest_type")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 18):
        raise ValueError("runner_manifest_permissions")
    stream = open(directory + "/manifest.json", "rb")
    try:
        raw = stream.read(262145)
    finally:
        stream.close()
    if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != sys.argv[2]:
        raise ValueError("runner_manifest_binding")
    manifest = json.loads(raw.decode("ascii"))
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 2:
        raise ValueError("runner_manifest_version")
    if set(manifest.get("files", {})) != set(
        ("profile.json", "probe.py", "runner.py", "launcher.py", "reservations.py")
    ):
        raise ValueError("runner_manifest_shape")
    for name in ("profile.json", "probe.py", "runner.py", "launcher.py", "reservations.py"):
        path = directory + "/" + name
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or os.path.realpath(path) != path:
            raise ValueError("runner_asset_type")
        if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 18):
            raise ValueError("runner_asset_permissions")
        stream = open(path, "rb")
        try:
            data = stream.read(262145)
        finally:
            stream.close()
        if manifest["files"][name] != {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }:
            raise ValueError("runner_asset_drift")
    if set(os.listdir(directory)) != set(
        ("profile.json", "probe.py", "runner.py", "launcher.py", "reservations.py", "manifest.json")
    ):
        raise ValueError("runner_inventory")
    import probe

    stream = open(directory + "/profile.json", "rb")
    try:
        profile_data = stream.read(32769)
    finally:
        stream.close()
    profile = probe.validate_profile(json.loads(profile_data.decode("utf-8")))
    root = profile["paths"]["managed_root"]
    if directory != root + "/runtime/" + sys.argv[2]:
        raise ValueError("runner_root_binding")
    if sys.argv[1] == "identity":
        result = {
            "schema_version": 1,
            "environment_id": profile["environment_id"],
            "manifest_sha256": sys.argv[2],
            "execution_authorized": False,
            "status": "RUNNER_CONTENT_BOUND_ENVIRONMENT_UNASSESSED",
        }
    else:
        if len(sys.argv) != 4 or not probe.matches(
            probe.re.compile(r"^[0-9a-f]{32}$"), sys.argv[3]
        ):
            raise ValueError("runner_nonce")
        result = probe.observe(
            profile,
            hashlib.sha256(profile_data).hexdigest(),
            manifest["files"]["probe.py"]["sha256"],
            sys.argv[3],
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        reason = str(failure)
        allowed = ("executable_permissions", "host_mismatch", "disk_floor", "runner_root_binding")
        sys.stderr.write((reason if reason in allowed else "RUNNER_REJECTED") + "\n")
        sys.exit(1)
