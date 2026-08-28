#!/usr/bin/python

from __future__ import with_statement

import json
import os
import re
import stat
import sys
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows-only test compatibility
    fcntl = None


JOB_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
PROFILE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
AUDIT_EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LOG_LIMIT_BYTES = 65536
LOG_SCAN_LIMIT_BYTES = 1048576
RESULT_ARTIFACT_LIMIT = 16


def emit(value):
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def as_bool(value):
    return value == "true"


def tree_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    if os.path.isdir(path):
        for root, directories, files in os.walk(path):
            directories.sort()
            files.sort()
            for filename in files:
                candidate = os.path.join(root, filename)
                if os.path.isfile(candidate):
                    total += os.path.getsize(candidate)
    return total


def artifact(job_dir, name, relative_path, media_type):
    path = os.path.join(job_dir, *relative_path.split("/"))
    if not os.path.exists(path):
        return None
    return {
        "media_type": media_type,
        "name": name,
        "relative_path": relative_path,
        "size_bytes": tree_size(path),
    }


def command_health(arguments):
    emit(
        {
            "license_env": {"CDS_LIC_FILE": arguments[8]},
            "ocean": {"available": as_bool(arguments[7])},
            "remote_host": arguments[0],
            "remote_root_accessible": as_bool(arguments[2]),
            "remote_user": arguments[1],
            "runner_version": arguments[9],
            "spectre": {"available": as_bool(arguments[5]), "version": arguments[6]},
            "ssh": "ok",
            "virtuoso": {"available": as_bool(arguments[3]), "version": arguments[4]},
        }
    )


def command_request(arguments):
    emit(
        {
            "job_id": arguments[0],
            "origin": arguments[3],
            "profile": arguments[1],
            "submitted_by": arguments[4],
            "submitted_at": arguments[2],
        }
    )


def command_status(arguments):
    emit(
        {
            "job_id": arguments[0],
            "message": arguments[5],
            "origin": arguments[3],
            "profile": arguments[2],
            "state": arguments[1],
            "updated_at": arguments[4],
        }
    )


def command_result(arguments):
    job_dir = arguments[0]
    jobs_root = os.path.realpath("/home/buet/cds_work/.cadence_mcp/jobs")
    real_job_dir = os.path.realpath(job_dir)
    contained = os.path.dirname(real_job_dir) == jobs_root
    directory_mode = "{0:04o}".format(stat.S_IMODE(os.stat(real_job_dir).st_mode))
    artifacts = []
    candidates = (
        ("smoke.log", "artifacts/smoke.log", "text/plain"),
        ("smoke.raw", "artifacts/smoke.raw", "application/x-cadence-psf"),
        ("stdout.log", "stdout.log", "text/plain"),
        ("stderr.log", "stderr.log", "text/plain"),
        ("profile.log", "artifacts/profile.log", "text/plain"),
        ("profile.raw", "artifacts/profile.raw", "application/x-cadence-psf"),
        ("profile.scs", "artifacts/profile.scs", "text/plain"),
        ("run-manifest.json", "artifacts/run-manifest.json", "application/json"),
    )
    for candidate in candidates:
        metadata = artifact(job_dir, candidate[0], candidate[1], candidate[2])
        if metadata is not None:
            artifacts.append(metadata)
    artifacts_total = len(artifacts)
    artifacts = artifacts[:RESULT_ARTIFACT_LIMIT]
    summary = arguments[7]
    request_path = os.path.join(job_dir, "request.json")
    with open(request_path, "rb") as request_handle:
        request = json.load(request_handle)
    emit(
        {
            "artifacts": artifacts,
            "exit_code": int(arguments[3]),
            "job_id": arguments[1],
            "limits": {
                "artifacts_returned": len(artifacts),
                "artifacts_total": artifacts_total,
                "artifacts_truncated": artifacts_total > len(artifacts),
                "response_limit_bytes": LOG_LIMIT_BYTES,
                "summary_original_chars": len(summary),
                "summary_returned_chars": len(summary[:512]),
                "summary_truncated": len(summary) > 512,
            },
            "origin": request.get("origin", "mcp"),
            "state": arguments[2],
            "storage": {
                "contained": contained,
                "directory_mode": directory_mode,
            },
            "summary": {
                "errors": int(arguments[4]),
                "notices": int(arguments[6]),
                "text": summary[:512],
                "warnings": int(arguments[5]),
            },
        }
    )


def command_state(arguments):
    with open(arguments[0], "rb") as handle:
        value = json.load(handle)
    sys.stdout.write(str(value.get("state", "unknown")) + "\n")


def command_field(arguments):
    with open(arguments[0], "rb") as handle:
        value = json.load(handle)
    field = arguments[1]
    if field not in ("origin", "profile"):
        raise ValueError("unsupported field")
    sys.stdout.write(str(value.get(field, "mcp")) + "\n")


def command_log_tail(arguments):
    path = arguments[0]
    job_id = arguments[1]
    stream = arguments[2]
    lines_requested = int(arguments[3])
    file_size = os.path.getsize(path)
    scan_bytes = min(file_size, LOG_SCAN_LIMIT_BYTES)
    with open(path, "rb") as handle:
        handle.seek(file_size - scan_bytes)
        data = handle.read(scan_bytes)
    selected = b"".join(data.splitlines(True)[-lines_requested:])
    exact = file_size == scan_bytes or data.count(b"\n") > lines_requested
    original_bytes = len(selected) if exact else None
    truncated = len(selected) > LOG_LIMIT_BYTES or not exact
    returned = selected[-LOG_LIMIT_BYTES:]
    while returned:
        try:
            text = returned.decode("utf-8")
            break
        except UnicodeDecodeError:
            returned = returned[1:]
    else:
        text = ""
    emit(
        {
            "job_id": job_id,
            "limit_bytes": LOG_LIMIT_BYTES,
            "lines_requested": lines_requested,
            "original_bytes": original_bytes,
            "returned_bytes": len(returned),
            "stream": stream,
            "text": text,
            "truncated": truncated,
        }
    )


def command_audit(arguments):
    path, event, job_id, origin, actor, timestamp, profile = arguments
    if (
        AUDIT_EVENT_PATTERN.match(event) is None
        or JOB_ID_PATTERN.match(job_id) is None
        or origin not in ("mcp", "operator")
        or ACTOR_PATTERN.match(actor) is None
        or PROFILE_PATTERN.match(profile) is None
    ):
        raise ValueError("invalid audit field")
    record = json.dumps(
        {
            "actor": actor,
            "event": event,
            "job_id": job_id,
            "origin": origin,
            "profile": profile,
            "timestamp": timestamp,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, int("600", 8))
    with os.fdopen(descriptor, "a") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(record + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def command_retention(arguments):
    jobs_root = arguments[0]
    retention_days = int(arguments[1])
    real_root = os.path.realpath(jobs_root)
    expected_root = "/home/buet/cds_work/.cadence_mcp/jobs"
    if real_root != expected_root or retention_days != 30:
        raise ValueError("invalid retention boundary")
    cutoff = time.time() - (retention_days * 86400)
    candidates = []
    for name in sorted(os.listdir(real_root)):
        if JOB_ID_PATTERN.match(name) is None:
            continue
        path = os.path.join(real_root, name)
        if os.path.islink(path) or not os.path.isdir(path):
            continue
        if os.path.dirname(os.path.realpath(path)) != real_root:
            continue
        status_path = os.path.join(path, "status.json")
        try:
            with open(status_path, "rb") as status_handle:
                state = json.load(status_handle).get("state")
        except (OSError, ValueError):
            continue
        if state not in ("succeeded", "failed", "cancelled", "unknown"):
            continue
        modified = os.path.getmtime(path)
        if modified < cutoff:
            candidates.append(
                {
                    "age_days": int((time.time() - modified) / 86400),
                    "job_id": name,
                    "state": state,
                }
            )
    emit(
        {
            "candidates": candidates,
            "dry_run": True,
            "jobs_root": expected_root,
            "retention_days": retention_days,
            "scanned_at": arguments[2],
        }
    )


def main():
    if len(sys.argv) < 2:
        return 64
    command = sys.argv[1]
    arguments = sys.argv[2:]
    expected = {
        "audit": 7,
        "field": 2,
        "health": 10,
        "log-tail": 4,
        "request": 5,
        "result": 8,
        "retention": 3,
        "state": 1,
        "status": 6,
    }
    if command not in expected or len(arguments) != expected[command]:
        return 64
    functions = {
        "audit": command_audit,
        "field": command_field,
        "health": command_health,
        "log-tail": command_log_tail,
        "request": command_request,
        "result": command_result,
        "retention": command_retention,
        "state": command_state,
        "status": command_status,
    }
    functions[command](arguments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
