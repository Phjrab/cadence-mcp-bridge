"""Fixed native admission/worker ownership; Python2.6, no CLI or grant writer.

Only the verified runtime supplies its compiled gate and worker. Progress uses
existing job storage; accounting and worker share the existing lifetime flock.
"""

# mypy: ignore-errors
import hashlib
import json
import os
import re
import stat

try:
    INTEGERS = (int, long)
except NameError:
    INTEGERS = (int,)

LIMIT = 262144
MAX_EVENTS = 64
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED")
PHASES = ("RESERVED", "DISPATCHED", "RUNNING", "EXTRACTING", "EXTRACTION_FAILED") + TERMINAL


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(value).hexdigest()


def token(pattern, value):
    found = re.match(pattern, value)
    if found is None or found.end() != len(value):
        raise ValueError("native_operation_identity")
    return value


def uuid(value):
    return token(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", value)


def sha(value):
    return token(r"^[0-9a-f]{64}$", value)


def private(path, directory=False):
    info = os.lstat(path)
    if (
        os.path.realpath(path) != os.path.abspath(path)
        or getattr(info, "st_file_attributes", 0) & 1024
        or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError("native_operation_path")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 63):
        raise ValueError("native_operation_permissions")
    return info


def read_bytes(path):
    before = private(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    stream = os.fdopen(fd, "rb")
    try:
        opened = os.fstat(fd)
        raw = stream.read(LIMIT + 1)
        after = private(path)
        expected = (before.st_dev, before.st_ino, before.st_size, before.st_mtime)
        if (
            expected != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime)
            or expected != (after.st_dev, after.st_ino, after.st_size, after.st_mtime)
            or len(raw) > LIMIT
        ):
            raise ValueError("native_operation_read_drift")
        return raw
    finally:
        stream.close()


def read(path):
    raw = read_bytes(path)
    value = json.loads(raw.decode("ascii"))
    if canonical(value) != raw:
        raise ValueError("native_operation_noncanonical")
    return value


def directory(path, accounting):
    if not os.path.lexists(path):
        private(os.path.dirname(path), True)
        os.mkdir(path, 448)
        accounting.sync_directory(os.path.dirname(path))
    private(path, True)


def transition(before, after):
    if after not in PHASES or before in TERMINAL:
        raise ValueError("native_operation_terminal_or_phase")
    ranks = dict((value, index) for index, value in enumerate(PHASES[:5]))
    if (
        before is not None
        and after in ranks
        and (before not in ranks or ranks[after] <= ranks[before])
    ):
        raise ValueError("native_operation_regression")
    if after == "CANCELLED" and before is not None and before != "RESERVED":
        raise ValueError("native_operation_active_cancellation")
    if before is None and after not in ("RESERVED", "CANCELLED"):
        raise ValueError("native_operation_initial_phase")
    if after == "SUCCEEDED" and before != "EXTRACTING":
        raise ValueError("native_operation_extraction_required")


class OperationJournal(object):
    """Immutable admission/numbered hash chain, readable without the EDA lock.

    Partial entries are retained and rejected, never overwritten. Admission
    without an event is unknown outcome, never permission to redispatch.
    """

    def __init__(self, root, operation_id, plan, accounting):
        self.root = os.path.abspath(root)
        self.operation_id = uuid(operation_id)
        self.plan = plan
        self.plan_sha = digest(canonical(plan))
        self.accounting = accounting
        self.job = self.root + "/" + accounting.JOBS + "/" + operation_id
        self.work = self.job + "/work"
        self.path = self.work + "/operation"

    def admission(self):
        if not os.path.lexists(self.job):
            return None
        private(self.job, True)
        # A legacy/partial occupied identity cannot become a new dispatch.
        private(self.work, True)
        if not os.path.lexists(self.path):
            raise ValueError("native_operation_occupied_identity")
        private(self.path, True)
        value = read(self.path + "/admission.json")
        if set(value) != set(("schema_version", "operation_id", "plan", "plan_sha256", "binding")):
            raise ValueError("native_operation_admission_shape")
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["operation_id"] != self.operation_id
            or value["plan"] != self.plan
            or value["plan_sha256"] != self.plan_sha
        ):
            raise ValueError("native_operation_replay_conflict")
        self.accounting.check_binding(self.root, value["binding"])
        if (
            any(
                value["binding"][key] != self.plan[key]
                for key in ("resource_domain_sha256", "runner_sha256", "grant_sha256")
            )
            or value["binding"]["plan_sha256"] != self.plan_sha
        ):
            raise ValueError("native_operation_reservation_binding")
        if self.plan["ledger_ref"] != self.accounting.LEDGER_REF:
            raise ValueError("native_operation_logical_ledger")
        return value

    def create(self, binding):
        if os.path.lexists(self.job):
            raise ValueError("native_operation_occupied_identity")
        self.accounting.check_binding(self.root, binding)
        manifest = self.accounting.identity_manifest(self.root, binding)
        if self.operation_id in manifest["legacy_operation_ids"]:
            raise ValueError("native_operation_legacy_identity")
        directory(self.job, self.accounting)
        directory(self.work, self.accounting)
        directory(self.path, self.accounting)
        self.accounting.write_new(
            self.path + "/admission.json",
            {
                "schema_version": 1,
                "operation_id": self.operation_id,
                "plan": self.plan,
                "plan_sha256": self.plan_sha,
                "binding": binding,
            },
        )
        self.admission()

    def events(self):
        admission = self.admission()
        if admission is None:
            return None, []
        # Concurrent append may appear at next read; no mutable latest pointer.
        names = sorted(os.listdir(self.path))
        expected = ["admission.json"]
        events = []
        previous = digest(canonical(admission))
        phase = None
        for index in range(1, MAX_EVENTS + 1):
            name = "%02d.json" % index
            if name not in names:
                break
            value = read(self.path + "/" + name)
            if set(value) != set(
                (
                    "schema_version",
                    "operation_id",
                    "plan_sha256",
                    "revision",
                    "previous_sha256",
                    "phase",
                    "evidence_sha256",
                )
            ) or (
                type(value["schema_version"]) is not int
                or value["schema_version"] != 1
                or type(value["revision"]) not in INTEGERS
                or value["revision"] != index
                or value["operation_id"] != self.operation_id
                or value["plan_sha256"] != self.plan_sha
                or value["previous_sha256"] != previous
            ):
                raise ValueError("native_operation_chain_identity")
            sha(value["evidence_sha256"])
            transition(phase, value["phase"])
            previous, phase = digest(canonical(value)), value["phase"]
            events.append(value)
            expected.append(name)
        if set(names) != set(expected):
            raise ValueError("native_operation_chain_gap_or_inventory")
        return admission, events

    def observation(self):
        admission, events = self.events()
        if admission is None:
            return None
        if not events:
            return self.reply("UNKNOWN_OUTCOME", 0, digest(canonical(admission)))
        event = events[-1]
        # Read immutable receipts while active worker owns run.lock. A changing
        # counter is neither read nor repaired on this lookup route.
        if events[0]["phase"] != "CANCELLED":
            manifest = self.accounting.identity_manifest(self.root, admission["binding"])
            intent = self.accounting.read(self.work + "/reservation-intent.json")
            receipt = self.accounting.read(self.work + "/reservation-receipt.json")
            if (
                intent["operation_id"] != self.operation_id
                or intent["binding"] != admission["binding"]
                or receipt != self.accounting.receipt_for(intent)
                or self.accounting.read(self.work + "/attempt-reserved") != intent["after"]
                or events[0]["evidence_sha256"] != digest(canonical(receipt))
            ):
                raise ValueError("native_operation_receipt_binding")
            self.accounting.counter_shape(intent["before"], manifest)
            self.accounting.counter_shape(intent["after"], manifest)
            if (
                intent["after"]["count"] != intent["before"]["count"] + 1
                or intent["after"]["result_reserved_bytes"]
                != intent["before"]["result_reserved_bytes"] + admission["binding"]["reserve_bytes"]
            ):
                raise ValueError("native_operation_receipt_delta")
        return self.reply(event["phase"], event["revision"], digest(canonical(event)))

    def reply(self, phase, revision, receipt_sha):
        return {
            "operation_id": self.operation_id,
            "plan_sha256": self.plan_sha,
            "resource_domain_sha256": self.plan["resource_domain_sha256"],
            "ledger_ref": self.plan["ledger_ref"],
            "progress": {
                "phase": phase,
                "remote_revision": revision,
                "provider_receipt_sha256": receipt_sha,
            },
        }

    def append(self, session, phase, evidence_sha):
        if type(session) is not self.accounting.ReservationSession or session.root != self.root:
            raise ValueError("native_operation_owned_session_required")
        session.check()
        admission, events = self.events()
        if admission is None or len(events) >= MAX_EVENTS:
            raise ValueError("native_operation_admission_or_event_limit")
        before = events[-1] if events else None
        transition(before["phase"] if before else None, phase)
        event = {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "plan_sha256": self.plan_sha,
            "revision": len(events) + 1,
            "previous_sha256": digest(canonical(before if before else admission)),
            "phase": phase,
            "evidence_sha256": sha(evidence_sha),
        }
        self.accounting.write_new(self.path + "/%02d.json" % event["revision"], event)
        return self.observation()


class NativeCoordinator(object):
    """Runtime-internal fixed gate/worker, never selected by request JSON.

    Gate rechecks consent/trust/registration under the session. Worker never
    reserves again. Unknown outcomes and accepted identities are lookup-only.
    """

    def __init__(self, root, accounting, gate, worker):
        self.root, self.accounting, self.gate, self.worker = root, accounting, gate, worker

    def journal(self, operation_id, plan):
        return OperationJournal(self.root, operation_id, plan, self.accounting)

    def authorize(self, operation_id, plan):
        with self.accounting.ReservationSession(self.root) as session:
            binding, observation = self.gate.check(session, plan, "authorize")
            session.observe(binding)
            return observation

    def lookup(self, operation_id, plan):
        # Read checks identity, not live consent/capacity. It cannot launch work.
        self.gate.read(plan)
        return self.journal(operation_id, plan).observation()

    def accept(self, operation_id, plan):
        journal = self.journal(operation_id, plan)
        existing = self.lookup(operation_id, plan)
        if existing is not None:
            return existing
        with self.accounting.ReservationSession(self.root) as session:
            existing = self.lookup(operation_id, plan)
            if existing is not None:
                return existing
            binding, observation = self.gate.check(session, plan, "submit")
            session.observe(binding)
            journal.create(binding)
            reservation = session.reserve(operation_id, binding)
            if reservation["status"] != "RESERVATION_COMMITTED_NOT_DISPATCHED":
                raise ValueError("native_operation_reservation_ambiguous")
            journal.append(session, "RESERVED", digest(canonical(reservation)))
            # Intent before fork: failure/lost acknowledgement can never resend.
            journal.append(
                session, "DISPATCHED", digest(canonical({"dispatch": "fixed_fork_once"}))
            )
            self.worker.start(session, journal, plan)
            return journal.observation()

    def cancel_pending(self, operation_id, plan):
        journal = self.journal(operation_id, plan)
        with self.accounting.ReservationSession(self.root) as session:
            binding, observation = self.gate.check(session, plan, "cancel_pending")
            session.observe(binding)
            existing = journal.observation()
            if existing is not None:
                if existing["progress"]["phase"] == "CANCELLED":
                    return existing
                if existing["progress"]["phase"] != "RESERVED":
                    raise ValueError("native_operation_active_or_unknown_cancellation")
            else:
                journal.create(binding)
            return journal.append(
                session, "CANCELLED", digest(canonical({"cancel": "pending_only"}))
            )


class ForkWorker(object):
    """POSIX fixed worker retaining the inherited shared flock descriptor.

    run is fixed verified code, never caller configuration. Closing the parent
    descriptor cannot release the lock before this normal-user worker finishes.
    """

    def __init__(self, run):
        self.run = run

    def start(self, session, journal, plan):
        if os.name != "posix" or not hasattr(os, "fork"):
            raise ValueError("native_operation_posix_worker_required")
        session.check()
        pid = os.fork()
        if pid:
            return pid
        try:
            os.setsid()
            os.umask(63)  # Private output inheritance for Cadence and all descendants.
            null = os.open(os.devnull, os.O_RDWR)
            for descriptor in (0, 1, 2):
                os.dup2(null, descriptor)
            if null > 2:
                os.close(null)
            session.check()
            journal.append(session, "RUNNING", digest(canonical({"worker": "normal_user"})))
            self.run(session, journal, plan)
            observed = journal.observation()
            if observed["progress"]["phase"] not in TERMINAL + ("EXTRACTION_FAILED",):
                raise ValueError("native_operation_missing_terminal")
            code = 0
        except Exception:
            code = 70
            try:
                observed = journal.observation()
                if observed["progress"]["phase"] not in TERMINAL + ("EXTRACTION_FAILED",):
                    journal.append(
                        session, "FAILED", digest(canonical({"failure": "fixed_worker_failed"}))
                    )
            except Exception:
                pass  # Retain ambiguous/partial evidence, never overwrite.
        finally:
            session.close()
        os._exit(code)
