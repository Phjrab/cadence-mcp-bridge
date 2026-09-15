#!/usr/bin/env python
"""Fixed, bounded, Python 2.6-compatible ADE/OA read-only introspection."""

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
RUNTIME = ROOT + "/ade-profile-introspection"
PROFILE_PATH = ROOT + "/profiles/" + PROFILE_ID + "/profile.json"
BEFORE_PATH = RUNTIME + "/before.json"
SKILL_STDOUT = RUNTIME + "/skill.stdout"
SOURCE_DIRECTORY = "/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic"
SOURCE_NETLIST = (
    "/home/buet/simulation/Differential_Amplifier_TB2/spectre/schematic/netlist/netlist"
)
STATE_DIRECTORY = (
    "/home/buet/.artist_states/MyDesignLib/Differential_Amplifier_TB2/spectre/state1"
)
MODEL_FILE = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"

MAX_JSON_BYTES = 65536
MAX_TEXT_BYTES = 1048576
MAX_SOURCE_BYTES = 10485760
MAX_MODEL_BYTES = 67108864
MAX_TREE_ENTRIES = 4096
MAX_TREE_BYTES = 134217728
MAX_PUBLIC_BYTES = 65536
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
SAFE_NUMBER = re.compile(
    r"^[+-]?(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)(?:[eE][+-]?[0-9]+)?[munpfkMGT]?$"
)
SAFE_OUTPUT = re.compile(r"^[A-Za-z0-9_#/:.()<>+* -]{1,128}$")
OA_MARKER = re.compile(r"^MCP_ADE_OA[|]true[|]([0-9]+)[|]([0-9]+)[|]([0-9]+)$")
STATE_FILES = (
    "ADE_state.info",
    "analyses",
    "modelSetup",
    "outputs",
    "simulatorOptions",
    "variables",
)


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _utc(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _read(path, maximum, allow_empty=False):
    if os.path.islink(path):
        raise ValueError("symlink input")
    metadata = os.stat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
        raise ValueError("invalid input")
    if not allow_empty and metadata.st_size <= 0:
        raise ValueError("empty input")
    with open(path, "rb") as handle:
        content = handle.read(maximum + 1)
    if len(content) != metadata.st_size or len(content) > maximum:
        raise ValueError("input changed")
    return content, metadata


def _load_json(path):
    content, metadata = _read(path, MAX_JSON_BYTES)
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("object required")
    return payload, metadata, _sha256(content)


def _tree(root):
    if os.path.islink(root) or not os.path.isdir(root) or not os.access(root, os.R_OK):
        raise ValueError("invalid tree")
    digest = hashlib.sha256()
    count = 0
    total = 0
    newest = os.stat(root).st_mtime
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        for name in directories + files:
            path = os.path.join(current, name)
            if os.path.islink(path):
                raise ValueError("tree symlink")
            metadata = os.stat(path)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if stat.S_ISDIR(metadata.st_mode):
                kind = "d"
                content_hash = "-"
            elif stat.S_ISREG(metadata.st_mode):
                kind = "f"
                total += metadata.st_size
                if total > MAX_TREE_BYTES:
                    raise ValueError("tree byte bound")
                content_hash = _sha256(_read(path, MAX_TREE_BYTES, True)[0])
            else:
                raise ValueError("unsupported tree entry")
            count += 1
            if count > MAX_TREE_ENTRIES:
                raise ValueError("tree entry bound")
            newest = max(newest, metadata.st_mtime)
            record = "%s\0%s\0%s\0%s\0%s\n" % (
                kind,
                relative,
                metadata.st_size,
                int(metadata.st_mtime),
                content_hash,
            )
            digest.update(record.encode("utf-8"))
    return {
        "entry_count": count,
        "newest_mtime_epoch": newest,
        "newest_mtime_utc": _utc(newest),
        "sha256": digest.hexdigest(),
        "total_bytes": total,
    }


def _lock_count(root):
    count = 0
    scanned = 0
    for _current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        for name in directories + files:
            scanned += 1
            if scanned > MAX_TREE_ENTRIES:
                raise ValueError("lock scan bound")
            lowered = name.lower()
            if "cdslck" in lowered or lowered == "lock" or lowered.endswith(".lock"):
                count += 1
    return count


def _validate_profile(profile):
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
        "state_path": STATE_DIRECTORY,
    }
    for key in expected:
        if profile.get(key) != expected[key]:
            raise ValueError("fixed profile drift")
    if os.path.realpath(profile.get("model_file", "")) != os.path.realpath(MODEL_FILE):
        raise ValueError("model path drift")
    if not isinstance(profile.get("analyses"), list):
        raise ValueError("analysis contract")
    if not isinstance(profile.get("fixed_parameters"), dict):
        raise ValueError("variable contract")
    if not isinstance(profile.get("outputs"), list):
        raise ValueError("output contract")


def build_snapshot():
    profile, _profile_stat, profile_hash = _load_json(PROFILE_PATH)
    _validate_profile(profile)
    source_tree = _tree(SOURCE_DIRECTORY)
    state_tree = _tree(STATE_DIRECTORY)
    source, source_stat = _read(SOURCE_NETLIST, MAX_SOURCE_BYTES)
    model, _model_stat = _read(MODEL_FILE, MAX_MODEL_BYTES)
    return {
        "locks": {
            "source": _lock_count(SOURCE_DIRECTORY),
            "state": _lock_count(STATE_DIRECTORY),
        },
        "model_sha256": _sha256(model),
        "profile_sha256": profile_hash,
        "source_netlist": {
            "mtime_epoch": source_stat.st_mtime,
            "mtime_utc": _utc(source_stat.st_mtime),
            "sha256": _sha256(source),
            "size_bytes": source_stat.st_size,
        },
        "source_tree": source_tree,
        "state_tree": state_tree,
    }


def _state_text(name, allow_empty=False):
    if name not in STATE_FILES:
        raise ValueError("state file allowlist")
    content = _read(os.path.join(STATE_DIRECTORY, name), MAX_TEXT_BYTES, allow_empty)[0]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _identity(text):
    match = re.search(
        r"(?m)^designInfo = '[\(]\"([^\"]+)\" \"([^\"]+)\" \"([^\"]+)\" \"([^\"]+)\"[\)]$",
        text,
    )
    if match is None:
        raise ValueError("missing identity")
    for value in match.groups():
        if SAFE_IDENTIFIER.match(value) is None:
            raise ValueError("unsafe identity")
    return match.groups()


def _variables(text):
    names = {}
    values = {}
    order = []
    for match in re.finditer(r'(?m)^tmp([0-9]+)->name = "([^"]+)"$', text):
        index, name = match.groups()
        if SAFE_IDENTIFIER.match(name) is None or name in names.values():
            raise ValueError("unsafe variable")
        names[index] = name
        order.append(index)
    for match in re.finditer(r'(?m)^tmp([0-9]+)->expression = "([^"]+)"$', text):
        index, value = match.groups()
        if SAFE_NUMBER.match(value) is None:
            raise ValueError("unsafe variable value")
        values[index] = value
    if len(order) > 32:
        raise ValueError("variable bound")
    result = []
    for index in order:
        if index not in values:
            raise ValueError("missing variable value")
        result.append({"name": names[index], "value": values[index]})
    return result


def _outputs(text):
    result = []
    matches = re.findall(r'(?m)^tmp[0-9]+->name = (nil|"[^"]+")$', text)
    if len(matches) > 128:
        raise ValueError("output bound")
    for token in matches:
        if token == "nil":
            continue
        name = token[1:-1]
        if SAFE_OUTPUT.match(name) is None or name.startswith("/") or ".." in name:
            raise ValueError("unsafe output")
        if name in result:
            raise ValueError("duplicate output")
        result.append(name)
    return result


def _analyses(text):
    result = []
    seen = set()
    pattern = re.compile(
        r"(?m)^analysis[\(]([A-Za-z][A-Za-z0-9_]*) fields enable[\)] [\(](t|nil)[\)]$"
    )
    for match in pattern.finditer(text):
        name, enabled = match.groups()
        if name in seen or len(name) > 32:
            raise ValueError("invalid analysis")
        seen.add(name)
        stop = None
        stop_match = re.search(
            r'(?m)^analysis[\(]' + re.escape(name) + r' fields stop[\)] "([^"]*)"$', text
        )
        if stop_match is not None and stop_match.group(1):
            stop = stop_match.group(1)
            if SAFE_NUMBER.match(stop) is None:
                raise ValueError("unsafe stop")
        result.append({"enabled": enabled == "t", "name": name, "stop_time": stop})
    if not result or len(result) > 32:
        raise ValueError("analysis bound")
    return result


def _model_section(text):
    match = re.match(r'^\(\(\"([^\"]+)\" \"([^\"]+)\"\)\)\s*$', text)
    if match is None or os.path.realpath(match.group(1)) != os.path.realpath(MODEL_FILE):
        raise ValueError("model setup drift")
    if SAFE_IDENTIFIER.match(match.group(2)) is None:
        raise ValueError("unsafe model section")
    return match.group(2)


def _temperature(text):
    match = re.search(r'(?m)^\(opts temp\) "([^"]+)"$', text)
    if match is None or SAFE_NUMBER.match(match.group(1)) is None:
        raise ValueError("temperature unavailable")
    return float(match.group(1))


def _topology():
    content = _read(SKILL_STDOUT, MAX_TEXT_BYTES)[0]
    found = []
    for line in content.decode("latin-1").splitlines():
        match = OA_MARKER.match(line.strip())
        if match is not None:
            found.append(tuple(int(item) for item in match.groups()))
    if len(found) != 1 or found[0] != (35, 14, 8):
        raise ValueError("OA topology invariant")
    return found[0]


def _pair(before, after):
    return {"after_sha256": after, "before_sha256": before, "unchanged": before == after}


def build_result(before, after):
    profile, _stat, current_profile_hash = _load_json(PROFILE_PATH)
    _validate_profile(profile)
    if before.get("profile_sha256") != current_profile_hash:
        raise ValueError("profile changed")
    pairs = {
        "pdk_model": _pair(before["model_sha256"], after["model_sha256"]),
        "source": _pair(before["source_tree"]["sha256"], after["source_tree"]["sha256"]),
        "source_netlist": _pair(
            before["source_netlist"]["sha256"], after["source_netlist"]["sha256"]
        ),
        "state": _pair(before["state_tree"]["sha256"], after["state_tree"]["sha256"]),
    }
    if not all(item["unchanged"] for item in pairs.values()):
        raise ValueError("protected fingerprint drift")
    if before["locks"] != after["locks"] or before["locks"]["source"] != 0:
        raise ValueError("source lock invariant")
    if before["locks"]["state"] != 0:
        raise ValueError("state lock invariant")

    identity = _identity(_state_text("ADE_state.info"))
    analyses = _analyses(_state_text("analyses"))
    variables = _variables(_state_text("variables"))
    outputs = _outputs(_state_text("outputs", True))
    model_section = _model_section(_state_text("modelSetup"))
    temperature = _temperature(_state_text("simulatorOptions"))
    instances, nets, terminals = _topology()

    drift = []
    if identity != ("MyDesignLib", "Differential_Amplifier_TB2", "schematic", "spectre"):
        drift.append("identity_mismatch")
    if [item["name"] for item in analyses if item["enabled"]] != profile["analyses"]:
        drift.append("analysis_mismatch")
    if dict((item["name"], item["value"]) for item in variables) != profile["fixed_parameters"]:
        drift.append("design_variable_mismatch")
    if outputs != profile["outputs"]:
        drift.append("output_mismatch")
    if model_section != profile["model_section"]:
        drift.append("model_mismatch")
    if temperature != float(profile["temperature_c"]):
        drift.append("temperature_mismatch")
    source_minus_state = int(
        after["source_netlist"]["mtime_epoch"] - after["state_tree"]["newest_mtime_epoch"]
    )
    fresh = source_minus_state >= 0
    if not fresh:
        drift.append("snapshot_freshness_unconfirmed")

    pairs["all_unchanged"] = True
    result = {
        "ade_product": "ADE L",
        "analyses": analyses,
        "cell": "Differential_Amplifier_TB2",
        "confidence": "high",
        "design_variables": variables,
        "drift_codes": drift,
        "fingerprints": pairs,
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
        "profile_contract_match": len(drift) == 0,
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
            "source_not_older_than_state": fresh,
            "state_newest_mtime_utc": after["state_tree"]["newest_mtime_utc"],
        },
        "source_structural_fingerprint": {
            "instances": instances,
            "nets": nets,
            "terminals": terminals,
            "tree_metadata_sha256": after["source_tree"]["sha256"],
        },
        "state_exists": True,
        "state_name": "state1",
        "status": "ok" if len(drift) == 0 else "profile_drift",
        "temperature_c": temperature,
        "view": "schematic",
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_PUBLIC_BYTES:
        raise ValueError("public output bound")
    return result


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "complete"):
        return 64
    try:
        if sys.argv[1] == "preflight":
            payload = build_snapshot()
        else:
            payload = build_result(_load_json(BEFORE_PATH)[0], build_snapshot())
    except (IOError, OSError, ValueError, KeyError, TypeError):
        sys.stderr.write("fixed ADE profile introspection failed\n")
        return 69
    json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
