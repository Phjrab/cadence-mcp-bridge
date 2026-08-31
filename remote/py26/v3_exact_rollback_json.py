#!/usr/bin/env python
"""Python 2.6-compatible verifier for the exact approved V3 rollback."""

from __future__ import print_function

import datetime
import fcntl
import hashlib
import json
import os
import re
import sys

PLAN_SHA256 = "eb057da2a866b92be5e1474bc3d06aba05f6ae49b5001465dd65ed9921afc911"
REPORT_SHA256 = "6329eafc458098b744a40b70fc0a1a0d876af57c326d2d79e854e1ceaeb9b02f"
CONFIRMATION = "APPROVE_V3_ROLLBACK_EB057DA2"
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.#-]{0,127}$")
SCOPES = (
    "source_before",
    "target_before",
    "backup_before",
    "source_after",
    "target_after",
    "backup_after",
)
STAGES = ["read_only_preconditions", "dry_run", "rollback", "post_verify"]


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def load_plan(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError("BLOCKED_PLAN_HASH_MISMATCH")
    plan = json.loads(raw.decode("utf-8", "strict"))
    if plan.get("plan_id") != "mcp-cellview-property-v3-exact-conditional-rollback":
        raise ValueError("invalid exact rollback plan id")
    if len(plan.get("acceptance_criteria", [])) != 15:
        raise ValueError("invalid exact rollback acceptance criteria")
    if len(plan.get("conditional_sequence", [])) != 14:
        raise ValueError("invalid exact rollback sequence")
    if plan.get("target") != "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic":
        raise ValueError("invalid exact rollback target")
    if plan.get("backup") != (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic"
    ):
        raise ValueError("invalid exact rollback backup")
    if plan.get("source") != "MyDesignLib/Differential_Amplifier_TB2/schematic":
        raise ValueError("invalid exact rollback source")
    if len(plan.get("exact_expected_property_changes", [])) != 2:
        raise ValueError("invalid exact rollback diff")
    return plan


def require_hash(value):
    if not HEX_PATTERN.match(value):
        raise ValueError("invalid exact rollback fingerprint")


def preflight(plan, hashes):
    if len(hashes) != 4:
        raise ValueError("invalid exact rollback preflight")
    for value in hashes:
        require_hash(value)
    expected = plan["current_tree_fingerprints"]
    if hashes[0] != expected["source"]:
        raise ValueError("source fingerprint precondition failed")
    if hashes[1] != expected["target"]:
        raise ValueError("target fingerprint precondition failed")
    if hashes[2] != expected["backup"]:
        raise ValueError("backup fingerprint precondition failed")
    if hashes[3] != REPORT_SHA256 or hashes[3] != plan["forensic_report_sha256"]:
        raise ValueError("forensic report fingerprint precondition failed")
    emit({
        "plan_sha256": PLAN_SHA256,
        "forensic_report_sha256": REPORT_SHA256,
        "preconditions_verified": True,
    })


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
    complete = False
    with open(path, "rb") as handle:
        for raw_line in handle:
            raw_line = raw_line.rstrip(b"\r\n")
            if not raw_line.startswith(b"MCP_V3_ROLLBACK_"):
                continue
            line = raw_line.decode("utf-8", "strict")
            if line.startswith("MCP_V3_ROLLBACK_FAILURE|"):
                raise ValueError("V3 rollback SKILL reported failure")
            if line.startswith("MCP_V3_ROLLBACK_TOPOLOGY|"):
                fields = line.split("|")
                if len(fields) != 5 or fields[1] not in SCOPES:
                    raise ValueError("invalid rollback topology")
                topologies[fields[1]] = [int(value) for value in fields[2:]]
            elif line.startswith("MCP_V3_ROLLBACK_PROPERTY|"):
                fields = line.split("|", 4)
                if len(fields) != 5 or fields[1] not in SCOPES:
                    raise ValueError("invalid rollback property")
                if not SAFE_NAME.match(fields[2]) or len(fields[4]) > 256:
                    raise ValueError("unsafe rollback property")
                properties[fields[1]].append({
                    "name": fields[2], "type": fields[3], "value": fields[4]
                })
            elif line.startswith("MCP_V3_ROLLBACK_INSTANCE|"):
                fields = line.split("|", 2)
                records[fields[1]]["instance"].append(fields[2])
            elif line.startswith("MCP_V3_ROLLBACK_NET|"):
                fields = line.split("|", 2)
                records[fields[1]]["net"].append(fields[2])
            elif line.startswith("MCP_V3_ROLLBACK_TERMINAL|"):
                fields = line.split("|", 2)
                records[fields[1]]["terminal"].append(fields[2])
            elif line.startswith("MCP_V3_ROLLBACK_STAGE|"):
                fields = line.split("|")
                if fields[1] in stage_fields:
                    raise ValueError("duplicate rollback stage")
                stages.append(fields[1])
                stage_fields[fields[1]] = fields[2:]
            elif line == "MCP_V3_ROLLBACK_COMPLETE|V3_ROLLBACK_VERIFIED":
                complete = True
            else:
                raise ValueError("unexpected rollback marker")
    if stages != STAGES or not complete or set(topologies) != set(SCOPES):
        raise ValueError("incomplete rollback output")
    expected_stage_fields = {
        "read_only_preconditions": ["true"],
        "dry_run": ["true", "2", "0", "false"],
        "rollback": ["true"],
        "post_verify": ["true"],
    }
    if stage_fields != expected_stage_fields:
        raise ValueError("rollback stage contract mismatch")
    for scope in SCOPES:
        if topologies[scope] != [35, 14, 8]:
            raise ValueError("rollback topology mismatch")
        if len(records[scope]["instance"]) != 35:
            raise ValueError("rollback instance record mismatch")
        if len(records[scope]["net"]) != 14:
            raise ValueError("rollback net record mismatch")
        if len(records[scope]["terminal"]) != 8:
            raise ValueError("rollback terminal record mismatch")
    return properties, records


def property_map(items):
    return dict((item["name"], item) for item in items)


def verify_logical_state(plan, properties, records):
    expected = plan["expected_structural_fingerprints"]
    logical = {}
    maps = {}
    for scope in SCOPES:
        maps[scope] = property_map(properties[scope])
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
            if logical[scope][key] != expected[key]:
                raise ValueError(scope + " structural fingerprint mismatch")
    if maps["source_before"] != maps["backup_before"]:
        raise ValueError("backup pre-state differs from source")
    if maps["source_after"] != maps["source_before"]:
        raise ValueError("source logical state changed")
    if maps["backup_after"] != maps["backup_before"]:
        raise ValueError("backup logical state changed")
    if maps["target_after"] != maps["backup_after"]:
        raise ValueError("target was not restored from backup")
    if logical["target_before"]["property_summary_sha256"] != (
        expected["target_property_summary_before_sha256"]
    ):
        raise ValueError("target pre-state property fingerprint mismatch")
    for scope in ("source_before", "backup_before", "source_after", "target_after", "backup_after"):
        if logical[scope]["property_summary_sha256"] != expected["backup_property_summary_sha256"]:
            raise ValueError(scope + " baseline property fingerprint mismatch")
    before = maps["target_before"]
    after = maps["target_after"]
    changed_names = set(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    if changed_names != set(("mcpMutationTest", "schGeometryLastUpdated")):
        raise ValueError("actual rollback diff mismatch")
    if before["mcpMutationTest"] != {
        "name": "mcpMutationTest", "type": "string", "value": '"validated-v1"'
    } or "mcpMutationTest" in after:
        raise ValueError("approved mutation rollback mismatch")
    if before["schGeometryLastUpdated"]["value"] != "107169" or (
        after["schGeometryLastUpdated"]["value"] != "107168"
    ):
        raise ValueError("baseline property rollback mismatch")
    return logical


def append_audit(path, plan, run_id, origin, actor):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent, 0o700)
    with open(path, "ab") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            for index, stage in enumerate(plan["conditional_sequence"]):
                record = {
                    "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "event": "design_write_v3_exact_rollback_" + stage,
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
    expected = [
        "design_write_v3_exact_rollback_" + stage
        for stage in plan["conditional_sequence"]
    ]
    if observed != expected:
        raise ValueError("rollback audit verification failed")


def prepare_manifest(path, payload):
    if os.path.exists(path) or os.path.exists(path + ".pending"):
        raise ValueError("rollback manifest already exists")
    pending = path + ".pending"
    with open(pending, "wb") as handle:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(pending, 0o600)
    return pending


def finalize_manifest(pending, path):
    os.rename(pending, path)
    os.chmod(path, 0o400)


def finalize(plan, args):
    if len(args) != 13:
        raise ValueError("invalid exact rollback finalization")
    run_id, output_path = args[:2]
    hashes = args[2:9]
    origin, actor, audit_path, manifest_path = args[9:]
    if not UUID_PATTERN.match(run_id) or origin != "operator":
        raise ValueError("invalid exact rollback identity")
    for value in hashes:
        require_hash(value)
    source_before, source_after, target_before, target_after = hashes[:4]
    backup_before, backup_after, report_hash = hashes[4:]
    expected = plan["current_tree_fingerprints"]
    if source_before != expected["source"] or source_after != source_before:
        raise ValueError("source changed during exact rollback")
    if backup_before != expected["backup"] or backup_after != backup_before:
        raise ValueError("backup changed during exact rollback")
    if target_before != expected["target"] or target_after == target_before:
        raise ValueError("target tree transition mismatch")
    if report_hash != REPORT_SHA256:
        raise ValueError("forensic report changed during exact rollback")
    properties, records = parse_output(output_path)
    logical = verify_logical_state(plan, properties, records)
    criteria = [
        {"index": index + 1, "criterion": criterion, "result": "PASS"}
        for index, criterion in enumerate(plan["acceptance_criteria"])
    ]
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "status": "V3_ROLLBACK_VERIFIED",
        "run_id": run_id,
        "timestamp": timestamp,
        "plan_sha256": PLAN_SHA256,
        "forensic_report_sha256": REPORT_SHA256,
        "source": plan["source"],
        "target": plan["target"],
        "backup": plan["backup"],
        "requested_operation": plan["operation"],
        "tree_fingerprints": {
            "source": {"before": source_before, "after": source_after},
            "target": {"before": target_before, "after": target_after},
            "backup": {"before": backup_before, "after": backup_after},
        },
        "logical_fingerprints": logical,
        "actual_rollback_diff": plan["exact_expected_property_changes"],
        "acceptance_criteria": criteria,
        "source_unchanged": True,
        "backup_unchanged": True,
        "audit_path": audit_path,
        "original_validation_manifest": "missing",
        "original_validation_audit": "missing",
        "original_runner_job_record": "missing",
        "release_gate": "FAILED",
        "v4_clean_validation_authorized": False,
    }
    pending = prepare_manifest(manifest_path, payload)
    append_audit(audit_path, plan, run_id, origin, actor)
    finalize_manifest(pending, manifest_path)
    emit(payload)


def main():
    if len(sys.argv) < 3:
        return fail("invalid exact rollback request")
    try:
        plan = load_plan(sys.argv[1])
        command = sys.argv[2]
        args = sys.argv[3:]
        if command == "plan-check" and not args:
            emit({
                "plan_sha256": PLAN_SHA256,
                "acceptance_criteria_count": 15,
                "sequence_count": 14,
                "execution_enabled_by_plan": False,
            })
        elif command == "confirm" and len(args) == 1:
            if args[0] != CONFIRMATION:
                raise ValueError("exact rollback confirmation rejected")
        elif command == "preflight":
            preflight(plan, args)
        elif command == "finalize":
            finalize(plan, args)
        else:
            return fail("invalid exact rollback command")
    except (IOError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
