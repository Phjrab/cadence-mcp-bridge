"""Explicit operator-only installation metadata repair; standalone Python 2.6.

No import side effects or vendor execution. Plans and receipts are private.
Only group/other write removal is supported; contents and owners never change.
"""
# mypy: ignore-errors
import sys

if __name__ == "__main__":
    # Reject inherited Python search hooks before any filesystem-backed import.
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        sys.stderr.write("INSTALLATION_REPAIR_ISOLATED_PYTHON_REQUIRED\n")
        sys.exit(1)
    # The fixed operator invocation uses -E -s -B. Exclude script/CWD before
    # filesystem-backed imports; authenticated retained modules keep stdlib.
    _entry_search = sys.path[0] if sys.path else None
    sys.path[:] = [p for p in sys.path if p and p != _entry_search]
import os

if __name__ == "__main__":
    _entry_directories = set((os.path.realpath(os.getcwd()),))
    if "__file__" in globals():
        _entry_directories.add(os.path.realpath(os.path.dirname(os.path.abspath(__file__))))
    sys.path[:] = [p for p in sys.path if os.path.isabs(p) and
                  os.path.realpath(p) not in _entry_directories]
import errno
import hashlib
import json
import re
import stat
import subprocess

LIMIT = 16777216
MAX_ITEMS = 8192
try:
    TEXT = (basestring,)  # noqa: F821
except NameError:
    TEXT = (str,)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def valid_path(value):
    if not isinstance(value, TEXT) or not value.startswith("/") or len(value) > 512:
        raise ValueError("path")
    if any(part in ("", ".", "..") for part in value.split("/")[1:]):
        raise ValueError("path")
    return value


def inside(path, root):
    return path == root or path.startswith(root + "/")


def open_fixed(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    current = os.open("/", flags | os.O_DIRECTORY)
    try:
        parts = valid_path(path).split("/")[1:]
        for index, part in enumerate(parts):
            extra = os.O_DIRECTORY if index < len(parts) - 1 else 0
            child = os.open("/proc/self/fd/%d/%s" % (current, part), flags | extra)
            os.close(current)
            current = child
        result = current
        current = None
        return result
    finally:
        if current is not None:
            os.close(current)


def file_hash(fd):
    value = hashlib.sha256()
    os.lseek(fd, 0, 0)
    while True:
        block = os.read(fd, 65536)
        if not block:
            break
        value.update(block)
    return value.hexdigest()


def descriptor_path(fd):
    value = "/proc/%d/fd/%d" % (os.getpid(), fd)
    # Old CentOS ACL tools walk a proc magic symlink to a directory.
    # A terminal dot addresses exactly the held directory, without a walk.
    return value + "/." if stat.S_ISDIR(os.fstat(fd).st_mode) else value


def acl(fd):
    child = subprocess.Popen(
        ["/usr/bin/getfacl", "-cpn", "--", descriptor_path(fd)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
    )
    out, err = child.communicate()
    if child.returncode or err or len(out) > 32768:
        raise ValueError("acl")
    return out.decode("ascii")


def snapshot(path):
    fd = open_fixed(path)
    try:
        return snapshot_descriptor(path, fd)
    finally:
        os.close(fd)


def snapshot_descriptor(path, fd):
    info = os.fstat(fd)
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise ValueError("file_type")
    # Reject a hardlink already present at this held observation, including one
    # added after an earlier pathname or descriptor link-count check. Keep the
    # historical inventory schema unchanged; trailing stability also binds nlink.
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise ValueError("hardlinked_code")
    result = {
        "path": path, "dev": info.st_dev, "ino": info.st_ino,
        "uid": info.st_uid, "gid": info.st_gid,
        "size": info.st_size if stat.S_ISREG(info.st_mode) else None,
        "mtime": "%.17g" % info.st_mtime if stat.S_ISREG(info.st_mode) else None,
        "mode": stat.S_IMODE(info.st_mode),
        "kind": "file" if stat.S_ISREG(info.st_mode) else "directory",
        "sha256": file_hash(fd) if stat.S_ISREG(info.st_mode) else None,
        "acl": acl(fd),
    }
    # ACL tools run while the descriptor is held. Reject changes during that
    # observation, including restored mtimes or unchanged file length.
    trailing = os.fstat(fd)
    stability = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                 "st_size", "st_mtime", "st_ctime")
    if any(getattr(info, key) != getattr(trailing, key) for key in stability):
        raise ValueError("snapshot_race")
    if result["sha256"] is not None and file_hash(fd) != result["sha256"]:
        raise ValueError("snapshot_race")
    final = os.fstat(fd)
    if any(getattr(trailing, key) != getattr(final, key) for key in stability):
        raise ValueError("snapshot_race")
    check = os.lstat(path)
    if (check.st_dev, check.st_ino, check.st_mode) != (
        info.st_dev, info.st_ino, info.st_mode
    ) or os.path.realpath(path) != path:
        raise ValueError("race")
    return result


def normalize_acl(value):
    return [line.split("#", 1)[0].rstrip() for line in value.splitlines() if line]


def restricted_acl(before):
    result = []
    for line in normalize_acl(before):
        parts = line.split(":")
        default = parts[0] == "default"
        offset = 1 if default else 0
        role, who, perms = parts[offset:offset + 3]
        if default:
            if not (role == "user" and who == ""):
                perms = perms.replace("w", "-")
        elif role in ("group", "other", "mask"):
            perms = perms.replace("w", "-")
        parts[offset + 2] = perms
        result.append(":".join(parts))
    return "\n".join(result) + "\n"


def chmod_acl(before, mode):
    lines = normalize_acl(before)
    has_mask = any(line.startswith("mask::") for line in lines)
    result = []
    for line in lines:
        role = line.split(":", 1)[0]
        shift = None
        if line.startswith("user::"):
            shift = 6
        elif line.startswith("other::"):
            shift = 0
        elif role == "mask" or (not has_mask and line.startswith("group::")):
            shift = 3
        if shift is not None:
            bits = (mode >> shift) & 7
            perms = "".join(flag if bits & bit else "-"
                            for flag, bit in (("r", 4), ("w", 2), ("x", 1)))
            line = line.rsplit(":", 1)[0] + ":" + perms
        result.append(line)
    return "\n".join(result) + "\n"


def plan(request):
    if set(request) != set(("installation_roots", "paths", "links",
                            "profile_sha256", "resource_lock")):
        raise ValueError("request_shape")
    roots, paths = request["installation_roots"], request["paths"]
    if not 1 <= len(roots) <= 3 or not 1 <= len(paths) <= MAX_ITEMS:
        raise ValueError("scope_size")
    for root in roots:
        valid_path(root)
        if os.path.realpath(root) != root or root.count("/") < 2:
            raise ValueError("installation_root")
    if paths != sorted(set(paths)):
        raise ValueError("duplicate_or_unsorted")
    records = []
    record_bytes = 0
    for path in paths:
        valid_path(path)
        if not any(inside(path, root) for root in roots):
            raise ValueError("scope_escape")
        record = snapshot(path)
        if record["kind"] == "file" and os.lstat(path).st_nlink != 1:
            raise ValueError("hardlinked_code")
        if record["mode"] & 3584:
            raise ValueError("special_mode")
        record["after_mode"] = record["mode"] & ~18
        record["after_acl"] = restricted_acl(record["acl"])
        record["reason"] = "remove_shared_code_write_preserve_content_owner_rx"
        record_bytes += len(canonical(record)) + 1
        if record_bytes > LIMIT:
            raise ValueError("inventory_serialized_limit")
        records.append(record)
    for link in request["links"]:
        if set(link) != set(("path", "target", "resolved")):
            raise ValueError("link_shape")
        if not any(inside(valid_path(link["path"]), r) for r in roots):
            raise ValueError("link_escape")
        if os.readlink(link["path"]) != link["target"]:
            raise ValueError("link_drift")
        if os.path.realpath(link["path"]) != link["resolved"]:
            raise ValueError("link_drift")
        if link["resolved"] not in paths:
            raise ValueError("unlisted_link_target")
    result = {
        "schema_version": 1, "scope": request, "records": records,
        "operation": "remove_022_and_default_acl_writes",
        "content_authority": "NONE", "execution_authorized": False,
    }
    return bounded_inventory({"plan": result, "plan_sha256": digest(result)})


def bounded_inventory(result):
    # Count the actual whole response including its terminal newline, and leave
    # room for the largest allowed authority string in a canonical apply/rollback
    # request. Individual target/ACL bounds alone do not bound the full plan.
    request = {"plan": result["plan"], "expected_plan_sha256": result["plan_sha256"],
               "operator_authority": u"\U0001f4a5" * 512}
    if len(canonical(result)) + 1 > LIMIT or len(canonical(request)) + 1 > LIMIT:
        raise ValueError("inventory_serialized_limit")
    return result


def verify_unlisted_ancestors(roots):
    # These directories are deliberately outside the exact mutation recipe.
    # Check them read-only, including /, rather than silently expanding targets.
    ancestors = set()
    for root in roots:
        parent = os.path.dirname(root)
        while True:
            ancestors.add(parent)
            if parent == "/":
                break
            parent = os.path.dirname(parent)
    for path in sorted(ancestors):
        fd = (os.open("/", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_DIRECTORY)
              if path == "/" else open_fixed(path))
        try:
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 18:
                raise ValueError("unlisted_ancestor_trust")
        finally:
            os.close(fd)


def emit(value):
    sys.stdout.write(canonical(value).decode("ascii") + "\n")
    sys.stdout.flush()


def metadata_equal(key, before, after):
    # New private inventories encode binary64 mtimes as round-trip strings.
    # Historical numeric records remain usable with their original digest/helper.
    if key == "mtime":
        before = "%.17g" % before if isinstance(before, float) else before
        after = "%.17g" % after if isinstance(after, float) else after
    return before == after


def completion_inventory(original):
    # Only the registered fixed installation recipe can enumerate new members;
    # no caller directory, glob or code path is accepted as a completion recipe.
    if original.get("recipe_id") == "standard-vm-model-trust-v1":
        return inventory_models({"profile": original["profile"],
            "model_include": original["model_include"]})["plan"]
    if original.get("recipe_id") == "standard-vm-trust-v1":
        return inventory(original["profile"])["plan"]
    raise ValueError("fixed_profile_recipe_required")


def verify_completed_targets(original, rollback, recipe_guard=False):
    # Recompute the whole exact recipe so skipped and previously processed targets
    # cannot escape final content/identity/ACL checks. plan() also rechecks links.
    final = plan(original["scope"])["plan"]
    if recipe_guard:
        # Refresh membership as well as stored paths. A new/renamed shared object
        # must not escape the original exact target scope, including on a no-op.
        fresh = completion_inventory(original)
        if fresh["scope"] != original["scope"]:
            raise ValueError("completion_recipe_scope")
        if original.get("recipe_id") == "standard-vm-trust-v1" and (
                not isinstance(original.get("readonly_compatibility_links"), list) or
                fresh.get("readonly_compatibility_links") !=
                original["readonly_compatibility_links"]):
            raise ValueError("completion_external_links")
        final = fresh
    if len(final["records"]) != len(original["records"]):
        raise ValueError("completion_record_count")
    for old, now in zip(original["records"], final["records"]):
        invariant = ("path", "dev", "ino", "uid", "gid", "kind",
                     "sha256", "size", "mtime", "reason")
        if any(not metadata_equal(key, old[key], now[key]) for key in invariant):
            raise ValueError("completion_protected_drift")
        target_mode = old["mode"] if rollback else old["after_mode"]
        target_acl = old["acl"] if rollback else old["after_acl"]
        if now["mode"] != target_mode or normalize_acl(now["acl"]) != normalize_acl(target_acl):
            raise ValueError("completion_metadata")


def _mutate_locked(request, rollback=False, receipt_guard=False, resource_guard=None):
    if set(request) != set(("plan", "expected_plan_sha256", "operator_authority")):
        raise ValueError("mutation_shape")
    original = request["plan"]
    if digest(original) != request["expected_plan_sha256"]:
        raise ValueError("plan_binding")
    authority = request["operator_authority"]
    if not isinstance(authority, TEXT) or not 1 <= len(authority) <= 512:
        raise ValueError("operator_authority_required")
    current = plan(original["scope"])["plan"]
    if len(current["records"]) != len(original["records"]):
        raise ValueError("record_count")
    allowed = []
    for old, now in zip(original["records"], current["records"]):
        invariant = ("path", "dev", "ino", "uid", "gid", "kind",
                     "sha256", "size", "mtime", "reason")
        if any(not metadata_equal(key, old[key], now[key]) for key in invariant):
            raise ValueError("protected_drift")
        if old["after_mode"] != old["mode"] & ~18:
            raise ValueError("mode_plan")
        if old["after_acl"] != restricted_acl(old["acl"]):
            raise ValueError("acl_plan")
        before = (now["mode"] == old["mode"] and
                  normalize_acl(now["acl"]) == normalize_acl(old["acl"]))
        after = (now["mode"] == old["after_mode"] and
                 normalize_acl(now["acl"]) == normalize_acl(old["after_acl"]))
        intermediate = (now["mode"] == old["after_mode"] and
                        normalize_acl(now["acl"]) ==
                        normalize_acl(chmod_acl(old["acl"], old["after_mode"])))
        rollback_intermediate = (rollback and now["mode"] == old["mode"] and
            normalize_acl(now["acl"]) ==
            normalize_acl(chmod_acl(old["after_acl"], old["mode"])))
        if not (before or after or intermediate or rollback_intermediate):
            raise ValueError("unexpected_metadata")
        allowed.append((old, now, before, after))
    if resource_guard is not None:
        resource_guard()
    emit({"event": "validated", "plan_sha256": request["expected_plan_sha256"],
          "authority_source": authority, "count": len(allowed), "rollback": rollback})
    changes = 0
    for old, now, before, after in allowed:
        if (before if rollback else after):
            continue
        check = snapshot(old["path"])
        if any(check[key] != now[key] for key in check):
            raise ValueError("prechange_drift")
        target_mode = old["mode"] if rollback else old["after_mode"]
        target_acl = old["acl"] if rollback else old["after_acl"]
        fd = open_fixed(old["path"])
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino, info.st_mode) != (old["dev"], old["ino"],
                    now["mode"] | (stat.S_IFREG if old["kind"] == "file" else stat.S_IFDIR)):
                raise ValueError("prechange_identity")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("prechange_hardlink")
            held = snapshot_descriptor(old["path"], fd)
            if any(not metadata_equal(key, held[key], now[key]) for key in held
                   if key != "acl") or normalize_acl(held["acl"]) != normalize_acl(now["acl"]):
                raise ValueError("prechange_descriptor_drift")
            # Recipe discovery precedes the resource lock; unrelated filesystem
            # tools do not obey that lock. Recheck omitted trust ancestors at
            # the last held-target observation before each metadata mutation.
            verify_unlisted_ancestors(original["scope"]["installation_roots"])
            if receipt_guard:
                verify_applied_receipt(request)
            if resource_guard is not None:
                resource_guard()
            # Receipt/ancestor/lock verification can run filesystem tools. Take
            # another complete held-target observation after those operations,
            # then check nlink immediately before changing this exact inode.
            held = snapshot_descriptor(old["path"], fd)
            if any(not metadata_equal(key, held[key], now[key]) for key in held
                   if key != "acl") or normalize_acl(held["acl"]) != normalize_acl(now["acl"]):
                raise ValueError("prechange_descriptor_drift")
            if resource_guard is not None:
                resource_guard()
            final_info = os.fstat(fd)
            if stat.S_ISREG(final_info.st_mode) and final_info.st_nlink != 1:
                raise ValueError("prechange_hardlink")
            stability = ("st_dev", "st_ino", "st_mode", "st_nlink")
            # Real held descriptors also protect content/ACL-sensitive ctime,
            # ownership, size and mtime across the final fixed-lock check.
            for key in ("st_uid", "st_gid", "st_size", "st_mtime", "st_ctime"):
                if hasattr(info, key):
                    stability += (key,)
            if any(getattr(final_info, key) != getattr(info, key) for key in stability):
                raise ValueError("prechange_descriptor_drift")
            os.fchmod(fd, target_mode)
            if normalize_acl(acl(fd)) != normalize_acl(target_acl):
                # Chmod and setfacl are separate mutations. Reject intervening
                # target/lock/receipt drift before applying the planned ACL.
                verify_unlisted_ancestors(original["scope"]["installation_roots"])
                if receipt_guard:
                    verify_applied_receipt(request)
                if resource_guard is not None:
                    resource_guard()
                interim_info = os.fstat(fd)
                interim = snapshot_descriptor(old["path"], fd)
                if (any(not metadata_equal(key, interim[key], now[key]) for key in interim
                        if key not in ("mode", "acl")) or interim["mode"] != target_mode or
                        normalize_acl(interim["acl"]) !=
                        normalize_acl(chmod_acl(now["acl"], target_mode))):
                    raise ValueError("preacl_descriptor_drift")
                if resource_guard is not None:
                    resource_guard()
                final_info = os.fstat(fd)
                if stat.S_ISREG(final_info.st_mode) and final_info.st_nlink != 1:
                    raise ValueError("preacl_hardlink")
                if any(getattr(final_info, key) != getattr(interim_info, key)
                       for key in stability):
                    raise ValueError("preacl_descriptor_drift")
                proc = subprocess.Popen(
                    ["/usr/bin/setfacl", "--set-file=-", "--", descriptor_path(fd)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                out, err = proc.communicate(target_acl.encode("ascii"))
                if proc.returncode or out or err:
                    raise ValueError("acl_apply")
        finally:
            os.close(fd)
        final = snapshot(old["path"])
        if any(not metadata_equal(key, final[key], old[key]) for key in
               ("dev", "ino", "uid", "gid", "kind", "sha256", "size", "mtime")):
            raise ValueError("postchange_protected_drift")
        if final["mode"] != target_mode or normalize_acl(final["acl"]) != normalize_acl(target_acl):
            raise ValueError("postchange_metadata")
        changes += 1
        emit({"event": "changed", "before": now, "after": final})
    # Also cover drift after the last change and idempotent/no-op application.
    # Reobserve all exact targets and links, not only the omitted ancestor chain.
    verify_completed_targets(original, rollback, receipt_guard)
    # Unsafe outside-scope ancestors remain untouched and cannot yield completion.
    verify_unlisted_ancestors(original["scope"]["installation_roots"])
    if receipt_guard:
        verify_applied_receipt(request)
    if resource_guard is not None:
        resource_guard()
    emit({"event": "complete", "changed": changes, "content_preserved": True,
          "owner_group_preserved": True, "execution_authorized": False})



def receipt_directory(original, create):
    # This is a fixed operator-data location, never a caller-supplied receipt
    # path. Root has a separate namespace and cannot accept a user's receipt.
    uid = os.getuid()
    if os.geteuid() != uid:
        raise ValueError("repair_identity")
    managed = os.path.dirname(original["scope"]["resource_lock"])
    name = "trust-repair-v1-%s-%d" % ("admin" if uid == 0 else "user", uid)
    parent = open_fixed(managed)
    try:
        info = os.fstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 18:
            raise ValueError("repair_receipt_parent")
        path = "/proc/self/fd/%d/%s" % (parent, name)
        if create:
            try:
                os.mkdir(path, 448)
            except OSError as failure:
                if failure.errno != errno.EEXIST:
                    raise
            # Persist the newly created directory before any target mutation.
            os.fsync(parent)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
        except OSError as failure:
            if failure.errno == errno.ENOENT and not create:
                return None
            raise
        try:
            entry = os.fstat(fd)
            if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != uid or
                    stat.S_IMODE(entry.st_mode) != 448):
                raise ValueError("repair_receipt_directory")
            # Reopening the fixed path must still identify the held directory.
            check = os.lstat(path)
            if (entry.st_dev, entry.st_ino) != (check.st_dev, check.st_ino):
                raise ValueError("repair_receipt_directory_race")
            result = fd
            fd = None
            return result
        finally:
            if fd is not None:
                os.close(fd)
    finally:
        os.close(parent)


def receipt_bytes(original):
    value = {"schema_version": 1, "receipt_kind": "observed-before-explicit-apply",
             "uid": os.getuid(), "plan_sha256": digest(original), "plan": original,
             "approval_evidence": False}
    data = canonical(value) + b"\n"
    if len(data) > LIMIT:
        raise ValueError("repair_receipt_limit")
    return data


def verify_receipt_parent_chain(original):
    # Include every named directory to /, not just the immediate managed parent.
    # An exact planned workspace repair may still be in its observed before or
    # known chmod/ACL intermediate state; an unlisted writable ancestor never is.
    selected = dict((row["path"], row) for row in original["records"]
                    if row["kind"] == "directory")
    current = os.path.dirname(original["scope"]["resource_lock"])
    observed = []
    while True:
        fd = (os.open("/", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_DIRECTORY)
              if current == "/" else open_fixed(current))
        try:
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("repair_receipt_ancestor_trust")
            observed.append((current, info))
            if current not in selected:
                if info.st_mode & 18:
                    raise ValueError("repair_receipt_ancestor_trust")
            else:
                old, now = selected[current], snapshot_descriptor(current, fd)
                invariant = ("path", "dev", "ino", "uid", "gid", "kind",
                             "sha256", "size", "mtime")
                if any(not metadata_equal(key, old[key], now[key]) for key in invariant):
                    raise ValueError("repair_receipt_ancestor_drift")
                candidates = ((old["mode"], old["acl"]),
                              (old["after_mode"], old["after_acl"]),
                              (old["after_mode"], chmod_acl(old["acl"], old["after_mode"])),
                              (old["mode"], chmod_acl(old["after_acl"], old["mode"])))
                if not any(now["mode"] == mode and normalize_acl(now["acl"]) ==
                           normalize_acl(value) for mode, value in candidates):
                    raise ValueError("repair_receipt_ancestor_drift")
        finally:
            os.close(fd)
        if current == "/":
            break
        current = os.path.dirname(current)
    # Reopen every named component after collection. Held ancestor descriptors
    # must not silently remain usable after a rename or a same-resolution link.
    for path, before in observed:
        fd = (os.open("/", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_DIRECTORY)
              if path == "/" else open_fixed(path))
        try:
            after = os.fstat(fd)
            if any(getattr(before, key) != getattr(after, key) for key in
                   ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")):
                raise ValueError("repair_receipt_ancestor_drift")
        finally:
            os.close(fd)


def verify_receipt_namespace(original, directory):
    # A held fd also names a detached directory. Reopen the fixed managed-root
    # entry after receipt reads/fsyncs so detached evidence cannot authorize code
    # mutation or completion merely because its descriptor remains usable.
    verify_receipt_parent_chain(original)
    uid = os.getuid()
    name = "trust-repair-v1-%s-%d" % ("admin" if uid == 0 else "user", uid)
    parent = open_fixed(os.path.dirname(original["scope"]["resource_lock"]))
    try:
        parent_info = os.fstat(parent)
        if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_mode & 18:
            raise ValueError("repair_receipt_parent")
        held = os.fstat(directory)
        try:
            linked = os.lstat("/proc/self/fd/%d/%s" % (parent, name))
        except OSError as failure:
            if failure.errno == errno.ENOENT:
                raise ValueError("repair_receipt_namespace")
            raise
        if (not stat.S_ISDIR(linked.st_mode) or linked.st_uid != uid or
                stat.S_IMODE(linked.st_mode) != 448 or
                (held.st_dev, held.st_ino) != (linked.st_dev, linked.st_ino)):
            raise ValueError("repair_receipt_namespace")
        # The managed parent can itself be detached while its proc-fd child
        # lookup still works. Reopen its entire no-follow named path as well.
        named = open_fixed(os.path.dirname(original["scope"]["resource_lock"]))
        try:
            actual = os.fstat(named)
            if any(getattr(parent_info, key) != getattr(actual, key) for key in
                   ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")):
                raise ValueError("repair_receipt_namespace")
        finally:
            os.close(named)
    finally:
        os.close(parent)


def read_receipt(directory, name, expected, original):
    path = "/proc/self/fd/%d/%s" % (directory, name)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as failure:
        if failure.errno == errno.ENOENT:
            return False
        raise
    try:
        directory_before = os.fstat(directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or
                stat.S_IMODE(before.st_mode) != 256 or before.st_nlink != 1 or
                before.st_size != len(expected)):
            raise ValueError("repair_receipt_trust")
        blocks, remaining = [], LIMIT + 1
        while remaining:
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        if b"".join(blocks) != expected:
            raise ValueError("repair_receipt_binding")
        after = os.fstat(fd)
        keys = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                "st_size", "st_mtime", "st_ctime")
        if any(getattr(before, key) != getattr(after, key) for key in keys):
            raise ValueError("repair_receipt_race")
        linked = os.lstat(path)
        if (after.st_dev, after.st_ino) != (linked.st_dev, linked.st_ino):
            raise ValueError("repair_receipt_race")
        # An interrupted directory fsync is resumed before mutation is allowed.
        os.fsync(fd)
        os.fsync(directory)
        verify_receipt_namespace(original, directory)
        directory_after = os.fstat(directory)
        if any(getattr(directory_before, key) != getattr(directory_after, key) for key in keys):
            raise ValueError("repair_receipt_directory_race")
        # Durability syscalls can block while an external process changes the
        # file or its fixed entry. Authenticate the held contents and metadata
        # again, then require the fixed name still to identify that exact file.
        trailing = os.fstat(fd)
        if any(getattr(after, key) != getattr(trailing, key) for key in keys):
            raise ValueError("repair_receipt_race")
        if file_hash(fd) != hashlib.sha256(expected).hexdigest():
            raise ValueError("repair_receipt_binding")
        final = os.fstat(fd)
        if any(getattr(trailing, key) != getattr(final, key) for key in keys):
            raise ValueError("repair_receipt_race")
        try:
            linked = os.lstat(path)
        except OSError as failure:
            if failure.errno == errno.ENOENT:
                raise ValueError("repair_receipt_race")
            raise
        if any(getattr(final, key) != getattr(linked, key) for key in keys):
            raise ValueError("repair_receipt_race")
        # The final hash can block after the earlier namespace observation.
        # Rebind the fixed directory/parent after all content and entry reads;
        # no further content read or durability operation follows this check.
        verify_receipt_namespace(original, directory)
        final_file, final_directory = os.fstat(fd), os.fstat(directory)
        if any(getattr(final, key) != getattr(final_file, key) for key in keys):
            raise ValueError("repair_receipt_race")
        if any(getattr(directory_before, key) != getattr(final_directory, key) for key in keys):
            raise ValueError("repair_receipt_directory_race")
        return True
    finally:
        os.close(fd)


def publish_receipt(directory, name, data, original):
    # Keep an interrupted candidate as private evidence. Only a fully written,
    # fsynced, verified candidate can be linked into the exclusive final name.
    candidate = ".candidate-" + hashlib.sha256(os.urandom(32)).hexdigest()
    path = "/proc/self/fd/%d/%s" % (directory, candidate)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 256)
    try:
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            if count <= 0:
                raise ValueError("repair_receipt_write")
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    if not read_receipt(directory, candidate, data, original):
        raise ValueError("repair_receipt_candidate")
    final = "/proc/self/fd/%d/%s" % (directory, name)
    # link is exclusive even when another process ignores the resource flock.
    # An interruption before unlink leaves a rejected multi-link receipt and its
    # evidence intact; no permissions have been changed at this point.
    os.link(path, final)
    os.unlink(path)
    os.fsync(directory)
    if not read_receipt(directory, name, data, original):
        raise ValueError("repair_receipt_publication")


def verify_applied_receipt(request):
    original = request["plan"]
    directory = receipt_directory(original, False)
    if directory is None:
        raise ValueError("repair_applied_receipt_required")
    try:
        if not read_receipt(
            directory, digest(original) + ".json", receipt_bytes(original), original
        ):
            raise ValueError("repair_applied_receipt_required")
    finally:
        os.close(directory)


def authenticate_applied_plan(request, rollback):
    original = request["plan"]
    data = receipt_bytes(original)
    name = digest(original) + ".json"
    directory = receipt_directory(original, False)
    if directory is not None:
        try:
            if read_receipt(directory, name, data, original):
                return
        finally:
            os.close(directory)
    if rollback:
        raise ValueError("repair_applied_receipt_required")
    # A self-computed request digest is not provenance. The first apply must
    # match every actually observed original record, including mode and ACL.
    current = plan(original["scope"])["plan"]["records"]
    if len(current) != len(original["records"]):
        raise ValueError("repair_initial_before_required")
    for old, now in zip(original["records"], current):
        if set(old) != set(now):
            raise ValueError("repair_initial_before_required")
        for key in now:
            same = (normalize_acl(old[key]) == normalize_acl(now[key])
                    if key in ("acl", "after_acl") else metadata_equal(key, old[key], now[key]))
            if not same:
                raise ValueError("repair_initial_before_required")
    directory = receipt_directory(original, True)
    try:
        # Fail closed on unexpected collision; never overwrite any receipt.
        publish_receipt(directory, name, data, original)
    finally:
        os.close(directory)



def verify_resource_lock(lock, fd, parent_fd, expected, parent_expected):
    # A flock protects its inode, not a pathname. Reopen both fixed names and
    # bind them to the held descriptors after acquisition and before every
    # mutation/completion. External filesystem tools are still not atomic.
    file_fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                   "st_size", "st_mtime", "st_ctime")
    parent_fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
    held, parent = os.fstat(fd), os.fstat(parent_fd)
    if (any(getattr(held, key) != getattr(expected, key) for key in file_fields) or
            any(getattr(parent, key) != getattr(parent_expected, key) for key in parent_fields)):
        raise ValueError("resource_lock_drift")
    named_parent = open_fixed(os.path.dirname(lock))
    try:
        named = open_fixed(lock)
        try:
            current_parent, current = os.fstat(named_parent), os.fstat(named)
            if (any(getattr(current, key) != getattr(held, key) for key in file_fields) or
                    any(getattr(current_parent, key) != getattr(parent, key)
                        for key in parent_fields)):
                raise ValueError("resource_lock_binding")
            # Recheck held metadata and final fixed entries after all reads.
            final, final_parent = os.fstat(fd), os.fstat(parent_fd)
            if (any(getattr(final, key) != getattr(held, key) for key in file_fields) or
                    any(getattr(final_parent, key) != getattr(parent, key)
                        for key in parent_fields)):
                raise ValueError("resource_lock_drift")
            entry, parent_entry = os.lstat(lock), os.lstat(os.path.dirname(lock))
            if (any(getattr(entry, key) != getattr(held, key) for key in file_fields) or
                    any(getattr(parent_entry, key) != getattr(parent, key)
                        for key in parent_fields) or os.path.realpath(lock) != lock):
                raise ValueError("resource_lock_binding")
        finally:
            os.close(named)
    finally:
        os.close(named_parent)


def mutate(request, rollback=False):
    if len(canonical(request)) + 1 > LIMIT:
        raise ValueError("request_limit")
    if set(request) != set(("plan", "expected_plan_sha256", "operator_authority")):
        raise ValueError("mutation_shape")
    authority = request["operator_authority"]
    if not isinstance(authority, TEXT) or not 1 <= len(authority) <= 512:
        raise ValueError("operator_authority_required")
    original = request["plan"]
    if original.get("schema_version") != 2 or original.get("recipe_id") not in (
            "standard-vm-trust-v1", "standard-vm-model-trust-v1"):
        raise ValueError("fixed_profile_recipe_required")
    if digest(original) != request["expected_plan_sha256"]:
        raise ValueError("plan_binding")
    # No caller target/mode command: recompute the fixed recipe from the bound
    # operator profile before accepting a private exact target list.
    expected_plan = completion_inventory(original)
    if expected_plan["scope"] != original["scope"]:
        raise ValueError("fixed_recipe_scope_mismatch")
    if original["recipe_id"] == "standard-vm-trust-v1" and (
            not isinstance(original.get("readonly_compatibility_links"), list) or
            expected_plan.get("readonly_compatibility_links") !=
            original["readonly_compatibility_links"]):
        raise ValueError("fixed_external_link_binding_required")
    import fcntl

    lock = original["scope"]["resource_lock"]
    fd = open_fixed(lock)
    try:
        info = os.fstat(fd)
        parent_fd = open_fixed(os.path.dirname(lock))
        try:
            parent = os.fstat(parent_fd)
            administrator_for_owner = os.getuid() == 0 and info.st_uid == parent.st_uid
            if (not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 18 or
                    not stat.S_ISREG(info.st_mode) or info.st_mode & 18 or
                    (info.st_uid not in (0, os.getuid()) and not administrator_for_owner) or
                    info.st_nlink != 1):
                raise ValueError("resource_lock_trust")
            def resource_guard():
                verify_resource_lock(lock, fd, parent_fd, info, parent)

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            resource_guard()
            authenticate_applied_plan(request, rollback)
            resource_guard()
            _mutate_locked(request, rollback, True, resource_guard)
        finally:
            os.close(parent_fd)
    finally:
        os.close(fd)



def common_installation_root(ic, ms):
    # commonprefix compares characters; vendor root names can share a prefix.
    components = []
    for left, right in zip(ic.split("/"), ms.split("/")):
        if left != right:
            break
        components.append(left)
    return "/".join(components) or "/"



def lexical_parent_snapshot(path):
    # Canonical descriptors do not bind compatibility aliases such as IC615/oa.
    # Observe each lexical parent without following its final component. Retain
    # legitimate directory symlinks, but reject a retarget or metadata change.
    parts = os.path.dirname(path).split("/")
    if not path.startswith("/") or len(parts) > 128:
        raise ValueError("external_link_race")
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
              "st_size", "st_mtime", "st_ctime")
    result, current = [], ""
    for part in parts:
        current = current.rstrip("/") + "/" + part if part else "/"
        before = os.lstat(current)
        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode)):
            raise ValueError("external_link_race")
        target = os.readlink(current) if stat.S_ISLNK(before.st_mode) else None
        after = os.lstat(current)
        values = tuple(getattr(before, key) for key in fields)
        if values != tuple(getattr(after, key) for key in fields):
            raise ValueError("external_link_race")
        result.append((current, values, target))
    return result


def external_link_record(path, expected_resolved):
    # Hold a canonical no-follow parent. Python 2.6 has no dir_fd or O_PATH;
    # proc-fd leaf operations retain the exact directory without opening vendor
    # code or following the external target for content/metadata mutation.
    lexical = lexical_parent_snapshot(path)
    parent_path = os.path.realpath(os.path.dirname(path))
    parent_fd = open_fixed(parent_path)
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
              "st_size", "st_mtime", "st_ctime")
    try:
        parent = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent.st_mode):
            raise ValueError("external_link_race")
        entry = descriptor_path(parent_fd) + "/" + os.path.basename(path)
        before = os.lstat(entry)
        is_link = stat.S_ISLNK(before.st_mode)
        target = os.readlink(entry) if is_link else None
        resolved, exists = os.path.realpath(entry), os.path.exists(entry)
        if resolved != expected_resolved:
            raise ValueError("external_link_race")
        result = {"path": path, "resolved": resolved, "exists": exists, "target": target,
                  "entry": dict((key[3:], "%.17g" % getattr(before, key)
                            if key in ("st_mtime", "st_ctime") else getattr(before, key))
                            for key in fields),
                  "parent": {"path": parent_path, "dev": parent.st_dev,
                             "ino": parent.st_ino, "uid": parent.st_uid,
                             "gid": parent.st_gid}}
        if ((os.readlink(entry) if is_link else None) != target or
                os.path.realpath(entry) != resolved or os.path.exists(entry) != exists):
            raise ValueError("external_link_race")
        named_parent = open_fixed(parent_path)
        try:
            named = os.fstat(named_parent)
            if any(getattr(named, key) != getattr(parent, key) for key in fields):
                raise ValueError("external_link_race")
            if (os.path.realpath(os.path.dirname(path)) != parent_path or
                    os.path.realpath(path) != resolved or
                    (os.readlink(entry) if is_link else None) != target):
                raise ValueError("external_link_race")
            # Trailing no-follow entries follow the leaf content/resolution reads.
            # The canonical and lexical parent chains are then reobserved.
            trailing, fixed, held_parent = os.lstat(entry), os.lstat(path), os.fstat(parent_fd)
            if (any(getattr(trailing, key) != getattr(before, key) or
                    getattr(fixed, key) != getattr(before, key) for key in fields) or
                    any(getattr(held_parent, key) != getattr(parent, key) for key in fields)):
                raise ValueError("external_link_race")
            # An ancestor rename during the final fixed-leaf read can leave the
            # held parent unchanged. Reopen its complete named no-follow chain
            # after that read, before accepting the original fixed namespace.
            final_parent = open_fixed(parent_path)
            try:
                final = os.fstat(final_parent)
                if any(getattr(final, key) != getattr(parent, key) for key in fields):
                    raise ValueError("external_link_race")
            finally:
                os.close(final_parent)
            if lexical_parent_snapshot(path) != lexical:
                raise ValueError("external_link_race")
        finally:
            os.close(named_parent)
        return result
    except OSError:
        raise ValueError("external_link_race")
    finally:
        os.close(parent_fd)


def installation(profile):
    """Standard-VM recipe; address/account/install roots come from operator data.

    This covers wrappers, the 32-bit binaries and shared-library search trees.
    It is not complete dynamic runtime attestation. Never include PDK/OA design
    data, licenses, logs, caches, documentation or the complete installation.
    """
    if profile.get("schema_version") != 1 or set(profile.get("tools", {})) != set(
            ("virtuoso", "ocean", "spectre")):
        raise ValueError("profile_shape")
    import platform
    import pwd

    actual_host = {
        "hostname": platform.node(), "os": platform.system(),
        "architecture": platform.machine(), "python_version": platform.python_version(),
        "user": pwd.getpwuid(os.getuid()).pw_name,
    }
    expected_host = profile.get("host")
    if os.getuid() == 0 and isinstance(expected_host, dict):
        # Administrator provisioning is allowed; the normal guest identity is
        # still a real account. Native/MCP startup never uses this exemption.
        pwd.getpwnam(expected_host["user"])
        actual_host["user"] = expected_host["user"]
    if actual_host != expected_host:
        raise ValueError("host_mismatch")
    tools = profile["tools"]
    roots = []
    for name in ("virtuoso", "ocean", "spectre"):
        path = valid_path(tools[name]["path"])
        if os.path.basename(path) != name or "/tools" not in path:
            raise ValueError("standard_vm_tool_layout")
        resolved = os.path.realpath(path)
        fd = open_fixed(resolved)
        try:
            if file_hash(fd) != tools[name]["sha256"]:
                raise ValueError("executable_drift")
        finally:
            os.close(fd)
        roots.append(os.path.realpath(path.split("/tools", 1)[0]))
    ic, ocean, ms = roots
    if ic != ocean or ic == ms:
        raise ValueError("standard_vm_installation_layout")
    base = common_installation_root(ic, ms)
    if not os.path.isdir(base) or base.count("/") < 2:
        raise ValueError("installation_common_root")
    protected = profile["paths"]["protected_roots"]
    if not all(any(inside(root, p) for p in protected) for root in (ic, ms)):
        raise ValueError("unprotected_installation")
    return ic, ms, base


def inventory(profile):
    """Standard-VM recipe; address/account/install roots come from operator data.

    This covers wrappers, the 32-bit binaries and shared-library search trees.
    It is not complete dynamic runtime attestation. Never include PDK/OA design
    data, licenses, logs, caches, documentation or the complete installation.
    """
    ic, ms, base = installation(profile)
    seeds = [ic + "/share/bin/" + x for x in (
        "cdnWrapperWithOA2010", ".cdnWrapper_core", ".cdnWrapper_argv_parsing",
        ".cdnWrapper_dev", ".cdnWrapper_help", ".cdnWrapper_cwlg", ".cdsWrapperLib")]
    seeds += [ic + "/tools.lnx86/" + x for x in (
        ".oawrap", ".cdnWrapper_pscompat", "dfII/bin/ocean", "dfII/bin/virtuoso",
        "dfII/bin/32bit/virtuoso", "bin/cds_plat", "bin/cds_plat.dat")]
    seeds += [ic + "/share/dfII/bin/.dfII_init", ms + "/tools/bin/spectre",
              ms + "/tools.lnx86/spectre/bin/32bit/spectre",
              ms + "/tools.lnx86/bin/.preHostEnvCheck", ic + "/tools", ic + "/oa",
              ms + "/tools"]
    oa_lib = os.path.realpath(ic + "/oa/lib")
    if not inside(oa_lib, ic) or not os.path.basename(os.path.dirname(oa_lib)).startswith("oa"):
        raise ValueError("oa_program_library_layout")
    code_roots = (
        ic + "/share/bin", ic + "/share/dfII/bin", ic + "/tools.lnx86/dfII/bin",
        ic + "/tools.lnx86/bin", ic + "/tools.lnx86/lib", oa_lib,
        ic + "/tools.lnx86/cdsSkillPcell/lib", ic + "/tools.lnx86/iota/lib",
        ms + "/tools.lnx86/spectre/bin", ms + "/tools.lnx86/bin", ms + "/tools.lnx86/lib",
        ms + "/tools.lnx86/ktl/lib", ms + "/tools.lnx86/nif/lib",
        ms + "/tools.lnx86/pub/lib", ms + "/tools.lnx86/vmor/lib",
    )
    exact_code = set((ic + "/tools.lnx86/.oawrap", ic + "/tools.lnx86/.cdnWrapper_pscompat"))
    paths, links, external = set(), {}, []

    def add(path):
        if not os.path.lexists(path):
            raise ValueError("standard_vm_dependency_missing")
        resolved = os.path.realpath(path)
        if not inside(resolved, base):
            # External targets never enter the mutation scope. Their entries
            # still require trusted installation-owned directory parent chains.
            parent = os.path.realpath(os.path.dirname(path))
            if not inside(parent, base):
                raise ValueError("external_link_parent_scope")
            paths.add(parent)
            while parent != base:
                parent = os.path.dirname(parent)
                paths.add(parent)
            if len(paths) > MAX_ITEMS:
                raise ValueError("scope_size")
            external.append(external_link_record(path, resolved))
            return
        if os.path.isfile(resolved) and resolved not in exact_code and not any(
                inside(resolved, code_root) for code_root in code_roots):
            raise ValueError("dependency_code_role_escape")
        if os.path.islink(path):
            links[path] = {"path": path, "target": os.readlink(path), "resolved": resolved}
        paths.add(resolved)
        while resolved != base:
            resolved = os.path.dirname(resolved)
            paths.add(resolved)
        if len(paths) > MAX_ITEMS:
            raise ValueError("scope_size")

    for seed in seeds:
        add(seed)
    for code in (ic + "/tools.lnx86/lib", ic + "/oa/lib", ms + "/tools.lnx86/lib"):
        add(code)
        for current, directories, filenames in os.walk(code, followlinks=False):
            directories[:] = [d for d in directories if "64" not in d and d not in (
                "license", "data", "doc", "samples")]
            for name in filenames:
                if ".so" in name:
                    add(current + "/" + name)
    workspace = valid_path(profile["paths"]["workspace_root"])
    if os.path.realpath(workspace) != workspace:
        raise ValueError("workspace_link")
    # Stable recipe membership across before/after states. Only this directory,
    # never its contents, is selected, and healthy metadata remains a no-op.
    paths.add(workspace)
    mutation_roots = [base, workspace]
    verify_unlisted_ancestors(mutation_roots)
    result = plan({"installation_roots": mutation_roots, "paths": sorted(paths),
                   "links": sorted(links.values(), key=lambda x: x["path"]),
                   "profile_sha256": digest(profile),
                   "resource_lock": valid_path(profile["paths"]["managed_root"] + "/run.lock")})
    result["plan"]["schema_version"] = 2
    result["plan"]["recipe_id"] = "standard-vm-trust-v1"
    result["plan"]["profile"] = profile
    # Bind read-only external members to the authenticated plan/receipt without
    # admitting their resolved targets into the exact metadata mutation scope.
    # Historical plans lacking this binding require a new read-only inventory;
    # old plans, helper bytes and receipts remain valid historical evidence.
    external.sort(key=lambda link: (link["path"], link["resolved"]))
    result["plan"]["readonly_compatibility_links"] = external
    result["plan_sha256"] = digest(result["plan"])
    result["readonly_compatibility_links"] = external
    result["dependency_scope"] = "wrappers_32bit_binaries_shared_library_trees"
    result["native_runtime_attestation"] = "NOT_ATTESTED"
    bounded = bounded_inventory(result)
    # Internal target hashes/ACL tools run after member enumeration. Reobserve
    # every held-parent external binding after those reads, without mutation.
    for link in external:
        if external_link_record(link["path"], link["resolved"]) != link:
            raise ValueError("external_link_race")
    return bounded


def model_graph(main, section):
    """Resolve selected model includes without executing or exporting model text."""
    model_root = os.path.dirname(main)
    pending, seen, records = [(main, section)], set(), {}
    total = 0
    while pending:
        path, selected = pending.pop()
        if (path, selected) in seen:
            continue
        seen.add((path, selected))
        if len(seen) > 512 or not inside(path, model_root) or os.path.realpath(path) != path:
            raise ValueError("model_graph_escape_or_bound")
        if path not in records:
            fd = open_fixed(path)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8388608:
                    raise ValueError("model_graph_file")
                raw = os.read(fd, 8388609)
                if len(raw) != info.st_size or len(raw) > 8388608:
                    raise ValueError("model_graph_read")
                if (os.lstat(path).st_dev, os.lstat(path).st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("model_graph_identity")
            finally:
                os.close(fd)
            total += len(raw)
            if total > 33554432 or len(records) >= 128:
                raise ValueError("model_graph_total_bound")
            text = raw.decode("latin-1")
            # Preserve quoted targets while discarding line/block comments.
            text = re.sub(
                r'"(?:[^"\\]|\\.)*"|/\*[\s\S]*?\*/|//[^\n]*',
                lambda m: (
                    m.group(0) if m.group(0).startswith('"') else "\n" * m.group(0).count("\n")
                ),
                text,
            )
            bodies, current = {None: []}, None
            for line in text.splitlines():
                line = line.strip()
                begin = re.match(r"^section\s+([A-Za-z][A-Za-z0-9_.$-]*)\s*$", line, re.I)
                end = re.match(r"^endsection(?:\s+([A-Za-z][A-Za-z0-9_.$-]*))?\s*$", line, re.I)
                if begin:
                    if current is not None or begin.group(1) in bodies:
                        raise ValueError("model_graph_sections")
                    current = begin.group(1)
                    bodies[current] = []
                elif end:
                    if current is None or end.group(1) not in (None, current):
                        raise ValueError("model_graph_sections")
                    current = None
                else:
                    bodies[current].append(line)
            if current is not None or len(bodies) > 65:
                raise ValueError("model_graph_sections")
            records[path] = {"sha256": hashlib.sha256(raw).hexdigest(), "bodies": bodies}
        bodies = records[path]["bodies"]
        if selected is not None and selected not in bodies:
            raise ValueError("model_graph_section_absent")
        if selected is None and len(bodies) > 1:
            raise ValueError("model_graph_section_required")
        for body in (bodies[None], bodies.get(selected, []) if selected is not None else []):
            for line in body:
                if not re.match(r"^include\b", line, re.I):
                    continue
                match = re.match(
                    r'^include\s+"([A-Za-z0-9._/-]+)"(?:\s+section\s*=\s*([A-Za-z][A-Za-z0-9_.$-]*))?\s*$',
                    line,
                    re.I,
                )
                if match is None:
                    raise ValueError("model_graph_include_syntax")
                child = os.path.normpath(os.path.join(os.path.dirname(path), match.group(1)))
                pending.append((child, match.group(2)))
    return dict((path, record["sha256"]) for path, record in records.items())



def trusted_model_metadata(values):
    """Stable read-only path/ancestor metadata; no contents or permission writes."""
    metadata = {}
    uid = os.getuid()
    if uid == 0:
        raise ValueError("model_graph_normal_user_required")
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
              "st_size", "st_mtime", "st_ctime")
    for path in values:
        current = path
        while True:
            info = os.lstat(current)
            if (info.st_uid not in (0, uid) or info.st_mode & 18 or
                    os.path.realpath(current) != current or
                    (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 if current == path else
                        not stat.S_ISDIR(info.st_mode))):
                raise ValueError("model_graph_untrusted_metadata")
            record = tuple(getattr(info, key) for key in fields)
            trailing = os.lstat(current)
            if (tuple(getattr(trailing, key) for key in fields) != record or
                    current in metadata and metadata[current] != record):
                raise ValueError("model_graph_metadata_drift")
            metadata[current] = record
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    return metadata


def trusted_model_graph(main, section):
    """Normal-user closure trust binds metadata around the final content scan."""
    if os.getuid() == 0:
        raise ValueError("model_graph_normal_user_required")
    values = model_graph(main, section)
    before = trusted_model_metadata(values)
    if model_graph(main, section) != values:
        raise ValueError("model_graph_content_drift")
    # No content scan follows this final namespace/type/permission observation.
    if trusted_model_metadata(values) != before:
        raise ValueError("model_graph_metadata_drift")
    return values



def inventory_models(request):
    if set(request) != set(("profile", "model_include")):
        raise ValueError("model_inventory_request")
    profile, include = request["profile"], request["model_include"]
    ic, ms, base = installation(profile)
    if not isinstance(include, dict) or set(include) != set(("path", "section", "file_sha256")):
        raise ValueError("model_inventory_binding")
    main = valid_path(include["path"])
    if (
        not inside(main, base)
        or inside(main, ic)
        or inside(main, ms)
        or not os.path.dirname(main).endswith("/models/spectre")
        or not main.endswith(".scs")
        or not isinstance(include["section"], TEXT)
        or re.match(r"^[A-Za-z][A-Za-z0-9_.$-]{0,95}$", include["section"]) is None
        or not any(inside(main, root) for root in profile["paths"]["protected_roots"])
    ):
        raise ValueError("model_inventory_scope")
    hashes = model_graph(main, include["section"])
    if hashes[main] != include["file_sha256"]:
        raise ValueError("model_inventory_top_hash")
    paths = set(hashes)
    for path in hashes:
        while path != base:
            path = os.path.dirname(path)
            paths.add(path)
    result = plan(
        {
            "installation_roots": [base],
            "paths": sorted(paths),
            "links": [],
            "profile_sha256": digest(profile),
            "resource_lock": profile["paths"]["managed_root"] + "/run.lock",
        }
    )
    for record in result["plan"]["records"]:
        if record["kind"] == "file" and record["sha256"] != hashes[record["path"]]:
            raise ValueError("model_inventory_content_race")
    result["plan"].update(
        schema_version=2,
        recipe_id="standard-vm-model-trust-v1",
        profile=profile,
        model_include=include,
    )
    result["plan_sha256"] = digest(result["plan"])
    return bounded_inventory(result)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in (
            "inventory", "inventory-models", "apply", "rollback"):
        raise ValueError("explicit_action_required")
    if not sys.platform.startswith("linux"):
        raise ValueError("linux_required")
    data = sys.stdin.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("request_limit")
    request = json.loads(data)
    if sys.argv[1] == "inventory-models":
        emit(inventory_models(request))
    elif sys.argv[1] == "inventory":
        emit(inventory(request))
    else:
        mutate(request, sys.argv[1] == "rollback")


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        emit({"event": "rejected", "reason": str(failure) if isinstance(failure, ValueError)
              else "system_error", "changed_state_may_be_partial": True,
              "execution_authorized": False})
        sys.exit(1)
