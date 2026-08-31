#!/usr/bin/env python
"""Python 2.6-compatible verifier for fixed read-only V3 property forensics."""

from __future__ import print_function

import json
import os
import re
import sys

VALIDATION_ID = "0b9bf93c-11e9-416f-9e4a-69b1060fbd8e"
PLAN_SHA256 = "3362e4fc13874d4f16c78506c24ae6ebd64c882718fe57e9cb2bb60619890c87"
EVIDENCE_ROOT = (
    "/home/buet/cds_work/.cadence_mcp/write-validation-v3/"
    + VALIDATION_ID
    + "/forensic-v1"
)
HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.#-]{0,127}$")
SAFE_TYPE_PATTERN = re.compile(r"^(?:absent|[A-Za-z_][A-Za-z0-9_.#-]{0,63})$")
DIFF_PREFIX = "MCP_V3_FORENSIC_DIFF|"
BASELINE_PREFIX = "MCP_V3_FORENSIC_BASELINE|"
SUMMARY_PREFIX = "MCP_V3_FORENSIC_SUMMARY|"


def fail(message):
    sys.stderr.write(message + "\n")
    return 64


def emit(payload):
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def require_hashes(values):
    if len(values) != 14:
        raise ValueError("invalid V3 forensic fingerprint count")
    for value in values:
        if not HEX_PATTERN.match(value):
            raise ValueError("invalid V3 forensic fingerprint")


def write_once(path, payload):
    if os.path.exists(path):
        raise ValueError("V3 forensic evidence already exists")
    temporary = path + ".tmp"
    with open(temporary, "wb") as handle:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        handle.write(serialized.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.rename(temporary, path)


def parse_output(path):
    baseline = None
    summary = None
    differences = []
    with open(path, "rb") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line.startswith(b"MCP_V3_FORENSIC_"):
                continue
            line = raw_line.decode("ascii", "strict")
            if line.startswith("MCP_V3_FORENSIC_FAILURE|"):
                raise ValueError("V3 forensic SKILL reported failure")
            if line.startswith(BASELINE_PREFIX):
                fields = line.split("|")
                if fields != ["MCP_V3_FORENSIC_BASELINE", "true", "35", "14", "8", "8"]:
                    raise ValueError("invalid V3 forensic baseline marker")
                if baseline is not None:
                    raise ValueError("duplicate V3 forensic baseline marker")
                baseline = True
            elif line.startswith(DIFF_PREFIX):
                fields = line.split("|")
                if len(fields) != 8:
                    raise ValueError("invalid V3 forensic property record")
                name, backup_type, target_type = fields[1:4]
                backup_present, target_present, value_equal, approved_equal = fields[4:8]
                if not SAFE_NAME_PATTERN.match(name):
                    raise ValueError("unsafe V3 forensic property name")
                if not SAFE_TYPE_PATTERN.match(backup_type):
                    raise ValueError("unsafe V3 forensic backup type")
                if not SAFE_TYPE_PATTERN.match(target_type):
                    raise ValueError("unsafe V3 forensic target type")
                if backup_present not in ("true", "false"):
                    raise ValueError("invalid V3 forensic backup presence")
                if target_present not in ("true", "false"):
                    raise ValueError("invalid V3 forensic target presence")
                if value_equal not in ("true", "false"):
                    raise ValueError("invalid V3 forensic equality flag")
                if approved_equal not in ("true", "false", "na"):
                    raise ValueError("invalid V3 approved-value equality flag")
                if backup_present == "false" and backup_type != "absent":
                    raise ValueError("inconsistent V3 forensic backup record")
                if target_present == "false" and target_type != "absent":
                    raise ValueError("inconsistent V3 forensic target record")
                if name == "mcpMutationTest":
                    if approved_equal not in ("true", "false"):
                        raise ValueError("missing approved-value equality result")
                elif approved_equal != "na":
                    raise ValueError("unexpected approved-value equality result")
                differences.append({
                    "name": name,
                    "backup_type": backup_type,
                    "target_type": target_type,
                    "backup_present": backup_present == "true",
                    "target_present": target_present == "true",
                    "value_equal": value_equal == "true",
                    "approved_value_equal": (
                        None if approved_equal == "na" else approved_equal == "true"
                    ),
                })
            elif line.startswith(SUMMARY_PREFIX):
                fields = line.split("|")
                if len(fields) != 6 or fields[1] != "true":
                    raise ValueError("invalid V3 forensic summary marker")
                if fields[3:] != ["35", "14", "8"]:
                    raise ValueError("invalid V3 forensic summary topology")
                if summary is not None:
                    raise ValueError("duplicate V3 forensic summary marker")
                summary = int(fields[2])
            else:
                raise ValueError("unexpected V3 forensic marker")
    if baseline is not True:
        raise ValueError("missing V3 forensic baseline marker")
    if summary is None or summary != len(differences):
        raise ValueError("V3 forensic property count mismatch")
    if not differences or len(differences) > 64:
        raise ValueError("invalid V3 forensic difference count")
    names = [item["name"] for item in differences]
    if len(set(names)) != len(names):
        raise ValueError("duplicate V3 forensic property name")
    return differences


def property_diff(output_path, hashes):
    require_hashes(hashes)
    names = (
        "source",
        "preserved_v1",
        "v2_target",
        "v2_backup",
        "v3_target",
        "v3_backup",
        "pdk",
    )
    fingerprints = {}
    for index, name in enumerate(names):
        before = hashes[index * 2]
        after = hashes[index * 2 + 1]
        if before != after:
            raise ValueError(name + " changed during V3 read-only forensic inspection")
        fingerprints[name] = {"before": before, "after": after}
    differences = parse_output(output_path)
    payload = {
        "validation_id": VALIDATION_ID,
        "plan_sha256": PLAN_SHA256,
        "property_diff_verified": True,
        "read_only_verified": True,
        "source_topology": [35, 14, 8],
        "target_topology": [35, 14, 8],
        "backup_topology": [35, 14, 8],
        "protected_fingerprints": fingerprints,
        "difference_count": len(differences),
        "differences": differences,
        "property_values_included": False,
    }
    write_once(os.path.join(EVIDENCE_ROOT, "v3-property-diff-evidence.json"), payload)
    emit(payload)


def main():
    if len(sys.argv) != 17:
        return fail("invalid V3 forensic evidence request")
    command = sys.argv[1]
    output_path = sys.argv[2]
    hashes = sys.argv[3:]
    try:
        if command != "property-diff":
            return fail("invalid V3 forensic evidence command")
        property_diff(output_path, hashes)
    except (IOError, OSError, UnicodeError, ValueError, TypeError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
