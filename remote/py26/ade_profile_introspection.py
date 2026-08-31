#!/usr/bin/env python
"""Python 2.6-compatible fixed read-only ADE L profile introspection."""

from __future__ import with_statement

import hashlib
import json
import os
import re
import stat
import sys
import time

PROFILE_ID = "actual-differential-amplifier-tb2-transient"
ROOT = "/home/buet/cds_work/.cadence_mcp"
PROFILE_PATH = ROOT + "/profiles/" + PROFILE_ID + "/profile.json"
RUNTIME = ROOT + "/ade-profile-introspection"
BEFORE_PATH = RUNTIME + "/before.json"
SKILL_STDOUT = RUNTIME + "/skill.stdout"
SOURCE_DIRECTORY = (
    "/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic"
)
SOURCE_NETLIST = (
    "/home/buet/simulation/Differential_Amplifier_TB2/spectre/schematic/netlist/netlist"
)
STATE_PATH = "/home/buet/.artist_states/MyDesignLib/Differential_Amplifier_TB2/spectre/state1"
MODEL_FILE = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"
MAX_JSON_BYTES = 64 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_TREE_ENTRIES = 4096
MAX_TREE_BYTES = 128 * 1024 * 1024
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
SAFE_VALUE = re.compile(
    r"^[+-]?(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)(?:[eE][+-]?[0-9]+)?[munpfkMGT]?$"
)
SAFE_OUTPUT = re.compile(r"^[A-Za-z0-9_#/:.()<>+* -]{1,128}$")
SKILL_MARKER = re.compile(r"^MCP_ADE_OA[|]true[|]([0-9]+)[|]([0-9]+)[|]([0-9]+)$")


def utc_timestamp(epoch_seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


def regular_file_stat(path, maximum_bytes, allow_empty=False):
    if os.path.islink(path):
        raise ValueError("introspection input must not be a symlink")
    metadata = os.stat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
        raise ValueError("introspection input is invalid")
    if not allow_empty and metadata.st_size <= 0:
        raise ValueError("introspection input is empty")
    if not os.access(path, os.R_OK):
        raise ValueError("introspection input is unreadable")
    return metadata


def read_bounded(path, maximum_bytes, allow_empty=False):
    metadata = regular_file_stat(path, maximum_bytes, allow_empty)
    with open(path, "rb") as handle:
        content = handle.read(maximum_bytes + 1)
    if len(content) != metadata.st_size or len(content) > maximum_bytes:
        raise ValueError("introspection input changed or exceeded its bound")
    return content, metadata


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def load_json(path):
    content, metadata = read_bounded(path, MAX_JSON_BYTES)
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload, metadata, sha256_bytes(content)


def tree_fingerprint(root):
    if os.path.islink(root) or not os.path.isdir(root) or not os.access(root, os.R_OK):
        raise ValueError("introspection tree is unavailable")
    digest = hashlib.sha256()
    entry_count = 0
    total_bytes = 0
    newest_mtime = os.stat(root).st_mtime
    for current_root, directory_names, file_names in os.walk(root):
        directory_names.sort()
        file_names.sort()
        for name in directory_names + file_names:
            path = os.path.join(current_root, name)
            if os.path.islink(path):
                raise ValueError("introspection tree contains a symlink")
            metadata = os.stat(path)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if stat.S_ISDIR(metadata.st_mode):
                kind = "d"
                content_hash = "-"
            elif stat.S_ISREG(metadata.st_mode):
                kind = "f"
                total_bytes += metadata.st_size
                if total_bytes > MAX_TREE_BYTES:
                    raise ValueError("introspection tree exceeds its byte bound")
                content, unused_metadata = read_bounded(path, MAX_TREE_BYTES, True)
                content_hash = sha256_bytes(content)
            else:
                raise ValueError("introspection tree contains an unsupported entry")
            entry_count += 1
            if entry_count > MAX_TREE_ENTRIES:
                raise ValueError("introspection tree exceeds its entry bound")
            newest_mtime = max(newest_mtime, metadata.st_mtime)
            record = "%s\0%s\0%s\0%s\0%s\n" % (
                kind,
                relative,
                metadata.st_size,
                int(metadata.st_mtime),
                content_hash,
            )
            digest.update(record.encode("utf-8"))
    return {
        "entry_count": entry_count,
        "newest_mtime_epoch": newest_mtime,
        "newest_mtime_utc": utc_timestamp(newest_mtime),
        "sha256": digest.hexdigest(),
        "total_bytes": total_bytes,
    }


def lock_count(root):
    count = 0
    for _current_root, directory_names, file_names in os.walk(root):
        directory_names.sort()
        file_names.sort()
        for name in directory_names + file_names:
            lowered = name.lower()
            if "cdslck" in lowered or lowered.endswith(".lock") or lowered == "lock":
                count += 1
    return count


def validate_profile(profile):
    expected = {
        "profile_id": PROFILE_ID,
        "classification": "actual",
        "library": "MyDesignLib",
        "cell": "Differential_Amplifier_TB2",
        "view": "schematic",
        "ade_product": "ADE L",
        "state": "state1",
        "pdk": "gpdk090",
        "pdk_version": "4.6",
        "model_section": "NN",
        "temperature_c": 27.0,
        "source_netlist": SOURCE_NETLIST,
        "state_path": STATE_PATH,
    }
    for key in expected:
        if profile.get(key) != expected[key]:
            raise ValueError("fixed actual profile registry drifted")
    if os.path.realpath(profile.get("model_file", "")) != os.path.realpath(MODEL_FILE):
        raise ValueError("fixed model file registry drifted")
    if not isinstance(profile.get("analyses"), list):
        raise ValueError("fixed analysis contract is invalid")
    if not isinstance(profile.get("outputs"), list):
        raise ValueError("fixed output contract is invalid")
    if not isinstance(profile.get("fixed_parameters"), dict):
        raise ValueError("fixed parameter contract is invalid")


def build_snapshot():
    profile, unused_stat, profile_sha256 = load_json(PROFILE_PATH)
    validate_profile(profile)
    source_tree = tree_fingerprint(SOURCE_DIRECTORY)
    state_tree = tree_fingerprint(STATE_PATH)
    source_content, source_stat = read_bounded(SOURCE_NETLIST, MAX_SOURCE_BYTES)
    model_content, unused_model_stat = read_bounded(MODEL_FILE, MAX_MODEL_BYTES)
    return {
        "locks": {
            "source": lock_count(SOURCE_DIRECTORY),
            "state": lock_count(STATE_PATH),
        },
        "model_sha256": sha256_bytes(model_content),
        "profile_sha256": profile_sha256,
        "source_netlist": {
            "mtime_utc": utc_timestamp(source_stat.st_mtime),
            "sha256": sha256_bytes(source_content),
            "size_bytes": source_stat.st_size,
        },
        "source_tree": source_tree,
        "state_tree": state_tree,
    }


def read_state_file(name, allow_empty=False):
    if name not in (
        "ADE_state.info",
        "analyses",
        "modelSetup",
        "outputs",
        "simulatorOptions",
        "variables",
    ):
        raise ValueError("state file is outside the fixed parser")
    content, unused_stat = read_bounded(
        os.path.join(STATE_PATH, name), MAX_TEXT_BYTES, allow_empty
    )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_identity(text):
    match = re.search(
        r"(?m)^designInfo = '[\(]\"([^\"]+)\" \"([^\"]+)\" "
        r"\"([^\"]+)\" \"([^\"]+)\"[\)]$",
        text,
    )
    if match is None:
        raise ValueError("ADE state identity is unavailable")
    values = match.groups()
    for value in values:
        if SAFE_IDENTIFIER.match(value) is None:
            raise ValueError("ADE state identity is unsafe")
    return values


def parse_variables(text):
    names = {}
    expressions = {}
    order = []
    for match in re.finditer(r'(?m)^tmp([0-9]+)->name = "([^"]+)"$', text):
        index, name = match.groups()
        if SAFE_IDENTIFIER.match(name) is None or name in names.values():
            raise ValueError("ADE variable name is unsafe or duplicated")
        names[index] = name
        order.append(index)
    for match in re.finditer(r'(?m)^tmp([0-9]+)->expression = "([^"]+)"$', text):
        index, value = match.groups()
        if SAFE_VALUE.match(value) is None:
            raise ValueError("ADE variable value is outside the bounded numeric grammar")
        expressions[index] = value
    result = []
    for index in order:
        if index not in expressions:
            raise ValueError("ADE variable is missing its value")
        result.append({"name": names[index], "value": expressions[index]})
    if len(result) > 32:
        raise ValueError("ADE variable count exceeds the fixed bound")
    return result


def parse_outputs(text):
    outputs = []
    assignments = re.findall(r'(?m)^tmp[0-9]+->name = (nil|"[^"]+")$', text)
    if len(assignments) > 128:
        raise ValueError("ADE output count exceeds the fixed bound")
    for assignment in assignments:
        if assignment == "nil":
            continue
        name = assignment[1:-1]
        if (
            SAFE_OUTPUT.match(name) is None
            or name.startswith("/")
            or ".." in name
            or name in outputs
        ):
            raise ValueError("ADE output name is unsafe or duplicated")
        outputs.append(name)
    return outputs


def parse_analyses(text):
    analyses = []
    seen = set()
    pattern = re.compile(
        r"(?m)^analysis[\(]([A-Za-z][A-Za-z0-9_]*) fields enable[\)] "
        r"[\(](t|nil)[\)]$"
    )
    for match in pattern.finditer(text):
        name, enabled = match.groups()
        if name in seen or len(name) > 32:
            raise ValueError("ADE analysis name is duplicated or too long")
        seen.add(name)
        stop_match = re.search(
            r'(?m)^analysis[\(]' + re.escape(name) + r' fields stop[\)] "([^"]*)"$',
            text,
        )
        stop_time = None
        if stop_match is not None and stop_match.group(1):
            stop_time = stop_match.group(1)
            if SAFE_VALUE.match(stop_time) is None:
                raise ValueError("ADE analysis stop time is unsafe")
        analyses.append(
            {"enabled": enabled == "t", "name": name, "stop_time": stop_time}
        )
    if not analyses or len(analyses) > 32:
        raise ValueError("ADE analyses are unavailable or exceed the fixed bound")
    return analyses


def parse_model(text):
    match = re.match(r'^\(\(\"([^\"]+)\" \"([^\"]+)\"\)\)\s*$', text)
    if match is None:
        raise ValueError("ADE model setup is unavailable")
    path, section = match.groups()
    if os.path.realpath(path) != os.path.realpath(MODEL_FILE):
        raise ValueError("ADE model file is outside the fixed profile")
    if SAFE_IDENTIFIER.match(section) is None:
        raise ValueError("ADE model section is unsafe")
    return section


def parse_temperature(text):
    match = re.search(r'(?m)^\(opts temp\) "([^"]+)"$', text)
    if match is None or SAFE_VALUE.match(match.group(1)) is None:
        raise ValueError("ADE temperature is unavailable")
    return float(match.group(1))


def parse_skill_marker():
    content, unused_stat = read_bounded(SKILL_STDOUT, MAX_TEXT_BYTES)
    marker = None
    for raw_line in content.decode("latin-1").splitlines():
        match = SKILL_MARKER.match(raw_line.strip())
        if match is not None:
            marker = match
    if marker is None:
        raise ValueError("read-only OA marker is unavailable")
    return tuple(int(value) for value in marker.groups())


def pair(before, after):
    return {
        "after_sha256": after,
        "before_sha256": before,
        "unchanged": before == after,
    }


def build_result(before, after):
    profile, unused_stat, current_profile_sha256 = load_json(PROFILE_PATH)
    validate_profile(profile)
    if before.get("profile_sha256") != current_profile_sha256:
        raise ValueError("profile registry changed during introspection")
    fingerprint_pairs = {
        "pdk_model": pair(before["model_sha256"], after["model_sha256"]),
        "source": pair(before["source_tree"]["sha256"], after["source_tree"]["sha256"]),
        "source_netlist": pair(
            before["source_netlist"]["sha256"], after["source_netlist"]["sha256"]
        ),
        "state": pair(before["state_tree"]["sha256"], after["state_tree"]["sha256"]),
    }
    all_unchanged = all(item["unchanged"] for item in fingerprint_pairs.values())
    if not all_unchanged:
        raise ValueError("protected fingerprint changed during introspection")
    if before["locks"] != after["locks"] or before["locks"]["source"]:
        raise ValueError("source lock invariant failed")
    if before["locks"]["state"]:
        raise ValueError("ADE state lock invariant failed")

    identity = parse_identity(read_state_file("ADE_state.info"))
    analyses = parse_analyses(read_state_file("analyses"))
    variables = parse_variables(read_state_file("variables"))
    outputs = parse_outputs(read_state_file("outputs"))
    model_section = parse_model(read_state_file("modelSetup"))
    temperature_c = parse_temperature(read_state_file("simulatorOptions"))
    instances, nets, terminals = parse_skill_marker()

    drift_codes = []
    if identity != ("MyDesignLib", "Differential_Amplifier_TB2", "schematic", "spectre"):
        drift_codes.append("identity_mismatch")
    enabled_analyses = [item["name"] for item in analyses if item["enabled"]]
    if enabled_analyses != profile["analyses"]:
        drift_codes.append("analysis_mismatch")
    variable_map = dict((item["name"], item["value"]) for item in variables)
    if variable_map != profile["fixed_parameters"]:
        drift_codes.append("design_variable_mismatch")
    if outputs != profile["outputs"]:
        drift_codes.append("output_mismatch")
    if model_section != profile["model_section"]:
        drift_codes.append("model_mismatch")
    if temperature_c != float(profile["temperature_c"]):
        drift_codes.append("temperature_mismatch")
    source_epoch = os.stat(SOURCE_NETLIST).st_mtime
    newest_state_utc = after["state_tree"]["newest_mtime_utc"]
    state_newest_epoch = after["state_tree"]["newest_mtime_epoch"]
    source_minus_state = int(source_epoch - state_newest_epoch)
    source_is_fresh = source_minus_state >= 0
    if not source_is_fresh:
        drift_codes.append("snapshot_freshness_unconfirmed")

    fingerprint_pairs["all_unchanged"] = True
    contract_match = len(drift_codes) == 0
    return {
        "ade_product": "ADE L",
        "analyses": analyses,
        "cell": "Differential_Amplifier_TB2",
        "confidence": "high",
        "design_variables": variables,
        "drift_codes": drift_codes,
        "fingerprints": fingerprint_pairs,
        "library": "MyDesignLib",
        "locks": {
            "blocking": False,
            "source_active_count": after["locks"]["source"],
            "state_active_count": after["locks"]["state"],
        },
        "model_section": model_section,
        "outputs": outputs,
        "paths_included": False,
        "pdk": "gpdk090",
        "pdk_version": "4.6",
        "profile_contract_match": contract_match,
        "profile_id": PROFILE_ID,
        "provenance": "fixed_registry+ade_state+oa_readonly+filesystem_metadata",
        "raw_content_included": False,
        "read_only": True,
        "schema_version": 1,
        "simulator": "spectre",
        "source_netlist": {
            "exists": True,
            "mtime_utc": after["source_netlist"]["mtime_utc"],
            "sha256": after["source_netlist"]["sha256"],
            "size_bytes": after["source_netlist"]["size_bytes"],
            "source_minus_state_seconds": source_minus_state,
            "source_not_older_than_state": source_is_fresh,
            "state_newest_mtime_utc": newest_state_utc,
        },
        "source_structural_fingerprint": {
            "instances": instances,
            "nets": nets,
            "terminals": terminals,
            "tree_metadata_sha256": after["source_tree"]["sha256"],
        },
        "state_exists": True,
        "state_name": "state1",
        "status": "ok" if contract_match else "profile_drift",
        "temperature_c": temperature_c,
        "view": "schematic",
    }


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "complete"):
        return 64
    try:
        if sys.argv[1] == "preflight":
            payload = build_snapshot()
        else:
            before, unused_stat, unused_sha256 = load_json(BEFORE_PATH)
            payload = build_result(before, build_snapshot())
    except (IOError, OSError, ValueError, KeyError, TypeError):
        sys.stderr.write("fixed ADE profile introspection failed\n")
        return 69
    json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
