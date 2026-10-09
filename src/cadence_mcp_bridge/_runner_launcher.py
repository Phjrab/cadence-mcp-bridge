#!/usr/bin/python -B
"""Fixed launcher for an operator root; no shell, eval or reference fallback."""

# mypy: ignore-errors
import hashlib
import json
import os
import stat
import subprocess
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
        raise ValueError("unqualified_command")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.realpath(root) != root:
        raise ValueError("linked_root")
    trusted_directory_chain(root)
    operator = os.path.basename(__file__) == "cadence-operator-runner"
    state = "active-operator-runner.json" if operator else "active-runner.json"
    revoked = "operator-runner-revoked.json" if operator else "runner-revoked.json"
    path = root + "/" + state
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("activation_type")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 63):
        raise ValueError("activation_permissions")
    stream = open(path, "rb")
    try:
        raw = stream.read(1025)
    finally:
        stream.close()
    value = json.loads(raw.decode("ascii"))
    if (
        set(value) != set(("schema_version", "manifest_sha256"))
        or value["schema_version"] != 1
        or (operator and type(value["schema_version"]) is not int)
    ):
        raise ValueError("activation_shape")
    digest = value["manifest_sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("activation_digest")
    if sys.argv[2] != digest:
        raise ValueError("selected_manifest_mismatch")
    directory = root + "/runtime/" + digest
    if os.path.lexists(root + "/" + revoked) or os.path.realpath(directory) != directory:
        raise ValueError("runner_revoked_or_linked")
    trusted_directory_chain(directory)
    stream = open(directory + "/manifest.json", "rb")
    try:
        raw = stream.read(262145)
    finally:
        stream.close()
    if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("manifest_binding")
    manifest = json.loads(raw.decode("ascii"))
    if operator:
        info = os.lstat(__file__)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or os.path.realpath(__file__) != os.path.abspath(__file__)
            or (
                os.name != "nt"
                and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 448)
            )
        ):
            raise ValueError("operator_launcher_permissions")
        stream = open(__file__, "rb")
        try:
            data = stream.read(262145)
        finally:
            stream.close()
        if manifest["files"]["launcher.py"] != {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }:
            raise ValueError("operator_launcher_drift")
    runner = directory + "/runner.py"
    info = os.lstat(runner)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or os.path.realpath(runner) != runner:
        raise ValueError("runner_type")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 18):
        raise ValueError("runner_permissions")
    stream = open(runner, "rb")
    try:
        raw = stream.read(262145)
    finally:
        stream.close()
    if manifest["files"]["runner.py"] != {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }:
        raise ValueError("runner_drift")
    args = ["/usr/bin/python", "-E", "-s", "-B", runner, sys.argv[1], digest] + sys.argv[3:]
    return subprocess.call(args, shell=False, close_fds=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stderr.write("RUNNER_SETUP_REQUIRED: verify activation, trust and immutable files\n")
        sys.exit(1)
