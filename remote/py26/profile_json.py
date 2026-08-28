#!/usr/bin/env python
"""Python 2.6-compatible fixed simulation profile preparation."""

from __future__ import with_statement

import decimal
import json
import os
import re
import sys

JOB_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
JOBS_ROOT = "/home/buet/cds_work/.cadence_mcp/jobs"
PROFILE_ID = "fixture-rc-transient"
CORNER = "nominal"


def atomic_json(path, payload):
    temporary = path + ".%s.tmp" % os.getpid()
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, int("600", 8))
    with os.fdopen(descriptor, "w") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.rename(temporary, path)


def decimal_value(text, minimum, maximum, name):
    try:
        value = decimal.Decimal(text)
    except decimal.InvalidOperation:
        raise ValueError("invalid %s" % name)
    if (
        not value.is_finite()
        or value < decimal.Decimal(minimum)
        or value > decimal.Decimal(maximum)
    ):
        raise ValueError("%s is outside the profile range" % name)
    return value


def load_profile(path):
    with open(path, "rb") as handle:
        profile = json.load(handle)
    if (
        profile.get("registry_version") != 1
        or profile.get("profile_id") != PROFILE_ID
        or profile.get("classification") != "fixture"
        or profile.get("netlist_source") != "built-in-rc-template"
        or profile.get("analyses") != ["tran"]
        or profile.get("corners") != [CORNER]
        or profile.get("outputs") != ["out"]
        or profile.get("timeout_seconds") != 60
    ):
        raise ValueError("invalid fixed profile registry")
    return profile


def validated_values(
    profile_path, profile_id, corner, resistance_text, capacitance_text, stop_time_text
):
    profile = load_profile(profile_path)
    if profile_id != PROFILE_ID or corner != CORNER:
        raise ValueError("profile or corner is outside the registry")
    return (
        profile,
        decimal_value(resistance_text, "100", "10000", "resistance_ohm"),
        decimal_value(capacitance_text, "1e-13", "1e-10", "capacitance_f"),
        decimal_value(stop_time_text, "1e-10", "1e-7", "stop_time_s"),
    )


def prepare(arguments):
    (
        profile_path,
        job_dir,
        job_id,
        profile_id,
        corner,
        resistance_text,
        capacitance_text,
        stop_time_text,
        submitted_at,
        origin,
        submitted_by,
    ) = arguments
    profile, resistance, capacitance, stop_time = validated_values(
        profile_path,
        profile_id,
        corner,
        resistance_text,
        capacitance_text,
        stop_time_text,
    )
    real_root = os.path.realpath(JOBS_ROOT)
    real_job_dir = os.path.realpath(job_dir)
    if (
        JOB_ID_PATTERN.match(job_id) is None
        or os.path.basename(real_job_dir) != job_id
        or os.path.dirname(real_job_dir) != real_root
        or os.path.islink(job_dir)
        or not os.path.isdir(job_dir)
    ):
        raise ValueError("invalid profile job directory")
    if origin not in ("mcp", "operator") or ACTOR_PATTERN.match(submitted_by) is None:
        raise ValueError("invalid profile submitter")
    artifacts_dir = os.path.join(job_dir, "artifacts")
    os.mkdir(artifacts_dir, int("700", 8))
    netlist_path = os.path.join(artifacts_dir, "profile.scs")
    descriptor = os.open(netlist_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, int("600", 8))
    with os.fdopen(descriptor, "w") as handle:
        handle.write("simulator lang=spectre\n\n")
        handle.write("V1 (in 0) vsource dc=1\n")
        handle.write("R1 (in out) resistor r=%s\n" % resistance)
        handle.write("C1 (out 0) capacitor c=%s\n\n" % capacitance)
        handle.write("save out\n")
        handle.write("tran1 tran stop=%s\n" % stop_time)
        handle.flush()
        os.fsync(handle.fileno())
    variables = {
        "capacitance_f": {"unit": "F", "value": str(capacitance)},
        "resistance_ohm": {"unit": "ohm", "value": str(resistance)},
        "stop_time_s": {"unit": "s", "value": str(stop_time)},
    }
    atomic_json(
        os.path.join(artifacts_dir, "run-manifest.json"),
        {
            "analyses": profile["analyses"],
            "classification": profile["classification"],
            "corner": corner,
            "job_id": job_id,
            "netlist_source": profile["netlist_source"],
            "outputs": profile["outputs"],
            "profile_id": profile_id,
            "registry_version": profile["registry_version"],
            "submitted_at": submitted_at,
            "timeout_seconds": profile["timeout_seconds"],
            "variables": variables,
        },
    )
    atomic_json(
        os.path.join(job_dir, "request.json"),
        {
            "corner": corner,
            "job_id": job_id,
            "origin": origin,
            "profile": profile_id,
            "submitted_at": submitted_at,
            "submitted_by": submitted_by,
            "variables": variables,
        },
    )


def main():
    try:
        if len(sys.argv) == 8 and sys.argv[1] == "validate":
            validated_values(*sys.argv[2:])
        elif len(sys.argv) == 13 and sys.argv[1] == "prepare":
            prepare(sys.argv[2:])
        else:
            return 64
    except (IOError, OSError, ValueError, KeyError, TypeError, decimal.InvalidOperation) as error:
        sys.stderr.write(str(error) + "\n")
        return 64
    return 0


if __name__ == "__main__":
    sys.exit(main())
