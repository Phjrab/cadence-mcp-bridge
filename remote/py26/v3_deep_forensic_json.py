#!/usr/bin/env python
"""Python 2.6-compatible fixed three-object V3 deep-forensic reporter."""

from __future__ import print_function

import datetime
import hashlib
import json
import os
import re
import stat
import sys

VALIDATION_ID = "0b9bf93c-11e9-416f-9e4a-69b1060fbd8e"
VALIDATION_ROOT = "/home/buet/cds_work/.cadence_mcp/write-validation-v3/" + VALIDATION_ID
AUDIT_PATH = "/home/buet/cds_work/.cadence_mcp/audit/write-events.jsonl"
SOURCE_VIEW = "/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic"
TARGET_VIEW = (
    "/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic"
)
BACKUP_VIEW = (
    "/home/buet/cds_work/MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic"
)
EXPECTED_APPROVED_VALUE = '"validated-v1"'
HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.#-]{0,127}$")
SAFE_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.#-]{0,63}$")
SCOPES = ("source", "target", "backup")
RECORD_LIMITS = {"instance": 35, "net": 14, "terminal": 8}
MAX_RECORDS = {"instance": 512, "net": 512, "terminal": 256}


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def require_hashes(values):
    if len(values) != 6:
        raise ValueError("invalid deep-forensic fingerprint count")
    for value in values:
        if not HEX_PATTERN.match(value):
            raise ValueError("invalid deep-forensic fingerprint")


def summary_hash(records):
    encoded = ("\n".join(sorted(records)) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_skill_output(path):
    topologies = {}
    properties = dict((scope, []) for scope in SCOPES)
    records = dict((scope, dict((kind, []) for kind in RECORD_LIMITS)) for scope in SCOPES)
    completed = False
    with open(path, "rb") as handle:
        for raw_line in handle:
            raw_line = raw_line.rstrip(b"\r\n")
            if not raw_line.startswith(b"MCP_V3_DEEP_"):
                continue
            line = raw_line.decode("utf-8", "strict")
            if line.startswith("MCP_V3_DEEP_FAILURE|"):
                raise ValueError("V3 deep-forensic SKILL reported failure")
            if line.startswith("MCP_V3_DEEP_TOPOLOGY|"):
                fields = line.split("|")
                if len(fields) != 5 or fields[1] not in SCOPES:
                    raise ValueError("invalid deep-forensic topology record")
                scope = fields[1]
                if scope in topologies:
                    raise ValueError("duplicate deep-forensic topology")
                topologies[scope] = [int(value) for value in fields[2:]]
            elif line.startswith("MCP_V3_DEEP_PROPERTY|"):
                fields = line.split("|", 5)
                if len(fields) != 6 or fields[1] not in SCOPES or fields[2] != "cellview":
                    raise ValueError("invalid deep-forensic property record")
                scope, name, value_type, value = fields[1], fields[3], fields[4], fields[5]
                if not SAFE_NAME_PATTERN.match(name) or not SAFE_TYPE_PATTERN.match(value_type):
                    raise ValueError("unsafe deep-forensic property metadata")
                if len(value) > 256:
                    raise ValueError("deep-forensic property value is too large")
                properties[scope].append({
                    "name": name,
                    "type": value_type,
                    "value": value,
                    "object_scope": "cellview",
                })
            elif line.startswith("MCP_V3_DEEP_INSTANCE|"):
                fields = line.split("|", 2)
                if len(fields) != 3 or fields[1] not in SCOPES:
                    raise ValueError("invalid deep-forensic instance record")
                records[fields[1]]["instance"].append(fields[2])
            elif line.startswith("MCP_V3_DEEP_NET|"):
                fields = line.split("|", 2)
                if len(fields) != 3 or fields[1] not in SCOPES:
                    raise ValueError("invalid deep-forensic net record")
                records[fields[1]]["net"].append(fields[2])
            elif line.startswith("MCP_V3_DEEP_TERMINAL|"):
                fields = line.split("|", 2)
                if len(fields) != 3 or fields[1] not in SCOPES:
                    raise ValueError("invalid deep-forensic terminal record")
                records[fields[1]]["terminal"].append(fields[2])
            elif line == "MCP_V3_DEEP_COMPLETE|true":
                if completed:
                    raise ValueError("duplicate deep-forensic completion marker")
                completed = True
            else:
                raise ValueError("unexpected deep-forensic marker")
    if not completed or set(topologies) != set(SCOPES):
        raise ValueError("incomplete deep-forensic output")
    if topologies["source"] != [35, 14, 8]:
        raise ValueError("BLOCKED_SOURCE_CHANGED")
    for scope in SCOPES:
        if len(properties[scope]) > 64:
            raise ValueError("too many deep-forensic properties")
        names = [item["name"] for item in properties[scope]]
        if len(set(names)) != len(names):
            raise ValueError("duplicate deep-forensic property")
        expected_by_kind = {
            "instance": topologies[scope][0],
            "net": topologies[scope][1],
            "terminal": topologies[scope][2],
        }
        for kind, expected_count in expected_by_kind.items():
            if expected_count < 0 or expected_count > MAX_RECORDS[kind]:
                raise ValueError(scope + " " + kind + " count exceeds forensic bound")
            if len(records[scope][kind]) != expected_count:
                raise ValueError(scope + " " + kind + " count mismatch")
    return topologies, properties, records


def property_map(items):
    return dict((item["name"], item) for item in items)


def annotate_properties(properties):
    maps = dict((scope, property_map(properties[scope])) for scope in SCOPES)
    annotated = {}
    for scope in SCOPES:
        annotated[scope] = []
        for item in sorted(properties[scope], key=lambda record: record["name"]):
            record = dict(item)
            record["present_in_source"] = item["name"] in maps["source"]
            record["present_in_target"] = item["name"] in maps["target"]
            record["present_in_backup"] = item["name"] in maps["backup"]
            annotated[scope].append(record)
    return annotated, maps


def diff_maps(left, right, source):
    differences = []
    for name in sorted(set(left) | set(right)):
        left_item = left.get(name)
        right_item = right.get(name)
        if left_item == right_item:
            continue
        differences.append({
            "name": name,
            "left_present": left_item is not None,
            "right_present": right_item is not None,
            "left_type": None if left_item is None else left_item["type"],
            "right_type": None if right_item is None else right_item["type"],
            "left_value": None if left_item is None else left_item["value"],
            "right_value": None if right_item is None else right_item["value"],
            "value_equal": (
                left_item is not None
                and right_item is not None
                and left_item["value"] == right_item["value"]
            ),
            "present_in_source": name in source,
            "source_type": None if name not in source else source[name]["type"],
            "source_value": None if name not in source else source[name]["value"],
            "approved_mutation": name == "mcpMutationTest",
            "baseline_property": name != "mcpMutationTest" and name in source,
        })
    return differences


def original_validation_evidence():
    stdout_path = os.path.join(VALIDATION_ROOT, "skill.stdout")
    manifest_path = os.path.join(VALIDATION_ROOT, "validation-manifest.json")
    stages = []
    failure = None
    with open(stdout_path, "rb") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if raw_line.startswith(b"MCP_V3_STAGE|"):
                fields = raw_line.decode("ascii", "strict").split("|")
                stages.append(fields[1])
            elif raw_line.startswith(b"MCP_V3_FAILURE|"):
                failure = raw_line.decode("ascii", "strict").split("|", 1)[1]
    audit_count = 0
    if os.path.isfile(AUDIT_PATH):
        with open(AUDIT_PATH, "rb") as handle:
            for raw_line in handle:
                if VALIDATION_ID.encode("ascii") in raw_line:
                    audit_count += 1
    stdout_stat = os.stat(stdout_path)
    timestamp = datetime.datetime.utcfromtimestamp(stdout_stat.st_mtime).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "validation_runtime": "present",
        "validation_stdout_path": stdout_path,
        "validation_timestamp_utc": timestamp,
        "validation_manifest": "present" if os.path.isfile(manifest_path) else "missing",
        "validation_manifest_path": manifest_path,
        "audit_record": "present" if audit_count else "missing",
        "audit_path": AUDIT_PATH,
        "audit_record_count": audit_count,
        "runner_job_record": (
            "present"
            if os.path.isdir("/home/buet/cds_work/.cadence_mcp/jobs/" + VALIDATION_ID)
            else "missing"
        ),
        "runner_job_record_path": (
            "/home/buet/cds_work/.cadence_mcp/jobs/" + VALIDATION_ID
        ),
        "run_id": VALIDATION_ID,
        "source": "MyDesignLib/Differential_Amplifier_TB2/schematic",
        "target": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic",
        "backup": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic",
        "requested_mutation": "mcpMutationTest string validated-v1",
        "completed_stages": stages,
        "dry_run_result": "passed" if "unchanged_verification" in stages else "not_verified",
        "apply_result": "applied" if "apply" in stages else "not_applied",
        "rollback_state": "not_run" if "rollback" not in stages else "reported",
        "error": failure,
    }


def file_metadata(path):
    result = []
    for filename in ("master.tag", "sch.oa"):
        full_path = os.path.join(path, filename)
        details = os.stat(full_path)
        result.append({
            "name": filename,
            "size": details.st_size,
            "mode": "%04o" % stat.S_IMODE(details.st_mode),
            "uid": details.st_uid,
            "gid": details.st_gid,
            "mtime_utc": datetime.datetime.utcfromtimestamp(details.st_mtime).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        })
    return result


def write_once(path, payload):
    if os.path.exists(path):
        raise ValueError("deep-forensic report already exists")
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.rename(temporary, path)


def deep_forensic(output_path, report_path, hashes):
    require_hashes(hashes)
    fingerprint_names = ("source", "target", "backup")
    tree_fingerprints = {}
    for index, name in enumerate(fingerprint_names):
        before = hashes[index * 2]
        after = hashes[index * 2 + 1]
        if before != after:
            raise ValueError(name + " changed during deep-forensic inspection")
        tree_fingerprints[name] = {"before": before, "after": after}

    topologies, properties, records = parse_skill_output(output_path)
    annotated, maps = annotate_properties(properties)
    structural = {}
    for scope in SCOPES:
        structural[scope] = {
            "topology": topologies[scope],
            "instance_summary_sha256": summary_hash(records[scope]["instance"]),
            "net_summary_sha256": summary_hash(records[scope]["net"]),
            "terminal_summary_sha256": summary_hash(records[scope]["terminal"]),
            "property_summary_sha256": summary_hash(
                [
                    item["name"] + "|" + item["type"] + "|" + item["value"]
                    for item in properties[scope]
                ]
            ),
        }

    target_backup_diff = diff_maps(maps["target"], maps["backup"], maps["source"])
    target_source_diff = diff_maps(maps["target"], maps["source"], maps["source"])
    backup_source_diff = diff_maps(maps["backup"], maps["source"], maps["source"])
    expected_names = set(("schGeometryLastUpdated", "mcpMutationTest"))
    target_diff_names = set(item["name"] for item in target_backup_diff)
    approved = maps["target"].get("mcpMutationTest")
    baseline_target = maps["target"].get("schGeometryLastUpdated")
    baseline_backup = maps["backup"].get("schGeometryLastUpdated")
    target_backup_structure_matches = (
        structural["target"]["topology"] == structural["backup"]["topology"]
        and all(
        structural["target"][key] == structural["backup"][key]
        for key in (
            "instance_summary_sha256",
            "net_summary_sha256",
            "terminal_summary_sha256",
        )
        )
    )
    all_structure_matches_source = all(
        structural[scope]["topology"] == structural["source"]["topology"]
        and all(
            structural[scope][key] == structural["source"][key]
            for key in (
                "instance_summary_sha256",
                "net_summary_sha256",
                "terminal_summary_sha256",
            )
        )
        for scope in ("target", "backup")
    )
    backup_structure_matches_source = all(
        structural["backup"][key] == structural["source"][key]
        for key in (
            "instance_summary_sha256",
            "net_summary_sha256",
            "terminal_summary_sha256",
        )
    )
    original = original_validation_evidence()
    exact_diff_explained = (
        target_diff_names == expected_names
        and baseline_target is not None
        and baseline_backup is not None
        and baseline_target["type"] == "int"
        and baseline_backup["type"] == "int"
        and baseline_target["value"] != baseline_backup["value"]
        and approved is not None
        and approved["type"] == "string"
        and approved["value"] == EXPECTED_APPROVED_VALUE
        and "mcpMutationTest" not in maps["backup"]
    )
    original_sequence_supports_backup = (
        "backup" in original["completed_stages"]
        and "apply" in original["completed_stages"]
        and original["completed_stages"].index("backup")
        < original["completed_stages"].index("apply")
    )
    safe = (
        target_backup_structure_matches
        and all_structure_matches_source
        and exact_diff_explained
        and original_sequence_supports_backup
    )
    if safe:
        classification = "SAFE_ROLLBACK_CANDIDATE"
    elif not target_backup_structure_matches or not all_structure_matches_source:
        classification = "UNSAFE_TO_ROLLBACK"
    else:
        classification = "AMBIGUOUS_FORENSICS"

    payload = {
        "forensic_classification": classification,
        "validation_id": VALIDATION_ID,
        "read_only_verified": True,
        "tree_fingerprints": tree_fingerprints,
        "structural_fingerprints": structural,
        "properties": annotated,
        "property_diffs": {
            "target_minus_backup": target_backup_diff,
            "backup_minus_target": diff_maps(
                maps["backup"], maps["target"], maps["source"]
            ),
            "target_minus_source": target_source_diff,
            "backup_minus_source": backup_source_diff,
        },
        "identified_baseline_property": baseline_target,
        "approved_mutation_property": approved,
        "backup_validity": {
            "read_only_open": True,
            "structure_matches_target": target_backup_structure_matches,
            "log_proves_backup_before_apply": original_sequence_supports_backup,
            "matches_source_structural_baseline": backup_structure_matches_source,
            "property_set_equals_source": maps["backup"] == maps["source"],
            "approved_property_absent": "mcpMutationTest" not in maps["backup"],
            "corruption_observed": False,
        },
        "file_metadata": {
            "source": file_metadata(SOURCE_VIEW),
            "target": file_metadata(TARGET_VIEW),
            "backup": file_metadata(BACKUP_VIEW),
        },
        "original_validation": original,
        "rollback_safety": {
            "safe_candidate": safe,
            "exact_diff_explained": exact_diff_explained,
            "topology_or_structure_difference": not all_structure_matches_source,
            "actual_rollback_performed": False,
        },
    }
    write_once(report_path, payload)
    emit(payload)


def main():
    if len(sys.argv) != 10:
        return fail("invalid V3 deep-forensic request")
    command = sys.argv[1]
    output_path = sys.argv[2]
    report_path = sys.argv[3]
    hashes = sys.argv[4:]
    try:
        if command != "report":
            return fail("invalid V3 deep-forensic command")
        deep_forensic(output_path, report_path, hashes)
    except (IOError, OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
