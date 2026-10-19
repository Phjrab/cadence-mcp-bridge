# mypy: ignore-errors
# ruff: noqa: UP004, UP024, UP031
# Python 2.6 requires new-style object and distinct IOError/format compatibility.
"""DRAFT fixed read-only standard-VM storage facts, standalone Python 2.6.

No package import hooks, commands, EDA, mounts, writes, locks, or approval minting.
Results are private operator evidence, never installation/execution qualification.
"""

import sys

if __name__ == "__main__":
    if (
        not sys.flags.ignore_environment
        or not sys.flags.no_user_site
        or not sys.dont_write_bytecode
    ):
        sys.stderr.write("STORAGE_INSPECTOR_ISOLATED_PYTHON_REQUIRED\n")
        sys.exit(1)
    _entry = sys.path[0] if sys.path else None
    sys.path[:] = [p for p in sys.path if p and p != _entry]
import os

if __name__ == "__main__":
    _excluded = set((os.path.realpath(os.getcwd()),))
    if globals().get("__file__"):
        _excluded.add(os.path.realpath(os.path.dirname(os.path.abspath(__file__))))
    sys.path[:] = [p for p in sys.path if os.path.isabs(p) and os.path.realpath(p) not in _excluded]
import errno
import hashlib
import json
import re
import signal
import stat

INPUT_BYTES = 65536
OUTPUT_BYTES = 1048576
MAX_PATHS = 128
MAX_SECONDS = 60
MAX_HASH_BYTES = 67108864
MAX_FILE_BYTES = 16777216
MAX_KERNEL_BYTES = 65536
MAX_LOOP_DEVICES = 16
BACKING = "/var/lib/cadence-mcp-bridge/observer-storage"
BINARIES = (
    ("mke2fs-sbin", "/sbin/mke2fs"),
    ("mke2fs-usr", "/usr/sbin/mke2fs"),
    ("mount-bin", "/bin/mount"),
    ("mount-usr", "/usr/bin/mount"),
    ("umount-bin", "/bin/umount"),
    ("umount-usr", "/usr/bin/umount"),
    ("losetup-sbin", "/sbin/losetup"),
    ("losetup-usr", "/usr/sbin/losetup"),
    ("python", "/usr/bin/python"),
    ("python26", "/usr/bin/python2.6"),
)
CAPABILITIES = ("ade_native", "dc", "ac", "tran", "psf_extraction")
ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
PATH = re.compile(r"^/[A-Za-z0-9._/-]{1,511}$")
try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


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
    if (
        not matches(PATH, value)
        or value == "/"
        or any(p in ("", ".", "..") for p in value.split("/")[1:])
    ):
        raise ValueError("path_shape")
    return value


def inside(child, parent):
    return child == parent or child.startswith(parent + "/")


def parse_request(raw):
    if len(raw) > INPUT_BYTES:
        raise ValueError("input_bound")
    request = json.loads(raw.decode("ascii"))
    if raw != canonical(request):
        raise ValueError("canonical_request_required")
    exact(
        request,
        (
            "schema_version",
            "kind",
            "profile",
            "profile_canonical_sha256",
            "resource_domain_sha256",
            "identity_manifest_sha256",
        ),
    )
    if (
        type(request["schema_version"]) is not int
        or request["schema_version"] != 1
        or (request["kind"] != "FIXED_STORAGE_PREREQUISITE_INSPECTION")
    ):
        raise ValueError("request_kind")
    profile = validate_profile(request["profile"])
    for name in ("profile_canonical_sha256", "resource_domain_sha256", "identity_manifest_sha256"):
        if not matches(SHA, request[name]):
            raise ValueError("hash_shape")
    # This hashes normalized content, not the runtime context's raw profile file.
    if digest(canonical(profile)) != request["profile_canonical_sha256"]:
        raise ValueError("profile_binding")
    domain = digest(
        canonical(
            {
                "hostname": profile["host"]["hostname"].lower().rstrip("."),
                "architecture": profile["host"]["architecture"],
            }
        )
    )
    if domain != request["resource_domain_sha256"]:
        raise ValueError("resource_domain_binding")
    home = "/home/" + profile["host"]["user"]
    if not profile["paths"]["workspace_root"].startswith(home + "/"):
        raise ValueError("home_workspace_required")
    if len(profile["paths"]["managed_root"].split("/")) > 16:
        raise ValueError("managed_root_depth")
    return request


def metadata(info):
    return dict(
        device=info.st_dev,
        inode=info.st_ino,
        mode=info.st_mode,
        uid=info.st_uid,
        gid=info.st_gid,
        nlink=info.st_nlink,
        size=info.st_size,
        rdev=getattr(info, "st_rdev", 0),
        mtime="%.17g" % info.st_mtime,
        ctime="%.17g" % info.st_ctime,
    )


class Inspector(object):
    def __init__(self, request):
        self.request, self.profile = request, request["profile"]
        self.root = self.profile["paths"]["managed_root"]
        self.deadline = os.times()[4] + MAX_SECONDS
        if "_FIXED_BOOTSTRAP_DEADLINE" in globals():
            self.deadline = min(self.deadline, globals()["_FIXED_BOOTSTRAP_DEADLINE"])
        self.seen, self.paths, self.hashed, self.errors, self.records = {}, set(), 0, [], []

    def check(self):
        if os.times()[4] >= self.deadline:
            raise ValueError("inspection_deadline")

    def reserve(self, selected):
        self.check()
        if not os.path.isabs(selected) or os.path.normpath(selected) != selected:
            raise ValueError("canonical_path_required")
        if selected not in self.paths and len(self.paths) >= MAX_PATHS:
            raise ValueError("inspected_path_bound")
        self.paths.add(selected)

    def remember(self, selected, info):
        self.reserve(selected)
        current = metadata(info)
        if selected in self.seen and self.seen[selected] != current:
            raise ValueError("path_metadata_drift")
        self.seen[selected] = current
        return info

    def see(self, selected):
        # Metadata-only leaves, including symlinks and devices, never get opened.
        # Retain and validate the parent chain before the no-follow leaf lstat.
        self.reserve(selected)
        if selected == "/":
            return self.remember(selected, os.lstat("/"))
        parent = self.opened(os.path.dirname(selected), True)
        try:
            info = os.lstat("/proc/self/fd/%d/%s" % (parent, os.path.basename(selected)))
            self.remember(selected, info)
            self.guard()
            return info
        finally:
            os.close(parent)

    def guard(self):
        # Rebuild a bounded retained directory tree. Absolute leaf lstat could
        # otherwise follow a replaced ancestor while checking metadata-only rows.
        if not self.seen:
            return
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_DIRECTORY
        held, parents = [], {}
        try:
            if "/" not in self.seen or metadata(os.lstat("/")) != self.seen["/"]:
                raise ValueError("path_metadata_drift")
            root = os.open("/", flags)
            held.append(root)
            if metadata(os.fstat(root)) != self.seen["/"]:
                raise ValueError("path_open_drift")
            parents["/"] = root
            for selected in sorted(self.seen, key=lambda name: (name.count("/"), name)):
                self.check()
                if selected == "/":
                    continue
                parent = parents.get(os.path.dirname(selected))
                if parent is None:
                    raise ValueError("unanchored_path_record")
                anchored = "/proc/self/fd/%d/%s" % (parent, os.path.basename(selected))
                info = os.lstat(anchored)
                if metadata(info) != self.seen[selected]:
                    raise ValueError("path_metadata_drift")
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(anchored, flags)
                    held.append(child)
                    if metadata(os.fstat(child)) != self.seen[selected]:
                        raise ValueError("path_open_drift")
                    parents[selected] = child
        finally:
            for fd in reversed(held):
                os.close(fd)

    def opened(self, selected, directory=False):
        # Anchor every component to a retained parent descriptor; do not let a
        # replaced ancestor redirect a read to an unregistered/sensitive leaf.
        if not os.path.isabs(selected) or os.path.normpath(selected) != selected:
            raise ValueError("canonical_path_required")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        held = []
        try:
            root_info = self.remember("/", os.lstat("/"))
            current = os.open("/", flags | os.O_DIRECTORY)
            held.append(current)
            if metadata(os.fstat(current)) != metadata(root_info):
                raise ValueError("path_open_drift")
            named = ""
            parts = selected.split("/")[1:] if selected != "/" else []
            for index, part in enumerate(parts):
                named += "/" + part
                self.reserve(named)
                expected = self.remember(named, os.lstat("/proc/self/fd/%d/%s" % (current, part)))
                is_directory = directory or index < len(parts) - 1
                if not (
                    stat.S_ISDIR(expected.st_mode)
                    if is_directory
                    else stat.S_ISREG(expected.st_mode)
                ):
                    raise ValueError("path_type_or_symlink_refused")
                child = os.open(
                    "/proc/self/fd/%d/%s" % (current, part),
                    flags | (os.O_DIRECTORY if is_directory else 0),
                )
                held.append(child)
                if metadata(os.fstat(child)) != metadata(expected):
                    raise ValueError("path_open_drift")
                current = child
            self.guard()
            result = held.pop()
            return result
        finally:
            for fd in reversed(held):
                os.close(fd)

    def read(self, selected, limit, kernel=False):
        fd = self.opened(selected)
        try:
            before = metadata(os.fstat(fd))
            if kernel and (before["uid"] not in (0, os.getuid()) or before["mode"] & 18):
                raise ValueError("kernel_metadata_owner_or_mode")
            parts, total = [], 0
            while True:
                self.check()
                remaining = MAX_HASH_BYTES - self.hashed
                if remaining <= 0:
                    raise ValueError("read_byte_bound")
                part = os.read(fd, min(65536, limit + 1 - total, remaining))
                if not part:
                    break
                parts.append(part)
                total += len(part)
                self.hashed += len(part)
                if total > limit or self.hashed > MAX_HASH_BYTES:
                    raise ValueError("read_byte_bound")
            if metadata(os.fstat(fd)) != before:
                raise ValueError("file_content_metadata_drift")
            self.guard()
            return b"".join(parts), before
        finally:
            os.close(fd)

    def record_error(self, role, error):
        number = getattr(error, "errno", None)
        code = str(error) if isinstance(error, ValueError) else "os_error"
        if not matches(re.compile(r"^[a-z_]{1,80}$"), code):
            code = "inspection_error"
        status = (
            "MISSING"
            if number == errno.ENOENT
            else ("INACCESSIBLE" if number in (errno.EACCES, errno.EPERM) else "INCOMPLETE")
        )
        result = dict(role=role, status=status, error_code=code, errno=number)
        self.records.append(result)
        if status != "MISSING":
            self.errors.append(result)
        return result

    def observe_path(self, role, selected):
        try:
            info = self.see(selected)
            record = dict(
                role=role,
                status="OBSERVED",
                metadata=metadata(info),
                path_sha256=digest(selected.encode("ascii")),
            )
            if stat.S_ISLNK(info.st_mode):
                record["status"] = "SYMLINK_OBSERVED_NOT_FOLLOWED"
            if stat.S_ISDIR(info.st_mode):
                fd = self.opened(selected, True)
                try:
                    fs = os.fstatvfs(fd)
                    record["filesystem"] = dict(
                        data_bytes=fs.f_blocks * fs.f_frsize,
                        available_bytes=fs.f_bavail * fs.f_frsize,
                        total_inodes=fs.f_files,
                    )
                    self.guard()
                finally:
                    os.close(fd)
            self.records.append(record)
            return record
        except (ValueError, OSError, IOError) as error:
            return self.record_error(role, error)

    def binary(self, role, selected):
        # Follow only named fixed-system aliases, never a link into a user's data.
        current, links = selected, []
        allowed = ("/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/libexec")
        try:
            for _unused in range(9):
                self.check()
                prefix, found = "", False
                for part in current.split("/")[1:]:
                    prefix += "/" + part
                    info = self.see(prefix)
                    if stat.S_ISLNK(info.st_mode):
                        target = self.alias_target(prefix, info)
                        resolved = os.path.normpath(
                            target
                            if os.path.isabs(target)
                            else os.path.join(os.path.dirname(prefix), target)
                        )
                        suffix = current[len(prefix) :]
                        replacement = resolved + suffix
                        links.append(
                            dict(
                                path_sha256=digest(prefix.encode("ascii")),
                                target_sha256=digest(target.encode("utf-8")),
                                metadata=metadata(info),
                            )
                        )
                        if not any(inside(replacement, root) for root in allowed):
                            raise ValueError("system_alias_escape")
                        current, found = replacement, True
                        break
                if not found:
                    raw, info = self.read(current, MAX_FILE_BYTES)
                    self.records.append(
                        dict(
                            role=role,
                            status="OBSERVED",
                            metadata=info,
                            sha256=digest(raw),
                            links=links,
                            resolved_path_sha256=digest(current.encode("ascii")),
                            executable=bool(info["mode"] & 73),
                            root_owned=info["uid"] == 0,
                            shared_write=bool(info["mode"] & 18),
                            binary_executed=False,
                            version_assessed=False,
                            dependency_trust_assessed=False,
                        )
                    )
                    return
            raise ValueError("system_alias_depth")
        except (ValueError, OSError, IOError) as error:
            self.record_error(role, error)

    def alias_target(self, selected, expected):
        # A parent may be replaced after see(); never inspect an alias target
        # through that absolute name. Readlink and both leaf checks share the
        # retained parent descriptor, and no link target is opened here.
        parent = self.opened(os.path.dirname(selected), True)
        try:
            anchored = "/proc/self/fd/%d/%s" % (parent, os.path.basename(selected))
            if metadata(os.lstat(anchored)) != metadata(expected):
                raise ValueError("link_metadata_drift")
            target = os.readlink(anchored)
            if metadata(os.lstat(anchored)) != metadata(expected):
                raise ValueError("link_metadata_drift")
            self.guard()
            return target
        finally:
            os.close(parent)

    def identity(self):
        raw, unused = self.read(self.root + "/reservation-identity/manifest.json", INPUT_BYTES)
        anchor = json.loads(raw.decode("ascii"))
        if raw not in (canonical(anchor), json.dumps(anchor, sort_keys=True).encode("ascii")):
            raise ValueError("identity_noncanonical")
        seal_path = self.root + "/reservation-identity/legacy-seal.json"
        try:
            seal_raw, unused = self.read(seal_path, INPUT_BYTES)
        except (OSError, IOError) as error:
            if error.errno != errno.ENOENT:
                raise
        else:
            seal = json.loads(seal_raw.decode("ascii"))
            exact(seal, ("schema_version", "prior_anchor_sha256", "anchor", "plan_sha256"))
            if seal_raw not in (canonical(seal), json.dumps(seal, sort_keys=True).encode("ascii")):
                raise ValueError("identity_seal_noncanonical")
            if (
                type(seal["schema_version"]) is not int
                or seal["schema_version"] != 1
                or (seal["prior_anchor_sha256"] != digest(canonical(anchor)))
            ):
                raise ValueError("identity_seal_binding")
            if dict(seal["anchor"], legacy_operation_ids=[]) != anchor:
                raise ValueError("identity_seal_anchor")
            anchor = seal["anchor"]
        if (
            not isinstance(anchor, dict)
            or anchor.get("root_sha256") != digest(self.root.encode("ascii"))
            or anchor.get("resource_domain_sha256") != self.request["resource_domain_sha256"]
            or (anchor.get("ledger_ref") != "sim-mcp-v2-jobs/counter.json")
            or digest(canonical(anchor)) != self.request["identity_manifest_sha256"]
        ):
            raise ValueError("identity_manifest_binding")
        self.guard()

    def kernel(self):
        # Raw mount paths, device sources and other users' backing paths never
        # leave the inspector. Return only selected roles/type/identity/digests.
        raw, unused = self.read("/proc/filesystems", MAX_KERNEL_BYTES, True)
        known = set(line.split()[-1] for line in raw.decode("ascii").splitlines() if line.split())
        filesystems = dict((name, name in known) for name in ("ext2", "ext3", "ext4"))
        # /proc/self is an intentional kernel alias, but a fully numeric current
        # PID path lets the component guard avoid following even that symlink.
        raw, unused = self.read("/proc/%d/mountinfo" % os.getpid(), MAX_KERNEL_BYTES, True)
        selected = {"stage": self.root + "/binding-observations", "backing": BACKING}
        mounts = dict((role, []) for role in selected)
        for line in raw.decode("utf-8").splitlines():
            self.check()
            fields = line.split()
            if len(fields) < 10 or "-" not in fields:
                raise ValueError("mountinfo_shape")
            separator = fields.index("-")
            if separator < 6 or separator + 3 >= len(fields):
                raise ValueError("mountinfo_shape")
            mounted = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4])
            for role, target in selected.items():
                if mounted == target or target.startswith(mounted.rstrip("/") + "/"):
                    mounts[role].append(
                        dict(
                            depth=len(mounted),
                            exact=mounted == target,
                            filesystem=fields[separator + 1],
                            device=fields[2],
                            source_sha256=digest(fields[separator + 2].encode("utf-8")),
                            restrictive_flags=dict(
                                (flag, flag in fields[5].split(","))
                                for flag in ("ro", "nodev", "nosuid", "noexec")
                            ),
                        )
                    )
        for role in mounts:
            mounts[role] = sorted(mounts[role], key=lambda row: row["depth"])[-1:]
        return dict(
            filesystems_listed=filesystems,
            selected_mounts=mounts,
            raw_mount_inventory_sha256=digest(raw),
            kernel_modules_loaded=False,
            persistent_backing_established=False,
            loop_feasibility_assessed=False,
        )

    def names(self, selected):
        if os.name == "nt":
            fd = self.opened(selected, True)
            os.close(fd)
            scan = os.scandir(selected)
            try:
                for entry in scan:
                    self.check()
                    yield entry.name
            finally:
                scan.close()
            return
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        libc.fdopendir.argtypes, libc.fdopendir.restype = [ctypes.c_int], ctypes.c_void_p
        libc.readdir64.argtypes, libc.readdir64.restype = [ctypes.c_void_p], ctypes.c_void_p
        libc.closedir.argtypes, libc.closedir.restype = [ctypes.c_void_p], ctypes.c_int
        fd = self.opened(selected, True)
        stream = None
        try:
            stream = libc.fdopendir(fd)
            if not stream:
                raise OSError(ctypes.get_errno(), "directory_stream")
            while True:
                self.check()
                ctypes.set_errno(0)
                entry = libc.readdir64(stream)
                if not entry:
                    if ctypes.get_errno():
                        raise OSError(ctypes.get_errno(), "directory_stream")
                    break
                length = ctypes.c_ushort.from_address(entry + 16).value
                if not 20 <= length <= 280:
                    raise ValueError("directory_record")
                raw = ctypes.string_at(entry + 19, length - 19).split(b"\x00", 1)[0]
                if raw not in (b".", b".."):
                    yield raw.decode("ascii")
            self.guard()
        finally:
            if stream:
                if libc.closedir(stream) != 0:
                    raise OSError(ctypes.get_errno(), "directory_close")
            else:
                os.close(fd)

    def stage(self):
        selected = self.root + "/binding-observations"
        record = self.observe_path("stage", selected)
        if record["status"] != "OBSERVED" or not stat.S_ISDIR(record["metadata"]["mode"]):
            return
        entries, hashed = 0, hashlib.sha256()
        names = self.names(selected)
        try:
            for name in names:
                self.check()
                entries += 1
                if entries > 256:
                    raise ValueError("stage_occupancy_bound")
                hashed.update(name.encode("ascii") + b"\0")
        finally:
            names.close()
        record.update(
            entry_count=entries,
            entries_sha256=hashed.hexdigest(),
            empty=entries == 0,
            existing_contents_read=False,
        )

    def loops(self):
        selected, loops = self.names("/sys/block"), []
        try:
            for count, name in enumerate(selected):
                self.check()
                if count >= 128:
                    raise ValueError("block_inventory_bound")
                if not matches(re.compile(r"^loop[0-9]{1,3}$"), name):
                    continue
                if len(loops) >= MAX_LOOP_DEVICES:
                    raise ValueError("loop_inventory_bound")
                self.observe_path("device-" + name, "/dev/" + name)
                # The kernel's standard virtual-loop target is fixed; do not
                # follow an arbitrary /sys/block alias into another device tree.
                association = "/sys/devices/virtual/block/" + name + "/loop/backing_file"
                try:
                    raw, unused = self.read(association, 4096, True)
                    expected = BACKING + "/" + self.request["resource_domain_sha256"] + ".ext2"
                    loops.append(
                        dict(
                            device=name,
                            association="EXPECTED_BACKING"
                            if raw.rstrip(b"\n") == expected.encode("ascii")
                            else "OTHER_REDACTED",
                            association_sha256=digest(raw),
                            available_for_use=False,
                        )
                    )
                except (ValueError, OSError, IOError) as error:
                    self.record_error("association-" + name, error)
                    loops.append(
                        dict(device=name, association="NOT_ESTABLISHED", available_for_use=False)
                    )
        finally:
            selected.close()
        return loops

    def run(self):
        self.check()
        uname = os.uname()
        if (
            uname[0] != "Linux"
            or uname[4] not in ("i686", "x86_64")
            or (os.getuid() == 0 or os.geteuid() != os.getuid())
        ):
            raise ValueError("ordinary_standard_linux_required")
        import pwd

        host = dict(
            hostname=uname[1],
            architecture=uname[4],
            python_version=".".join(str(number) for number in sys.version_info[:3]),
            os=uname[0],
            user=pwd.getpwuid(os.getuid()).pw_name,
        )
        if host != self.profile["host"]:
            raise ValueError("observed_host_binding")
        self.identity()
        self.stage()
        for role, selected in (
            ("var", "/var"),
            ("var-lib", "/var/lib"),
            ("backing-parent", "/var/lib/cadence-mcp-bridge"),
            ("backing", BACKING),
            ("loop-control", "/dev/loop-control"),
        ):
            self.observe_path(role, selected)
        self.observe_path(
            "backing-image", BACKING + "/" + self.request["resource_domain_sha256"] + ".ext2"
        )
        for role, selected in BINARIES:
            self.binary(role, selected)
        kernel, loops = {}, []
        try:
            kernel = self.kernel()
        except (ValueError, OSError, IOError) as error:
            self.record_error("kernel", error)
        try:
            loops = self.loops()
        except (ValueError, OSError, IOError) as error:
            self.record_error("loops", error)
        self.guard()
        return dict(
            schema_version=1,
            kind="FIXED_STORAGE_PREREQUISITE_FACTS",
            status="INCOMPLETE" if self.errors else "OBSERVATIONS_ONLY",
            request_sha256=digest(canonical(self.request)),
            profile_canonical_sha256=self.request["profile_canonical_sha256"],
            resource_domain_sha256=self.request["resource_domain_sha256"],
            identity_manifest_sha256=self.request["identity_manifest_sha256"],
            inspected_paths=len(self.paths),
            bytes_read=self.hashed,
            path_observations=[
                dict(
                    path_sha256=digest(name.encode("ascii")),
                    metadata=info,
                    root_owned=info["uid"] == 0,
                    shared_write=bool(info["mode"] & 18),
                )
                for name, info in sorted(self.seen.items())
            ],
            records=self.records,
            kernel=kernel,
            loops=loops,
            errors=self.errors,
            ready_for_apply=False,
            acl_assessed=False,
            runtime_trust_assessed=False,
            binary_versions_assessed=False,
            execution_authorized=False,
            system_commands_executed=0,
            eda_starts=0,
            new_simulations=0,
            reserved_bytes=0,
            intentional_remote_writes=0,
        )


def bounded_result(value):
    raw = canonical(value)
    if len(raw) > OUTPUT_BYTES:
        raise ValueError("output_bound")
    return raw


def main():
    def expired(signum, frame):
        raise ValueError("inspection_deadline")

    prior_handler = None
    try:
        if len(sys.argv) != 1:
            raise ValueError("no_command_or_path_arguments")
        if not hasattr(signal, "SIGALRM"):
            raise ValueError("ordinary_standard_linux_required")
        if not globals().get("_FIXED_BOOTSTRAP_ACTIVE", False):
            prior_handler = signal.signal(signal.SIGALRM, expired)
            signal.alarm(MAX_SECONDS)
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        request = parse_request(stream.read(INPUT_BYTES + 1))
        result = Inspector(request).run()
        raw = bounded_result(result)
    except (ValueError, OSError, IOError, KeyError, TypeError) as error:
        code = str(error) if isinstance(error, ValueError) else "inspection_incomplete"
        if not matches(re.compile(r"^[a-z_]{1,80}$"), code):
            code = "inspection_incomplete"
        raw = bounded_result(
            dict(
                schema_version=1,
                status="INCOMPLETE",
                error_code=code,
                ready_for_apply=False,
                execution_authorized=False,
            )
        )
    finally:
        if prior_handler is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prior_handler)
    output = getattr(sys.stdout, "buffer", sys.stdout)
    output.write(raw + b"\n")


# validate_profile below preserves the pinned existing read-only validator logic
# _environment_probe.py validator; no environment tool or Cadence code executes.


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


if __name__ == "__main__":
    main()
