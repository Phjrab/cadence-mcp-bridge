#!/usr/bin/env python
"""Python 2.6-compatible verifier for the approved fixed V4 validation."""

from __future__ import print_function

import datetime
import fcntl
import hashlib
import json
import os
import re
import sys

PLAN_SHA256 = "c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66"
CONFIRMATION = "APPROVE_MCP_WRITE_VALIDATED_V4_C5B2F418"
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.#-]{0,127}$")
SCOPES = (
    "baseline",
    "dry_run",
    "backup",
    "apply",
    "rollback",
    "backup_final",
)
SKILL_SEQUENCE = [
    "source_read_only_verify",
    "V4_copy_from_source",
    "baseline_structural_and_property_fingerprint",
    "non_mutating_dry_run",
    "dry_run_unchanged_verification",
    "V4_backup_from_baseline",
    "apply_approved_property_once",
    "exact_semantic_and_bounded_metadata_diff_verification",
    "rollback_V4_target_from_V4_backup",
    "baseline_restoration_and_property_absence_verification",
]


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def load_plan(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError("V4 plan SHA-256 mismatch")
    plan = json.loads(raw.decode("utf-8", "strict"))
    if plan.get("plan_id") != "mcp-cellview-property-v4-clean-validation":
        raise ValueError("invalid V4 plan id")
    if plan.get("target") != (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4/schematic"
    ):
        raise ValueError("invalid V4 target")
    if plan.get("backup") != (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4_BACKUP/schematic"
    ):
        raise ValueError("invalid V4 backup")
    if len(plan.get("sequence", [])) != 18:
        raise ValueError("invalid V4 sequence")
    if len(plan.get("acceptance_criteria", [])) != 18:
        raise ValueError("invalid V4 acceptance criteria")
    if plan.get("worker_timeout_seconds") != 300:
        raise ValueError("invalid V4 timeout")
    if plan.get("affected_semantic_objects") != 1:
        raise ValueError("invalid V4 affected object count")
    if plan.get("original_library_mutations") != 0 or plan.get("destructive") is not False:
        raise ValueError("invalid V4 mutation boundary")
    if plan.get("automatic_retry_allowed") is not False:
        raise ValueError("invalid V4 retry boundary")
    return plan


def require_hash(value):
    if not HEX_PATTERN.match(value):
        raise ValueError("invalid V4 fingerprint")


def summary_hash(records):
    encoded = ("\n".join(sorted(records)) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_output(path):
    topologies = {}
    properties = dict((scope, []) for scope in SCOPES)
    records = dict(
        (scope, {"instance": [], "net": [], "terminal": []}) for scope in SCOPES
    )
    stages = []
    stage_fields = {}
    metadata = None
    complete = False
    with open(path, "rb") as handle:
        for raw_line in handle:
            raw_line = raw_line.rstrip(b"\r\n")
            if not raw_line.startswith(b"MCP_V4_"):
                continue
            line = raw_line.decode("utf-8", "strict")
            if line.startswith("MCP_V4_FAILURE|"):
                raise ValueError("V4 SKILL reported failure")
            if line.startswith("MCP_V4_TOPOLOGY|"):
                fields = line.split("|")
                if len(fields) != 5 or fields[1] not in SCOPES:
                    raise ValueError("invalid V4 topology")
                topologies[fields[1]] = [int(value) for value in fields[2:]]
            elif line.startswith("MCP_V4_PROPERTY|"):
                fields = line.split("|", 4)
                if len(fields) != 5 or fields[1] not in SCOPES:
                    raise ValueError("invalid V4 property")
                if not SAFE_NAME.match(fields[2]) or len(fields[4]) > 256:
                    raise ValueError("unsafe V4 property")
                properties[fields[1]].append({
                    "name": fields[2], "type": fields[3], "value": fields[4]
                })
            elif line.startswith("MCP_V4_INSTANCE|"):
                fields = line.split("|", 2)
                if len(fields) != 3 or fields[1] not in SCOPES:
                    raise ValueError("invalid V4 instance")
                records[fields[1]]["instance"].append(fields[2])
            elif line.startswith("MCP_V4_NET|"):
                fields = line.split("|", 2)
                if len(fields) != 3 or fields[1] not in SCOPES:
                    raise ValueError("invalid V4 net")
                records[fields[1]]["net"].append(fields[2])
            elif line.startswith("MCP_V4_TERMINAL|"):
                fields = line.split("|", 2)
                if len(fields) != 3 or fields[1] not in SCOPES:
                    raise ValueError("invalid V4 terminal")
                records[fields[1]]["terminal"].append(fields[2])
            elif line.startswith("MCP_V4_METADATA|"):
                fields = line.split("|")
                if len(fields) != 5 or metadata is not None:
                    raise ValueError("invalid V4 metadata transition")
                metadata = {
                    "name": fields[1],
                    "type": fields[2],
                    "before": fields[3],
                    "after": fields[4],
                }
            elif line.startswith("MCP_V4_STAGE|"):
                fields = line.split("|")
                if len(fields) < 3 or fields[1] in stage_fields:
                    raise ValueError("invalid or duplicate V4 stage")
                stages.append(fields[1])
                stage_fields[fields[1]] = fields[2:]
            elif line == "MCP_V4_COMPLETE|V4_CLEAN_VALIDATION_VERIFIED":
                complete = True
            else:
                raise ValueError("unexpected V4 marker")
    if stages != SKILL_SEQUENCE or not complete or set(topologies) != set(SCOPES):
        raise ValueError("incomplete V4 output")
    expected_fields = {
        "source_read_only_verify": ["true", "35", "14", "8", "V3_BASELINE_EQUAL"],
        "V4_copy_from_source": ["true", "35", "14", "8"],
        "baseline_structural_and_property_fingerprint": ["true"],
        "non_mutating_dry_run": ["true", "absent", "1", "0", "false"],
        "dry_run_unchanged_verification": ["true"],
        "V4_backup_from_baseline": ["true"],
        "apply_approved_property_once": ["true", "1"],
        "exact_semantic_and_bounded_metadata_diff_verification": ["true", "1", "1"],
        "rollback_V4_target_from_V4_backup": ["true"],
        "baseline_restoration_and_property_absence_verification": ["true"],
    }
    if stage_fields != expected_fields:
        raise ValueError("V4 stage contract mismatch")
    if metadata is None or metadata["name"] != "schGeometryLastUpdated":
        raise ValueError("missing V4 metadata evidence")
    if metadata["type"] != "int":
        raise ValueError("invalid V4 metadata type")
    return properties, records, metadata


def property_map(items):
    return dict((item["name"], item) for item in items)


def verify_logical_state(properties, records, metadata):
    maps = {}
    logical = {}
    for scope in SCOPES:
        maps[scope] = property_map(properties[scope])
        if len(records[scope]["instance"]) != 35:
            raise ValueError(scope + " V4 instance record mismatch")
        if len(records[scope]["net"]) != 14:
            raise ValueError(scope + " V4 net record mismatch")
        if len(records[scope]["terminal"]) != 8:
            raise ValueError(scope + " V4 terminal record mismatch")
        logical[scope] = {
            "instance_summary_sha256": summary_hash(records[scope]["instance"]),
            "net_summary_sha256": summary_hash(records[scope]["net"]),
            "terminal_summary_sha256": summary_hash(records[scope]["terminal"]),
            "property_summary_sha256": summary_hash([
                item["name"] + "|" + item["type"] + "|" + item["value"]
                for item in properties[scope]
            ]),
        }
    for kind in ("instance", "net", "terminal"):
        key = kind + "_summary_sha256"
        if len(set(logical[scope][key] for scope in SCOPES)) != 1:
            raise ValueError("V4 structural fingerprint changed")
    baseline = maps["baseline"]
    for scope in ("dry_run", "backup", "rollback", "backup_final"):
        if maps[scope] != baseline:
            raise ValueError(scope + " differs from V4 baseline")
    apply_map = maps["apply"]
    mutation = apply_map.get("mcpMutationTest")
    if mutation != {
        "name": "mcpMutationTest", "type": "string", "value": '"validated-v1"'
    }:
        raise ValueError("V4 approved mutation mismatch")
    if "mcpMutationTest" in baseline:
        raise ValueError("V4 baseline contains approved mutation")
    changed_names = set(
        name
        for name in set(baseline) | set(apply_map)
        if baseline.get(name) != apply_map.get(name)
    )
    if changed_names not in (
        set(("mcpMutationTest",)),
        set(("mcpMutationTest", "schGeometryLastUpdated")),
    ):
        raise ValueError("V4 actual apply diff exceeded approved boundary")
    before_geometry = baseline.get("schGeometryLastUpdated")
    after_geometry = apply_map.get("schGeometryLastUpdated")
    if before_geometry is None or after_geometry is None:
        raise ValueError("V4 geometry metadata is missing")
    if before_geometry["type"] != "int" or after_geometry["type"] != "int":
        raise ValueError("V4 geometry metadata type mismatch")
    if metadata["before"] != before_geometry["value"]:
        raise ValueError("V4 metadata before value mismatch")
    if metadata["after"] != after_geometry["value"]:
        raise ValueError("V4 metadata after value mismatch")
    return logical, changed_names


def append_and_verify_audit(path, plan, run_id, origin, actor):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent, 0o700)
    with open(path, "ab") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            for index, stage in enumerate(plan["sequence"]):
                record = {
                    "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "event": "design_write_v4_" + stage,
                    "actor": actor,
                    "origin": origin,
                    "run_id": run_id,
                    "plan_sha256": PLAN_SHA256,
                    "sequence_index": index + 1,
                }
                line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    observed = []
    with open(path, "rb") as handle:
        for raw_line in handle:
            record = json.loads(raw_line.decode("utf-8", "strict"))
            if record.get("run_id") == run_id:
                observed.append(record.get("event"))
    expected = ["design_write_v4_" + stage for stage in plan["sequence"]]
    if observed != expected:
        raise ValueError("V4 audit verification failed")


def write_immutable_manifest(path, payload):
    if os.path.exists(path) or os.path.exists(path + ".pending"):
        raise ValueError("V4 manifest already exists")
    pending = path + ".pending"
    with open(pending, "wb") as handle:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(pending, 0o600)
    os.rename(pending, path)
    os.chmod(path, 0o400)


def finalize(plan, arguments):
    if len(arguments) != 22:
        raise ValueError("invalid V4 finalization")
    run_id = arguments[0]
    output_path = arguments[1]
    protected_hashes = arguments[2:16]
    target_final = arguments[16]
    backup_final = arguments[17]
    origin, actor, audit_path, manifest_path = arguments[18:]
    if not UUID_PATTERN.match(run_id) or origin != "operator":
        raise ValueError("invalid V4 identity")
    for value in protected_hashes + [target_final, backup_final]:
        require_hash(value)
    names = (
        "source",
        "preserved_v1",
        "v2_target",
        "v2_backup",
        "restored_v3_target",
        "v3_backup",
        "pdk",
    )
    pairs = []
    for index, name in enumerate(names):
        before = protected_hashes[index * 2]
        after = protected_hashes[index * 2 + 1]
        if before != after:
            raise ValueError(name + " changed during V4 validation")
        pairs.append((name, before, after))
    properties, records, metadata = parse_output(output_path)
    logical, changed_names = verify_logical_state(properties, records, metadata)
    criteria = [
        {"index": index + 1, "criterion": criterion, "result": "PASS"}
        for index, criterion in enumerate(plan["acceptance_criteria"])
    ]
    payload = {
        "status": "V4_CLEAN_VALIDATION_VERIFIED",
        "run_id": run_id,
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan_id": plan["plan_id"],
        "plan_sha256": PLAN_SHA256,
        "source": plan["source"],
        "target": plan["target"],
        "backup": plan["backup"],
        "sequence": plan["sequence"],
        "acceptance_criteria": criteria,
        "protected_fingerprints": dict(
            (name, {"before": before, "after": after})
            for name, before, after in pairs
        ),
        "target_final_tree_fingerprint": target_final,
        "backup_final_tree_fingerprint": backup_final,
        "logical_fingerprints": logical,
        "actual_apply_diff": {
            "changed_property_names": sorted(changed_names),
            "semantic_change": {
                "name": "mcpMutationTest",
                "type": "string",
                "before_present": False,
                "after_value": "validated-v1",
            },
            "bounded_metadata_side_effect": {
                "name": metadata["name"],
                "type": metadata["type"],
                "before_value": metadata["before"],
                "after_value": metadata["after"],
                "changed": metadata["before"] != metadata["after"],
            },
        },
        "dry_run_unchanged": True,
        "backup_unchanged": True,
        "rollback_verified": True,
        "source_and_prior_evidence_unchanged": True,
        "audit_verified": True,
        "release_gate": "PENDING_REPOSITORY_ACCEPTANCE",
        "tag_or_release_created": False,
    }
    append_and_verify_audit(audit_path, plan, run_id, origin, actor)
    write_immutable_manifest(manifest_path, payload)
    emit(payload)


def main():
    if len(sys.argv) < 3:
        return fail("invalid V4 validation request")
    try:
        plan = load_plan(sys.argv[1])
        command = sys.argv[2]
        arguments = sys.argv[3:]
        if command == "plan-check" and not arguments:
            emit({
                "plan_id": plan["plan_id"],
                "plan_sha256": PLAN_SHA256,
                "acceptance_criteria_count": 18,
                "sequence_count": 18,
                "execution_enabled_by_plan": False,
                "separate_approval_required": True,
            })
        elif command == "confirm" and len(arguments) == 1:
            if arguments[0] != CONFIRMATION:
                raise ValueError("V4 confirmation rejected")
        elif command == "finalize":
            finalize(plan, arguments)
        else:
            return fail("invalid V4 validation command")
    except (IOError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
