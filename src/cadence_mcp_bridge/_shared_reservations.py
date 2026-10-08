"""Internal existing-ledger transactions; no authority, dispatch or CLI.

The production provider must independently attest the OS operator, installation,
grant and job admission before calling reserve. This asset alone cannot authorize
execution. Windows locking is disposable-file test support, not native qualification.
"""

# mypy: ignore-errors
import hashlib
import json
import os
import re
import stat
import time

try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)

try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)

LEDGER = "sim-mcp-v2-jobs/counter.json"
JOBS = "native-mcp-v1-jobs"
CEILING_COUNT = 500
CEILING_BYTES = 10737418240
LIMIT = 8192
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
BINDING = (
    "root_sha256",
    "resource_domain_sha256",
    "ledger_ref",
    "grant_sha256",
    "runner_sha256",
    "plan_sha256",
    "execution_input_sha256",
    "expires_at",
    "max_attempts",
    "max_reserved_bytes",
    "reserve_bytes",
    "disk_floor_bytes",
)
GRANT_FIELDS = tuple(
    x for x in BINDING if x not in ("plan_sha256", "execution_input_sha256", "reserve_bytes")
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(data):
    return hashlib.sha256(data).hexdigest()


def matches(pattern, value):
    match = pattern.match(value) if isinstance(value, STRING_TYPES) else None
    return match is not None and match.end() == len(value)


def check_binding(root, value):
    if not isinstance(value, dict) or set(value) != set(BINDING):
        raise ValueError("reservation_binding_shape")
    for key in BINDING[:7]:
        if key != "ledger_ref" and not matches(HASH, value[key]):
            raise ValueError("reservation_binding_hash")
    if value["ledger_ref"] != LEDGER or value["root_sha256"] != digest(root.encode("utf-8")):
        raise ValueError("reservation_domain_binding")
    for key in BINDING[7:]:
        if type(value[key]) not in INTEGER_TYPES:
            raise ValueError("reservation_binding_integer")
    if not (
        0 < value["expires_at"] < 4102444800
        and 1 <= value["max_attempts"] <= 500
        and 1 <= value["reserve_bytes"] <= value["max_reserved_bytes"] <= CEILING_BYTES
        and 0 <= value["disk_floor_bytes"] <= CEILING_BYTES
    ):
        raise ValueError("reservation_binding_bounds")


def identity(info):
    return info.st_dev, info.st_ino


def safe(path, directory=False):
    info = os.lstat(path)
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not kind
        or os.path.realpath(path) != os.path.abspath(path)
        or getattr(info, "st_file_attributes", 0) & 1024
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError("reservation_unsafe_path")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 18):
        raise ValueError("reservation_unsafe_owner_or_mode")
    return info


def read(path):
    before = safe(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    stream = os.fdopen(fd, "rb")
    try:
        if identity(os.fstat(fd)) != identity(before):
            raise ValueError("reservation_open_drift")
        raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT or identity(safe(path)) != identity(before):
            raise ValueError("reservation_file_drift")
        value = json.loads(raw.decode("ascii"))
        # Python2.6 lacks object_pairs_hook. Two exact legacy/new serializations
        # reject duplicate keys and undocumented representations. Field validators
        # independently reject nonfinite or coerced counter/binding values.
        if raw not in (canonical(value), json.dumps(value, sort_keys=True).encode("ascii")):
            raise ValueError("reservation_noncanonical")
        return value
    finally:
        stream.close()


def sync_directory(path):
    if os.name == "nt":
        return  # Windows tests cannot establish POSIX directory durability.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, value):
    safe(os.path.dirname(path), True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)
    stream = os.fdopen(fd, "wb")
    try:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(fd)
    finally:
        stream.close()
    sync_directory(os.path.dirname(path))


def shape(value, minimum_count, minimum_bytes):
    if (
        not isinstance(value, dict)
        or set(value) != set(("campaign_id", "count", "result_reserved_bytes"))
        or value["campaign_id"] != "AUTO-PHASE-01"
        or type(value["count"]) not in INTEGER_TYPES
        or type(value["result_reserved_bytes"]) not in INTEGER_TYPES
        or not minimum_count <= value["count"] <= CEILING_COUNT
        or not minimum_bytes <= value["result_reserved_bytes"] <= CEILING_BYTES
    ):
        raise ValueError("reservation_counter_integrity")


def counter_shape(value):
    # Current cumulative policy floor; never accept rollback to the old baseline.
    shape(value, 32, 3088056320)


def marker_shape(value):
    # Retained native-v1 jobs predate the current policy. Preserve their markers
    # starting at the first post-reservation22 /1,745,879,040 values. The
    # unincremented policy baseline is never a valid attempt-reserved marker.
    shape(value, 22, 1745879040)


def open_lock(root):
    safe(root, True)
    if os.name != "nt":
        parent = os.path.dirname(root)
        while True:
            info = os.lstat(parent)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in (0, os.getuid())
                or info.st_mode & 18
            ):
                raise ValueError("reservation_untrusted_ancestor")
            next_parent = os.path.dirname(parent)
            if next_parent == parent:
                break
            parent = next_parent
    for name in ("sim-mcp-v2-jobs", JOBS):
        safe(os.path.join(root, name), True)
    path = os.path.join(root, "run.lock")
    before = safe(path)
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        if identity(os.fstat(fd)) != identity(before):
            raise ValueError("reservation_lock_drift")
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if identity(safe(path)) != identity(before):
            raise ValueError("reservation_lock_drift")
        return fd
    except Exception:
        os.close(fd)
        raise


def paths(root, operation_id):
    if not matches(ID, operation_id):
        raise ValueError("reservation_operation_id")
    record = os.path.join(root, JOBS, operation_id)
    safe(record, True)
    work = os.path.join(record, "work")
    safe(work, True)
    return work


def transaction(work, root, operation_id, counter):
    intent_path = os.path.join(work, "reservation-intent.json")
    receipt_path = os.path.join(work, "reservation-receipt.json")
    has_intent, has_receipt = os.path.lexists(intent_path), os.path.lexists(receipt_path)
    if not has_intent:
        if has_receipt:
            raise ValueError("reservation_receipt_without_intent")
        return None
    intent = read(intent_path)
    if (
        not isinstance(intent, dict)
        or set(intent) != set(("schema_version", "operation_id", "binding", "before", "after"))
        or type(intent["schema_version"]) is not int
        or intent["schema_version"] != 1
        or intent["operation_id"] != operation_id
    ):
        raise ValueError("reservation_intent_identity")
    check_binding(root, intent["binding"])
    before, after = intent["before"], intent["after"]
    counter_shape(before)
    counter_shape(after)
    if (
        after["count"] != before["count"] + 1
        or after["result_reserved_bytes"]
        != before["result_reserved_bytes"] + intent["binding"]["reserve_bytes"]
    ):
        raise ValueError("reservation_intent_delta")
    marker = read(os.path.join(work, "attempt-reserved"))
    if marker != after:
        raise ValueError("reservation_marker_binding")
    if (
        after["count"] > counter["count"]
        or after["result_reserved_bytes"] > counter["result_reserved_bytes"]
    ):
        raise ValueError("reservation_unreconciled_counter")
    receipt = None
    if has_receipt:
        receipt = read(receipt_path)
        if canonical(receipt) != canonical(receipt_for(intent)):
            raise ValueError("reservation_receipt_binding")
    return intent, receipt


def receipt_for(intent):
    return {
        "schema_version": 1,
        "operation_id": intent["operation_id"],
        "intent_sha256": digest(canonical(intent)),
        "after": intent["after"],
        "status": "RESERVATION_COMMITTED_NOT_DISPATCHED",
    }


def audit(root, counter):
    records = []
    jobs = os.path.join(root, JOBS)
    names = os.listdir(jobs)
    if len(names) > 2048:
        raise ValueError("reservation_inventory_limit")
    for name in names:
        if name in ("control.lock", "active"):
            safe(os.path.join(jobs, name))
            continue
        if not matches(ID, name):
            raise ValueError("reservation_inventory_identity")
        record = os.path.join(jobs, name)
        safe(record, True)
        work = os.path.join(record, "work")
        if not os.path.lexists(work):
            continue  # Existing admitted legacy job may not have reached netlisting.
        safe(work, True)
        marker = os.path.join(work, "attempt-reserved")
        if os.path.lexists(marker):
            value = read(marker)
            marker_shape(value)
            if (
                value["count"] > counter["count"]
                or value["result_reserved_bytes"] > counter["result_reserved_bytes"]
            ):
                raise ValueError("reservation_legacy_unreconciled")
        item = transaction(work, root, name, counter)
        if item is not None:
            records.append(item)
    counts = [item[0]["after"]["count"] for item in records]
    if len(set(counts)) != len(counts):
        raise ValueError("reservation_duplicate_counter_slot")
    return records


def state(root):
    counter_path = os.path.join(root, LEDGER)
    if os.path.lexists(counter_path + ".ade-tmp"):
        raise ValueError("reservation_ambiguous_barrier")
    counter = read(counter_path)
    counter_shape(counter)
    return counter, audit(root, counter)


def lookup(root, operation_id, binding):
    """Read-only, also after grant expiry. Never repairs, charges or dispatches."""
    root = os.path.abspath(root)
    check_binding(root, binding)
    fd = open_lock(root)
    try:
        work = paths(root, operation_id)
        counter, records = state(root)
        item = transaction(work, root, operation_id, counter)
        if item is None:
            return None
        if item[0]["binding"] != binding:
            raise ValueError("reservation_replay_identity")
        return item[1] or {"status": "UNKNOWN_OUTCOME", "operation_id": operation_id}
    finally:
        os.close(fd)


def free_bytes(root):
    if os.name == "nt":
        import shutil

        return shutil.disk_usage(root).free
    info = os.statvfs(root)
    return info.f_bavail * info.f_frsize


def reserve(root, operation_id, binding):
    """Internal accounting only. Caller MUST already attest authority/admission."""
    root = os.path.abspath(root)
    check_binding(root, binding)
    fd = open_lock(root)
    try:
        work = paths(root, operation_id)
        counter, records = state(root)
        existing = transaction(work, root, operation_id, counter)
        if existing is not None:
            if existing[0]["binding"] != binding:
                raise ValueError("reservation_replay_identity")
            return existing[1] or {"status": "UNKNOWN_OUTCOME", "operation_id": operation_id}
        if any(item[1] is None for item in records):
            raise ValueError("reservation_unresolved_intent")
        if os.path.lexists(os.path.join(work, "attempt-reserved")):
            raise ValueError("reservation_legacy_replay")
        if os.path.lexists(os.path.join(root, JOBS, "active")):
            raise ValueError("reservation_active_legacy_job")
        if time.time() >= binding["expires_at"]:
            raise ValueError("reservation_grant_expired")
        used_count, used_bytes, inflight = 0, 0, 0
        for intent, receipt in records:
            old = intent["binding"]
            # No terminal-worker attestation exists yet. Treat every own reservation
            # as in-flight forever; later reviewed completion must retain receipts.
            inflight += old["reserve_bytes"]
            if old["grant_sha256"] == binding["grant_sha256"]:
                if any(old[key] != binding[key] for key in GRANT_FIELDS):
                    raise ValueError("reservation_grant_binding_drift")
                used_count += 1
                used_bytes += old["reserve_bytes"]
        amount = binding["reserve_bytes"]
        if (
            used_count + 1 > binding["max_attempts"]
            or used_bytes + amount > binding["max_reserved_bytes"]
        ):
            raise ValueError("reservation_grant_capacity")
        if (
            counter["count"] + 1 > CEILING_COUNT
            or counter["result_reserved_bytes"] + amount > CEILING_BYTES
        ):
            raise ValueError("reservation_cumulative_capacity")
        if free_bytes(root) < binding["disk_floor_bytes"] + inflight + amount:
            raise ValueError("reservation_physical_disk_floor")
        after = dict(counter)
        after["count"] += 1
        after["result_reserved_bytes"] += amount
        intent = {
            "schema_version": 1,
            "operation_id": operation_id,
            "binding": binding,
            "before": counter,
            "after": after,
        }
        counter_path = os.path.join(root, LEDGER)
        # Legacy adapter recognizes this same barrier. It must precede intent/
        # marker writes so a crash cannot be overtaken by legacy reservation.
        write_new(counter_path + ".ade-tmp", after)
        write_new(os.path.join(work, "reservation-intent.json"), intent)
        write_new(os.path.join(work, "attempt-reserved"), after)
        safe(counter_path)
        if os.name == "nt":
            os.replace(counter_path + ".ade-tmp", counter_path)
        else:
            os.rename(counter_path + ".ade-tmp", counter_path)
        sync_directory(os.path.dirname(counter_path))
        receipt = receipt_for(intent)
        write_new(os.path.join(work, "reservation-receipt.json"), receipt)
        return receipt
    finally:
        os.close(fd)
