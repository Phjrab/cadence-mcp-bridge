"""Fixed read-only environment probe; also runs on Python 2.6 (standard library)."""
# mypy: ignore-errors

import hashlib
import json
import os
import platform
import re
import select
import signal
import stat
import subprocess
import sys
import time

PROFILE_LIMIT = 32768
OUTPUT_LIMIT = 4096
CAPABILITIES = ("ade_native", "dc", "ac", "tran", "psf_extraction")
PUBLIC_REASONS = (
    "host_mismatch",
    "root_symlink_or_missing",
    "root_not_writable",
    "executable_escape",
    "executable_missing",
    "executable_permissions",
    "executable_drift",
    "executable_post_drift",
    "version_timeout",
    "version_output_limit",
    "version_exit",
    "version_mismatch",
    "disk_floor",
    "root_post_drift",
    "probe_binding",
    "profile_permissions",
    "profile_binding",
    "probe_location",
    "probe_post_drift",
)
ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
PATH = re.compile(r"^/[A-Za-z0-9._/-]{1,511}$")
try:
    INTEGER_TYPES = (int, long)  # noqa: F821
except NameError:
    INTEGER_TYPES = (int,)


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("closed_shape")


def matches(pattern, value):
    try:
        found = pattern.match(value)
        return found is not None and found.end() == len(value)
    except TypeError:
        return False


def path(value):
    if not matches(PATH, value):
        raise ValueError("path_shape")
    if any(p in ("", ".", "..") for p in value.split("/")[1:]) or value == "/":
        raise ValueError("path_component")
    return value


def inside(child, parent):
    return child == parent or child.startswith(parent + "/")


def validate_profile(profile):
    exact(
        profile,
        (
            "schema_version",
            "environment_id",
            "ssh_alias",
            "host",
            "paths",
            "tools",
            "limits",
            "requested_capabilities",
        ),
    )
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        raise ValueError("schema_version")
    if not matches(ID, profile["environment_id"]) or not matches(TOKEN, profile["ssh_alias"]):
        raise ValueError("identity_shape")
    exact(profile["host"], ("hostname", "user", "os", "architecture", "python_version"))
    host = profile["host"]
    if host["os"] != "Linux" or any(not matches(TOKEN, host[k]) for k in host):
        raise ValueError("host_shape")
    if not matches(re.compile(r"^(2\.6|2\.7|3\.[0-9]+)\.[0-9]+$"), host["python_version"]):
        raise ValueError("python_requirement")
    roots = profile["paths"]
    exact(roots, ("workspace_root", "managed_root", "job_root", "result_root", "protected_roots"))
    for key in ("workspace_root", "managed_root", "job_root", "result_root"):
        path(roots[key])
    if (
        not isinstance(roots["protected_roots"], list)
        or not 1 <= len(roots["protected_roots"]) <= 16
    ):
        raise ValueError("protected_roots")
    protected = roots["protected_roots"]
    if len(set(protected)) != len(protected):
        raise ValueError("duplicate_roots")
    for root in protected:
        path(root)
    if roots["managed_root"] != roots["workspace_root"] + "/.cadence_mcp":
        raise ValueError("managed_root")
    for key in ("job_root", "result_root"):
        if not inside(roots[key], roots["managed_root"]) or roots[key] == roots["managed_root"]:
            raise ValueError("writable_root")
    for root in protected:
        if inside(root, roots["managed_root"]) or inside(roots["managed_root"], root):
            raise ValueError("protection_overlap")
    exact(profile["tools"], ("virtuoso", "spectre", "ocean"))
    for name, binding in profile["tools"].items():
        exact(binding, ("path", "sha256", "version"))
        path(binding["path"])
        if os.path.basename(binding["path"]) != name or not any(
            inside(binding["path"], p) for p in protected
        ):
            raise ValueError("executable_allowlist")
        if not matches(SHA, binding["sha256"]) or not matches(TOKEN, binding["version"]):
            raise ValueError("tool_binding")
    limits = profile["limits"]
    exact(
        limits,
        (
            "disk_floor_bytes",
            "disk_floor_percent",
            "spectre_attempts",
            "result_reserved_bytes",
            "eda_concurrency",
            "paid_resources",
        ),
    )
    bounds = {
        "disk_floor_bytes": (2147483648, 1099511627776),
        "disk_floor_percent": (10, 100),
        "spectre_attempts": (0, 1000000),
        "result_reserved_bytes": (0, 1099511627776),
        "eda_concurrency": (1, 1),
        "paid_resources": (0, 0),
    }
    for name, value in limits.items():
        low, high = bounds[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, INTEGER_TYPES)
            or not low <= value <= high
        ):
            raise ValueError("resource_limit")
    requested = profile["requested_capabilities"]
    if (
        not isinstance(requested, list)
        or len(requested) > 5
        or len(set(requested)) != len(requested)
    ):
        raise ValueError("capability_list")
    if any(c not in CAPABILITIES for c in requested):
        raise ValueError("capability_allowlist")
    return profile


def digest_file(filename):
    value = hashlib.sha256()
    total = 0
    stream = open(filename, "rb")
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 134217728:
                raise ValueError("executable_size")
            value.update(chunk)
    finally:
        stream.close()
    return value.hexdigest()


def version_matches(executable, version):
    """Only the reviewed version switch; no shell, environment or script input."""
    null = open(os.devnull, "rb")
    try:
        process = subprocess.Popen(
            [executable, "-W"],
            stdin=null,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
            preexec_fn=os.setsid,
        )
    finally:
        null.close()
    deadline = time.time() + 8
    data = b""
    try:
        while True:
            if time.time() >= deadline:
                raise ValueError("version_timeout")
            readable, _, _ = select.select([process.stdout], [], [], 0.1)
            if readable:
                chunk = os.read(process.stdout.fileno(), OUTPUT_LIMIT + 1 - len(data))
                if not chunk:
                    break
                data += chunk
                if len(data) > OUTPUT_LIMIT:
                    raise ValueError("version_output_limit")
        while process.poll() is None:
            if time.time() >= deadline:
                raise ValueError("version_timeout")
            time.sleep(0.01)
        if process.wait() != 0:
            raise ValueError("version_exit")
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", data.decode("ascii", "strict"))
        return version in tokens
    finally:
        # A wrapper may exit while its descendant still holds the output pipe.
        # Always close the dedicated group, including after wrapper termination.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        process.wait()
        process.stdout.close()


def observe(profile, profile_sha, probe_sha, nonce):
    import pwd

    validate_profile(profile)
    host = {
        "hostname": platform.node(),
        "user": pwd.getpwuid(os.getuid()).pw_name,
        "os": platform.system(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
    }
    if host != profile["host"]:
        raise ValueError("host_mismatch")
    roots = profile["paths"]
    directories = [roots[k] for k in ("workspace_root", "managed_root", "job_root", "result_root")]
    directories.extend(roots["protected_roots"])
    before = {}
    for root in directories:
        if os.path.realpath(root) != root or not os.path.isdir(root):
            raise ValueError("root_symlink_or_missing")
        info = os.stat(root)
        before[root] = (info.st_dev, info.st_ino)
    writable = all(
        os.access(roots[k], os.W_OK | os.X_OK)
        for k in ("workspace_root", "managed_root", "job_root", "result_root")
    )
    if not writable:
        raise ValueError("root_not_writable")
    tools = {}
    for name in ("virtuoso", "spectre", "ocean"):
        binding = profile["tools"][name]
        resolved = os.path.realpath(binding["path"])
        if not any(inside(resolved, root) for root in roots["protected_roots"]):
            raise ValueError("executable_escape")
        if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            raise ValueError("executable_missing")
        info = os.stat(resolved)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 18:  # group/other writable
            raise ValueError("executable_permissions")
        ancestor = os.path.dirname(resolved)
        while ancestor != "/":
            if os.stat(ancestor).st_mode & 18:
                raise ValueError("executable_permissions")
            ancestor = os.path.dirname(ancestor)
        if digest_file(resolved) != binding["sha256"]:
            raise ValueError("executable_drift")
        matched = name == "ocean" or version_matches(binding["path"], binding["version"])
        if not matched:
            raise ValueError("version_mismatch")
        tools[name] = {
            "available": True,
            "sha256": binding["sha256"],
            "version": binding["version"] if name != "ocean" else None,
            "version_observed": name != "ocean",
        }
        after = os.stat(resolved)
        if (
            os.path.realpath(binding["path"]) != resolved
            or (after.st_dev, after.st_ino, after.st_mode)
            != (info.st_dev, info.st_ino, info.st_mode)
            or digest_file(resolved) != binding["sha256"]
        ):
            raise ValueError("executable_post_drift")
    disk = os.statvfs(roots["managed_root"])
    free, total = disk.f_bavail * disk.f_frsize, disk.f_blocks * disk.f_frsize
    if free < max(
        profile["limits"]["disk_floor_bytes"],
        (total * profile["limits"]["disk_floor_percent"] + 99) // 100,
    ):
        raise ValueError("disk_floor")
    for root in directories:
        info = os.stat(root)
        if os.path.realpath(root) != root or (info.st_dev, info.st_ino) != before[root]:
            raise ValueError("root_post_drift")
    return {
        "schema_version": 1,
        "environment_id": profile["environment_id"],
        "profile_sha256": profile_sha,
        "probe_sha256": probe_sha,
        "nonce": nonce,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": host,
        "tools": tools,
        "workspace_writable": writable,
        "writability_method": "os_access_no_write_test",
        "root_containment": True,
        "protected_roots_disjoint": True,
        "free_bytes": free,
        "total_bytes": total,
        "license_environment": dict(
            (name, "SET" if os.environ.get(name) else "UNSET")
            for name in ("CDS_LIC_FILE", "LM_LICENSE_FILE")
        ),
    }


def main():
    if (
        len(sys.argv) != 4
        or any(not matches(SHA, a) for a in sys.argv[1:3])
        or not matches(re.compile(r"^[0-9a-f]{32}$"), sys.argv[3])
    ):
        raise ValueError("arguments")
    here = os.path.realpath(__file__)
    directory = os.path.dirname(here)
    config = directory + "/profile.json"
    if digest_file(here) != sys.argv[2] or os.path.islink(config):
        raise ValueError("probe_binding")
    info = os.stat(config)
    if info.st_uid != os.getuid() or info.st_mode & 63 or not stat.S_ISREG(info.st_mode):
        raise ValueError("profile_permissions")
    stream = open(config, "rb")
    try:
        data = stream.read(PROFILE_LIMIT + 1)
    finally:
        stream.close()
    if len(data) > PROFILE_LIMIT or hashlib.sha256(data).hexdigest() != sys.argv[1]:
        raise ValueError("profile_binding")
    profile = validate_profile(json.loads(data.decode("utf-8")))
    expected = (
        profile["paths"]["managed_root"] + "/environments/" + profile["environment_id"] + "/v1"
    )
    if directory != expected or os.path.realpath(directory) != directory:
        raise ValueError("probe_location")
    result = observe(profile, sys.argv[1], sys.argv[2], sys.argv[3])
    if digest_file(here) != sys.argv[2] or digest_file(config) != sys.argv[1]:
        raise ValueError("probe_post_drift")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        reason = str(failure) if str(failure) in PUBLIC_REASONS else "environment_probe_failed"
        sys.stderr.write(reason + "\n")
        sys.exit(1)
