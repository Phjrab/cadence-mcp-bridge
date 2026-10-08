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
LEDGER_REF = "shared-ledger"  # Public logical reference; never a caller-selected file.
JOBS = "native-mcp-v1-jobs"
REGISTRY = "reservation-identity"
CEILING_COUNT = 500
CEILING_BYTES = 10737418240
LEGACY_BASE_COUNT = 21
LEGACY_BASE_BYTES = 1611661312
LEGACY_RESERVATION = 134217728
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
    "identity_manifest_sha256",
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
    for key in BINDING[:8]:
        if key != "ledger_ref" and not matches(HASH, value[key]):
            raise ValueError("reservation_binding_hash")
    if value["ledger_ref"] != LEDGER or value["root_sha256"] != digest(root.encode("utf-8")):
        raise ValueError("reservation_domain_binding")
    for key in BINDING[8:]:
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


def fresh_shape(value, manifest, marker=False):
    policy = manifest["policy"]
    if (
        not isinstance(value, dict)
        or set(value) != set(("campaign_id", "count", "result_reserved_bytes"))
        or value["campaign_id"] != policy["campaign_id"]
        or type(value["count"]) not in INTEGER_TYPES
        or type(value["result_reserved_bytes"]) not in INTEGER_TYPES
        or not (1 if marker else 0) <= value["count"] <= policy["attempt_ceiling"]
        or not (1 if marker else 0)
        <= value["result_reserved_bytes"]
        <= policy["result_ceiling_bytes"]
    ):
        raise ValueError("reservation_fresh_counter_integrity")


def counter_shape(value, manifest=None):
    if manifest is not None and manifest["schema_version"] == 2:
        return fresh_shape(value, manifest)
    # Current cumulative policy floor; never accept rollback to the old baseline.
    shape(value, 32, 3088056320)


def marker_shape(value, manifest=None):
    if manifest is not None and manifest["schema_version"] == 2:
        return fresh_shape(value, manifest, True)
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
    for name in ("sim-mcp-v2-jobs", JOBS, REGISTRY):
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


def transaction(work, root, operation_id, counter, manifest=None):
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
    counter_shape(before, manifest)
    counter_shape(after, manifest)
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


def identity_manifest(root, binding):
    # Operator-provisioned immutable migration anchor, never created by this asset.
    value = read(os.path.join(root, REGISTRY, "manifest.json"))
    seal_path = os.path.join(root, REGISTRY, "legacy-seal.json")
    if os.path.lexists(seal_path):
        seal = read(seal_path)
        if (
            not isinstance(seal, dict)
            or set(seal) != set(("schema_version", "prior_anchor_sha256", "anchor", "plan_sha256"))
            or type(seal["schema_version"]) is not int
            or seal["schema_version"] != 1
            or not matches(HASH, seal["plan_sha256"])
            or seal["prior_anchor_sha256"] != digest(canonical(value))
            or not isinstance(seal["anchor"], dict)
            or value.get("legacy_operation_ids") != []
            or dict(seal["anchor"], legacy_operation_ids=[]) != value
        ):
            raise ValueError("reservation_legacy_classification_seal")
        value = seal["anchor"]
    if (
        not isinstance(value, dict)
        or set(value)
        != set(
            (
                "schema_version",
                "root_sha256",
                "resource_domain_sha256",
                "ledger_ref",
                "baseline",
                "legacy_operation_ids",
            )
        )
        | (set(("policy",)) if value.get("schema_version") == 2 else set())
        or type(value["schema_version"]) is not int
        or value["schema_version"] not in (1, 2)
        or value["root_sha256"] != binding["root_sha256"]
        or value["resource_domain_sha256"] != binding["resource_domain_sha256"]
        or value["ledger_ref"] != LEDGER
        or digest(canonical(value)) != binding["identity_manifest_sha256"]
    ):
        raise ValueError("reservation_identity_manifest_binding")
    if value["schema_version"] == 2:
        policy = value["policy"]
        if (
            not isinstance(policy, dict)
            or set(policy) != set(("campaign_id", "attempt_ceiling", "result_ceiling_bytes"))
            or not isinstance(policy["campaign_id"], STRING_TYPES)
            or not matches(ID, policy["campaign_id"])
            or type(policy["attempt_ceiling"]) not in INTEGER_TYPES
            or type(policy["result_ceiling_bytes"]) not in INTEGER_TYPES
            or not 1 <= policy["attempt_ceiling"] <= CEILING_COUNT
            or not 1 <= policy["result_ceiling_bytes"] <= CEILING_BYTES
            or value["baseline"]
            != {"campaign_id": policy["campaign_id"], "count": 0, "result_reserved_bytes": 0}
            or value["legacy_operation_ids"] != []
        ):
            raise ValueError("reservation_fresh_policy_binding")
    counter_shape(value["baseline"], value)
    if value["baseline"]["result_reserved_bytes"] != expected_bytes(
        value["baseline"]["count"], [], value
    ):
        raise ValueError("reservation_migration_baseline")
    ids = value["legacy_operation_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 128
        or any(not matches(ID, op) for op in ids)
        or sorted(set(ids)) != ids
    ):
        raise ValueError("reservation_legacy_identity_allowlist")
    return value


def audit(root, counter, manifest, manifest_sha):

    records = []
    markers = []
    marker_ids = {}
    by_id = {}
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
            marker_shape(value, manifest)
            markers.append(value)
            marker_ids[name] = value
            if (
                value["count"] > counter["count"]
                or value["result_reserved_bytes"] > counter["result_reserved_bytes"]
            ):
                raise ValueError("reservation_legacy_unreconciled")
        item = transaction(work, root, name, counter, manifest)
        if item is not None:
            records.append(item)
            by_id[name] = item[0]
    registry = os.path.join(root, REGISTRY)
    entries = os.listdir(registry)
    if len(entries) > 501:
        raise ValueError("reservation_identity_inventory_limit")
    indexed = {}
    for entry in entries:
        if entry in ("manifest.json", "legacy-seal.json"):
            continue
        op = entry[:-5] if entry.endswith(".json") else ""
        if not matches(ID, op):
            raise ValueError("reservation_identity_inventory")
        intent = read(os.path.join(registry, entry))
        if op not in by_id or canonical(intent) != canonical(by_id[op]):
            raise ValueError("reservation_identity_record_missing_or_changed")
        if (
            intent["binding"]["identity_manifest_sha256"] != manifest_sha
            or intent["after"]["count"] <= manifest["baseline"]["count"]
        ):
            raise ValueError("reservation_identity_migration_drift")
        indexed[op] = intent
    if set(indexed) != set(by_id):
        raise ValueError("reservation_identity_seal_missing")
    legacy_ids = set(manifest["legacy_operation_ids"])
    if set(indexed).intersection(legacy_ids):
        raise ValueError("reservation_identity_class_conflict")
    covered = set()
    for op, value in marker_ids.items():
        if value["count"] > manifest["baseline"]["count"]:
            if op not in indexed and op not in legacy_ids:
                raise ValueError("reservation_post_migration_identity_missing")
            covered.add(value["count"])
    if covered != set(range(manifest["baseline"]["count"] + 1, counter["count"] + 1)):
        raise ValueError("reservation_post_migration_slot_missing")
    counts = [value["count"] for value in markers]
    if len(set(counts)) != len(counts):
        raise ValueError("reservation_duplicate_counter_slot")
    # Every legacy increment after native-v1 baseline uses128MiB. New variable
    # increments are accounted by their immutable own records, not another ledger.
    # Include unresolved own intents for conservation only; never infer completion.
    for value in markers:
        if value["result_reserved_bytes"] != expected_bytes(value["count"], records, manifest):
            raise ValueError("reservation_marker_conservation")
    for intent, receipt in records:
        for value in (intent["before"], intent["after"]):
            if value["result_reserved_bytes"] != expected_bytes(value["count"], records, manifest):
                raise ValueError("reservation_intent_conservation")
    if counter["result_reserved_bytes"] != expected_bytes(counter["count"], records, manifest):
        raise ValueError("reservation_counter_conservation")
    return records


def expected_bytes(count, records, manifest=None):
    if manifest is not None and manifest["schema_version"] == 2:
        return sum(
            intent["binding"]["reserve_bytes"]
            for intent, receipt in records
            if intent["after"]["count"] <= count
        )
    total = LEGACY_BASE_BYTES + (count - LEGACY_BASE_COUNT) * LEGACY_RESERVATION
    for intent, receipt in records:
        if intent["after"]["count"] <= count:
            total += intent["binding"]["reserve_bytes"] - LEGACY_RESERVATION
    return total


def state(root, binding):
    manifest = identity_manifest(root, binding)
    counter_path = os.path.join(root, LEDGER)
    if os.path.lexists(counter_path + ".ade-tmp"):
        raise ValueError("reservation_ambiguous_barrier")
    counter = read(counter_path)
    counter_shape(counter, manifest)
    if (
        counter["count"] < manifest["baseline"]["count"]
        or counter["result_reserved_bytes"] < manifest["baseline"]["result_reserved_bytes"]
    ):
        raise ValueError("reservation_migration_rollback")
    return counter, audit(root, counter, manifest, binding["identity_manifest_sha256"])


def lookup(root, operation_id, binding):
    """Read-only, also after grant expiry. Never repairs, charges or dispatches."""
    root = os.path.abspath(root)
    check_binding(root, binding)
    fd = open_lock(root)
    try:
        work = paths(root, operation_id)
        counter, records = state(root, binding)
        item = transaction(work, root, operation_id, counter, identity_manifest(root, binding))
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


class ReservationSession(object):
    """Internal owned flock for one worker lifetime; never constructed from JSON.

    The fixed provider must attest operator/trust/admission before reserving. A
    session pins the existing lock inode once and retains it through EDA/extraction.
    Public reserve/lookup callers continue using short-lived sessions. There is no
    caller flag that can skip locking and no new lock or resource domain.
    """

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.fd = open_lock(self.root)
        self.lock_identity = identity(os.fstat(self.fd))

    def check(self):
        if self.fd is None:
            raise ValueError("reservation_session_closed")
        current = safe(os.path.join(self.root, "run.lock"))
        if (
            identity(current) != self.lock_identity
            or identity(os.fstat(self.fd)) != self.lock_identity
        ):
            raise ValueError("reservation_lock_drift")

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, kind, value, traceback):
        self.close()

    def reserve(self, operation_id, binding):
        self.check()
        return _reserve_held(self, operation_id, binding)

    def observe(self, binding):
        self.check()
        return state(self.root, binding)


def _reserve_held(session, operation_id, binding):
    # This accepts the actual owned session object, never a descriptor/path/flag
    # supplied by caller JSON. Closing or substituting the lock fails closed.
    if type(session) is not ReservationSession:
        raise ValueError("reservation_owned_session_required")
    session.check()
    root = session.root
    check_binding(root, binding)
    work = paths(root, operation_id)
    if operation_id in identity_manifest(root, binding)["legacy_operation_ids"]:
        raise ValueError("reservation_identity_class_conflict")
    counter, records = state(root, binding)
    existing = transaction(work, root, operation_id, counter, identity_manifest(root, binding))
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
    manifest = identity_manifest(root, binding)
    policy = manifest.get(
        "policy", {"attempt_ceiling": CEILING_COUNT, "result_ceiling_bytes": CEILING_BYTES}
    )
    if (
        counter["count"] + 1 > policy["attempt_ceiling"]
        or counter["result_reserved_bytes"] + amount > policy["result_ceiling_bytes"]
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
    write_new(os.path.join(root, REGISTRY, operation_id + ".json"), intent)
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


def reserve(root, operation_id, binding):
    """Internal accounting only. Caller MUST already attest authority/admission."""
    with ReservationSession(root) as session:
        return session.reserve(operation_id, binding)
