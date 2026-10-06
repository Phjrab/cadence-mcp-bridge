"""Fixed read-only reference loop audit; no simulation or caller execution inputs."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import ade_qual as io
import bandwidth_qualification as bandwidth
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/ANALOG_PM_AUDIT_V1.json"
DELEGATION = ROOT / ".codex/analog-pm01-delegation-v1.private.json"
SOURCE_INPUT = "53dd6c3bdee80808bfd67880f7e43be289fb275abf4f5486adf5b13f6aad275a"
SOURCE_CIRCUIT = "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a"
TOPICS = ("stb", "iprobe", "diffstbprobe")

# Constant operator program, never an MCP request or model-controlled expression.
# All raw circuit/help text is saved privately and excluded from normal output.
REMOTE_CODE = r"""
import imp,json,subprocess,os,fcntl
R="/home/buet/cds_work/.cadence_mcp"
lock=R+"/run.lock"
if os.path.realpath(lock)!=lock or not os.path.isfile(lock):raise ValueError("EDA lock identity")
fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
running=subprocess.Popen(["ps","-eo","comm"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
out,err=running.communicate()
if running.returncode or err or len(out)>65536:raise ValueError("worker state unknown")
if any(x.strip() in ("spectre","ocean","virtuoso") for x in out.splitlines()):
    raise ValueError("active EDA")
for version in ("bandwidth-qual-v1","native-mcp-v3","native-mcp-v2","native-mcp-v1",
                "native-candidate-v2","native-ac-tran-v4","native-ac-tran-v3",
                "ade-qual-v6","sim-mcp-v2","role-v1"):
    p=subprocess.Popen(["sha256sum","-c","manifest.sha256"],cwd=R+"/phase-campaign/"+version,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    out,err=p.communicate()
    if p.returncode or err:raise ValueError("immutable manifest")
m=imp.load_source("pm_reference_audit",R+"/phase-campaign/bandwidth-qual-v1/helper.py")
m.authorization()
before=m.checkpoint()
m.source()
B=m.B
text=B.read(B.NETDIR+"/input.scs",65536)
circuit=B.read(B.NETDIR+"/netlist",65536).decode("latin-1")
if B.sha(text)!=m.INPUT_SHA:raise ValueError("pinned input")
helps={}
exe="/home/buet/cadence/MMSIM121/tools/bin/spectre"
for topic in ("stb","iprobe","diffstbprobe"):
    p=subprocess.Popen(["timeout","20",exe,"-h",topic],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    out,err=p.communicate()
    if len(out)+len(err)>16384:raise ValueError("bounded installed help")
    helps[topic]={"returncode":p.returncode,"stdout":out.decode("latin-1"),"stderr":err.decode("latin-1")}
if before!=m.checkpoint():raise ValueError("protected reference drift")
result={"schema_version":1,"source_input_sha256":B.sha(text),"circuit":circuit,
        "help":helps,"protected_unchanged":True,"counter":m.counter(True)}
output=json.dumps(result,sort_keys=True)
if len(output)>65536:raise ValueError("bounded private audit")
print(output)
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def topology(circuit: str) -> dict[str, Any]:
    """Inspect explicit terminal connectivity, never infer model-internal stability."""
    if not isinstance(circuit, str) or not 0 < len(circuit) <= 65536:
        raise ValueError("bounded circuit required")
    circuit = re.sub(r"\\\r?\n\s*", " ", circuit)
    instances: dict[str, tuple[list[str], str]] = {}
    for line in circuit.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_]+) \(([A-Za-z0-9_ ]+)\) ([A-Za-z0-9_]+)(?: .*)?", line)
        if match is None:
            raise ValueError("unclassified circuit statement")
        name, terminals, model = match.groups()
        nodes = terminals.split()
        if name in instances or len(instances) >= 128:
            raise ValueError("duplicate or excessive circuit instances")
        if model in ("nmos", "pmos", "gpdk090_nmos1v", "gpdk090_pmos1v"):
            if len(nodes) != 4:
                raise ValueError("MOS terminal contract")
            kind = "mos"
        elif model == "vsource":
            if len(nodes) != 2:
                raise ValueError("source terminal contract")
            kind = "vsource"
        else:
            raise ValueError("unreviewed circuit component")
        instances[name] = (nodes, kind)
    if not instances:
        raise ValueError("empty circuit")
    mos = [nodes for nodes, kind in instances.values() if kind == "mos"]
    sources = [nodes for nodes, kind in instances.values() if kind == "vsource"]
    inputs_clamped = all(sources.count([node, "0"]) == 1 for node in ("Vp", "Vm"))
    output_connections = [nodes for nodes, _ in instances.values() if {"Vop", "Vom"} & set(nodes)]
    # In this explicit boundary outputs occur only at MOS drains, not gate/source/
    # bulk sensing or a feedback network. This is NOT a claim about intrinsic
    # transistor capacitance, diode-connected local bias or all hidden model loops.
    output_drains_only = all(
        any(nodes[0] == node for nodes in mos) for node in ("Vop", "Vom")
    ) and all(
        len(nodes) == 4 and nodes[0] in ("Vop", "Vom") and not ({"Vop", "Vom"} & set(nodes[1:]))
        for nodes in output_connections
    )
    return {
        "mos_count": len(mos),
        "voltage_source_count": len(sources),
        "diode_connected_mos_count": sum(nodes[0] == nodes[1] for nodes in mos),
        "independent_input_voltage_sources": inputs_clamped,
        "output_terminals_only_mos_drains": output_drains_only,
        "explicit_application_feedback": "ABSENT_IN_INSPECTED_BOUNDARY"
        if inputs_clamped and output_drains_only
        else "REVIEW_REQUIRED",
        "explicit_common_mode_control": "ABSENT_IN_INSPECTED_BOUNDARY"
        if inputs_clamped and output_drains_only
        else "REVIEW_REQUIRED",
        "model_internal_loops": "NOT_ASSESSED",
    }


def help_status(topic: str, row: dict[str, Any]) -> str:
    if topic not in TOPICS or set(row) != {"returncode", "stdout", "stderr"}:
        raise ValueError("closed installed-help record")
    if type(row["returncode"]) is not int or any(
        not isinstance(row[k], str) for k in ("stdout", "stderr")
    ):
        raise ValueError("help scalar types")
    text = row["stdout"] + row["stderr"]
    if len(text) > 16384:
        raise ValueError("help size")
    # This installed Spectre returns zero even for an unknown help topic.
    if "no such component, analysis, or other" in text.lower():
        return "NOT_DOCUMENTED_BY_INSTALLED_HELP"
    titles = {
        "stb": "Stability Analysis",
        "iprobe": "Current Probe",
        "diffstbprobe": "Differential",
    }
    if (
        row["returncode"] != 0
        or "warning from spectre" in text.lower()
        or "error" in row["stderr"].lower()
    ):
        return "UNVERIFIED"
    return "HELP_DOCUMENTED_ONLY" if titles[topic] in text else "UNVERIFIED"


def assessment(raw: dict[str, Any]) -> dict[str, Any]:
    if set(raw) != {
        "schema_version",
        "source_input_sha256",
        "circuit",
        "help",
        "protected_unchanged",
        "counter",
    }:
        raise ValueError("closed audit record")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("audit version")
    if raw["source_input_sha256"] != SOURCE_INPUT or raw["protected_unchanged"] is not True:
        raise ValueError("protected source identity")
    if (
        not isinstance(raw["circuit"], str)
        or digest(raw["circuit"].encode("latin-1")) != SOURCE_CIRCUIT
    ):
        raise ValueError("reviewed circuit identity")
    if set(raw["help"]) != set(TOPICS):
        raise ValueError("complete installed help required")
    t = topology(raw["circuit"])
    if t["explicit_application_feedback"] != "ABSENT_IN_INSPECTED_BOUNDARY":
        raise ValueError("reference feedback assessment changed")
    counter = raw["counter"]
    if counter != {
        "campaign_id": "AUTO-PHASE-01",
        "count": 64,
        "result_reserved_bytes": 7383023616,
    }:
        raise ValueError("phase baseline accounting changed")
    return {
        "schema_version": 1,
        "assessment_id": "reference-phase-margin-applicability-v1",
        "source_input_sha256": SOURCE_INPUT,
        "source_circuit_sha256": SOURCE_CIRCUIT,
        "source_operation_id": bandwidth.SOURCE_ID,
        "topology": t,
        "installed_help": {
            topic: {
                "status": help_status(topic, raw["help"][topic]),
                "sha256": digest(campaign._canonical(raw["help"][topic])),
            }
            for topic in TOPICS
        },
        "conditions": {
            "corner": "NN",
            "temperature_c": 27,
            "vdd_v": 1.0,
            "effective_bias_v": [0.320, 0.702],
        },
        "qualification": "UNQUALIFIED",
        "reason": "no_defined_application_feedback_loop_in_reference_testbench",
        "phase_margin_deg": None,
        "licensed_STB_execution": "NOT_RUN",
        "device_based_stability": "NOT_QUALIFIED_FOR_APPLICATION_PHASE_MARGIN",
        "definition_binding": "original_analog_phase_margin_v1_unchanged",
        "new_simulation_attempts": 0,
        "new_reserved_bytes": 0,
        "raw_circuit_or_help_included": False,
        "protection": "UNCHANGED",
        "counter": counter,
    }


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "ANALOG-PM-01",
        "parent_policy_sha256": parent,
        "operation": "inspect_reference_loop_only",
        "source_input_sha256": SOURCE_INPUT,
        "source_circuit_sha256": SOURCE_CIRCUIT,
        "max_new_attempts": 0,
        "max_new_reserved_bytes": 0,
        "max_help_bytes_per_topic": 16384,
        "topics": list(TOPICS),
        "delete_authority": False,
        "publication_authority": False,
        "script_sha256": digest(Path(__file__).read_bytes()),
    }


def authority() -> str:
    parent = campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or Path(__file__).is_symlink():
        raise ValueError("fixed phase audit policy changed")
    value = digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "phase": "ANALOG-PM-01",
        "policy_sha256": value,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "proceed",
    }:
        raise ValueError("phase audit delegation absent")
    return value


def inspect() -> dict[str, Any]:
    policy_hash = authority()
    intent = ROOT / ".codex/pm01-fixed-audit-intent-v1.private.json"
    io.save_new(
        intent,
        {
            "state": "reserved",
            "policy_sha256": policy_hash,
            "remote_code_sha256": digest(REMOTE_CODE.encode()),
            "no_simulation": True,
        },
    )
    before = bandwidth.postflight()
    raw = io.decode_result(
        io.command((*io.SSH, "/usr/bin/python -c " + shlex.quote(REMOTE_CODE)), 75)
    )
    io.save_new(ROOT / ".codex/pm01-fixed-audit-raw-v1.private.json", raw)
    result = assessment(raw)
    after = bandwidth.postflight()
    if before != after:
        # Free-space observations may change independently; compare protected
        # identities, ledger and complete prior jobs rather than elapsed disk use.
        for key in ("protected_unchanged", "counter", "jobs", "native_jobs", "phase_attempts"):
            if before[key] != after[key]:
                raise ValueError("protected phase identity changed")
    io.save_new(
        ROOT / ".codex/pm01-fixed-audit-result-v1.private.json",
        {
            "state": "PASS",
            "policy_sha256": policy_hash,
            "assessment": result,
            "before": before,
            "after": after,
        },
    )
    return result


if __name__ == "__main__":
    if sys.argv[1:] != ["inspect"]:
        raise SystemExit("usage: phase_margin_qualification.py inspect")
    print(json.dumps(inspect(), sort_keys=True))
