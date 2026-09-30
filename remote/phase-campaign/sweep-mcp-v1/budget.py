#!/usr/bin/env python
"""Python 2.6 cumulative Spectre reservation for owned fixture sweep jobs."""
from __future__ import with_statement

import json
import os
import re
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
JOBS = ROOT + "/sim-mcp-v2-jobs"
COUNTER = JOBS + "/counter.json"
MARKERS = ROOT + "/sweep-mcp-v1-reservations"
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
RESERVE_BYTES = 128 * 1024 * 1024


def read(path, limit):
    if os.path.islink(path) or os.stat(path).st_size > limit:
        raise ValueError("unsafe file")
    with open(path, "rb") as stream:
        return stream.read(limit + 1)


def write_new(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("reserve", "lookup", "effective") or not ID.match(sys.argv[2]):
        sys.exit(64)
    job_id = sys.argv[2]
    if sys.argv[1] == "effective":
        path = ROOT + "/jobs/" + job_id + "/artifacts/run-manifest.json"
        manifest = json.loads(read(path, 16384))
        if (manifest.get("job_id") != job_id or
                manifest.get("profile_id") != "fixture-rc-transient" or
                manifest.get("corner") != "nominal" or
                manifest.get("classification") != "fixture"):
            raise ValueError("fixture manifest mismatch")
        variables = manifest.get("variables")
        if type(variables) is not dict or set(variables) != set(("resistance_ohm", "capacitance_f", "stop_time_s")):
            raise ValueError("fixture variables mismatch")
        for name, unit in (("resistance_ohm", "ohm"), ("capacitance_f", "F"), ("stop_time_s", "s")):
            if type(variables[name]) is not dict or variables[name].get("unit") != unit or type(variables[name].get("value")) not in (str, unicode):
                raise ValueError("fixture variable binding mismatch")
        sys.stdout.write(json.dumps({"variables": variables}, sort_keys=True) + "\n")
        return
    if os.path.islink(MARKERS) or not os.path.isdir(MARKERS):
        raise ValueError("reservation root")
    marker = MARKERS + "/" + job_id + ".json"
    if os.path.lexists(marker):
        record = json.loads(read(marker, 1024))
        if (record.get("job_id") != job_id or record.get("campaign_id") != "AUTO-PHASE-01" or
                type(record.get("count")) is not int or
                type(record.get("result_reserved_bytes")) is not int):
            raise ValueError("reservation marker")
        counter = json.loads(read(COUNTER, 1024))
        if counter.get("count", -1) < record["count"] or counter.get("result_reserved_bytes", -1) < record["result_reserved_bytes"]:
            raise ValueError("reservation counter regressed")
        sys.stdout.write('{"reserved":true}\n')
        return
    if sys.argv[1] == "lookup":
        sys.stdout.write('{"reserved":false}\n')
        return
    counter = json.loads(read(COUNTER, 1024))
    if counter.get("campaign_id") != "AUTO-PHASE-01" or type(counter.get("count")) is not int or not 11 <= counter["count"] < 100:
        raise ValueError("Spectre budget")
    if type(counter.get("result_reserved_bytes")) is not int or counter["result_reserved_bytes"] < 269484032 or counter["result_reserved_bytes"] + RESERVE_BYTES > 5 * 1024 ** 3:
        raise ValueError("result budget")
    process = subprocess.Popen(["ps", "-eo", "comm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process_output, unused_error = process.communicate()
    if process.returncode != 0 or any(name.strip() in ("spectre", "ocean", "virtuoso") for name in process_output.decode("ascii", "ignore").splitlines()):
        raise ValueError("active EDA process")
    fs = os.statvfs(ROOT)
    total = fs.f_blocks * fs.f_frsize
    free = fs.f_bavail * fs.f_frsize
    if free - RESERVE_BYTES < max(2 * 1024 ** 3, (total + 9) // 10):
        raise ValueError("free-space floor")
    new = {"campaign_id": "AUTO-PHASE-01", "count": counter["count"] + 1,
           "result_reserved_bytes": counter["result_reserved_bytes"] + RESERVE_BYTES}
    temporary = COUNTER + ".sweep-tmp"
    if os.path.lexists(temporary):
        raise ValueError("counter update uncertain")
    write_new(temporary, json.dumps(new, sort_keys=True))
    os.rename(temporary, COUNTER)
    # If power fails here, budget is conservatively consumed but the caller
    # sees UNKNOWN and never starts an unreserved simulation.
    write_new(marker, json.dumps({"job_id": job_id, "campaign_id": "AUTO-PHASE-01",
                                 "count": new["count"],
                                 "result_reserved_bytes": new["result_reserved_bytes"]}, sort_keys=True))
    sys.stdout.write('{"reserved":true}\n')


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError):
        sys.stderr.write("sweep budget reservation unavailable\n")
        sys.exit(69)
