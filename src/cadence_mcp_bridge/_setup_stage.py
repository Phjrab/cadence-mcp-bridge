"""Fixed explicit package staging asset; importing it never provisions a VM."""

# mypy: ignore-errors
import base64
import hashlib
import json
import os
import stat
import sys


def main():
    import pwd

    raw = sys.stdin.read(262145)
    if len(raw) > 262144:
        raise ValueError("stage_limit")
    v = json.loads(raw)
    if json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True) != raw:
        raise ValueError("stage_canonical")
    if set(v) != set(("profile", "expected", "files")):
        raise ValueError("stage_shape")
    expected = sys.argv[1]
    if (
        len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)
        or v["expected"] != expected
    ):
        raise ValueError("stage_binding")
    p = v["profile"]
    actual = os.uname()
    if (actual[0], actual[1], actual[4], pwd.getpwuid(os.getuid()).pw_name) != (
        p["host"]["os"],
        p["host"]["hostname"],
        p["host"]["architecture"],
        p["host"]["user"],
    ) or os.getuid() == 0:
        raise ValueError("stage_operator")
    workspace = p["paths"]["workspace_root"]
    guest_home = pwd.getpwuid(os.getuid()).pw_dir
    if not workspace.startswith(guest_home + "/") or os.path.realpath(workspace) != workspace:
        raise ValueError("stage_workspace")
    current = workspace
    while True:
        info = os.lstat(current)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.getuid())
            or info.st_mode & 18
        ):
            raise ValueError("stage_ancestor")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    members = set(
        ("setup.py", "migration.py", "reservations.py", "installer.py", "probe.py", "manifest.json")
    )
    confirmation_members = set(
        ("confirmation.py", "reservations.py", "installer.py", "probe.py", "manifest.json")
    )
    migration_members = set(
        ("migration.py", "reservations.py", "installer.py", "probe.py", "manifest.json")
    )
    migration = set(v["files"]) == migration_members
    if migration:
        members = migration_members
    confirmation = set(v["files"]) == confirmation_members
    if confirmation:
        members = confirmation_members
    if set(v["files"]) != members:
        raise ValueError("stage_members")
    assets = dict((name, base64.b64decode(raw)) for name, raw in v["files"].items())
    if (
        any(len(raw) > 262144 for raw in assets.values())
        or hashlib.sha256(assets["manifest.json"]).hexdigest() != expected
    ):
        raise ValueError("stage_manifest")
    m = json.loads(assets["manifest.json"])
    kind = (
        "EXISTING_DOMAIN_OPERATOR_HELPER"
        if migration
        else (
            "STANDARD_VM_OPERATOR_CONFIRMATION_HELPER"
            if confirmation
            else "STANDARD_VM_DOMAIN_SETUP_HELPER"
        )
    )
    if set(m) != set(("schema_version", "kind", "files")) or (
        type(m["schema_version"]) is not int or m["schema_version"] != 1
    ):
        raise ValueError("stage_manifest_schema")
    if m["kind"] != kind or set(m["files"]) != members - set(("manifest.json",)):
        raise ValueError("stage_manifest_shape")
    for name in m["files"]:
        if m["files"][name] != {
            "sha256": hashlib.sha256(assets[name]).hexdigest(),
            "bytes": len(assets[name]),
        }:
            raise ValueError("stage_asset")

    def sync(path):
        fd = os.open(path, os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)

    def directory(path):
        if not os.path.lexists(path):
            os.mkdir(path, 448)
            sync(os.path.dirname(path))
        info = os.lstat(path)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 18
            or os.path.realpath(path) != path
        ):
            raise ValueError("stage_directory")

    parent = workspace + "/.cadence_mcp-setup"
    if migration:
        managed = p["paths"]["managed_root"]
        if not managed.startswith(workspace + "/") or os.path.realpath(managed) != managed:
            raise ValueError("stage_existing_root")
        if not os.path.isdir(managed):
            raise ValueError("stage_existing_root_missing")
        current = managed
        while current != workspace:
            info = os.lstat(current)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 18:
                raise ValueError("stage_existing_root_trust")
            current = os.path.dirname(current)
        parent = managed + "/operator-helpers"
    directory(parent)
    stage = parent + "/" + expected
    directory(stage)
    if set(os.listdir(stage)) - members:
        raise ValueError("stage_partial_inventory")
    changed = 0
    for name, data in assets.items():
        path = stage + "/" + name
        if os.path.lexists(path):
            info = os.lstat(path)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
                or info.st_mode & 18
            ):
                raise ValueError("stage_file")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            stream = os.fdopen(fd, "rb")
            try:
                before = os.fstat(fd)
                if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino) or stream.read(
                    262145
                ) != data:
                    raise ValueError("stage_retained_content")
                after = os.lstat(path)
                if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
                    raise ValueError("stage_file_drift")
            finally:
                stream.close()
        else:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384)
            stream = os.fdopen(fd, "wb")
            try:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
            finally:
                stream.close()
            changed += 1
    sync(stage)
    print(
        json.dumps(
            {
                "status": (
                    "STANDARD_VM_CONFIRMATION_HELPER_STAGED"
                    if confirmation
                    else "STANDARD_VM_SETUP_HELPER_STAGED"
                ),
                "manifest_sha256": expected,
                "changed_files": changed,
                "execution_authorized": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("STANDARD_VM_SETUP_STAGING_REJECTED\n")
        sys.exit(1)
