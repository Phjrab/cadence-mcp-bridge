#!/usr/bin/env python
"""Python 2.6-compatible fixed simulation profile preparation."""

from __future__ import with_statement

import decimal
import hashlib
import json
import os
import re
import stat
import sys

JOB_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
JOBS_ROOT = "/home/buet/cds_work/.cadence_mcp/jobs"
FIXTURE_PROFILE_ID = "fixture-rc-transient"
ACTUAL_PROFILE_ID = "actual-differential-amplifier-tb2-transient"
FIXTURE_CORNER = "nominal"
ACTUAL_CORNER = "NN"
ACTUAL_SOURCE_NETLIST = (
    "/home/buet/simulation/Differential_Amplifier_TB2/spectre/schematic/netlist/netlist"
)
ACTUAL_STATE_PATH = (
    "/home/buet/.artist_states/MyDesignLib/Differential_Amplifier_TB2/spectre/state1"
)
ACTUAL_MODEL_FILE = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"
MAX_SOURCE_BYTES = 10 * 1024 * 1024


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


def load_json(path):
    with open(path, "rb") as handle:
        return json.load(handle)


def load_fixture_profile(path):
    profile = load_json(path)
    if (
        profile.get("registry_version") != 1
        or profile.get("profile_id") != FIXTURE_PROFILE_ID
        or profile.get("classification") != "fixture"
        or profile.get("netlist_source") != "built-in-rc-template"
        or profile.get("analyses") != ["tran"]
        or profile.get("corners") != [FIXTURE_CORNER]
        or profile.get("outputs") != ["out"]
        or profile.get("timeout_seconds") != 60
    ):
        raise ValueError("invalid fixed fixture profile registry")
    return profile


def load_actual_profile(path):
    profile = load_json(path)
    expected = {
        "registry_version": 1,
        "profile_id": ACTUAL_PROFILE_ID,
        "classification": "actual",
        "netlist_source": "ade-l-state-netlist",
        "library": "MyDesignLib",
        "cell": "Differential_Amplifier_TB2",
        "view": "schematic",
        "ade_product": "ADE L",
        "state": "state1",
        "pdk": "gpdk090",
        "pdk_version": "4.6",
        "model_file": ACTUAL_MODEL_FILE,
        "model_section": ACTUAL_CORNER,
        "temperature_c": 27.0,
        "analyses": ["tran"],
        "spectre_stop_time": "4m",
        "stop_time_s": 0.004,
        "fixed_parameters": {"VBIASN": "300m", "VBIASP": "650m"},
        "variables": {},
        "corners": [ACTUAL_CORNER],
        "outputs": [],
        "timeout_seconds": 300,
        "warning_policy": {"allowed_codes": ["CMI-2477"], "maximum_count": 2},
        "source_netlist": ACTUAL_SOURCE_NETLIST,
        "state_path": ACTUAL_STATE_PATH,
    }
    if profile != expected:
        raise ValueError("invalid fixed actual profile registry")
    return profile


def validate_source_file(path):
    if path != ACTUAL_SOURCE_NETLIST or os.path.islink(path):
        raise ValueError("invalid actual profile source")
    source_stat = os.stat(path)
    if (
        not stat.S_ISREG(source_stat.st_mode)
        or source_stat.st_size <= 0
        or source_stat.st_size > MAX_SOURCE_BYTES
        or not os.access(path, os.R_OK)
    ):
        raise ValueError("actual profile source is unavailable")


def validate_actual_paths(profile):
    validate_source_file(profile["source_netlist"])
    if (
        profile["model_file"] != ACTUAL_MODEL_FILE
        or not os.path.isfile(ACTUAL_MODEL_FILE)
        or not os.access(ACTUAL_MODEL_FILE, os.R_OK)
    ):
        raise ValueError("actual profile model is unavailable")
    if (
        profile["state_path"] != ACTUAL_STATE_PATH
        or os.path.islink(ACTUAL_STATE_PATH)
        or not os.path.isdir(ACTUAL_STATE_PATH)
        or not os.access(ACTUAL_STATE_PATH, os.R_OK)
    ):
        raise ValueError("actual ADE state is unavailable")


def validated_fixture_values(
    profile_path, profile_id, corner, resistance_text, capacitance_text, stop_time_text
):
    profile = load_fixture_profile(profile_path)
    if profile_id != FIXTURE_PROFILE_ID or corner != FIXTURE_CORNER:
        raise ValueError("profile or corner is outside the registry")
    return (
        profile,
        decimal_value(resistance_text, "100", "10000", "resistance_ohm"),
        decimal_value(capacitance_text, "1e-13", "1e-10", "capacitance_f"),
        decimal_value(stop_time_text, "1e-10", "1e-7", "stop_time_s"),
    )


def validated_actual_profile(profile_path, profile_id, corner):
    profile = load_actual_profile(profile_path)
    if profile_id != ACTUAL_PROFILE_ID or corner != ACTUAL_CORNER:
        raise ValueError("profile or corner is outside the registry")
    validate_actual_paths(profile)
    return profile


def validate_job(job_dir, job_id, origin, submitted_by):
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


def create_artifacts_dir(job_dir):
    artifacts_dir = os.path.join(job_dir, "artifacts")
    os.mkdir(artifacts_dir, int("700", 8))
    return artifacts_dir


def write_file(path, content):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, int("600", 8))
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def copy_bounded(source, destination):
    validate_source_file(source)
    digest = hashlib.sha256()
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, int("600", 8))
    # Python 2.6 does not support multiple context managers in one with statement.
    with open(source, "rb") as source_handle:  # noqa: SIM117
        with os.fdopen(descriptor, "wb") as destination_handle:
            total = 0
            while True:
                chunk = source_handle.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise ValueError("actual profile source exceeds size limit")
                digest.update(chunk)
                destination_handle.write(chunk)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
    return digest.hexdigest()


def prepare_fixture(arguments):
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
    profile, resistance, capacitance, stop_time = validated_fixture_values(
        profile_path,
        profile_id,
        corner,
        resistance_text,
        capacitance_text,
        stop_time_text,
    )
    validate_job(job_dir, job_id, origin, submitted_by)
    artifacts_dir = create_artifacts_dir(job_dir)
    netlist = (
        "simulator lang=spectre\n\n"
        "V1 (in 0) vsource dc=1\n"
        "R1 (in out) resistor r=%s\n"
        "C1 (out 0) capacitor c=%s\n\n"
        "save out\n"
        "tran1 tran stop=%s\n"
    ) % (resistance, capacitance, stop_time)
    write_file(os.path.join(artifacts_dir, "profile.scs"), netlist)
    variables = {
        "capacitance_f": {"unit": "F", "value": str(capacitance)},
        "resistance_ohm": {"unit": "ohm", "value": str(resistance)},
        "stop_time_s": {"unit": "s", "value": str(stop_time)},
    }
    write_records(
        profile,
        artifacts_dir,
        job_dir,
        job_id,
        profile_id,
        corner,
        variables,
        submitted_at,
        origin,
        submitted_by,
        None,
    )


def prepare_actual(arguments):
    (
        profile_path,
        job_dir,
        job_id,
        profile_id,
        corner,
        submitted_at,
        origin,
        submitted_by,
    ) = arguments
    profile = validated_actual_profile(profile_path, profile_id, corner)
    validate_job(job_dir, job_id, origin, submitted_by)
    artifacts_dir = create_artifacts_dir(job_dir)
    source_hash = copy_bounded(
        profile["source_netlist"], os.path.join(artifacts_dir, "design-netlist.scs")
    )
    wrapper = (
        "simulator lang=spectre\n\n"
        "global 0\n"
        "include \"%s\" section=%s\n"
        "parameters VBIASN=300m VBIASP=650m\n"
        "include \"design-netlist.scs\"\n\n"
        "simulatorOptions options temp=%s tnom=%s\n"
        "tran_profile tran stop=%s\n"
    ) % (
        profile["model_file"],
        profile["model_section"],
        profile["temperature_c"],
        profile["temperature_c"],
        profile["spectre_stop_time"],
    )
    write_file(os.path.join(artifacts_dir, "profile.scs"), wrapper)
    write_records(
        profile,
        artifacts_dir,
        job_dir,
        job_id,
        profile_id,
        corner,
        {},
        submitted_at,
        origin,
        submitted_by,
        source_hash,
    )


def write_records(
    profile,
    artifacts_dir,
    job_dir,
    job_id,
    profile_id,
    corner,
    variables,
    submitted_at,
    origin,
    submitted_by,
    source_hash,
):
    manifest = {
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
        "warning_policy": profile.get(
            "warning_policy", {"allowed_codes": [], "maximum_count": 0}
        ),
    }
    if profile["classification"] == "actual":
        manifest["ade"] = {
            "ade_product": profile["ade_product"],
            "cell": profile["cell"],
            "fixed_parameters": profile["fixed_parameters"],
            "library": profile["library"],
            "model_section": profile["model_section"],
            "pdk": profile["pdk"],
            "pdk_version": profile["pdk_version"],
            "spectre_stop_time": profile["spectre_stop_time"],
            "state": profile["state"],
            "stop_time_s": profile["stop_time_s"],
            "temperature_c": profile["temperature_c"],
            "view": profile["view"],
        }
        manifest["source_sha256"] = source_hash
    atomic_json(os.path.join(artifacts_dir, "run-manifest.json"), manifest)
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


def manifest_timeout(path):
    manifest = load_json(path)
    timeout_seconds = manifest.get("timeout_seconds")
    if timeout_seconds not in (60, 300):
        raise ValueError("invalid profile timeout")
    sys.stdout.write(str(timeout_seconds) + "\n")


def manifest_warning_policy(path):
    manifest = load_json(path)
    policy = manifest.get("warning_policy")
    if policy == {"allowed_codes": [], "maximum_count": 0}:
        sys.stdout.write("strict\n")
    elif policy == {"allowed_codes": ["CMI-2477"], "maximum_count": 2}:
        sys.stdout.write("allow-cmi-2477-2\n")
    else:
        raise ValueError("invalid profile warning policy")


def main():
    try:
        if len(sys.argv) == 8 and sys.argv[1] in ("validate", "validate-fixture"):
            validated_fixture_values(*sys.argv[2:])
        elif len(sys.argv) == 13 and sys.argv[1] in ("prepare", "prepare-fixture"):
            prepare_fixture(sys.argv[2:])
        elif len(sys.argv) == 5 and sys.argv[1] == "validate-actual":
            validated_actual_profile(*sys.argv[2:])
        elif len(sys.argv) == 10 and sys.argv[1] == "prepare-actual":
            prepare_actual(sys.argv[2:])
        elif len(sys.argv) == 3 and sys.argv[1] == "manifest-timeout":
            manifest_timeout(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == "manifest-warning-policy":
            manifest_warning_policy(sys.argv[2])
        else:
            return 64
    except (IOError, OSError, ValueError, KeyError, TypeError, decimal.InvalidOperation) as error:
        sys.stderr.write(str(error) + "\n")
        return 64
    return 0


if __name__ == "__main__":
    sys.exit(main())
