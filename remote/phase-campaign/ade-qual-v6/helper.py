#!/usr/bin/env python
"""Python 2.6 fixed ADE state qualification; raw evidence remains job-owned."""
from __future__ import with_statement

import hashlib
import imp
import json
import math
import os
import re
import shutil
import sys
import socket
import pwd

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/ade-qual-v6"
JOB = ROOT + "/ade-qual-v6"
STATE = "/home/buet/.artist_states/MyDesignLib/Differential_Amplifier_TB2/spectre/state1"
COPIED_STATE = JOB + "/state-root/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/spectre/state1"
NETDIR = JOB + "/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
MODEL = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"
COUNTER = ROOT + "/sim-mcp-v2-jobs/counter.json"
RESERVATION = 128 * 1024 * 1024
try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)
STAGES = ("netlisting", "netlist_failed", "netlisted", "reserving", "reservation_failed",
          "simulating", "simulator_failed", "extracting", "extraction_failed",
          "verifying", "verification_failed", "succeeded")
NATIVE_CONTROL = '''simulatorOptions options reltol=1e-3 vabstol=1e-6 iabstol=1e-12 temp=27
tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 maxnotes=5 maxwarns=5
digits=5 cols=80 pivrel=1e-3 sensfile="../psf/sens.output"
checklimitdest=psf
dcOp dc write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status
dcOpInfo info what=oppoint where=rawfile
modelParameter info what=models where=rawfile
element info what=inst where=rawfile
outputParameter info what=output where=rawfile
designParamVals info what=parameters where=rawfile
primitives info what=primitives where=rawfile
subckts info what=subckts where=rawfile
saveOptions options save=allpub'''


def read(path, limit=1048576):
    if os.path.islink(path) or not os.path.isfile(path) or os.stat(path).st_size > limit:
        raise ValueError("unsafe bounded file")
    with open(path, "rb") as stream:
        return stream.read(limit + 1)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_new(path, data):
    if not isinstance(data, bytes):
        data = data.encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def save(path, data):
    write_new(path, json.dumps(data, sort_keys=True))


def emit(data):
    text = json.dumps(data, sort_keys=True)
    if len(text) > 32768:
        raise ValueError("result limit")
    sys.stdout.write(text + "\n")


def guard():
    return imp.load_source("ade_qual_diag", ROOT + "/phase-campaign/sim-mcp-v2/diagnostic.py")


def snapshot():
    # Reuses pinned source, state, model, source-copy and snapshot regression guards.
    return guard().snapshot()


def number(text):
    match = re.match(r"^([+-]?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)([munpf]?)$", text)
    if not match:
        raise ValueError("bounded engineering number")
    value = float(match.group(1)) * {"": 1, "m": 1e-3, "u": 1e-6,
                                   "n": 1e-9, "p": 1e-12, "f": 1e-15}[match.group(2)]
    if math.isnan(value) or math.isinf(value) or abs(value) > 1e12:
        raise ValueError("nonfinite or unbounded number")
    return value


def state_facts():
    variables = read(STATE + "/variables").decode("latin-1")
    names = dict(re.findall(r'(?m)^tmp([0-9]+)->name = "([^"]+)"$', variables))
    expressions = dict(re.findall(r'(?m)^tmp([0-9]+)->expression = "([^"]+)"$', variables))
    if set(names) != set(expressions) or set(names.values()) != set(("VBIASN", "VBIASP")):
        raise ValueError("state variable binding")
    values = dict((name, number(expressions[index])) for index, name in names.items())
    analyses = read(STATE + "/analyses").decode("latin-1")
    enabled = re.findall(r"(?m)^analysis\(([A-Za-z]+) fields enable\) \(t\)$", analyses)
    if enabled != ["dc"]:
        raise ValueError("only current-state DC bundle is qualified")
    model = read(STATE + "/modelSetup").decode("latin-1").strip()
    binding = re.match(r'^\(\("([^"\n]+)" "NN"\)\)$', model)
    if binding is None or os.path.realpath(binding.group(1)) != MODEL:
        raise ValueError("state model binding")
    options = read(STATE + "/simulatorOptions").decode("latin-1")
    temperature = re.findall(r'(?m)^\(opts temp\) "([^"]+)"$', options)
    if len(temperature) != 1 or number(temperature[0]) != 27:
        raise ValueError("state temperature")
    return {"variables_v": values, "enabled_analyses": enabled,
            "model_section": "NN", "temperature_c": 27}


def environment_preflight():
    if socket.gethostname() != "cadence" or pwd.getpwuid(os.getuid()).pw_name != "buet":
        raise ValueError("remote identity")
    disk = os.statvfs(ROOT)
    free = disk.f_bavail * disk.f_frsize
    total = disk.f_blocks * disk.f_frsize
    if free - RESERVATION < max(2 * 1024 ** 3, (total + 9) // 10):
        raise ValueError("managed disk floor")


def remap_info(text):
    identity = 'designInfo = \'("MyDesignLib" "Differential_Amplifier_TB2" "schematic" "spectre")'
    project = 'projectDir = \'"~/simulation"'
    if text.count(identity) != 1 or text.count(project) != 1:
        raise ValueError("state identity or project path changed")
    return text.replace(identity, 'designInfo = \'("MCP_WorkLib" "WP14_AUTO_PHASE_01_TB2" "schematic" "spectre")').replace(
        project, 'projectDir = \'"' + JOB + '/project"')


def prepare():
    environment_preflight()
    before = snapshot()
    facts = state_facts()
    if os.path.lexists(JOB):
        raise ValueError("netlist replay")
    os.mkdir(JOB, 0o700)
    os.makedirs(JOB + "/project", 0o700)
    os.makedirs(os.path.dirname(COPIED_STATE), 0o700)
    shutil.copytree(STATE, COPIED_STATE)
    for current, dirs, files in os.walk(COPIED_STATE):
        os.chmod(current, 0o700)
        for name in files:
            os.chmod(os.path.join(current, name), 0o600)
    path = COPIED_STATE + "/ADE_state.info"
    original = read(path).decode("latin-1")
    replacement = remap_info(original).encode("latin-1")
    # Only the owned state copy's routing changes. Other state files stay byte-identical.
    with open(path, "wb") as stream:
        stream.write(replacement)
    before["state_facts"] = facts
    before["state_copy_info_sha256"] = sha(replacement)
    save(JOB + "/before.json", before)
    set_stage("netlisting")
    verify_protected(before)


def verify_protected(before):
    after = snapshot()
    expected = dict((key, before[key]) for key in after)
    if expected != after or before["state_facts"] != state_facts():
        raise ValueError("protected drift")
    if sha(read(COPIED_STATE + "/ADE_state.info")) != before["state_copy_info_sha256"]:
        raise ValueError("owned state routing drift")
    if state_records(STATE) != state_records(COPIED_STATE):
        raise ValueError("owned state content drift")


def state_records(root):
    records = []
    if os.path.islink(root) or not os.path.isdir(root):
        raise ValueError("state root boundary")
    for current, dirs, files in os.walk(root):
        relative = os.path.relpath(current, root)
        for name in dirs:
            if os.path.islink(os.path.join(current, name)):
                raise ValueError("state directory link")
            records.append(("directory", os.path.join(relative, name)))
        for name in files:
            if relative == "." and name == "ADE_state.info":
                continue
            records.append(("file", os.path.join(relative, name), sha(read(os.path.join(current, name)))))
    return sorted(records)


def circuit_records(text):
    return " ".join(line.strip() for line in text.splitlines()
                    if line.strip() and not line.strip().startswith("//"))


def validate_netlist(text, circuit, previous, facts):
    if circuit_records(circuit) != circuit_records(previous):
        raise ValueError("source-copy netlist semantic drift")
    if circuit.count("V0 (VDD 0) vsource dc=1 type=dc") != 1:
        raise ValueError("VDD constraint")
    for name, value in facts["variables_v"].items():
        matches = re.findall(r"\b" + name + r"=([^\s\\]+)", text)
        if len(matches) != 1 or abs(number(matches[0]) - value) > 1e-15:
            raise ValueError("effective design variable mismatch")
    includes = re.findall(r'(?m)^include "([^"]+)"(?: section=([A-Za-z0-9_]+))?', text)
    if len(includes) != 1 or (os.path.realpath(includes[0][0]), includes[0][1]) != (MODEL, "NN"):
        raise ValueError("input include boundary")
    # This installed native netlister embeds the full circuit rather than an include.
    if not circuit or text.count(circuit) != 1:
        raise ValueError("native inline circuit binding")
    prefix, suffix = text.split(circuit)
    header = [line.strip() for line in prefix.splitlines()
              if line.strip() and not line.strip().startswith("//")]
    if (len(header) != 4 or header[:2] != ["simulator lang=spectre", "global 0"] or
            not re.match(r'^parameters VBIASN=[^\s]+ VBIASP=[^\s]+$', header[2]) or
            header[3] != 'include "' + includes[0][0] + '" section=NN'):
        raise ValueError("native header boundary")
    if circuit_records(suffix).replace("\\", "").split() != NATIVE_CONTROL.split():
        raise ValueError("native control boundary")
    analyses = re.findall(r"(?m)^([A-Za-z0-9_]+)\s+(dc|ac|tran|noise|stb)\b", text)
    if len(analyses) != 1 or analyses[0][1] != "dc":
        raise ValueError("analysis bundle mismatch")
    temperatures = re.findall(r"\btemp=([^\s\\]+)", text)
    if len(temperatures) != 1 or number(temperatures[0]) != facts["temperature_c"]:
        raise ValueError("effective temperature mismatch")
    return analyses[0][0]


def validate_native_log(output):
    lines = output.splitlines()
    actual = [line[3:].strip() for line in lines if line.startswith("\\o ")]
    if any(line.startswith("\\e ") or "*Error*" in line for line in lines
           if not line.startswith("\\i ")):
        raise ValueError("native ADE error")
    for marker in ("MCP_ADE_SOURCE_COPY|true", "MCP_ADE_SESSION|true",
                   "MCP_ADE_STATE_LOAD|true", "MCP_ADE_NETLIST|true"):
        if actual.count(marker) != 1:
            raise ValueError("native state load or copy equivalence incomplete")


def netlist():
    before = json.loads(read(JOB + "/before.json"))
    verify_protected(before)
    output = read(JOB + "/netlist.log").decode("latin-1")
    validate_native_log(output)
    text = read(NETDIR + "/input.scs").decode("latin-1")
    circuit = read(NETDIR + "/netlist").decode("latin-1")
    previous = read(guard().NETLIST).decode("latin-1")
    result_name = validate_netlist(text, circuit, previous, before["state_facts"])
    data = {"execution_mode": "ade_state", "analysis": "dc", "result_name": result_name,
            "source_sha256": before["source_sha256"], "state_sha256": before["protected"]["ade_state_tree"],
            "model_sha256": before["model_sha256"], "copy_sha256": before["copy_sha256"],
            "input_sha256": sha(text.encode("latin-1")), "circuit_sha256": sha(circuit.encode("latin-1")),
            "effective": before["state_facts"], "vdd_v": 1.0,
            "source_copy_signature_equal": True, "protected_unchanged": True,
            "state_loaded": True, "netlist_valid": True, "simulation": "not_started",
            "spec_evaluation": "not_evaluated"}
    emit(data)


def verify_netlist():
    facts = json.loads(read(JOB + "/netlist-result.json"))
    before = json.loads(read(JOB + "/before.json"))
    verify_protected(before)
    if (facts["input_sha256"] != sha(read(NETDIR + "/input.scs")) or
            facts["circuit_sha256"] != sha(read(NETDIR + "/netlist"))):
        raise ValueError("netlist changed")
    return facts


def reserve():
    environment_preflight()
    verify_netlist()
    if os.path.lexists(JOB + "/attempt-reserved"):
        raise ValueError("simulation replay")
    counter = json.loads(read(COUNTER, 1024))
    if (counter.get("campaign_id") != "AUTO-PHASE-01" or
            type(counter.get("count")) not in INTEGER_TYPES or not 14 <= counter["count"] < 100):
        raise ValueError("simulation budget")
    if (type(counter.get("result_reserved_bytes")) not in INTEGER_TYPES or
            not 672137216 <= counter["result_reserved_bytes"] <= 5 * 1024 ** 3 - RESERVATION):
        raise ValueError("result budget")
    counter["count"] += 1
    counter["result_reserved_bytes"] += RESERVATION
    # Intent precedes the counter update. A crash at either step blocks replay.
    save(JOB + "/attempt-reserved", counter)
    save(COUNTER + ".ade-tmp", counter)
    os.rename(COUNTER + ".ade-tmp", COUNTER)


def extraction():
    facts = verify_netlist()
    text = read(ROOT + "/phase-campaign/sim-mcp-v2/extract-dc.ocn").decode("ascii")
    if facts["result_name"] != "dcOp":
        raise ValueError("unqualified native DC result name")
    # Verify results() advertises the exact native analysis before selecting it.
    text = text.replace("@JOB@", JOB).replace("  unless(selectResult('dc) close(port) exit(1))",
        '  unless(member(\'dcOp results()) || member("dcOp" results()) close(port) exit(1))\n'
        "  unless(selectResult('dcOp) close(port) exit(1))\n"
        '  let((proof) proof=outfile("' + JOB + '/selector.txt")\n'
        '    unless(proof close(port) exit(1))\n'
        '    fprintf(proof "MCP_ADE_RESULT_SELECTOR|dcOp\\n") close(proof))')
    write_new(JOB + "/extract.ocn", text)


def complete():
    facts = verify_netlist()
    diag = guard()
    log = read(JOB + "/spectre.log").decode("latin-1")
    summary = diag.SUMMARY.findall(log)
    if len(summary) != 1 or int(summary[0][0]) != 0:
        raise ValueError("simulator result invalid")
    warnings = [line for line in log.splitlines() if "WARNING" in line]
    if (int(summary[0][1]) > 2 or len(warnings) != int(summary[0][1]) or
            any("WARNING (CMI-2477):" not in line for line in warnings)):
        raise ValueError("simulator warning quality")
    scalars = diag.dc_result(read(JOB + "/scalars.txt").decode("ascii"))
    extract_log = read(JOB + "/extract.log").decode("latin-1")
    if (read(JOB + "/selector.txt", 64) != b"MCP_ADE_RESULT_SELECTOR|dcOp\n" or
            any("*Error*" in line for line in extract_log.splitlines() if not line.startswith("\\i "))):
        raise ValueError("native result selector evidence")
    data = dict((item["logical_id"], item["value"]) for item in scalars)
    if abs(data["vdd"] - 1.0) > 1e-9:
        raise ValueError("measured VDD constraint")
    psf = imp.load_source("ade_qual_role", ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py")._tree_fingerprint(JOB + "/psf")
    if psf["entry_count"] == 0 or psf["total_bytes"] <= 0 or psf["total_bytes"] > RESERVATION:
        raise ValueError("PSF bound")
    facts.update({"simulation": "succeeded", "extraction": "succeeded", "quality": "valid",
                  "psf_sha256": psf["sha256"], "scalars": scalars,
                  "warnings": int(summary[0][1]), "notices": int(summary[0][2]),
                  "output_common_mode_v": data["output_common_mode"],
                  "output_differential_v": data["output_differential"],
                  "result_selector": "dcOp", "input_vcm_v": (data["vp"] + data["vm"]) / 2.0,
                  "counter": json.loads(read(COUNTER, 1024))})
    emit(facts)


def set_stage(stage):
    if stage not in STAGES or os.path.islink(JOB):
        raise ValueError("invalid stage")
    write_new(JOB + "/stage.new", stage + "\n")
    os.rename(JOB + "/stage.new", JOB + "/stage")


def status():
    if not os.path.lexists(JOB):
        emit({"state": "not_run", "simulation": "not_started", "extraction": "not_started"})
        return
    stage = read(JOB + "/stage", 64).decode("ascii").strip()
    if stage not in STAGES:
        raise ValueError("corrupt stage")
    state = ("succeeded" if stage == "succeeded" else "failed" if stage.endswith("_failed")
             else "netlisted" if stage == "netlisted" else "unknown")
    # An interrupted process is not reported as running or as the old netlist success.
    result = {"state": state, "stage": stage,
              "attempt_reserved": os.path.lexists(JOB + "/attempt-reserved"),
              "simulation": "succeeded" if stage in ("extracting", "extraction_failed", "verifying",
                                                        "verification_failed", "succeeded")
                            else "failed" if stage == "simulator_failed" else "not_confirmed",
              "extraction": "succeeded" if stage in ("verifying", "verification_failed", "succeeded")
                            else "failed" if stage == "extraction_failed" else "not_confirmed"}
    if stage == "succeeded":
        result["result"] = json.loads(read(JOB + "/result.json", 32768))
    emit(result)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "stage":
        set_stage(sys.argv[2])
        return
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "netlist", "reserve", "extraction", "complete", "status"):
        sys.exit(64)
    if sys.argv[1] == "status":
        status()
    else:
        globals()[sys.argv[1]]()


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
        sys.stderr.write("fixed ADE state qualification failed\n")
        sys.exit(69)
