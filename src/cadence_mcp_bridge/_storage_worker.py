"""Closed reference storage worker; compatible with guest Python 2.6.

Only inventory and exact selected leaf cleanup are dispatchable. No caller paths.
Operator registration/consent are separate canonical mode-600 records.
"""

from __future__ import with_statement

import binascii
import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time

ROOT = "/home/buet/cds_work/.cadence_mcp"
CONTROL = "storage-mgmt-v1"
SPOOL = "storage-disposable-v1"
GROUPS = (
    ("legacy", "jobs", "REPLAY_REQUIRED"),
    ("native", "native-mcp-v1-jobs", "REPLAY_REQUIRED"),
    ("diagnostic", "sim-mcp-v2-jobs", "EVIDENCE_REQUIRED"),
    ("pvt", "ade-pvt-qual-v1-jobs", "EVIDENCE_REQUIRED"),
    ("headroom", "bias-headroom-v1-jobs", "EVIDENCE_REQUIRED"),
    ("disposable", SPOOL, "PROTECTED_OR_UNKNOWN"),
)
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT = re.compile(r"^sa-[0-9a-f]{64}$")
MAX_ITEMS = 64
MAX_NODES = 8192
MAX_HASH_BYTES = 64 * 1024 * 1024
try:
    INTEGERS = (int, long)
    STRINGS = (basestring,)
except NameError:
    INTEGERS = (int,)
    STRINGS = (str,)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError("invalid closed contract")


class PosixIO(object):
    """Pin each parent by descriptor. Never follow a link or recursively delete."""

    def __init__(self):
        if not sys.platform.startswith("linux"):
            raise ValueError("safe platform unavailable")
        self.libc = ctypes.CDLL(None, use_errno=True)
        for name, args in (
            ("openat", [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint]),
            ("renameat", [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p]),
            ("unlinkat", [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]),
            ("mkdirat", [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]),
        ):
            fn = getattr(self.libc, name)
            fn.argtypes, fn.restype = args, ctypes.c_int
        for name, args, restype in (
            ("fdopendir", [ctypes.c_int], ctypes.c_void_p),
            ("readdir64", [ctypes.c_void_p], ctypes.c_void_p),
            ("closedir", [ctypes.c_void_p], ctypes.c_int),
        ):
            fn = getattr(self.libc, name)
            fn.argtypes, fn.restype = args, restype
        self.directory = getattr(os, "O_DIRECTORY", 0o200000)
        self.nofollow = getattr(os, "O_NOFOLLOW", 0o400000)

    def component(self, name):
        if not name or name in (".", "..") or "/" in name or "\x00" in name:
            raise ValueError("unsafe component")
        return name.encode("utf-8") if not isinstance(name, bytes) else name

    def checked(self, result):
        if result < 0:
            raise OSError(ctypes.get_errno(), "registered storage operation failed")
        return result

    def open(self, parent, name, directory=False, create=False):
        flags = os.O_RDONLY | os.O_NONBLOCK | self.nofollow
        if directory:
            flags |= self.directory
        if create:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | self.nofollow
        return self.checked(self.libc.openat(parent, self.component(name), flags, 0o600))

    def root(self, path):
        fd = os.open("/", os.O_RDONLY | self.directory)
        try:
            for part in path.split("/"):
                if part:
                    child = self.open(fd, part, directory=True)
                    os.close(fd)
                    fd = child
            return fd
        except Exception:
            os.close(fd)
            raise

    def account_home(self):
        import pwd

        return pwd.getpwuid(os.getuid()).pw_dir

    def canonical_root(self, fd):
        # Linux descriptor path is observed, never supplied by model input.
        path = os.readlink("/proc/self/fd/" + str(fd))
        if not path.startswith("/") or os.path.realpath(path) != path:
            raise ValueError("storage root identity unavailable")
        opened, named = os.fstat(fd), os.lstat(path)
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError("storage root identity drift")
        return path

    def names(self, fd):
        duplicate = self.checked(
            self.libc.openat(fd, b".", os.O_RDONLY | self.directory | self.nofollow, 0)
        )
        stream = self.libc.fdopendir(duplicate)
        if not stream:
            os.close(duplicate)
            raise OSError(ctypes.get_errno(), "directory stream unavailable")
        result = []
        try:
            while True:
                ctypes.set_errno(0)
                entry = self.libc.readdir64(stream)
                if not entry:
                    if ctypes.get_errno():
                        raise OSError(ctypes.get_errno(), "directory stream failed")
                    break
                # Linux dirent64 has d_reclen at byte 16 and d_name at byte 19,
                # independent of the 32/64-bit host C long size.
                length = ctypes.c_ushort.from_address(entry + 16).value
                if not 20 <= length <= 280:
                    raise ValueError("invalid directory record")
                name = ctypes.string_at(entry + 19, length - 19).split(b"\x00", 1)[0]
                if name in (b".", b".."):
                    continue
                if len(result) >= MAX_NODES:
                    raise ValueError("directory entry bound")
                result.append(name.decode("utf-8"))
            return sorted(result)
        finally:
            self.libc.closedir(stream)

    def mkdir(self, parent, name):
        self.checked(self.libc.mkdirat(parent, self.component(name), 0o700))

    def rename(self, parent, name, destination, leaf):
        self.checked(
            self.libc.renameat(parent, self.component(name), destination, self.component(leaf))
        )

    def unlink(self, parent, name):
        self.checked(self.libc.unlinkat(parent, self.component(name), 0))


def private_directory(io, parent, name):
    fd = io.open(parent, name, directory=True)
    s = os.fstat(fd)
    if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
        os.close(fd)
        raise ValueError("operator directory permissions")
    return fd


def metadata(fd):
    s = os.fstat(fd)
    return [
        s.st_dev,
        s.st_ino,
        s.st_mode,
        s.st_nlink,
        s.st_size,
        repr(s.st_mtime),
        repr(s.st_ctime),
    ]


def read_json(io, parent, name, limit, private=False):
    fd = io.open(parent, name)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size > limit or s.st_nlink != 1:
            raise ValueError("unsafe metadata record")
        if private and (s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600):
            raise ValueError("operator metadata permissions")
        raw = os.read(fd, limit + 1)
        if len(raw) > limit:
            raise ValueError("metadata bound")
        value = json.loads(raw.decode("ascii"))
        if private and raw.strip() != canonical(value):
            raise ValueError("canonical operator metadata required")
        return value
    finally:
        os.close(fd)


def write_json(io, parent, name, value):
    raw = canonical(value)
    if len(raw) > 32768:
        raise ValueError("audit bound")
    fd = io.open(parent, name, create=True)
    try:
        written = 0
        while written < len(raw):
            count = os.write(fd, raw[written:])
            if count <= 0:
                raise ValueError("partial audit write")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(parent)


def tree(io, parent, name, budget, depth=0):
    if depth > 16 or budget[0] >= MAX_NODES:
        raise ValueError("inventory traversal bound")
    fd = io.open(parent, name)
    try:
        info = metadata(fd)
        budget[0] += 1
        mode = info[2]
        s = os.fstat(fd)
        logical = s.st_size if stat.S_ISREG(mode) else 0
        allocated = getattr(s, "st_blocks", 0) * 512
        frames = [info]
        if stat.S_ISDIR(mode):
            for child in io.names(fd):
                size, blocks, frame = tree(io, fd, child, budget, depth + 1)
                logical += size
                allocated += blocks
                frames.append([hashlib.sha256(child.encode("utf-8")).hexdigest(), frame])
        elif not stat.S_ISREG(mode):
            raise ValueError("unsupported artifact object")
        return logical, allocated, digest(frames)
    finally:
        os.close(fd)


def payload_fingerprint(io, parent, hash_budget=None):
    fd = io.open(parent, "payload.bin")
    try:
        before = metadata(fd)
        if not stat.S_ISREG(before[2]) or before[3] != 1 or before[4] > MAX_HASH_BYTES:
            raise ValueError("unsafe disposable leaf")
        if hash_budget is not None:
            if hash_budget[0] + before[4] > MAX_HASH_BYTES:
                raise ValueError("inventory hash-work bound")
            hash_budget[0] += before[4]
        h = hashlib.sha256()
        count = 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            count += len(block)
            if count > MAX_HASH_BYTES:
                raise ValueError("payload hash bound")
            h.update(block)
        if before != metadata(fd) or count != before[4]:
            raise ValueError("payload changed during hash")
        return digest([before, h.hexdigest()]), before, h.hexdigest()
    finally:
        os.close(fd)


def active_eda(root):
    # Non-destructive inventory can still report active storage. Deletes hold run.lock.
    process = subprocess.Popen(
        ["ps", "-eo", "comm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True
    )
    out, errors = process.communicate()
    if process.returncode or errors or len(out) > 65536:
        return True
    if any(line.strip() in (b"spectre", b"ocean", b"virtuoso") for line in out.splitlines()):
        return True
    return any(
        os.path.lexists(root + "/" + relative + "/active")
        for group, relative, _retention in GROUPS
        if group != "disposable"
    )


def registration(io, root, name, fingerprint, content_hash):
    control = private_directory(io, root, CONTROL)
    records = private_directory(io, control, "registrations")
    try:
        value = read_json(io, records, name + ".json", 2048, private=True)
        exact(
            value,
            "contract_version artifact_uuid analysis_type measurement_extracted "
            "replay_dependency evidence_dependency active_dependency fingerprint content_sha256",
        )
        if (
            type(value["contract_version"]) is not int
            or value["contract_version"] != 1
            or value["artifact_uuid"] != name
            or value["analysis_type"] not in ("dc", "ac", "tran", "sweep")
            or value["measurement_extracted"] is not True
            or value["replay_dependency"] is not False
            or value["evidence_dependency"] is not False
            or value["active_dependency"] is not False
            or value["fingerprint"] != fingerprint
            or value["content_sha256"] != content_hash
        ):
            raise ValueError("disposable contract denied")
        return value
    finally:
        os.close(records)
        os.close(control)


def append_artifact(artifacts, aggregates, item):
    if item["storage_group_id"] == "disposable":
        artifacts.append(item)
        return
    # Historical job trees are protected groups, never individual delete targets.
    key = (item["storage_group_id"], item["analysis_type"], item["retention_class"])
    if key not in aggregates:
        value = dict(item)
        value.update(
            artifact_id="sa-" + digest(["protected-group-v1"] + list(key)),
            job_id=None,
            size_bytes=0,
            allocated_bytes=0,
            job_count=0,
        )
        aggregates[key] = (value, [])
    value, frames = aggregates[key]
    value["size_bytes"] += item["size_bytes"]
    value["allocated_bytes"] += item["allocated_bytes"]
    value["job_count"] += item["job_count"]
    frames.append([item["artifact_id"], item["fingerprint"]])


def fresh_ledger(io, root, counter):
    """Authenticate schema2 policy at the pinned root and audit conserved slots.

    This internal consumer assumes its caller holds the existing run.lock, like
    snapshot/cleanup. It never acquires another flock, reserves or repairs.
    Standalone generic bundles must hash-verify reservations.py before import.
    The historical standalone worker never loads it for a legacy counter.
    """
    try:
        registry = private_directory(io, root, "reservation-identity")
    except OSError as failure:
        if failure.errno == errno.ENOENT:
            return None  # Unmigrated historical installation only.
        raise
    try:
        anchor = read_json(io, registry, "manifest.json", 262144, private=True)
    finally:
        os.close(registry)
    if type(anchor) is not dict or type(anchor.get("schema_version")) is not int:
        raise ValueError("storage anchor schema required")
    if anchor["schema_version"] == 1:
        return None  # Retained migration policy uses the historical counter.
    if anchor["schema_version"] != 2:
        raise ValueError("fresh storage anchor required")
    path = io.canonical_root(root)
    home = io.root(io.account_home())
    try:
        domain = private_directory(io, home, ".cadence_mcp-domain")
        try:
            index = read_json(io, domain, "manifest.json", 8192, private=True)
        finally:
            os.close(domain)
    finally:
        os.close(home)
    exact(index, "schema_version root resource_domain_sha256 identity_manifest_sha256 plan_sha256")
    if (
        type(index["schema_version"]) is not int or index["schema_version"] != 1
        or index["root"] != path
        or index["resource_domain_sha256"] != anchor.get("resource_domain_sha256")
        or index["identity_manifest_sha256"] != digest(anchor)
        or any(
            not isinstance(index[k], STRINGS) or not DIGEST.match(index[k])
            for k in ("resource_domain_sha256", "identity_manifest_sha256", "plan_sha256")
        )
    ):
        raise ValueError("fresh storage registered domain drift")
    if __package__:
        from cadence_mcp_bridge import _shared_reservations as accounting
    else:
        # A legacy standalone deployment cannot grow generic capability by
        # importing code from CWD/PYTHONPATH. Only an immutable schema3 runtime
        # may supply the two hash-bound fixed assets at its private location.
        directory = os.path.dirname(os.path.abspath(__file__))
        if os.path.realpath(directory) != directory or os.path.basename(__file__) != "storage.py":
            raise ValueError("fresh storage fixed asset location")
        ancestor = directory
        while True:
            info = os.lstat(ancestor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, os.getuid()) or info.st_mode & 18
            ):
                raise ValueError("fresh storage asset ancestor trust")
            parent = os.path.dirname(ancestor)
            if parent == ancestor:
                break
            ancestor = parent
        source = io.root(directory)
        try:
            manifest = read_json(io, source, "manifest.json", 262144, private=True)
            if (
                type(manifest) is not dict or type(manifest.get("schema_version")) is not int
                or manifest["schema_version"] != 3
                or digest(manifest) != os.path.basename(directory)
            ):
                raise ValueError("fresh storage fixed asset manifest")
            for name in ("storage.py", "reservations.py"):
                fd = io.open(source, name)
                try:
                    info = os.fstat(fd)
                    if (
                        not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.getuid() or info.st_mode & 18 or info.st_size > 262144
                    ):
                        raise ValueError("fresh storage fixed asset trust")
                    raw = os.read(fd, 262145)
                    if manifest["files"][name] != {
                        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                    }:
                        raise ValueError("fresh storage fixed asset drift")
                finally:
                    os.close(fd)
        finally:
            os.close(source)
        import imp

        accounting = imp.load_source("fixed_storage_accounting", directory + "/reservations.py")
    binding = {
        "root_sha256": hashlib.sha256(path.encode("utf-8")).hexdigest(),
        "resource_domain_sha256": anchor.get("resource_domain_sha256"),
        "ledger_ref": "sim-mcp-v2-jobs/counter.json",
        "identity_manifest_sha256": digest(anchor),
    }
    accounting.identity_manifest(path, binding)
    audited, records = accounting.state(path, binding)
    if canonical(counter) != canonical(audited):
        raise ValueError("storage ledger changed during observation")
    return anchor["policy"]


def snapshot(io, root, is_active):
    artifacts, coverage = [], {}
    reasons = {}
    aggregates = {}
    complete = True
    scanned = 0
    hash_budget = [0]
    for group, relative, retention in GROUPS:
        budget = [0]
        try:
            parent = io.open(root, relative, directory=True)
        except OSError as exc:
            coverage[group] = "MISSING" if exc.errno == errno.ENOENT else "BLOCKED"
            reasons[group] = "missing" if exc.errno == errno.ENOENT else "io_unavailable"
            if exc.errno != errno.ENOENT:
                complete = False
            continue
        try:
            coverage[group] = "SCANNED"
            reasons[group] = "none"
            for name in io.names(parent):
                if budget[0] >= MAX_NODES or (
                    group == "disposable" and len(artifacts) + len(aggregates) >= MAX_ITEMS
                ):
                    coverage[group], complete = "PARTIAL", False
                    reasons[group] = "scan_limit" if budget[0] >= MAX_NODES else "artifact_limit"
                    break
                identity = "sa-" + digest([group, name])
                disposition = retention
                analysis, extracted = "unknown", None
                replay, evidence = retention == "REPLAY_REQUIRED", retention == "EVIDENCE_REQUIRED"
                fingerprint = None
                size, blocks = 0, 0
                try:
                    size, blocks, fingerprint = tree(io, parent, name, budget)
                    if group == "disposable" and UUID.match(name):
                        leaf = io.open(parent, name, directory=True)
                        try:
                            if io.names(leaf) != ["payload.bin"]:
                                raise ValueError("unregistered disposable children")
                            fingerprint, info, content_hash = payload_fingerprint(
                                io, leaf, hash_budget
                            )
                            record = registration(io, root, name, fingerprint, content_hash)
                            analysis, extracted = record["analysis_type"], True
                            disposition = "DELETE_CANDIDATE"
                        finally:
                            os.close(leaf)
                    elif group in ("native", "diagnostic", "pvt", "headroom") and UUID.match(name):
                        leaf = io.open(parent, name, directory=True)
                        try:
                            request = read_json(io, leaf, "request.json", 2048)
                            if request.get("analysis") in ("dc", "ac", "tran"):
                                analysis = request["analysis"]
                        finally:
                            os.close(leaf)
                    elif group == "legacy" and UUID.match(name):
                        leaf = io.open(parent, name, directory=True)
                        try:
                            state = read_json(io, leaf, "status.json", 4096).get("state")
                            if state not in ("succeeded", "failed", "cancelled"):
                                disposition = (
                                    "ACTIVE"
                                    if state
                                    in (
                                        "running",
                                        "queued",
                                        "extracting",
                                        "cancelling",
                                        "recovering",
                                    )
                                    else "PROTECTED_OR_UNKNOWN"
                                )
                        finally:
                            os.close(leaf)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    disposition = "PROTECTED_OR_UNKNOWN"
                    # Incomplete traversal cannot yield a trustworthy aggregate/candidate.
                    if fingerprint is None:
                        coverage[group], complete = "PARTIAL", False
                        reasons[group] = (
                            "scan_limit"
                            if str(exc) == "inventory traversal bound"
                            else "unsafe_or_unavailable_object"
                        )
                        fingerprint = digest([group, name, "uninspected"])
                if is_active:
                    disposition = "ACTIVE"
                reason = {
                    "ACTIVE": "active_or_unresolved",
                    "REPLAY_REQUIRED": "replay_required",
                    "EVIDENCE_REQUIRED": "evidence_required",
                    "PROTECTED_OR_UNKNOWN": "dependency_unknown",
                    "DELETE_CANDIDATE": "reviewed_disposable_intermediate",
                }[disposition]
                append_artifact(
                    artifacts,
                    aggregates,
                    dict(
                        artifact_id=identity,
                        storage_group_id=group,
                        artifact_type="registered_intermediate"
                        if group == "disposable"
                        else "job_group",
                        job_id=name if group != "disposable" and UUID.match(name) else None,
                        job_count=1 if group != "disposable" and UUID.match(name) else 0,
                        analysis_type=analysis,
                        design_id=None,
                        created_at=None,
                        last_used_at=None,
                        size_bytes=size,
                        allocated_bytes=blocks,
                        retention_class=disposition,
                        replay_dependency=replay,
                        evidence_dependency=evidence,
                        active_dependency=is_active or disposition == "ACTIVE",
                        measurement_extracted=extracted,
                        deletion_status="ELIGIBLE"
                        if disposition == "DELETE_CANDIDATE"
                        else "PROTECTED_OR_UNKNOWN",
                        deletion_reason=reason,
                        fingerprint=fingerprint,
                        provenance="registered_metadata_snapshot_v1",
                    ),
                )
        except (OSError, ValueError):
            coverage[group], complete = "PARTIAL", False
            reasons[group] = "directory_unavailable_or_bounded"
        finally:
            os.close(parent)
            scanned += budget[0]
    for key in sorted(aggregates):
        item, frames = aggregates[key]
        item["fingerprint"] = digest(frames)
        artifacts.append(item)
    if len(artifacts) > MAX_ITEMS:
        raise ValueError("storage group response bound")
    counter_root = io.open(root, "sim-mcp-v2-jobs", directory=True)
    try:
        counter = read_json(io, counter_root, "counter.json", 2048)
    finally:
        os.close(counter_root)
    exact(counter, "campaign_id count result_reserved_bytes")
    policy = fresh_ledger(io, root, counter)
    if policy is None:
        if (
            counter["campaign_id"] != "AUTO-PHASE-01"
            or type(counter["count"]) not in INTEGERS
            or not 62 <= counter["count"] <= 500
            or type(counter["result_reserved_bytes"]) not in INTEGERS
            or not 7114588160 <= counter["result_reserved_bytes"] <= 10737418240
        ):
            raise ValueError("invalid cumulative ledger")
    disk = os.fstatvfs(root)
    is_active = is_active or any(a["active_dependency"] for a in artifacts)
    value = dict(
        contract_version=2 if policy else 1,
        artifacts=sorted(artifacts, key=lambda a: a["artifact_id"]),
        coverage_complete=complete,
        group_coverage=coverage,
        group_coverage_reason=reasons,
        scan_nodes=scanned,
        excluded_scope="source_ADE_PDK_vendor_local_state_and_unregistered_roots",
        filesystem_free_bytes=disk.f_bavail * disk.f_frsize,
        filesystem_total_bytes=disk.f_blocks * disk.f_frsize,
        reserved_result_bytes=counter["result_reserved_bytes"],
        result_ceiling_bytes=policy["result_ceiling_bytes"] if policy else 10737418240,
        spectre_attempts=counter["count"],
        active_eda=is_active,
        platform_delete_primitives=True,
    )
    if policy is not None:
        value["ledger_policy"] = policy
    bound = dict(value)
    del bound["filesystem_free_bytes"]
    del bound["filesystem_total_bytes"]
    value["snapshot_id"] = digest(bound)
    return value


def plan(s, selection):
    exact(selection, "snapshot_id artifact_ids")
    ids = selection["artifact_ids"]
    if (
        type(ids) is not list
        or not 1 <= len(ids) <= 16
        or len(set(ids)) != len(ids)
        or any(not isinstance(i, STRINGS) or not ARTIFACT.match(i) for i in ids)
        or selection["snapshot_id"] != s["snapshot_id"]
    ):
        raise ValueError("stale or malformed selection")
    artifacts = dict((a["artifact_id"], a) for a in s["artifacts"])
    if any(i not in artifacts for i in ids):
        raise ValueError("unknown registered artifact")
    ids = sorted(ids)
    eligible = [
        i for i in ids if s["coverage_complete"] and artifacts[i]["deletion_status"] == "ELIGIBLE"
    ]
    excluded = [i for i in ids if i not in eligible]
    warnings = ["user_selection_required"]
    if not s["coverage_complete"]:
        warnings.append("partial_inventory")
    if excluded:
        warnings.append("selected_items_protected")
    value = dict(
        contract_version=1,
        snapshot_id=s["snapshot_id"],
        selected_artifact_ids=ids,
        eligible_artifact_ids=eligible,
        protected_exclusions=excluded,
        estimated_reclaim_bytes=sum(artifacts[i]["size_bytes"] for i in eligible),
        fingerprints=dict((i, artifacts[i]["fingerprint"]) for i in ids),
        replay_impact="none_permitted",
        evidence_impact="none_permitted",
        warnings=warnings,
        deleted=False,
    )
    sha = digest(value)
    value.update(cleanup_plan_id="sc-" + sha, plan_sha256=sha)
    return value


def validate_cleanup(request):
    exact(
        request, "selection cleanup_plan_id plan_sha256 selected_artifact_ids operation_id dry_run"
    )
    if (
        not isinstance(request["operation_id"], STRINGS)
        or not UUID.match(request["operation_id"])
        or type(request["dry_run"]) is not bool
        or not isinstance(request["plan_sha256"], STRINGS)
        or not DIGEST.match(request["plan_sha256"])
        or request["cleanup_plan_id"] != "sc-" + request["plan_sha256"]
    ):
        raise ValueError("invalid cleanup identity")
    exact(request["selection"], "snapshot_id artifact_ids")
    selected = request["selected_artifact_ids"]
    if (
        type(selected) is not list
        or not 1 <= len(selected) <= 16
        or any(not isinstance(i, STRINGS) or not ARTIFACT.match(i) for i in selected)
        or len(set(selected)) != len(selected)
        or not set(selected).issubset(request["selection"]["artifact_ids"])
    ):
        raise ValueError("invalid selected artifact identity")


def outcome(
    request, state, removed, blocked, expected, logical=0, allocated=0, delta=0, audit=False
):
    return dict(
        operation_id=request["operation_id"],
        cleanup_plan_id=request["cleanup_plan_id"],
        state=state,
        selected_artifact_ids=request["selected_artifact_ids"],
        removed_artifact_ids=removed,
        blocked_artifact_ids=blocked,
        expected_bytes=expected,
        removed_logical_bytes=logical,
        filesystem_free_delta_bytes=delta,
        unlinked_allocated_bytes=allocated,
        actual_reclaimed_bytes=None,
        reclaim_semantics="physical_reclaim_not_attributed_free_delta_reported",
        audit_recorded=audit,
        reservation_refunded_bytes=0,
    )


def remove_leaf(io, root, quarantine, artifact, internal):
    spool = private_directory(io, root, SPOOL)
    leaf = private_directory(io, spool, internal)
    try:
        fingerprint, info, content_hash = payload_fingerprint(io, leaf)
        registration(io, root, internal, fingerprint, content_hash)
        if fingerprint != artifact["fingerprint"]:
            raise ValueError("selected artifact changed")
        # Atomic move first. A substituted leaf is preserved in quarantine, not deleted.
        io.rename(leaf, "payload.bin", quarantine, internal)
        os.fsync(leaf)
        os.fsync(quarantine)
        moved = io.open(quarantine, internal)
        try:
            changed = metadata(moved)
            # rename changes ctime, not device/inode/mode/nlink/size/mtime.
            if changed[:6] != info[:6]:
                raise ValueError("quarantined identity mismatch")
            h = hashlib.sha256()
            count = 0
            while True:
                block = os.read(moved, 65536)
                if not block:
                    break
                count += len(block)
                if count > MAX_HASH_BYTES:
                    raise ValueError("quarantine bound")
                h.update(block)
            if count != info[4] or h.hexdigest() != content_hash or changed != metadata(moved):
                raise ValueError("quarantined content mismatch")
            allocated = getattr(os.fstat(moved), "st_blocks", 0) * 512
            io.unlink(quarantine, internal)
        finally:
            os.close(moved)
        os.fsync(quarantine)
        if internal in io.names(quarantine) or "payload.bin" in io.names(leaf):
            raise ValueError("deletion verification uncertain")
        return info[4], allocated
    finally:
        os.close(leaf)
        os.close(spool)


def cleanup(io, root, request, is_active):
    validate_cleanup(request)
    control = private_directory(io, root, CONTROL)
    operations = private_directory(io, control, "operations")
    approvals = private_directory(io, control, "approvals")
    signature = digest(request)
    operation = request["operation_id"]
    try:
        if not request["dry_run"] and operation in io.names(operations):
            record = private_directory(io, operations, operation)
            try:
                intent = read_json(io, record, "intent.json", 8192, private=True)
                if intent["request_sha256"] != signature:
                    raise ValueError("operation identity substitution")
                if "result.json" in io.names(record):
                    return read_json(io, record, "result.json", 8192, private=True)
                return outcome(
                    request,
                    "UNKNOWN",
                    [],
                    request["selected_artifact_ids"],
                    intent["expected_bytes"],
                    audit=True,
                )
            finally:
                os.close(record)
        s = snapshot(io, root, is_active)
        p = plan(s, request["selection"])
        if p["plan_sha256"] != request["plan_sha256"]:
            raise ValueError("cleanup plan changed")
        chosen = request["selected_artifact_ids"]
        eligible = p["eligible_artifact_ids"]
        blocked = [i for i in chosen if i not in eligible]
        artifacts = dict((a["artifact_id"], a) for a in s["artifacts"])
        expected = sum(artifacts[i]["size_bytes"] for i in chosen if i in eligible)
        if request["dry_run"]:
            return outcome(request, "DRY_RUN", [], blocked, expected)
        if blocked or s["active_eda"] or not s["coverage_complete"]:
            return outcome(request, "DENIED", [], chosen, expected)
        try:
            approval = read_json(io, approvals, operation + ".json", 8192, private=True)
            exact(
                approval,
                "contract_version request_sha256 selected_artifact_ids plan_sha256 user_selection",
            )
            if (
                type(approval["contract_version"]) is not int
                or approval["contract_version"] != 1
                or approval["request_sha256"] != signature
                or approval["plan_sha256"] != p["plan_sha256"]
                or approval["selected_artifact_ids"] != chosen
                or approval["user_selection"] != "explicit-selected-items"
            ):
                raise ValueError("exact selection consent required")
        except (OSError, ValueError, KeyError):
            return outcome(request, "DENIED", [], chosen, expected)
        io.mkdir(operations, operation)
        record = private_directory(io, operations, operation)
        try:
            write_json(
                io,
                record,
                "intent.json",
                dict(
                    request_sha256=signature,
                    operation_id=operation,
                    plan_sha256=p["plan_sha256"],
                    selected_artifact_ids=chosen,
                    expected_bytes=expected,
                    at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    pre_delete_classification=dict(
                        (i, artifacts[i]["retention_class"]) for i in chosen
                    ),
                ),
            )
            io.mkdir(record, "quarantine")
            quarantine = private_directory(io, record, "quarantine")
            removed, logical, allocated = [], 0, 0
            uncertain = False
            try:
                before = os.fstatvfs(root).f_bavail * os.fstatvfs(root).f_frsize
                for item in chosen:
                    try:
                        spool = private_directory(io, root, SPOOL)
                        try:
                            internal = next(
                                name
                                for name in io.names(spool)
                                if "sa-" + digest(["disposable", name]) == item
                            )
                        finally:
                            os.close(spool)
                        size, blocks = remove_leaf(io, root, quarantine, artifacts[item], internal)
                        logical += size
                        allocated += blocks
                        removed.append(item)
                        write_json(
                            io,
                            record,
                            item + ".json",
                            dict(
                                artifact_id=item,
                                removed_logical_bytes=size,
                                unlinked_allocated_bytes=blocks,
                                verified=True,
                            ),
                        )
                    except (OSError, ValueError, StopIteration):
                        uncertain = True
                        break
                after = os.fstatvfs(root).f_bavail * os.fstatvfs(root).f_frsize
                result = outcome(
                    request,
                    "PARTIAL" if uncertain and removed else "UNKNOWN" if uncertain else "COMPLETE",
                    removed,
                    [i for i in chosen if i not in removed],
                    expected,
                    logical,
                    allocated,
                    after - before,
                    audit=True,
                )
                write_json(io, record, "result.json", result)
                return result
            finally:
                os.close(quarantine)
        finally:
            os.close(record)
    finally:
        os.close(approvals)
        os.close(operations)
        os.close(control)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("inventory", "cleanup"):
        raise ValueError("unsupported storage action")
    encoded = sys.argv[2]
    if not re.match(r"^[0-9a-f]{2,16384}$", encoded) or len(encoded) % 2:
        raise ValueError("bounded encoded request required")
    request = json.loads(binascii.unhexlify(encoded).decode("ascii"))
    if sys.argv[1] == "inventory":
        exact(request, "")
    else:
        validate_cleanup(request)
    io = PosixIO()
    root = io.root(ROOT)
    try:
        import fcntl

        # Existing run.lock serializes EDA and cleanup; inventory is nonblocking too.
        lock = io.open(root, "run.lock")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            if sys.argv[1] == "cleanup":
                raise ValueError("active EDA lock")
            value = snapshot(io, root, True)
        else:
            active = active_eda(ROOT)
            if sys.argv[1] == "inventory":
                exact(request, "")
                value = snapshot(io, root, active)
            else:
                value = cleanup(io, root, request, active)
        finally:
            os.close(lock)
        raw = canonical(value)
        if len(raw) > 65536:
            raise ValueError("storage response bound")
        sys.stdout.write(raw.decode("ascii") + "\n")
    finally:
        os.close(root)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("storage request denied or state unavailable\n")
        sys.exit(69)
