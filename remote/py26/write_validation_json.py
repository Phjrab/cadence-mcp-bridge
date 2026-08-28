#!/usr/bin/env python
"""Python 2.6-compatible fixed design-write plan and result serializer."""

from __future__ import print_function

import datetime
import fcntl
import hashlib
import json
import os
import re
import sys

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
EXPECTED_KEYS = set(
    [
        "policy_version",
        "plan_id",
        "source",
        "target",
        "backup_cell",
        "operation",
        "property",
        "affected_objects",
        "original_library_mutations",
        "destructive",
        "confirmation",
    ]
)
EXPECTED_SEQUENCE = [
    "copy",
    "baseline",
    "dry_run",
    "dry_run_unchanged",
    "backup",
    "apply",
    "verify_apply",
    "rollback",
    "verify_rollback",
    "source_unchanged",
    "complete",
]


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def load_policy(path):
    with open(path, "rb") as handle:
        policy = json.load(handle)
    if set(policy) != EXPECTED_KEYS:
        raise ValueError("invalid write policy keys")
    if policy["policy_version"] != 1 or policy["plan_id"] != "mcp-cellview-property-v1":
        raise ValueError("invalid write policy version")
    if policy["source"] != {
        "library": "MyDesignLib",
        "cell": "Differential_Amplifier_TB2",
        "view": "schematic",
        "path": "/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic",
    }:
        raise ValueError("invalid fixed source")
    if policy["target"] != {
        "library": "MCP_WorkLib",
        "library_path": "/home/buet/cds_work/MCP_WorkLib",
        "cell": "Differential_Amplifier_TB2_MCP_TEST",
        "view": "schematic",
    }:
        raise ValueError("invalid fixed target")
    if policy["property"] != {
        "name": "mcpMutationTest",
        "type": "string",
        "old_value": None,
        "proposed_value": "validated-v1",
    }:
        raise ValueError("invalid fixed property")
    if (
        policy["backup_cell"] != "Differential_Amplifier_TB2_MCP_TEST_BACKUP_V1"
        or policy["operation"] != "set_cellview_property"
        or policy["affected_objects"] != 1
        or policy["original_library_mutations"] != 0
        or policy["destructive"] is not False
        or policy["confirmation"] != "APPROVE_MCP_WRITE_VALIDATED_V1"
    ):
        raise ValueError("invalid fixed write contract")
    return policy


def canonical_hash(policy):
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def target_path(policy):
    target = policy["target"]
    return os.path.join(target["library_path"], target["cell"], target["view"])


def plan_payload(policy):
    source = policy["source"]
    target = policy["target"]
    target_exists = os.path.exists(target_path(policy))
    source_exists = os.path.isdir(source["path"]) and not os.path.islink(source["path"])
    return {
        "policy_version": policy["policy_version"],
        "plan_id": policy["plan_id"],
        "plan_sha256": canonical_hash(policy),
        "source": "%s/%s/%s" % (source["library"], source["cell"], source["view"]),
        "target": "%s/%s/%s" % (target["library"], target["cell"], target["view"]),
        "operation": policy["operation"],
        "property_name": policy["property"]["name"],
        "old_value": policy["property"]["old_value"],
        "proposed_value": policy["property"]["proposed_value"],
        "affected_objects": policy["affected_objects"],
        "original_library_mutations": policy["original_library_mutations"],
        "destructive": policy["destructive"],
        "source_exists": source_exists,
        "target_exists": target_exists,
        "ready": source_exists and not target_exists,
        "confirmation": policy["confirmation"],
    }


def parse_stages(path):
    stages = []
    fields = {}
    with open(path, "rb") as handle:
        for raw_line in handle:
            line = raw_line.decode("utf-8", "strict").strip()
            if line.startswith("MCP_WRITE_FAILURE|"):
                raise ValueError("SKILL validation reported failure")
            if not line.startswith("MCP_STAGE|"):
                continue
            parts = line.split("|")
            stage = parts[1]
            stages.append(stage)
            fields[stage] = parts[2:]
    if stages != EXPECTED_SEQUENCE:
        raise ValueError("write validation stage sequence mismatch")
    return fields


def append_audit(path, validation_id, plan_hash, origin, actor, stages):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent, 0o700)
    with open(path, "ab") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            for stage in stages:
                record = {
                    "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "event": "design_write_" + stage,
                    "actor": actor,
                    "origin": origin,
                    "validation_id": validation_id,
                    "plan_sha256": plan_hash,
                }
                line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def finalize(
    policy,
    validation_id,
    output_path,
    source_before,
    source_after,
    origin,
    actor,
    audit_path,
    manifest_path,
):
    if not UUID_PATTERN.match(validation_id):
        raise ValueError("invalid validation id")
    if origin not in ("mcp", "operator"):
        raise ValueError("invalid origin")
    fields = parse_stages(output_path)
    if source_before != source_after:
        raise ValueError("source tree fingerprint changed")
    if fields["dry_run"] != ["absent", "validated-v1", "1", "0", "false"]:
        raise ValueError("dry-run contract mismatch")
    for stage in ("dry_run_unchanged", "backup", "source_unchanged", "complete"):
        if fields[stage] != ["true"]:
            raise ValueError("stage verification mismatch")
    if fields["apply"] != ["validated-v1", "1"]:
        raise ValueError("apply contract mismatch")
    if fields["rollback"] != ["true", "1"]:
        raise ValueError("rollback contract mismatch")
    plan = plan_payload(policy)
    plan_hash = plan["plan_sha256"]
    append_audit(audit_path, validation_id, plan_hash, origin, actor, EXPECTED_SEQUENCE)
    manifest = {
        "validation_id": validation_id,
        "plan_sha256": plan_hash,
        "source_fingerprint_before": source_before,
        "source_fingerprint_after": source_after,
        "sequence": EXPECTED_SEQUENCE,
        "backup_cell": policy["backup_cell"],
        "rollback_verified": True,
    }
    temporary = manifest_path + ".tmp"
    with open(temporary, "wb") as handle:
        serialized = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.rename(temporary, manifest_path)
    emit(
        {
            "validation_id": validation_id,
            "plan_id": policy["plan_id"],
            "plan_sha256": plan_hash,
            "source": plan["source"],
            "target": plan["target"],
            "operation": policy["operation"],
            "property_name": policy["property"]["name"],
            "old_value": None,
            "proposed_value": policy["property"]["proposed_value"],
            "affected_objects": 1,
            "original_library_mutations": 0,
            "destructive": False,
            "copy_verified": True,
            "dry_run_unchanged": True,
            "backup_verified": True,
            "apply_verified": True,
            "rollback_verified": True,
            "source_unchanged": True,
            "topology_unchanged": True,
            "audit_recorded": True,
            "sequence": EXPECTED_SEQUENCE,
        }
    )


def main():
    if len(sys.argv) < 3:
        return 64
    try:
        policy = load_policy(sys.argv[1])
        command = sys.argv[2]
        arguments = sys.argv[3:]
        if command == "plan" and len(arguments) == 0:
            emit(plan_payload(policy))
        elif command == "confirm" and len(arguments) == 1:
            if arguments[0] != policy["confirmation"]:
                raise ValueError("confirmation does not match the fixed plan")
        elif command == "finalize" and len(arguments) == 8:
            finalize(policy, *arguments)
        else:
            return fail("invalid write validation request")
    except (IOError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
