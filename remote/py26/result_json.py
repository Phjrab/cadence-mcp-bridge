#!/usr/bin/python

from __future__ import with_statement

import json
import os
import stat
import sys


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
            "profile": arguments[1],
            "submitted_at": arguments[2],
        }
    )


def command_status(arguments):
    emit(
        {
            "job_id": arguments[0],
            "message": arguments[4],
            "profile": arguments[2],
            "state": arguments[1],
            "updated_at": arguments[3],
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
    )
    for candidate in candidates:
        metadata = artifact(job_dir, candidate[0], candidate[1], candidate[2])
        if metadata is not None:
            artifacts.append(metadata)
    emit(
        {
            "artifacts": artifacts,
            "exit_code": int(arguments[3]),
            "job_id": arguments[1],
            "state": arguments[2],
            "storage": {
                "contained": contained,
                "directory_mode": directory_mode,
            },
            "summary": {
                "errors": int(arguments[4]),
                "notices": int(arguments[6]),
                "text": arguments[7][:512],
                "warnings": int(arguments[5]),
            },
        }
    )


def command_state(arguments):
    with open(arguments[0], "rb") as handle:
        value = json.load(handle)
    sys.stdout.write(str(value.get("state", "unknown")) + "\n")


def main():
    if len(sys.argv) < 2:
        return 64
    command = sys.argv[1]
    arguments = sys.argv[2:]
    expected = {"health": 10, "request": 3, "result": 8, "state": 1, "status": 5}
    if command not in expected or len(arguments) != expected[command]:
        return 64
    functions = {
        "health": command_health,
        "request": command_request,
        "result": command_result,
        "state": command_state,
        "status": command_status,
    }
    functions[command](arguments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
