#!/usr/bin/env python
"""Python 2.6-compatible evidence writer for the fixed V2 recovery."""

from __future__ import print_function

import datetime
import fcntl
import json
import os
import re
import sys

VALIDATION_ID = "e55c7e81-cf20-4d5e-b2d9-67dae0ddcd1b"
PLAN_SHA256 = "7dba36b1a98dd3a5e4e6d041d413a3e75fc39233d2bace750813bca5a0aeb023"
EVIDENCE_ROOT = "/home/buet/cds_work/.cadence_mcp/write-validation/" + VALIDATION_ID
AUDIT_PATH = "/home/buet/cds_work/.cadence_mcp/audit/write-events.jsonl"
HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FORENSIC_MARKER = "MCP_V2_FORENSIC|true|35|14|8|8|9|validated-v1"
ROLLBACK_MARKER = "MCP_V2_ROLLBACK|true|35|14|8|8|8|absent"


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def require_hashes(values):
    for value in values:
        if not HEX_PATTERN.match(value):
            raise ValueError("invalid recovery fingerprint")


def require_marker(path, expected):
    with open(path, "rb") as handle:
        lines = [line.decode("utf-8", "strict").strip() for line in handle]
    if expected not in lines:
        raise ValueError("fixed V2 recovery marker is missing")
    for line in lines:
        if line.startswith("MCP_V2_") and line != expected:
            raise ValueError("unexpected V2 recovery marker")


def write_once(path, payload):
    if os.path.exists(path):
        raise ValueError("recovery evidence already exists")
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.rename(temporary, path)


def append_rollback_audit():
    parent = os.path.dirname(AUDIT_PATH)
    if not os.path.isdir(parent):
        os.makedirs(parent, 0o700)
    record = {
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "design_write_v2_recovery_rollback",
        "actor": "cadence-mcp-bridge",
        "origin": "operator",
        "validation_id": VALIDATION_ID,
        "plan_sha256": PLAN_SHA256,
    }
    with open(AUDIT_PATH, "ab") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def forensic(output_path, hashes):
    require_hashes(hashes)
    require_marker(output_path, FORENSIC_MARKER)
    source_before, source_after, preserved_before, preserved_after = hashes[:4]
    target_before, target_after, backup_before, backup_after = hashes[4:]
    if source_before != source_after:
        raise ValueError("source changed during V2 forensic inspection")
    if preserved_before != preserved_after:
        raise ValueError("preserved V1 changed during V2 forensic inspection")
    if target_before != target_after or backup_before != backup_after:
        raise ValueError("V2 changed during read-only forensic inspection")
    payload = {
        "validation_id": VALIDATION_ID,
        "forensic_verified": True,
        "source_unchanged": True,
        "preserved_v1_unchanged": True,
        "target_unchanged": True,
        "backup_unchanged": True,
        "source_topology": [35, 14, 8],
        "target_topology": [35, 14, 8],
        "backup_topology": [35, 14, 8],
        "backup_property_absent": True,
        "target_exact_approved_difference": True,
        "approved_property": "mcpMutationTest",
        "approved_value": "validated-v1",
    }
    write_once(os.path.join(EVIDENCE_ROOT, "v2-forensic-evidence.json"), payload)
    emit(payload)


def rollback(output_path, hashes):
    require_hashes(hashes)
    require_marker(output_path, ROLLBACK_MARKER)
    source_before, source_after, preserved_before, preserved_after = hashes[:4]
    backup_before, backup_after, target_before, target_after = hashes[4:]
    if source_before != source_after:
        raise ValueError("source changed during V2 rollback")
    if preserved_before != preserved_after:
        raise ValueError("preserved V1 changed during V2 rollback")
    if backup_before != backup_after:
        raise ValueError("V2 backup changed during rollback")
    if target_before == target_after:
        raise ValueError("V2 rollback did not change the approved target")
    payload = {
        "validation_id": VALIDATION_ID,
        "rollback_verified": True,
        "source_unchanged": True,
        "preserved_v1_unchanged": True,
        "backup_unchanged": True,
        "target_changed": True,
        "restored_topology": [35, 14, 8],
        "restored_property_count": 8,
        "approved_property_absent": True,
        "backup_logically_matches_target": True,
        "target_fingerprint_before": target_before,
        "target_fingerprint_after": target_after,
    }
    write_once(os.path.join(EVIDENCE_ROOT, "v2-rollback-evidence.json"), payload)
    append_rollback_audit()
    emit(payload)


def main():
    if len(sys.argv) != 11:
        return fail("invalid V2 recovery evidence request")
    command = sys.argv[1]
    output_path = sys.argv[2]
    hashes = sys.argv[3:]
    try:
        if command == "forensic":
            forensic(output_path, hashes)
        elif command == "rollback":
            rollback(output_path, hashes)
        else:
            return fail("invalid V2 recovery evidence command")
    except (IOError, OSError, UnicodeError, ValueError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
