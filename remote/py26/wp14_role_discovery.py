#!/usr/bin/env python
"""Python 2.6-compatible redaction boundary for fixed WP-14 OA discovery."""

from __future__ import with_statement

import hashlib
import json
import os
import re
import stat
import sys

PLAN_ID = "WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN"
PLAN_SHA256 = "2e44ca523c122744f6b16036785f285fc0f6a3d7b1b904326fe84ecc9165f12d"
SOURCE_FINGERPRINT = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
DOMAIN_SEPARATOR = "wp14-role-selector-v1"
ROOT = "/home/buet/cds_work/.cadence_mcp"
RUNTIME = ROOT + "/wp14-role-discovery"
BEFORE_PATH = RUNTIME + "/before.json"
SOURCE_DIRECTORY = "/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic"
SOURCE_SNAPSHOT = (
    "/home/buet/simulation/Differential_Amplifier_TB2/spectre/schematic/netlist/netlist"
)
STATE_DIRECTORY = "/home/buet/.artist_states/MyDesignLib/Differential_Amplifier_TB2/spectre/state1"
PROFILE_PATH = ROOT + "/profiles/actual-differential-amplifier-tb2-transient/profile.json"
MODEL_PATH = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"

MAX_JSON_BYTES = 64 * 1024
MAX_STREAM_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
MAX_TREE_ENTRIES = 4096
MAX_TREE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_CANDIDATES = 16
ROLES = ("VDD", "VCM", "load_condition")
MASTER_CLASSES = (
    "independent_voltage_source",
    "independent_current_source",
    "resistor",
    "capacitor",
)
CONNECTION_ROLES = (
    "reference_connected_two_terminal",
    "global_supply_candidate",
    "common_mode_stimulus_candidate",
    "differential_input_branch_candidate",
    "differential_output_load_candidate",
    "single_ended_output_load_candidate",
    "nonreference_two_terminal",
    "unclassified",
)
SLOT_CLASSES = (
    "voltage_dc_slot",
    "current_dc_slot",
    "resistance_slot",
    "capacitance_slot",
)
BLOCKER_ENUMS = (
    "blocking_lock",
    "ambiguous_lock",
    "panic_or_recovery_artifact",
    "source_fingerprint_mismatch",
    "topology_mismatch",
    "unsupported_candidate",
    "candidate_limit_exceeded",
    "property_limit_exceeded",
    "fingerprint_drift",
    "lock_state_drift",
    "oa_lifecycle_failure",
    "redaction_failure",
)
SAFE_PRIVATE_TOKEN = re.compile(r"^[A-Za-z0-9_!$<>/+.:@-]{1,128}$")
PRIVATE_PREFIX = "MCP_WP14_PRIVATE|"
BLOCKER_PREFIX = "MCP_WP14_BLOCKER|"
TOPOLOGY_PATTERN = re.compile(r"^MCP_WP14_TOPOLOGY[|]([0-9]+)[|]([0-9]+)[|]([0-9]+)[|]([0-9]+)$")
COMPLETE_PATTERN = re.compile(r"^MCP_WP14_COMPLETE[|]true[|]true$")


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _read_bounded(path, maximum_bytes, allow_empty=False):
    if os.path.islink(path):
        raise ValueError("symlink")
    metadata = os.stat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
        raise ValueError("invalid file")
    if not allow_empty and metadata.st_size <= 0:
        raise ValueError("empty file")
    with open(path, "rb") as handle:
        content = handle.read(maximum_bytes + 1)
    if len(content) != metadata.st_size or len(content) > maximum_bytes:
        raise ValueError("file changed")
    return content


def _tree_fingerprint(root):
    if os.path.islink(root) or not os.path.isdir(root) or not os.access(root, os.R_OK):
        raise ValueError("invalid tree")
    digest = hashlib.sha256()
    entries = 0
    total_bytes = 0
    for current_root, directory_names, file_names in os.walk(root):
        directory_names.sort()
        file_names.sort()
        for name in directory_names + file_names:
            path = os.path.join(current_root, name)
            if os.path.islink(path):
                raise ValueError("tree symlink")
            metadata = os.stat(path)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if stat.S_ISDIR(metadata.st_mode):
                kind = "d"
                content_hash = "-"
            elif stat.S_ISREG(metadata.st_mode):
                kind = "f"
                total_bytes += metadata.st_size
                if total_bytes > MAX_TREE_BYTES:
                    raise ValueError("tree bytes")
                content_hash = _sha256(_read_bounded(path, MAX_TREE_BYTES, True))
            else:
                raise ValueError("tree object")
            entries += 1
            if entries > MAX_TREE_ENTRIES:
                raise ValueError("tree entries")
            record = "%s\0%s\0%s\0%s\0%s\n" % (
                kind,
                relative,
                metadata.st_size,
                int(metadata.st_mtime),
                content_hash,
            )
            digest.update(record.encode("utf-8"))
    return {"entry_count": entries, "sha256": digest.hexdigest(), "total_bytes": total_bytes}


def _blocker_classes(root):
    classes = set()
    entries = 0
    for _current_root, directory_names, file_names in os.walk(root):
        directory_names.sort()
        file_names.sort()
        for name in directory_names + file_names:
            entries += 1
            if entries > MAX_TREE_ENTRIES:
                raise ValueError("blocker scan bound")
            lowered = name.lower()
            if "cdslck" in lowered:
                classes.add("blocking_lock")
            elif lowered == "lock" or lowered.endswith(".lock"):
                classes.add("ambiguous_lock")
            elif "panic" in lowered or "recover" in lowered:
                classes.add("panic_or_recovery_artifact")
    return sorted(classes)


def build_snapshot():
    source_snapshot = _read_bounded(SOURCE_SNAPSHOT, MAX_SOURCE_BYTES)
    profile = _read_bounded(PROFILE_PATH, MAX_JSON_BYTES)
    model = _read_bounded(MODEL_PATH, MAX_MODEL_BYTES)
    source_tree = _tree_fingerprint(SOURCE_DIRECTORY)
    state_tree = _tree_fingerprint(STATE_DIRECTORY)
    blockers = sorted(set(_blocker_classes(SOURCE_DIRECTORY) + _blocker_classes(STATE_DIRECTORY)))
    return {
        "blockers": blockers,
        "locks": blockers,
        "protected": {
            "ade_state_tree": state_tree["sha256"],
            "fixed_profile_registry": _sha256(profile),
            "pdk_model_file": _sha256(model),
            "source_cellview_tree": source_tree["sha256"],
            "source_snapshot": _sha256(source_snapshot),
        },
        "source_tree": source_tree,
    }


def _candidate(role, master_class, connection_role, slot_class, private_fields):
    if role not in ROLES or master_class not in MASTER_CLASSES:
        raise ValueError("candidate enum")
    if connection_role not in CONNECTION_ROLES or slot_class not in SLOT_CLASSES:
        raise ValueError("candidate enum")
    canonical = "\0".join((DOMAIN_SEPARATOR, SOURCE_FINGERPRINT) + tuple(private_fields))
    commitment = _sha256(canonical.encode("utf-8"))
    return {
        "connection_role": connection_role,
        "master_class": master_class,
        "property_slot_class": slot_class,
        "selector_commitment_sha256": commitment,
        "semantically_confirmed": False,
        "source_fingerprint_bound": True,
        "terminal_count": 2,
    }


def parse_private_stream(stream_text):
    if len(stream_text.encode("latin-1")) > MAX_STREAM_BYTES:
        raise ValueError("stream bound")
    roles = dict((role, []) for role in ROLES)
    unsupported = dict((role, False) for role in ROLES)
    topology = None
    complete = False
    for raw_line in stream_text.splitlines():
        line = raw_line.strip()
        match = TOPOLOGY_PATTERN.match(line)
        if match is not None:
            if topology is not None:
                raise ValueError("duplicate topology")
            topology = tuple(int(value) for value in match.groups())
            continue
        if COMPLETE_PATTERN.match(line) is not None:
            complete = True
            continue
        if line.startswith(BLOCKER_PREFIX):
            parts = line.split("|")
            if len(parts) != 3 or parts[1] not in ROLES or parts[2] != "unsupported_candidate":
                raise ValueError("blocker marker")
            unsupported[parts[1]] = True
            continue
        if not line.startswith(PRIVATE_PREFIX):
            continue
        parts = line.split("|")
        if len(parts) != 12:
            raise ValueError("private marker")
        role, master_class, connection_role, slot_class = parts[1:5]
        if parts[5] != "2":
            raise ValueError("terminal count")
        private_fields = parts[6:12]
        for value in private_fields[:4] + private_fields[5:]:
            if SAFE_PRIVATE_TOKEN.match(value) is None:
                raise ValueError("unsafe private token")
        ordered_pairs = private_fields[4].split(",")
        if len(ordered_pairs) != 2 or ordered_pairs != sorted(ordered_pairs):
            raise ValueError("terminal pairs")
        for value in ordered_pairs:
            if SAFE_PRIVATE_TOKEN.match(value) is None:
                raise ValueError("unsafe terminal pair")
        roles[role].append(
            _candidate(role, master_class, connection_role, slot_class, private_fields)
        )
        if len(roles[role]) > MAX_CANDIDATES:
            raise OverflowError("candidate bound")
    if topology is None or not complete:
        raise ValueError("OA lifecycle")
    if topology[:3] != (35, 14, 8):
        raise ArithmeticError("topology")
    if topology[3] > 1024:
        raise OverflowError("property bound")
    for role in ROLES:
        roles[role].sort(key=lambda item: item["selector_commitment_sha256"])
    return roles, unsupported


def _empty_roles():
    return dict((role, {"candidate_count": 0, "candidates": []}) for role in ROLES)


def _result(roles, unsupported, blockers, unchanged, opened, closed):
    for blocker in blockers:
        if blocker not in BLOCKER_ENUMS:
            raise ValueError("blocker enum")
    if len(set(blockers)) > len(BLOCKER_ENUMS):
        raise ValueError("blocker bound")
    role_output = {}
    ambiguity = {}
    for role in ROLES:
        candidates = roles[role]
        role_output[role] = {"candidate_count": len(candidates), "candidates": candidates}
        if unsupported.get(role):
            ambiguity[role] = "unsupported_candidate"
        elif not candidates:
            ambiguity[role] = "zero_candidates"
        elif len(candidates) > 1:
            ambiguity[role] = "multiple_candidates"
        else:
            ambiguity[role] = "none"
    if blockers:
        status = "blocked"
    elif any(ambiguity[role] == "multiple_candidates" for role in ROLES):
        status = "ambiguous"
    elif any(ambiguity[role] == "zero_candidates" for role in ROLES):
        status = "incomplete_evidence"
    else:
        status = "ok"
    return {
        "ambiguity": ambiguity,
        "blockers": sorted(set(blockers)),
        "invariants": {
            "blocking_locks": "blocking_lock" in blockers or "ambiguous_lock" in blockers,
            "fingerprints_all_unchanged": unchanged,
            "names_included": False,
            "paths_included": False,
            "raw_content_included": False,
            "simulation_run": False,
            "source_closed_without_save": closed,
            "source_opened_read_only": opened,
            "values_included": False,
        },
        "plan_id": PLAN_ID,
        "plan_sha256": PLAN_SHA256,
        "roles": role_output,
        "schema_version": 1,
        "source_fingerprint_sha256": SOURCE_FINGERPRINT,
        "status": status,
    }


def build_blocked_result(blockers):
    roles = dict((role, []) for role in ROLES)
    unsupported = dict((role, False) for role in ROLES)
    return _result(roles, unsupported, blockers, False, False, False)


def build_complete_result(before, after, stream_text):
    blockers = []
    if before["source_tree"]["sha256"] != SOURCE_FINGERPRINT:
        blockers.append("source_fingerprint_mismatch")
    if before["protected"] != after["protected"]:
        blockers.append("fingerprint_drift")
    if before["locks"] != after["locks"]:
        blockers.append("lock_state_drift")
    blockers.extend(before["blockers"])
    blockers.extend(after["blockers"])
    try:
        roles, unsupported = parse_private_stream(stream_text)
    except OverflowError as error:
        code = "property_limit_exceeded" if "property" in str(error) else "candidate_limit_exceeded"
        return build_blocked_result([code] + blockers)
    except ArithmeticError:
        return build_blocked_result(["topology_mismatch"] + blockers)
    except ValueError as error:
        message = str(error)
        if message in (
            "candidate enum",
            "private marker",
            "blocker marker",
            "unsafe private token",
            "unsafe terminal pair",
            "stream bound",
            "terminal pairs",
            "terminal count",
        ):
            return build_blocked_result(["redaction_failure"] + blockers)
        return build_blocked_result(["oa_lifecycle_failure"] + blockers)
    for role in ROLES:
        if unsupported[role]:
            blockers.append("unsupported_candidate")
    return _result(roles, unsupported, blockers, not blockers, True, True)


def _dump_bounded(payload):
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("output bound")
    sys.stdout.write(serialized)


def _load_before():
    payload = json.loads(_read_bounded(BEFORE_PATH, MAX_JSON_BYTES))
    if not isinstance(payload, dict):
        raise ValueError("before snapshot")
    return payload


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
        return 64
    try:
        if sys.argv[1] == "preflight":
            _dump_bounded(build_snapshot())
            return 0
        before = _load_before()
        if sys.argv[1] == "gate":
            blockers = list(before.get("blockers", []))
            if before["source_tree"]["sha256"] != SOURCE_FINGERPRINT:
                blockers.append("source_fingerprint_mismatch")
            if blockers:
                _dump_bounded(build_blocked_result(blockers))
                return 69
            return 0
        stream = sys.stdin.read(MAX_STREAM_BYTES + 1)
        _dump_bounded(build_complete_result(before, build_snapshot(), stream))
        return 0
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
        sys.stderr.write("fixed WP-14 role discovery failed\n")
        return 69


if __name__ == "__main__":
    sys.exit(main())
