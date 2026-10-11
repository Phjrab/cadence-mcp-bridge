"""Fixed migration entry: authenticate retained script bytes before execution."""
# mypy: ignore-errors
import sys

if __name__ == "__main__":
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        sys.exit(1)
    if sys.path:
        del sys.path[0]
    sys.path[:] = [item for item in sys.path if item]
import hashlib
import json
import os
import stat


def read(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime", "st_ctime")
        observed = tuple(getattr(before, key) for key in fields)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or
                before.st_mode & 18 or before.st_nlink != 1 or before.st_size > 262144):
            raise ValueError("migration_entry_file_trust")
        raw = os.read(fd, 262145)
        if (len(raw) != before.st_size or
                tuple(getattr(os.fstat(fd), key) for key in fields) != observed or
                tuple(getattr(os.lstat(path), key) for key in fields) != observed):
            raise ValueError("migration_entry_file_drift")
        return raw
    finally:
        os.close(fd)


def run(directory, action, expected):
    if (action not in ("inventory-existing", "apply-existing", "inventory-legacy-seal",
                      "seal-existing") or len(expected) != 64 or
            any(c not in "0123456789abcdef" for c in expected) or
            not os.path.isabs(directory) or os.path.realpath(directory) != directory):
        raise ValueError("migration_entry_binding")
    current = directory
    while True:
        info = os.lstat(current)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_mode & 18):
            raise ValueError("migration_entry_ancestor_trust")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    raw = read(directory + "/manifest.json")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("migration_entry_manifest_binding")
    manifest = json.loads(raw.decode("ascii"))
    if (manifest.get("kind") != "EXISTING_DOMAIN_OPERATOR_HELPER" or
            type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1):
        raise ValueError("migration_entry_manifest_kind")
    source = read(directory + "/migration.py")
    source_sha = hashlib.sha256(source).hexdigest()
    if manifest["files"]["migration.py"] != {"sha256": source_sha, "bytes": len(source)}:
        raise ValueError("migration_entry_source_binding")
    namespace = {"__name__": "bound_domain_migration", "__package__": "",
                 "__file__": directory + "/migration.py",
                 "_EXECUTING_MIGRATION_SHA256": source_sha}
    # Execute only retained authenticated bytes, never a reopened script path.
    eval(compile(source, namespace["__file__"], "exec"), namespace)
    original = sys.argv
    try:
        sys.argv = [namespace["__file__"], action, expected]
        return namespace["main"]()
    finally:
        sys.argv = original


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("migration_entry_arguments")
        run(*sys.argv[1:])
    except Exception:
        sys.stderr.write("OPERATOR_DOMAIN_MIGRATION_REJECTED\n")
        sys.exit(1)
