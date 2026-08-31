#!/usr/bin/env python
"""Python 2.6-compatible fixed, read-only actual-profile baseline audit."""

from __future__ import with_statement

import hashlib
import json
import os
import re
import stat
import sys
import time

try:
    STRING_TYPES = (basestring,)
except NameError:  # pragma: no cover - Python 3 test compatibility
    STRING_TYPES = (str,)


PROFILE_ID = "actual-differential-amplifier-tb2-transient"
PROFILE_PATH = (
    "/home/buet/cds_work/.cadence_mcp/profiles/"
    "actual-differential-amplifier-tb2-transient/profile.json"
)
SOURCE_NETLIST = (
    "/home/buet/simulation/Differential_Amplifier_TB2/spectre/schematic/netlist/netlist"
)
STATE_PATH = "/home/buet/.artist_states/MyDesignLib/Differential_Amplifier_TB2/spectre/state1"
JOBS_ROOT = "/home/buet/cds_work/.cadence_mcp/jobs"
PARAMETERS = ("VBIASN", "VBIASP")
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024
MAX_STATE_ENTRIES = 4096
JOB_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def utc_timestamp(epoch_seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch_seconds))


def regular_file_stat(path, maximum_bytes):
    if os.path.islink(path):
        raise ValueError("audit input must not be a symlink")
    metadata = os.stat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > maximum_bytes
        or not os.access(path, os.R_OK)
    ):
        raise ValueError("audit input is unavailable")
    return metadata


def read_bounded(path, maximum_bytes):
    metadata = regular_file_stat(path, maximum_bytes)
    with open(path, "rb") as handle:
        content = handle.read(maximum_bytes + 1)
    if len(content) != metadata.st_size or len(content) > maximum_bytes:
        raise ValueError("audit input changed or exceeded its bound")
    return content, metadata


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def load_bounded_json(path):
    content, metadata = read_bounded(path, MAX_JSON_BYTES)
    return json.loads(content), metadata, sha256_bytes(content)


def parameter_metadata(source_content):
    source_text = source_content.decode("latin-1")
    result = {}
    for name in PARAMETERS:
        token_pattern = re.compile(
            r"(^|[^A-Za-z0-9_])" + re.escape(name) + r"([^A-Za-z0-9_]|$)"
        )
        token_occurrences = 0
        declaration_occurrences = 0
        for raw_line in source_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("*") or line.startswith("//"):
                continue
            line = line.split("//", 1)[0]
            count = len(token_pattern.findall(line))
            if count == 0:
                continue
            token_occurrences += count
            if line.lower().startswith("parameters "):
                declaration_occurrences += count
        non_declaration = token_occurrences - declaration_occurrences
        result[name] = {
            "declared_in_source": declaration_occurrences > 0,
            "declaration_occurrences": declaration_occurrences,
            "non_declaration_occurrences": non_declaration,
            "referenced_outside_declaration": non_declaration > 0,
            "token_occurrences": token_occurrences,
        }
    return result


def state_tree_fingerprint(root):
    if os.path.islink(root) or not os.path.isdir(root) or not os.access(root, os.R_OK):
        raise ValueError("actual ADE state is unavailable")
    digest = hashlib.sha256()
    entry_count = 0
    newest_mtime = os.stat(root).st_mtime
    for current_root, directory_names, file_names in os.walk(root):
        directory_names.sort()
        file_names.sort()
        for name in directory_names + file_names:
            path = os.path.join(current_root, name)
            if os.path.islink(path):
                raise ValueError("actual ADE state contains a symlink")
            metadata = os.stat(path)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            kind = "d" if stat.S_ISDIR(metadata.st_mode) else "f"
            if kind == "f" and not stat.S_ISREG(metadata.st_mode):
                raise ValueError("actual ADE state contains an unsupported entry")
            entry_count += 1
            if entry_count > MAX_STATE_ENTRIES:
                raise ValueError("actual ADE state exceeds the metadata entry bound")
            newest_mtime = max(newest_mtime, metadata.st_mtime)
            record = "%s\0%s\0%s\0%s\n" % (
                kind,
                relative,
                metadata.st_size,
                int(metadata.st_mtime),
            )
            digest.update(record.encode("utf-8"))
    return {
        "entry_count": entry_count,
        "exists": True,
        "newest_mtime_utc": utc_timestamp(newest_mtime),
        "tree_metadata_sha256": digest.hexdigest(),
    }, newest_mtime


def latest_actual_manifest(current_source_sha256):
    latest = None
    if os.path.islink(JOBS_ROOT) or not os.path.isdir(JOBS_ROOT):
        return {"found": False}
    job_names = sorted(os.listdir(JOBS_ROOT))
    if len(job_names) > MAX_STATE_ENTRIES:
        raise ValueError("job registry exceeds the audit bound")
    for job_name in job_names:
        if JOB_ID_PATTERN.match(job_name) is None:
            continue
        job_dir = os.path.join(JOBS_ROOT, job_name)
        if os.path.islink(job_dir) or not os.path.isdir(job_dir):
            continue
        manifest_path = os.path.join(job_dir, "artifacts", "run-manifest.json")
        result_path = os.path.join(job_dir, "result.json")
        if not os.path.isfile(manifest_path) or not os.path.isfile(result_path):
            continue
        try:
            manifest, manifest_stat, unused_hash = load_bounded_json(manifest_path)
            result, unused_stat, unused_result_hash = load_bounded_json(result_path)
        except (IOError, OSError, ValueError, TypeError):
            continue
        source_sha256 = manifest.get("source_sha256")
        if (
            manifest.get("profile_id") != PROFILE_ID
            or result.get("state") != "succeeded"
            or not isinstance(source_sha256, STRING_TYPES)
            or SHA256_PATTERN.match(source_sha256) is None
        ):
            continue
        candidate = {
            "found": True,
            "manifest_mtime_utc": utc_timestamp(manifest_stat.st_mtime),
            "matches_current_source": source_sha256 == current_source_sha256,
            "source_sha256": source_sha256,
        }
        if latest is None or manifest_stat.st_mtime > latest[0]:
            latest = (manifest_stat.st_mtime, candidate)
    if latest is None:
        return {"found": False}
    return latest[1]


def validate_profile(profile):
    if (
        profile.get("profile_id") != PROFILE_ID
        or profile.get("source_netlist") != SOURCE_NETLIST
        or profile.get("state_path") != STATE_PATH
        or profile.get("fixed_parameters")
        != {"VBIASN": "300m", "VBIASP": "650m"}
        or profile.get("variables") != {}
    ):
        raise ValueError("actual profile registry drifted")


def build_audit():
    profile, profile_stat, profile_sha256 = load_bounded_json(PROFILE_PATH)
    validate_profile(profile)
    source_content, source_stat = read_bounded(SOURCE_NETLIST, MAX_SOURCE_BYTES)
    source_sha256 = sha256_bytes(source_content)
    state, state_mtime = state_tree_fingerprint(STATE_PATH)
    return {
        "ade_state": state,
        "freshness": {
            "source_minus_state_seconds": int(source_stat.st_mtime - state_mtime),
            "source_not_older_than_state": source_stat.st_mtime >= state_mtime,
        },
        "latest_successful_actual_manifest": latest_actual_manifest(source_sha256),
        "paths_included": False,
        "profile": {
            "fixed_parameters": profile["fixed_parameters"],
            "mtime_utc": utc_timestamp(profile_stat.st_mtime),
            "profile_id": PROFILE_ID,
            "sha256": profile_sha256,
            "variables_enabled": False,
        },
        "raw_content_included": False,
        "schema_version": 1,
        "source_netlist": {
            "exists": True,
            "mtime_utc": utc_timestamp(source_stat.st_mtime),
            "parameter_metadata": parameter_metadata(source_content),
            "sha256": source_sha256,
            "size_bytes": source_stat.st_size,
        },
    }


def main():
    if len(sys.argv) != 1:
        return 64
    try:
        payload = build_audit()
    except (IOError, OSError, ValueError, KeyError, TypeError):
        sys.stderr.write("fixed actual-profile baseline audit failed\n")
        return 69
    json.dump(payload, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
