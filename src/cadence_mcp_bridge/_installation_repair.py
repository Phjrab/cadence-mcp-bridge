"""Explicit operator-only installation metadata repair; standalone Python 2.6.

No import side effects or vendor execution. Plans and receipts are private.
Only group/other write removal is supported; contents and owners never change.
"""
# mypy: ignore-errors
import hashlib
import json
import os
import stat
import subprocess
import sys

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
    return {"plan": result, "plan_sha256": digest(result)}


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


def _mutate_locked(request, rollback=False):
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
            os.fchmod(fd, target_mode)
            if normalize_acl(acl(fd)) != normalize_acl(target_acl):
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
    emit({"event": "complete", "changed": changes, "content_preserved": True,
          "owner_group_preserved": True, "execution_authorized": False})



def mutate(request, rollback=False):
    original = request["plan"]
    if original.get("schema_version") != 2 or original.get("recipe_id") != "standard-vm-trust-v1":
        raise ValueError("fixed_profile_recipe_required")
    if digest(original) != request["expected_plan_sha256"]:
        raise ValueError("plan_binding")
    # No caller target/mode command: recompute the fixed recipe from the bound
    # operator profile before accepting a private exact target list.
    expected_scope = inventory(original["profile"])["plan"]["scope"]
    if expected_scope != original["scope"]:
        raise ValueError("fixed_recipe_scope_mismatch")
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
        finally:
            os.close(parent_fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _mutate_locked(request, rollback)
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


def inventory(profile):
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
            # Alternative compatibility-library links are not mutation targets.
            external.append({"path": path, "resolved": resolved,
                             "exists": os.path.exists(resolved)})
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
    result = plan({"installation_roots": mutation_roots, "paths": sorted(paths),
                   "links": sorted(links.values(), key=lambda x: x["path"]),
                   "profile_sha256": digest(profile),
                   "resource_lock": valid_path(profile["paths"]["managed_root"] + "/run.lock")})
    result["plan"]["schema_version"] = 2
    result["plan"]["recipe_id"] = "standard-vm-trust-v1"
    result["plan"]["profile"] = profile
    result["plan_sha256"] = digest(result["plan"])
    result["readonly_compatibility_links"] = external
    result["dependency_scope"] = "wrappers_32bit_binaries_shared_library_trees"
    result["native_runtime_attestation"] = "NOT_ATTESTED"
    return result


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("inventory", "apply", "rollback"):
        raise ValueError("explicit_action_required")
    if not sys.platform.startswith("linux"):
        raise ValueError("linux_required")
    data = sys.stdin.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("request_limit")
    request = json.loads(data)
    if sys.argv[1] == "inventory":
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
