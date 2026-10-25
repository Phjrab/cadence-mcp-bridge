# mypy: ignore-errors
# ruff: noqa: UP004, UP024, UP031
"""Draft fixed standard-VM storage provisioning; explicit administrator entry only.

Exported configuration is data, not permission or runtime trust. Never imported
by server startup. No remote transport, deletion, module loading or fstab edits.
"""

import sys

if __name__ == "__main__":
    if (not sys.flags.ignore_environment or not sys.flags.no_user_site
            or not sys.dont_write_bytecode):
        sys.exit("isolated_python_required")
    _entry = sys.path[0] if sys.path else None
    sys.path[:] = [item for item in sys.path if item and item != _entry]
import os

if __name__ == "__main__":
    _cwd = os.path.realpath(os.getcwd())
    sys.path[:] = [item for item in sys.path
                   if os.path.isabs(item) and os.path.realpath(item) != _cwd]
import errno
import hashlib
import json
import re
import signal
import stat
import struct
import subprocess
import time

CONFIG_JSON = None  # Replaced only by the local package exporter.
BACKING = "/var/lib/cadence-mcp-bridge/observer-storage"
IMAGE_BYTES = 8388608
INODES = 128
LOOP_GET_STATUS64 = 0x4C05
LOOP_SET_FD = 0x4C00
LOOP_CLR_FD = 0x4C01
LOOP_FORMAT = "=QQQQQIIII64s64s32sQQ"
INPUT_BOUND = 65536
try:
    STRING_TYPES = (basestring,)
    INTEGER_TYPES = (int, long)
except NameError:
    STRING_TYPES = (str,)
    INTEGER_TYPES = (int,)


def matches(pattern, value):
    if not isinstance(value, STRING_TYPES):
        return False
    found = re.match(pattern, value)
    return found is not None and found.end() == len(value)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_rdev]


def protected_metadata(info):
    # Read-induced atime changes do not alter accounting identity/security.
    return identity(info) + [info.st_nlink, info.st_size, info.st_mtime, info.st_ctime]


def fdname(fd):
    return "/proc/self/fd/%d" % fd


def valid_config(config):
    keys = ("schema_version", "kind", "hostname", "architecture", "user", "managed_root",
            "resource_domain_sha256", "identity_manifest_sha256", "mke2fs_sha256",
            "runtime_review_sha256", "formatter_path", "formatter_nlink",
            "disk_floor_bytes", "disk_floor_percent")
    if not isinstance(config, dict) or set(config) != set(keys):
        raise ValueError("closed_configuration")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1 or (
        config["kind"] != "FIXED_BINDING_STORAGE_ADMIN"
        or config["architecture"] not in ("i686", "x86_64")
        or not matches(r"^[a-z_][a-z0-9_-]{0,31}$", config["user"])
        or not matches(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$", config["hostname"])
        or config["formatter_path"] not in ("/sbin/mke2fs", "/usr/sbin/mke2fs")
    ):
        raise ValueError("standard_vm_configuration")
    root = config["managed_root"]
    if not isinstance(root, STRING_TYPES) or (
        not root.startswith("/home/" + config["user"] + "/")
    ) or (
        len(root) > 512 or not root.endswith("/.cadence_mcp")
        or not matches(r"^/[A-Za-z0-9._/-]+$", root)
        or any(part in ("", ".", "..") for part in root.split("/")[1:])
    ):
        raise ValueError("managed_root_configuration")
    for name in ("resource_domain_sha256", "identity_manifest_sha256", "mke2fs_sha256",
                 "runtime_review_sha256"):
        if not matches(r"^[0-9a-f]{64}$", config[name]):
            raise ValueError("configuration_digest")
    for name in ("disk_floor_bytes", "disk_floor_percent"):
        if type(config[name]) not in INTEGER_TYPES:
            raise ValueError("configuration_disk_floor")
    if config["disk_floor_bytes"] < 0 or not 0 <= config["disk_floor_percent"] <= 99:
        raise ValueError("configuration_disk_floor")
    if type(config["formatter_nlink"]) not in INTEGER_TYPES or (
        not 1 <= config["formatter_nlink"] <= 64
    ):
        raise ValueError("reviewed_formatter_link_count")
    if config["resource_domain_sha256"] != digest(canonical(dict(
        hostname=config["hostname"].lower().rstrip("."), architecture=config["architecture"]
    ))):
        raise ValueError("configuration_resource_domain")
    return config


class StorageAdmin(object):
    def __init__(self, config):
        self.config = valid_config(config)
        self.root = config["managed_root"]
        self.domain = config["resource_domain_sha256"]
        self.stage = self.root + "/binding-observations"
        self.image = BACKING + "/" + self.domain + ".ext2"
        self.receipt = BACKING + "/" + self.domain + ".receipt.json"
        self.claim = BACKING + "/" + self.domain + ".intent.json"
        self.directories, self.fds = {}, []
        self.deadline = os.times()[4] + 60
        self.cancelled = False
        self.lock = None
        self.protected = {}
        self.absent_protected = []

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds = []

    def check(self):
        if self.cancelled or os.times()[4] >= self.deadline:
            raise ValueError("administrator_operation_cancelled")
        for path in sorted(self.directories, key=lambda item: (item.count("/"), item)):
            pair = self.directories[path]
            fd, expected = pair
            named = path if path == "/" else (
                fdname(self.directories[os.path.dirname(path)][0]) + "/" + os.path.basename(path)
            )
            if identity(os.fstat(fd)) != expected or identity(os.lstat(named)) != expected:
                raise ValueError("held_directory_identity_drift")

    def track(self, fd):
        import fcntl
        self.fds.append(fd)
        fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.fcntl(fd, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)
        if len(self.fds) > 128:
            raise ValueError("administrator_descriptor_bound")
        return fd

    def release(self, fd):
        os.close(fd)
        self.fds.remove(fd)

    def named(self, path):
        return fdname(self.directories[os.path.dirname(path)][0]) + "/" + os.path.basename(path)

    def directory(self, path, owner, create=False):
        if path in self.directories:
            self.check()
            return self.directories[path][0]
        if path != "/":
            parent = os.path.dirname(path)
            parent_owner = self.uid if (
                parent == self.root or parent.startswith(self.root + "/")
            ) else 0
            # Existing user-owned home/work ancestors are permitted, never created.
            if parent.startswith("/home/" + self.config["user"]):
                parent_owner = self.uid
            parentfd = self.directory(parent, parent_owner)
            selected = fdname(parentfd) + "/" + os.path.basename(path)
        else:
            selected = "/"
        self.check()
        if create:
            os.mkdir(selected, 0o700)
            os.fsync(parentfd)
        fd = self.track(os.open(selected, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, owner) or (
            stat.S_IMODE(info.st_mode) & 0o022
        ) or identity(info) != identity(os.lstat(selected)):
            raise ValueError("directory_trust_required")
        self.directories[path] = (fd, identity(info))
        return fd

    def leaf(self, path, flags=os.O_RDONLY, mode=0o600):
        parent = os.path.dirname(path)
        owner = (self.uid if parent == self.root or parent.startswith(self.root + "/")
                 else 0)
        fd = self.directory(parent, owner)
        self.check()
        return self.track(os.open(fdname(fd) + "/" + os.path.basename(path),
                                  flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode))

    def raw(self, path, owner, bound, keep=False, nlink=1):
        fd = self.leaf(path)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != owner or (
            before.st_nlink != nlink or before.st_mode & 0o022 or before.st_size > bound
        ):
            raise ValueError("regular_file_trust_required")
        pieces, size = [], 0
        while size <= bound:
            self.check()
            piece = os.read(fd, min(65536, bound + 1 - size))
            if not piece:
                break
            pieces.append(piece)
            size += len(piece)
        raw = b"".join(pieces)
        after = os.fstat(fd)
        if len(raw) > bound or len(raw) != before.st_size or (
            identity(before) != identity(after) or before.st_mtime != after.st_mtime
            or before.st_nlink != after.st_nlink or before.st_size != after.st_size
            or before.st_ctime != after.st_ctime
            or identity(os.lstat(self.named(path))) != identity(after)
        ):
            raise ValueError("regular_file_drift")
        self.check()
        if not keep:
            self.release(fd)
        return raw, fd

    def exclusive(self, path, value):
        raw = canonical(value)
        fd = self.leaf(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        if os.write(fd, raw) != len(raw):
            raise ValueError("receipt_short_write")
        os.fsync(fd)
        os.fsync(self.directories[os.path.dirname(path)][0])
        info = os.fstat(fd)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or (
            identity(info) != identity(os.lstat(self.named(path))) or info.st_size != len(raw)
        ):
            raise ValueError("receipt_publication_drift")
        self.check()

    def remember_protected(self, suffix, bound):
        path = self.root + "/" + suffix
        raw, fd = self.raw(path, self.uid, bound, True)
        try:
            record = dict(sha256=digest(raw), metadata=protected_metadata(os.fstat(fd)))
            if protected_metadata(os.lstat(self.named(path))) != record["metadata"]:
                raise ValueError("existing_accounting_drift")
            self.protected[suffix] = record
            return raw
        finally:
            self.release(fd)

    def enter(self):
        import fcntl
        import pwd

        if os.getuid() != 0 or os.geteuid() != 0 or os.uname()[0] != "Linux" or (
            os.uname()[1] != self.config["hostname"] or os.uname()[4] != self.config["architecture"]
        ):
            raise ValueError("exact_standard_vm_administrator_required")
        user = pwd.getpwnam(self.config["user"])
        self.uid, self.gid = user.pw_uid, user.pw_gid
        if self.uid == 0:
            raise ValueError("ordinary_operator_required")
        self.directory(self.root, self.uid)
        if os.fstat(self.directories[self.root][0]).st_uid != self.uid:
            raise ValueError("existing_operator_owned_root_required")
        # Reuse the existing lifecycle lock; never create, replace or truncate it.
        lockpath = self.root + "/run.lock"
        raw, self.lock = self.raw(lockpath, self.uid, 4096, True)
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.lock_identity = identity(os.fstat(self.lock))
        self.lock_raw = raw
        self.lockpath = lockpath
        for suffix, bound in (("sim-mcp-v2-jobs/counter.json", 8192),
                              ("reservation-identity/manifest.json", 65536)):
            self.remember_protected(suffix, bound)
        anchor = json.loads(self.raw(self.root + "/reservation-identity/manifest.json",
                                     self.uid, 65536)[0])
        if anchor.get("resource_domain_sha256") != self.domain or (
            anchor.get("root_sha256") != digest(self.root.encode("ascii"))
        ):
            raise ValueError("existing_identity_binding")
        sealpath = self.root + "/reservation-identity/legacy-seal.json"
        if os.path.lexists(sealpath):
            sealraw = self.remember_protected("reservation-identity/legacy-seal.json", 65536)
            seal = json.loads(sealraw.decode("ascii"))
            if set(seal) != set((
                "schema_version", "prior_anchor_sha256", "anchor", "plan_sha256"
            )) or (
                type(seal["schema_version"]) is not int or seal["schema_version"] != 1
                or seal["prior_anchor_sha256"] != digest(canonical(anchor))
                or dict(seal["anchor"], legacy_operation_ids=[]) != anchor
            ):
                raise ValueError("existing_legacy_seal_binding")
            anchor = seal["anchor"]
        else:
            self.absent_protected.append("reservation-identity/legacy-seal.json")
        if digest(canonical(anchor)) != self.config["identity_manifest_sha256"]:
            raise ValueError("existing_identity_requires_separate_seal_review")
        self.guard()

    def guard(self):
        self.check()
        if self.lock is not None:
            if identity(os.fstat(self.lock)) != self.lock_identity or (
                identity(os.lstat(self.named(self.lockpath))) != self.lock_identity
                or os.fstat(self.lock).st_nlink != 1
                or os.fstat(self.lock).st_size != len(self.lock_raw)
            ):
                raise ValueError("existing_lock_drift")
            os.lseek(self.lock, 0, os.SEEK_SET)
            if os.read(self.lock, 4097) != self.lock_raw:
                raise ValueError("existing_lock_content_drift")
        held = []
        try:
            for suffix, expected in self.protected.items():
                path = self.root + "/" + suffix
                raw, fd = self.raw(path, self.uid, 65536, True)
                held.append((suffix, fd))
                if dict(sha256=digest(raw), metadata=protected_metadata(os.fstat(fd))) != expected:
                    raise ValueError("existing_accounting_drift")
            # Recheck the complete union after all content reads; a later read
            # must not invalidate an earlier protected-file observation.
            for suffix, fd in held:
                expected = self.protected[suffix]["metadata"]
                if protected_metadata(os.fstat(fd)) != expected or (
                    protected_metadata(os.lstat(self.named(self.root + "/" + suffix))) != expected
                ):
                    raise ValueError("existing_accounting_drift")
            for suffix in self.absent_protected:
                if os.path.lexists(self.named(self.root + "/" + suffix)):
                    raise ValueError("existing_accounting_namespace_drift")
            self.check()
        finally:
            for _suffix, fd in held:
                self.release(fd)

    def disk(self):
        fd = self.directory("/var/lib", 0)
        info = os.fstatvfs(fd)
        available = info.f_bavail * info.f_frsize
        total = info.f_blocks * info.f_frsize
        remaining = available - IMAGE_BYTES
        if remaining < self.config["disk_floor_bytes"] or (
            remaining * 100 < total * self.config["disk_floor_percent"]
        ):
            raise ValueError("minimum_disk_floor")

    def loop(self, number):
        if type(number) is not int or not 0 <= number < 16:
            raise ValueError("closed_loop_device")
        fd = self.leaf("/dev/loop%d" % number, os.O_RDWR)
        info = os.fstat(fd)
        if not stat.S_ISBLK(info.st_mode) or info.st_uid != 0 or (
            os.major(info.st_rdev) != 7 or os.minor(info.st_rdev) != number
            or identity(info) != identity(os.lstat(self.named("/dev/loop%d" % number)))
        ):
            raise ValueError("loop_device_identity")
        state = self.loop_status(fd)
        if state is not None and state["number"] != number:
            raise ValueError("loop_device_number_drift")
        return fd, state, identity(info)

    def loop_status(self, fd):
        import fcntl
        self.check()
        try:
            raw = fcntl.ioctl(fd, LOOP_GET_STATUS64, b"\0" * struct.calcsize(LOOP_FORMAT))
            values = struct.unpack(LOOP_FORMAT, raw)
            state = dict(device=values[0], inode=values[1], rdevice=values[2], offset=values[3],
                         size_limit=values[4], number=values[5], encryption=values[6],
                         key_size=values[7], flags=values[8])
        except (OSError, IOError) as error:
            if error.errno != errno.ENXIO:
                raise
            state = None
        return state

    def plan(self):
        self.guard()
        self.disk()
        for path in (self.stage, self.image, self.receipt, self.claim):
            if os.path.lexists(path):
                raise ValueError("existing_storage_requires_retained_recovery")
        # All format/runtime dependency trust is external to these hashes.
        utility, fd = self.raw(self.config["formatter_path"], 0, 16777216, True,
                               self.config["formatter_nlink"])
        if digest(utility) != self.config["mke2fs_sha256"] or not os.fstat(fd).st_mode & 0o111:
            raise ValueError("reviewed_formatter_required")
        selected = None
        for number in range(16):
            try:
                unused, state, info = self.loop(number)
            except (OSError, IOError) as error:
                if error.errno in (errno.ENOENT, errno.ENODEV):
                    continue
                raise
            if state is None:
                selected = dict(number=number, metadata=info)
                self.release(unused)
                break
            self.release(unused)
        if selected is None:
            raise ValueError("no_existing_supported_free_loop_device")
        self.release(fd)
        self.guard()
        return dict(schema_version=1, kind="FIXED_BINDING_STORAGE_PLAN",
                    config_sha256=digest(canonical(self.config)), protected=self.protected,
                    loop=selected, image_bytes=IMAGE_BYTES, inode_ceiling=INODES,
                    source_runtime_trust="EXTERNAL_REVIEW_REQUIRED_NOT_PROVED_BY_HASH",
                    execution_authorized=False)

    def formatter(self, imagefd):
        # Keep only held image/utility descriptors across exec, not ambient paths.
        unused, utilityfd = self.raw(self.config["formatter_path"], 0, 16777216, True,
                                     self.config["formatter_nlink"])
        if digest(unused) != self.config["mke2fs_sha256"]:
            raise ValueError("reviewed_formatter_required")
        import fcntl
        for fd in (imagefd, utilityfd):
            fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.fcntl(fd, fcntl.F_GETFD) & ~fcntl.FD_CLOEXEC)
        self.guard()
        child = None
        nullfd = self.leaf("/dev/null", os.O_RDWR)
        nullinfo = os.fstat(nullfd)
        if not stat.S_ISCHR(nullinfo.st_mode) or nullinfo.st_uid != 0 or (
            os.major(nullinfo.st_rdev) != 1 or os.minor(nullinfo.st_rdev) != 3
        ):
            raise ValueError("system_null_device_required")
        try:
            child = subprocess.Popen(
                [fdname(utilityfd), "-F", "-q", "-t", "ext2", "-O", "none", "-E", "nodiscard",
                 "-b", "1024",
                 "-N", str(INODES), "-m", "0", fdname(imagefd)],
                stdin=nullfd, stdout=nullfd, stderr=nullfd, close_fds=False,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                     "MKE2FS_CONFIG": "/dev/null"}, preexec_fn=os.setsid,
            )
            deadline = min(self.deadline, os.times()[4] + 30)
            while child.poll() is None:
                if self.cancelled or os.times()[4] >= deadline:
                    raise ValueError("formatter_deadline_or_cancellation")
                time.sleep(0.05)
            if child.returncode != 0:
                raise ValueError("formatter_failed")
        finally:
            if child is not None and child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except OSError as error:
                    if error.errno != errno.ESRCH:
                        raise
                finally:
                    child.wait()  # Retain the lock until the owned formatter is reaped.
            for fd in (imagefd, utilityfd):
                fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.fcntl(fd, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)
            self.release(nullfd)

    def image_state(self, imagefd, require_clean=False):
        import binascii
        self.check()
        info = os.fstat(imagefd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != IMAGE_BYTES or (
            info.st_blocks * 512 < IMAGE_BYTES or info.st_uid != 0 or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or identity(info) != identity(os.lstat(self.named(self.image)))
        ):
            raise ValueError("private_full_image_required")
        os.lseek(imagefd, 1024, os.SEEK_SET)
        header = os.read(imagefd, 256)
        if len(header) != 256:
            raise ValueError("formatted_image_header")
        inode_count, blocks = struct.unpack_from("<II", header)
        if not 0 < inode_count <= 256 or blocks != 8192 or (
            struct.unpack_from("<I", header, 24)[0] != 0
            or struct.unpack_from("<H", header, 56)[0] != 0xEF53
            or struct.unpack_from("<III", header, 92) != (0, 0, 0)
        ):
            raise ValueError("fixed_formatted_image_required")
        if require_clean and struct.unpack_from("<H", header, 58)[0] != 1:
            # No fsck or automatic repair: retain the image for separate review.
            raise ValueError("unclean_image_requires_separate_recovery")
        return dict(identity=identity(info), inodes=inode_count, blocks=blocks,
                    uuid=binascii.hexlify(header[104:120]).decode("ascii"))

    def mounted(self, loop_info=None):
        import ctypes
        path = "/proc/%d/mountinfo" % os.getpid()
        fd = self.leaf(path)
        try:
            info = os.fstat(fd)
            libc = ctypes.CDLL(None, use_errno=True)
            libc.fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
            libc.fstatfs.restype = ctypes.c_int
            buffer = ctypes.create_string_buffer(256)
            if libc.fstatfs(fd, buffer) or ctypes.c_long.from_buffer(buffer).value != 0x9FA0 or (
                not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
            ):
                raise ValueError("kernel_mount_source_required")
            pieces, size = [], 0
            while size <= 65536:
                self.check()
                piece = os.read(fd, min(8192, 65537 - size))
                if not piece:
                    break
                pieces.append(piece)
                size += len(piece)
            raw = b"".join(pieces)
            if len(raw) > 65536 or not raw.endswith(b"\n") or (
                identity(os.fstat(fd)) != identity(info)
                or identity(os.lstat(self.named(path))) != identity(info)
            ):
                raise ValueError("kernel_mount_bound_or_drift")
        finally:
            self.release(fd)
        found = []
        for line in raw.decode("ascii").splitlines():
            fields = line.split()
            if len(fields) < 10 or "-" not in fields:
                raise ValueError("kernel_mount_shape")
            named = re.sub(r"\\([0-7]{3})", lambda item: chr(int(item.group(1), 8)), fields[4])
            if named == self.stage:
                sep = fields.index("-")
                if sep < 6 or sep + 3 >= len(fields) or fields[sep + 1] != "ext4" or (
                    fields[3] != "/"
                    or not set(("rw", "nodev", "nosuid", "noexec")).issubset(
                        set(fields[5].split(",")))
                ):
                    raise ValueError("fixed_kernel_mount_required")
                found.append(fields[2])
        if len(found) > 1 or (found and (loop_info is None or found[0] != "7:%d" % loop_info)):
            raise ValueError("unexpected_or_duplicate_stage_mount")
        return bool(found)

    def association(self, state, imagefd):
        info = os.fstat(imagefd)
        return state is not None and state == dict(
            device=info.st_dev, inode=info.st_ino, rdevice=0, offset=0, size_limit=0,
            number=state["number"], encryption=0, key_size=0, flags=0)

    def mount(self, loopfd, imagefd, targetfd, number, attach=True):
        import ctypes
        import fcntl

        self.guard()
        self.image_state(imagefd, require_clean=True)
        self.stage_guard(targetfd)
        if attach:
            fcntl.ioctl(loopfd, LOOP_SET_FD, imagefd)
        checked, state, unused = self.loop(number)
        if not self.association(state, imagefd):
            raise ValueError("exact_loop_association_required")
        self.release(checked)
        self.guard()
        self.stage_guard(targetfd)
        # Persistent association: do not use AUTOCLEAR while an operational mount exists.
        libc = ctypes.CDLL(None, use_errno=True)
        libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                               ctypes.c_ulong, ctypes.c_void_p]
        libc.mount.restype = ctypes.c_int
        if libc.mount(fdname(loopfd).encode("ascii"), fdname(targetfd).encode("ascii"),
                      b"ext4", 14, None):
            raise OSError(ctypes.get_errno(), "fixed_mount_failed")
        self.guard()
        if not self.mounted(number):
            raise ValueError("fixed_kernel_mount_required")
        mountedfd = self.leaf(self.stage, os.O_RDONLY | os.O_DIRECTORY)
        os.fchown(mountedfd, self.uid, self.gid)
        os.fchmod(mountedfd, 0o700)
        os.fsync(mountedfd)
        fs = os.fstatvfs(mountedfd)
        info = os.fstat(mountedfd)
        if not 0 < fs.f_blocks * fs.f_frsize <= IMAGE_BYTES or not 0 < fs.f_files <= 256 or (
            info.st_dev == os.fstat(self.directories[self.root][0]).st_dev
            or info.st_uid != self.uid or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ValueError("mounted_kernel_limits_required")
        return info.st_dev

    def stage_guard(self, fd):
        self.guard()
        held = os.fstat(fd)
        if not stat.S_ISDIR(held.st_mode) or held.st_uid != 0 or (
            stat.S_IMODE(held.st_mode) != 0o700
            or identity(held) != identity(os.lstat(self.named(self.stage)))
        ):
            raise ValueError("fixed_unmounted_stage_identity_required")

    def apply(self, plan):
        if plan != self.plan():
            raise ValueError("approved_plan_drift")
        for path in ("/var/lib/cadence-mcp-bridge", BACKING):
            if not os.path.lexists(path):
                self.directory(path, 0, create=True)
            fd = self.directory(path, 0)
            if os.fstat(fd).st_uid != 0 or stat.S_IMODE(os.fstat(fd).st_mode) != 0o700:
                raise ValueError("private_backing_required")
        self.guard()
        # Intent precedes image creation, formatting, device attachment and mounting.
        self.exclusive(self.claim, dict(kind="SPENT_STORAGE_APPLY_NO_BLIND_RETRY",
                                       plan_sha256=digest(canonical(plan)), plan=plan))
        imagefd = self.leaf(self.image, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        for _unused in range(128):
            self.guard()
            if os.write(imagefd, b"\0" * 65536) != 65536:
                raise ValueError("image_short_write")
        os.fsync(imagefd)
        self.guard()
        self.formatter(imagefd)
        os.fsync(imagefd)
        superblock = self.image_state(imagefd)
        imageinfo = os.fstat(imagefd)
        if imageinfo.st_size != IMAGE_BYTES or imageinfo.st_blocks * 512 < IMAGE_BYTES or (
            imageinfo.st_uid != 0 or imageinfo.st_nlink != 1
            or stat.S_IMODE(imageinfo.st_mode) != 0o600
        ):
            raise ValueError("private_full_image_required")
        parentfd = self.directories[self.root][0]
        self.guard()
        os.mkdir(fdname(parentfd) + "/binding-observations", 0o700)
        os.fsync(parentfd)
        targetfd = self.leaf(self.stage, os.O_RDONLY | os.O_DIRECTORY)
        loopfd, state, info = self.loop(plan["loop"]["number"])
        if state is not None or info != plan["loop"]["metadata"]:
            raise ValueError("selected_loop_no_longer_free")
        # Failed/unknown attach or mount is retained in intent; never autoformat/retry.
        mounted_device = self.mount(loopfd, imagefd, targetfd, plan["loop"]["number"])
        self.guard()
        self.exclusive(self.receipt, dict(schema_version=1, kind="FIXED_STORAGE_MOUNTED_RECEIPT",
                       plan_sha256=digest(canonical(plan)),
                       config_sha256=digest(canonical(self.config)),
                       image_identity=identity(imageinfo), image_bytes=IMAGE_BYTES,
                       superblock=superblock,
                       loop=plan["loop"]["number"], mounted_device=mounted_device,
                       protected=self.protected, execution_authorized=False))
        return dict(status="STORAGE_MOUNTED_REQUIRES_ORDINARY_USER_POSTCHECK",
                    execution_authorized=False, new_simulations=0, new_reserved_bytes=0)

    def recovery_plan(self, operation):
        if operation not in ("remount", "detach"):
            raise ValueError("closed_recovery_operation")
        self.guard()
        claimraw, unused = self.raw(self.claim, 0, 65536)
        claim = json.loads(claimraw.decode("ascii"))
        if canonical(claim) != claimraw or set(claim) != set(("kind", "plan_sha256", "plan")) or (
            claim["kind"] != "SPENT_STORAGE_APPLY_NO_BLIND_RETRY"
            or digest(canonical(claim["plan"])) != claim["plan_sha256"]
            or claim["plan"].get("config_sha256") != digest(canonical(self.config))
        ):
            raise ValueError("retained_original_intent_required")
        imagefd = self.leaf(self.image, os.O_RDWR)
        superblock = self.image_state(imagefd)
        receiptsha = None
        if os.path.lexists(self.receipt):
            raw, unused = self.raw(self.receipt, 0, 65536)
            receipt = json.loads(raw.decode("ascii"))
            if canonical(receipt) != raw or (
                receipt.get("kind") != "FIXED_STORAGE_MOUNTED_RECEIPT"
            ) or (
                receipt.get("plan_sha256") != claim["plan_sha256"]
                or receipt.get("config_sha256") != digest(canonical(self.config))
                or receipt.get("superblock") != superblock
            ):
                raise ValueError("retained_storage_receipt_binding")
            receiptsha = digest(raw)
        associated, free = [], []
        for number in range(16):
            try:
                loopfd, state, info = self.loop(number)
            except (OSError, IOError) as error:
                if error.errno in (errno.ENOENT, errno.ENODEV):
                    continue
                raise
            if self.association(state, imagefd):
                associated.append(dict(number=number, metadata=info, state=state))
            elif state is None:
                free.append(dict(number=number, metadata=info, state=None))
            self.release(loopfd)
        self.release(imagefd)
        if len(associated) > 1 or not (associated or free):
            raise ValueError("unambiguous_existing_loop_required")
        selected = (associated or free)[0]
        mounted = self.mounted(selected["number"] if associated else None)
        if not mounted:
            imagefd = self.leaf(self.image, os.O_RDWR)
            self.image_state(imagefd, require_clean=True)
            self.release(imagefd)
        stagefd = self.leaf(self.stage, os.O_RDONLY | os.O_DIRECTORY)
        info = os.fstat(stagefd)
        if info.st_uid != (self.uid if mounted else 0) or stat.S_IMODE(info.st_mode) != 0o700 or (
            not mounted and os.listdir(fdname(stagefd))
        ):
            raise ValueError("preserved_stage_required")
        self.release(stagefd)
        # Completed transitions distinguish a later legitimate detach/remount
        # from a blind retry of the same possibly partial privileged action.
        history = []
        parentfd = self.directory(BACKING, 0)
        names = os.listdir(fdname(parentfd))
        if len(names) > 512:
            raise ValueError("private_recovery_inventory_bound")
        for name in sorted(names):
            if matches(re.escape(self.domain) + r"\.[0-9a-f]{64}\.done\.json$", name):
                if len(history) >= 32:
                    raise ValueError("retained_recovery_history_bound")
                raw, unused = self.raw(BACKING + "/" + name, 0, 4096)
                history.append([name, digest(raw)])
        self.guard()
        return dict(schema_version=1, kind="FIXED_BINDING_STORAGE_RECOVERY_PLAN",
                    operation=operation, config_sha256=digest(canonical(self.config)),
                    original_intent_sha256=digest(claimraw), original_receipt_sha256=receiptsha,
                    superblock=superblock, loop=selected, mounted=mounted,
                    stage_identity=identity(info), protected=self.protected,
                    completed_history_sha256=digest(canonical(history)),
                    execution_authorized=False)

    def recover(self, plan):
        import ctypes
        import fcntl
        operation = plan.get("operation")
        if plan != self.recovery_plan(operation):
            raise ValueError("approved_recovery_plan_drift")
        pin = digest(canonical(plan))
        # A new approval is needed for any changed recovery plan; identical plans
        # cannot repeat a possibly partial privileged action.
        self.exclusive(BACKING + "/" + self.domain + "." + pin + ".intent.json", plan)
        number = plan["loop"]["number"]
        loopfd, state, info = self.loop(number)
        imagefd = self.leaf(self.image, os.O_RDWR)
        if info != plan["loop"]["metadata"] or state != plan["loop"]["state"] or (
            self.image_state(imagefd) != plan["superblock"]
        ):
            raise ValueError("recovery_subject_drift")
        if operation == "remount" and not plan["mounted"]:
            targetfd = self.leaf(self.stage, os.O_RDONLY | os.O_DIRECTORY)
            self.mount(loopfd, imagefd, targetfd, number, attach=state is None)
        elif operation == "detach":
            if plan["mounted"]:
                targetfd = self.leaf(self.stage, os.O_RDONLY | os.O_DIRECTORY)
                self.guard()
                if identity(os.fstat(targetfd)) != plan["stage_identity"] or (
                    identity(os.lstat(self.named(self.stage))) != plan["stage_identity"]
                    or not self.mounted(number)
                ):
                    raise ValueError("recovery_mounted_stage_drift")
                # An open directory on this filesystem would itself prevent a
                # normal unmount. Use the held parent and revalidated fixed name.
                self.release(targetfd)
                libc = ctypes.CDLL(None, use_errno=True)
                libc.umount2.argtypes = [ctypes.c_char_p, ctypes.c_int]
                libc.umount2.restype = ctypes.c_int
                if libc.umount2(self.named(self.stage).encode("ascii"), 0):
                    raise OSError(ctypes.get_errno(), "normal_unmount_failed_no_force")
            if self.mounted(number):
                raise ValueError("stage_still_mounted")
            current = self.loop_status(loopfd)
            if current is not None:
                self.guard()
                if not self.association(current, imagefd):
                    raise ValueError("recovery_loop_subject")
                fcntl.ioctl(loopfd, LOOP_CLR_FD, 0)
                if self.loop_status(loopfd) is not None:
                    raise ValueError("loop_still_associated")
            self.image_state(imagefd, require_clean=True)
        self.guard()
        self.exclusive(BACKING + "/" + self.domain + "." + pin + ".done.json",
                       dict(status="STORAGE_RECOVERY_COMPLETED", plan_sha256=pin,
                            image_and_contents_preserved=True, operation=operation))
        return dict(status="STORAGE_RECOVERY_REQUIRES_ORDINARY_USER_POSTCHECK",
                    operation=operation, execution_authorized=False,
                    new_simulations=0, new_reserved_bytes=0)


def main():
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in (
        "plan", "apply", "remount-plan", "detach-plan", "recover"
    ):
        raise ValueError("closed_admin_operation")
    if CONFIG_JSON is None:
        raise ValueError("exported_fixed_configuration_required")
    config = valid_config(json.loads(CONFIG_JSON.decode("ascii")))
    admin = StorageAdmin(config)
    previous = {}
    def cancelled(signum, frame):
        admin.cancelled = True
    try:
        for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, cancelled)
        admin.enter()
        if sys.argv[1].endswith("plan"):
            if len(sys.argv) != 2:
                raise ValueError("plan_has_no_approval_arguments")
            plan = (admin.plan() if sys.argv[1] == "plan"
                    else admin.recovery_plan(sys.argv[1].split("-")[0]))
            result = dict(plan=plan, plan_sha256=digest(canonical(plan)))
        else:
            if len(sys.argv) != 3 or not re.match(r"^[0-9a-f]{64}$", sys.argv[2]):
                raise ValueError("exact_human_approved_plan_required")
            raw = getattr(sys.stdin, "buffer", sys.stdin).read(INPUT_BOUND + 1)
            if len(raw) > INPUT_BOUND or digest(raw) != sys.argv[2]:
                raise ValueError("approved_plan_digest")
            plan = json.loads(raw.decode("ascii"))
            if canonical(plan) != raw:
                raise ValueError("canonical_approved_plan_required")
            result = admin.apply(plan) if sys.argv[1] == "apply" else admin.recover(plan)
        sys.stdout.write(canonical(result).decode("ascii") + "\n")
    finally:
        admin.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
