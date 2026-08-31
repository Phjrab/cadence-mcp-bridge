#!/usr/bin/env python
"""Python 2.6-compatible verifier for the approved fixed V3 validation."""

from __future__ import print_function

import datetime
import fcntl
import hashlib
import json
import os
import re
import sys

PLAN_SHA256 = "3362e4fc13874d4f16c78506c24ae6ebd64c882718fe57e9cb2bb60619890c87"
CONFIRMATION = "APPROVE_MCP_WRITE_VALIDATED_V3_3362E4FC"
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SKILL_SEQUENCE = [
    "source_verify",
    "V3_destination_absence_check",
    "V3_backup_absence_check",
    "V3_copy",
    "baseline_fingerprint",
    "dry_run",
    "unchanged_verification",
    "backup",
    "apply",
    "exact_diff_verification",
    "rollback",
    "baseline_restoration_verification",
    "source_unchanged_verification",
]
FULL_SEQUENCE = SKILL_SEQUENCE + ["audit_verification"]


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def load_plan(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError("V3 plan SHA-256 mismatch")
    plan = json.loads(raw.decode("utf-8", "strict"))
    if plan.get("plan_id") != "mcp-cellview-property-v3":
        raise ValueError("invalid V3 plan id")
    if plan.get("target") != "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic":
        raise ValueError("invalid V3 target")
    if plan.get("backup") != (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic"
    ):
        raise ValueError("invalid V3 backup")
    if plan.get("sequence") != FULL_SEQUENCE:
        raise ValueError("invalid V3 sequence")
    if len(plan.get("acceptance_criteria", [])) != 10:
        raise ValueError("invalid V3 acceptance criteria")
    if plan.get("worker_timeout_seconds") != 300:
        raise ValueError("invalid V3 timeout")
    if plan.get("affected_objects") != 1:
        raise ValueError("invalid V3 affected object count")
    if plan.get("original_library_mutations") != 0 or plan.get("destructive") is not False:
        raise ValueError("invalid V3 mutation boundary")
    return plan


def require_hashes(values):
    for value in values:
        if not HEX_PATTERN.match(value):
            raise ValueError("invalid V3 fingerprint")


def parse_output(path):
    stages = []
    fields = {}
    fingerprints = {}
    with open(path, "rb") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line.startswith(b"MCP_V3_"):
                continue
            line = raw_line.decode("ascii", "strict")
            if line.startswith("MCP_V3_FAILURE|"):
                raise ValueError("V3 SKILL reported failure")
            if line.startswith("MCP_V3_FINGERPRINT|"):
                parts = line.split("|")
                if len(parts) < 4:
                    raise ValueError("invalid V3 logical fingerprint")
                fingerprints.setdefault(parts[1], []).append("|".join(parts[2:]))
                continue
            if line.startswith("MCP_V3_STAGE|"):
                parts = line.split("|")
                if len(parts) < 3 or parts[1] in fields:
                    raise ValueError("invalid or duplicate V3 stage")
                stages.append(parts[1])
                fields[parts[1]] = parts[2:]
                continue
            raise ValueError("unexpected V3 marker")
    if stages != SKILL_SEQUENCE:
        raise ValueError("V3 stage sequence mismatch")
    logical_hashes = {}
    for stage in ("baseline", "dry_run", "backup", "rollback", "backup_final"):
        records = fingerprints.get(stage)
        if not records:
            raise ValueError("missing V3 logical fingerprint")
        encoded = ("\n".join(sorted(records)) + "\n").encode("utf-8")
        logical_hashes[stage] = hashlib.sha256(encoded).hexdigest()
    if len(set(logical_hashes.values())) != 1:
        raise ValueError("V3 logical baseline was not restored")
    expected_fields = {
        "source_verify": ["true", "35", "14", "8"],
        "V3_destination_absence_check": ["true"],
        "V3_backup_absence_check": ["true"],
        "V3_copy": ["true", "35", "14", "8"],
        "dry_run": ["true", "absent", "1", "0", "false"],
        "unchanged_verification": ["true"],
        "backup": ["true"],
        "apply": ["true", "1"],
        "exact_diff_verification": ["true", "1"],
        "rollback": ["true"],
        "baseline_restoration_verification": ["true"],
        "source_unchanged_verification": ["true"],
    }
    for stage, expected in expected_fields.items():
        if fields.get(stage) != expected:
            raise ValueError("V3 stage contract mismatch")
    baseline_fields = fields.get("baseline_fingerprint", [])
    if len(baseline_fields) != 2 or baseline_fields[0] != "true":
        raise ValueError("V3 baseline fingerprint contract mismatch")
    try:
        if int(baseline_fields[1]) < 1:
            raise ValueError("invalid V3 baseline property count")
    except ValueError:
        raise ValueError("invalid V3 baseline property count")
    return logical_hashes


def append_and_verify_audit(path, validation_id, origin, actor):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent, 0o700)
    with open(path, "ab") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            for stage in FULL_SEQUENCE:
                record = {
                    "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "event": "design_write_v3_" + stage,
                    "actor": actor,
                    "origin": origin,
                    "validation_id": validation_id,
                    "plan_sha256": PLAN_SHA256,
                }
                serialized = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                handle.write(serialized.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    observed = []
    with open(path, "rb") as handle:
        for raw_line in handle:
            record = json.loads(raw_line.decode("utf-8", "strict"))
            if record.get("validation_id") == validation_id:
                observed.append(record.get("event"))
    expected = ["design_write_v3_" + stage for stage in FULL_SEQUENCE]
    if observed != expected:
        raise ValueError("V3 audit verification failed")


def write_once(path, payload):
    if os.path.exists(path):
        raise ValueError("V3 manifest already exists")
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.rename(temporary, path)


def finalize(plan, arguments):
    validation_id = arguments[0]
    output_path = arguments[1]
    protected_hashes = arguments[2:12]
    target_final = arguments[12]
    backup_final = arguments[13]
    origin = arguments[14]
    actor = arguments[15]
    audit_path = arguments[16]
    manifest_path = arguments[17]
    if not UUID_PATTERN.match(validation_id):
        raise ValueError("invalid V3 validation id")
    if origin not in ("mcp", "operator"):
        raise ValueError("invalid V3 origin")
    require_hashes(protected_hashes + [target_final, backup_final])
    pairs = [
        ("source", protected_hashes[0], protected_hashes[1]),
        ("preserved_v1", protected_hashes[2], protected_hashes[3]),
        ("v2_target", protected_hashes[4], protected_hashes[5]),
        ("v2_backup", protected_hashes[6], protected_hashes[7]),
        ("pdk", protected_hashes[8], protected_hashes[9]),
    ]
    for name, before, after in pairs:
        if before != after:
            raise ValueError(name + " changed during V3 validation")
    logical_hashes = parse_output(output_path)
    append_and_verify_audit(audit_path, validation_id, origin, actor)
    manifest = {
        "validation_id": validation_id,
        "plan_id": plan["plan_id"],
        "plan_sha256": PLAN_SHA256,
        "sequence": FULL_SEQUENCE,
        "source_topology": [35, 14, 8],
        "protected_fingerprints": dict(
            (name, {"before": before, "after": after}) for name, before, after in pairs
        ),
        "target_final_tree_fingerprint": target_final,
        "backup_final_tree_fingerprint": backup_final,
        "baseline_logical_fingerprint": logical_hashes["baseline"],
        "rollback_logical_fingerprint": logical_hashes["rollback"],
        "property_name": "mcpMutationTest",
        "property_type": "string",
        "affected_objects": 1,
        "dry_run_unchanged": True,
        "apply_exact_diff_verified": True,
        "rollback_verified": True,
        "audit_verified": True,
        "property_values_included": False,
    }
    write_once(manifest_path, manifest)
    emit({
        "validation_id": validation_id,
        "plan_id": plan["plan_id"],
        "plan_sha256": PLAN_SHA256,
        "target": plan["target"],
        "backup": plan["backup"],
        "copy_verified": True,
        "dry_run_unchanged": True,
        "backup_verified": True,
        "apply_exact_diff_verified": True,
        "rollback_verified": True,
        "source_unchanged": True,
        "preserved_v1_unchanged": True,
        "v2_target_unchanged": True,
        "v2_backup_unchanged": True,
        "pdk_unchanged": True,
        "audit_verified": True,
        "property_values_included": False,
        "sequence": FULL_SEQUENCE,
    })


def main():
    if len(sys.argv) < 3:
        return fail("invalid V3 validation request")
    try:
        plan = load_plan(sys.argv[1])
        command = sys.argv[2]
        arguments = sys.argv[3:]
        if command == "plan-check" and len(arguments) == 0:
            emit({
                "plan_id": plan["plan_id"],
                "plan_sha256": PLAN_SHA256,
                "acceptance_criteria_count": len(plan["acceptance_criteria"]),
                "sequence_count": len(plan["sequence"]),
                "approved_for_fixed_runner": True,
            })
        elif command == "confirm" and len(arguments) == 1:
            if arguments[0] != CONFIRMATION:
                raise ValueError("V3 confirmation rejected")
        elif command == "finalize" and len(arguments) == 18:
            finalize(plan, arguments)
        else:
            return fail("invalid V3 validation request")
    except (IOError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
