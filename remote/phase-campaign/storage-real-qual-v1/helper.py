"""Closed single-use synthetic fixture producer; guest Python 2.6.

No delete, consent, caller paths or arbitrary sizes. Partial writes stay preserved.
"""
from __future__ import with_statement
import errno
import hashlib
import os
import stat
import sys
sys.path.insert(0, "/home/buet/cds_work/.cadence_mcp/phase-campaign/storage-mgmt-v6")
import worker as w

EVIDENCE = "storage-real-qual-v1-evidence"
EXPECTED = {'contract_version': 1, 'phase': 'STORAGE-REAL-QUAL-01', 'fixtures': [{'artifact_uuid': 'c63a8b3b-cc0b-4b14-9eac-9a1890ce4869', 'size_bytes': 8192, 'label': 'A'}, {'artifact_uuid': 'e6610b58-7bcf-476b-8e8d-e118bb00e60a', 'size_bytes': 12288, 'label': 'B'}], 'max_new_payload_bytes': 20480, 'max_new_simulations': 0, 'max_new_reserved_bytes': 0, 'delete_authority': False, 'automatic_retry': False, 'disk_floor_bytes': 2147483648, 'disk_floor_percent': 10, 'correction_ceiling': 20, 'extraction': 'synthetic-byte-count-and-sha256-not-analog-measurement'}

def validate(policy):
    if policy != EXPECTED:
        raise ValueError("fixed fixture policy drift")
    for item in policy["fixtures"]:
        if not w.UUID.match(item["artifact_uuid"]):
            raise ValueError("fixed identity invalid")

def payload(item):
    return (("storage-real-qual-v1-synthetic-" + item["label"] + "\n").encode("ascii")
            * item["size_bytes"])[:item["size_bytes"]]

def absent(io, parent, name):
    try:
        fd = io.open(parent, name)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return
        raise
    else:
        os.close(fd)
        raise ValueError("preexisting identity denied")

def inspect_payloads(io, spool):
    values = []
    for item in EXPECTED["fixtures"]:
        fd = w.private_directory(io, spool, item["artifact_uuid"])
        try:
            if io.names(fd) != ["payload.bin"]:
                raise ValueError("isolated leaf required")
            fingerprint, meta, content = w.payload_fingerprint(io, fd)
            raw = payload(item)
            info_fd = io.open(fd, "payload.bin")
            try:
                s = os.fstat(info_fd)
                if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
                    raise ValueError("private payload required")
            finally:
                os.close(info_fd)
            if meta[4] != item["size_bytes"] or content != hashlib.sha256(raw).hexdigest():
                raise ValueError("synthetic payload mismatch")
            values.append(dict(item, fingerprint=fingerprint, content_sha256=content,
                               extraction=EXPECTED["extraction"]))
        finally:
            os.close(fd)
    return values

def operate(io, root, action, policy):
    validate(policy)
    if action not in ("prepare", "inspect"):
        raise ValueError("closed fixture action required")
    spool = w.private_directory(io, root, w.SPOOL)
    try:
        if action == "prepare":
            disk = os.fstatvfs(root)
            free = disk.f_bavail * disk.f_frsize
            total = disk.f_blocks * disk.f_frsize
            floor = max(policy["disk_floor_bytes"],
                        total * policy["disk_floor_percent"] // 100)
            if free - policy["max_new_payload_bytes"] < floor:
                raise ValueError("disk floor denied")
            absent(io, root, EVIDENCE)
            for item in policy["fixtures"]:
                absent(io, spool, item["artifact_uuid"])
            io.mkdir(root, EVIDENCE)
            os.fsync(root)
            evidence = w.private_directory(io, root, EVIDENCE)
            try:
                w.write_json(io, evidence, "prepare-intent.json",
                             dict(policy_sha256=w.digest(policy), automatic_retry=False))
                for item in policy["fixtures"]:
                    io.mkdir(spool, item["artifact_uuid"])
                    os.fsync(spool)
                    container = w.private_directory(io, spool, item["artifact_uuid"])
                    try:
                        fd = io.open(container, "payload.bin", create=True)
                        try:
                            raw = payload(item)
                            count = 0
                            while count < len(raw):
                                n = os.write(fd, raw[count:])
                                if n <= 0:
                                    raise ValueError("partial fixture write")
                                count += n
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                        os.fsync(container)
                    finally:
                        os.close(container)
                values = inspect_payloads(io, spool)
                w.write_json(io, evidence, "extraction.json",
                             dict(fixtures=values, analog_qualification=False))
            finally:
                os.close(evidence)
        else:
            evidence = w.private_directory(io, root, EVIDENCE)
            try:
                intent = w.read_json(io, evidence, "prepare-intent.json", 32768, True)
                if intent != dict(policy_sha256=w.digest(policy), automatic_retry=False):
                    raise ValueError("fixture intent mismatch")
                saved = w.read_json(io, evidence, "extraction.json", 32768, True)
                values = inspect_payloads(io, spool)
                if saved != dict(fixtures=values, analog_qualification=False):
                    raise ValueError("fixture extraction drift or incomplete prepare")
            finally:
                os.close(evidence)
        return dict(state="PREPARED" if action == "prepare" else "INSPECTED",
                    fixtures=values, deleted_artifacts=0, new_simulations=0,
                    reservation_delta=0, analog_qualification=False)
    finally:
        os.close(spool)

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "inspect"):
        raise ValueError("unsupported fixture operation")
    base = os.path.dirname(os.path.abspath(__file__))
    policy = __import__("json").loads(open(base + "/policy.json", "rb").read())
    activation = __import__("json").loads(open(base + "/activation.private.json", "rb").read())
    if activation != dict(phase=EXPECTED["phase"], policy_sha256=w.digest(policy),
                          user_delegation="explicit-synthetic-preparation-no-delete"):
        raise ValueError("fixture activation absent")
    io = w.PosixIO()
    root = io.root(w.ROOT)
    try:
        import fcntl
        lock = io.open(root, "run.lock")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if w.active_eda(w.ROOT):
                raise ValueError("active EDA denied")
            value = operate(io, root, sys.argv[1], policy)
        finally:
            os.close(lock)
        sys.stdout.write(w.canonical(value).decode("ascii") + "\n")
    finally:
        os.close(root)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("fixture denied or uncertain; no automatic retry\n")
        sys.exit(69)
