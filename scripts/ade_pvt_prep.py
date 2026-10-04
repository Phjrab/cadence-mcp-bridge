"""Fixed, journaled operator inventory; no circuit execution or public path input."""

from __future__ import annotations

import json
import re
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_qual as dc
import deploy_native_mcp_v1 as native
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/ade-pvt-prep-v4"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-pvt-prep-v4"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/ade-pvt-prep-v4"
POLICY = ROOT / "docs/policy/ADE_PVT_PREP_V4.json"
DELEGATION = ROOT / ".codex/ade-pvt-prep-v4-delegation.json"
FILES = ("run.sh", "inventory.py")
PRIOR_POLICY_SHA = "fed557f759df1beef2a3217d8af57c697374b700b99ea9ee83924cc799bee2cf"
PRIOR_RESULT_SHA = "e7fd701fc8eee38df94650fe0a5c25be98883b58fdc828ab973ce3ff9ae691bc"
V2_POLICY_SHA = "7775ba5d8881ba1dfcd8ea553e10087936552231962b142eb1654b72d1ca5bdd"
V3_POLICY_SHA = "ab635ed8ae59488c13fbcedea2a09cb0f1908ff3cf3db4f0e8508012993c4ea6"
PRIOR_REMOTE_SHA = "64d0f5f74ff1627897b07d1630c9c832e476e6b8019a3d8b059d92f930930472"
COUNTER = {"campaign_id": "AUTO-PHASE-01", "count": 24, "result_reserved_bytes": 2014314496}


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-PREP-01",
        "parent_policy_sha256": parent,
        "new_circuit_runs": 0,
        "remote_version": "phase-campaign/ade-pvt-prep-v4",
        "prior_policy_sha256": V3_POLICY_SHA,
        "prior_result_sha256": PRIOR_RESULT_SHA,
        "prior_remote_result_sha256": PRIOR_REMOTE_SHA,
        "corrections_used": 3,
        "source_mode": "protected_fixed_pdk_read_only",
        "vdd_constraint_v": 1.0,
        "candidate_preserved_v": [0.32, 0.702],
        "elapsed_ceiling": None,
        "baseline_counter": COUNTER,
        "preserve_other_cumulative_budgets": True,
        "eda_concurrency": 1,
        "paid_resources": 0,
        "maximum_corrections_same_change": 3,
        "maximum_model_bytes": 32 * 1024**2,
        "maximum_model_files": 256,
        "max_read_communication_attempts": 3,
        "spec_evaluation": "not_evaluated",
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> str:
    parent = campaign._load_authority()
    native.authority()
    third = campaign._read_json(ROOT / "docs/policy/ADE_PVT_PREP_V3.json")
    if dc.digest(campaign._canonical(third)) != V3_POLICY_SHA:
        raise ValueError("preserved third inventory policy changed")
    for name, expected in third["files"].items():
        path = ROOT / "remote/phase-campaign/ade-pvt-prep-v3" / name
        if path.is_symlink() or dc.digest(path.read_bytes()) != expected:
            raise ValueError("preserved third inventory source changed")
    second = campaign._read_json(ROOT / "docs/policy/ADE_PVT_PREP_V2.json")
    if dc.digest(campaign._canonical(second)) != V2_POLICY_SHA:
        raise ValueError("preserved model binding policy changed")
    for name, expected in second["files"].items():
        path = ROOT / "remote/phase-campaign/ade-pvt-prep-v2" / name
        if path.is_symlink() or dc.digest(path.read_bytes()) != expected:
            raise ValueError("preserved model binding source changed")
    prior = campaign._read_json(ROOT / "docs/policy/ADE_PVT_PREP_V1.json")
    if dc.digest(campaign._canonical(prior)) != PRIOR_POLICY_SHA:
        raise ValueError("preserved first inventory policy changed")
    for name, expected in prior["files"].items():
        path = ROOT / "remote/phase-campaign/ade-pvt-prep-v1" / name
        if path.is_symlink() or dc.digest(path.read_bytes()) != expected:
            raise ValueError("preserved first inventory source changed")
    result_path = ROOT / ".codex/ade-pvt-prep-v1-result.json"
    if (
        result_path.is_symlink()
        or dc.digest(campaign._canonical(json.loads(result_path.read_bytes()))) != PRIOR_RESULT_SHA
    ):
        raise ValueError("preserved installed capability result changed")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / name).is_symlink() for name in FILES):
        raise ValueError("fixed PVT preparation policy or bytes changed")
    digest = dc.digest(campaign._canonical(policy))
    raw_prior = ROOT / ".codex/ade-pvt-prep-v1-remote-result.bytes.json"
    if raw_prior.is_symlink() or dc.digest(raw_prior.read_bytes()) != PRIOR_REMOTE_SHA:
        raise ValueError("preserved raw prior inventory changed")
    for ordinal, bound in ((1, V2_POLICY_SHA), (2, V3_POLICY_SHA), (3, digest)):
        correction = campaign._read_json(ROOT / f".codex/ade-pvt-prep-correction-{ordinal}.json")
        if (
            correction.get("ordinal") != ordinal
            or correction.get("maximum") != 3
            or correction.get("state") != "consumed"
            or correction.get("policy_sha256") != bound
        ):
            raise ValueError("PVT correction history changed or absent")
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-PREP-01",
        "policy_sha256": digest,
        "parent_policy_sha256": parent,
        "user_delegation": "explicit-in-current-task",
        "user_selection": "investigate_actual_pdk_pvt_statistics_support",
    }:
        raise ValueError("explicit PVT preparation delegation absent")
    return digest


def record(action: str) -> Path:
    return ROOT / (".codex/ade-pvt-prep-v4-" + action + ".json")


def checkpoint() -> dict[str, Any]:
    result = native.postflight()
    if result["counter"] != COUNTER or result["active_eda"] != 0:
        raise ValueError("preparation cumulative checkpoint changed")
    return result


def deploy() -> dict[str, Any]:
    digest = authority()
    before = checkpoint()
    dc.save_new(
        record("deploy"),
        {
            "state": "reserved",
            "policy_sha256": digest,
            "before": before,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    stage = REMOTE + ".stage"
    native.ssh(
        "test ! -e "
        + REMOTE
        + " && test ! -L "
        + REMOTE
        + " && test ! -e "
        + stage
        + " && test ! -L "
        + stage
        + " && test ! -e "
        + RUNTIME
        + " && test ! -L "
        + RUNTIME
    )
    native.ssh("umask 077; mkdir -m 700 " + stage)
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/ade-pvt-prep-v4-manifest.sha256"
    policy = campaign._read_json(POLICY)
    with manifest.open("xb") as stream:
        stream.write(
            "".join(policy["files"][name] + "  " + name + "\n" for name in FILES).encode("ascii")
        )
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    native.ssh(
        "cd " + stage + " && sha256sum -c manifest.sha256 >/dev/null"
        " && bash -n run.sh"
        ' && /usr/bin/python -c \'compile(open("inventory.py","rb").read(),'
        '"inventory.py","exec")\''
        " && chmod 700 run.sh inventory.py && chmod 600 manifest.sha256"
        " && mv " + stage + " " + REMOTE
    )
    after = checkpoint()
    result = {
        "state": "succeeded",
        "policy_sha256": digest,
        "manifest_sha256": dc.digest(manifest.read_bytes()),
        "after": after,
    }
    campaign._replace_record(record("deploy"), result)
    return result


def validate(result: dict[str, Any]) -> None:
    expected_keys = {
        "phase",
        "model_sha256",
        "model_inventory_sha256",
        "model_file_count",
        "model_bytes_scanned",
        "sections",
        "saved_state",
        "spectre_montecarlo_help",
        "ocean_api",
        "protected_unchanged",
        "counter",
        "new_circuit_runs",
        "spec_evaluation",
        "prior_result_sha256",
        "prior_remote_result_sha256",
    }
    if set(result) != expected_keys or type(result.get("new_circuit_runs")) is not int:
        raise ValueError("inventory projection contains unknown or invalid fields")
    if (
        result.get("phase") != "ADE-PVT-PREP-01"
        or result.get("new_circuit_runs") != 0
        or result.get("counter") != COUNTER
        or result.get("protected_unchanged") is not True
        or result.get("spec_evaluation") != "not_evaluated"
        or result.get("model_sha256")
        != "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
        or "NN" not in result.get("sections", {})
        or result.get("prior_result_sha256") != PRIOR_RESULT_SHA
        or result.get("prior_remote_result_sha256") != PRIOR_REMOTE_SHA
    ):
        raise ValueError("PVT inventory provenance changed")
    if (
        result["model_file_count"] != 9
        or result["model_bytes_scanned"] != 427717
        or result["saved_state"]
        != {
            "variables_v": {"VBIASN": 0.3, "VBIASP": 0.65},
            "enabled_analyses": ["dc"],
            "model_section": "NN",
            "temperature_c": 27,
        }
    ):
        raise ValueError("inventoried model or saved state checkpoint changed")
    section_names = {
        "NN",
        "FF",
        "SS",
        "FS",
        "SF",
        "NN_highPerf",
        "FF_highPerf",
        "SS_highPerf",
        "FS_highPerf",
        "SF_highPerf",
    }
    if set(result["sections"]) != section_names:
        raise ValueError("observed section inventory changed")
    count_keys = {
        "statistics_blocks",
        "process_blocks",
        "mismatch_blocks",
        "vary_declarations",
        "vary_names_referenced",
        "visited_file_sections",
    }
    for section in result["sections"].values():
        if (
            set(section)
            != count_keys
            | {
                "observed_device_definitions",
                "used_mos_model_bindings",
                "effective_variation_verified",
            }
            or section["effective_variation_verified"] is not False
            or section["observed_device_definitions"] != []
            or any(
                type(section[key]) is not int or not 0 <= section[key] <= 1000 for key in count_keys
            )
        ):
            raise ValueError("invalid bounded section metadata")
        bindings = section["used_mos_model_bindings"]
        if len(bindings) != 2 or sorted(value["circuit_instances"] for value in bindings) != [6, 8]:
            raise ValueError("invalid MOS model binding counts")
        for binding in bindings:
            if (
                set(binding)
                != {
                    "model_id_sha256",
                    "circuit_instances",
                    "definition_matches",
                    "vary_references_in_definition",
                    "effective_variation_verified",
                }
                or re.fullmatch(r"[0-9a-f]{64}", binding["model_id_sha256"]) is None
                or binding["definition_matches"] != 1
                or binding["effective_variation_verified"] is not False
                or type(binding["vary_references_in_definition"]) is not int
                or not 0 <= binding["vary_references_in_definition"] <= 1000
            ):
                raise ValueError("invalid bounded MOS metadata")
    # Probes are copied from the exact preserved v1 result, not caller-provided strings.
    prior = json.loads((ROOT / ".codex/ade-pvt-prep-v1-result.json").read_bytes())
    for key in ("ocean_api", "spectre_montecarlo_help"):
        if result[key] != prior[key]:
            raise ValueError("preserved installed support probe changed")


def read() -> dict[str, Any]:
    digest = authority()
    deployment = campaign._read_json(record("deploy"))
    if deployment.get("state") != "succeeded" or deployment.get("policy_sha256") != digest:
        raise ValueError("verified deployment required")
    checkpoint()
    dc.save_new(
        record("read"),
        {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
    )
    result = dc.decode_result(native.ssh(REMOTE + "/run.sh", 90))
    validate(result)
    after = checkpoint()
    dc.save_new(ROOT / ".codex/ade-pvt-prep-v4-result.json", result)
    campaign._replace_record(
        record("read"),
        {
            "state": "succeeded",
            "policy_sha256": digest,
            "result_sha256": dc.digest(campaign._canonical(result)),
            "after": after,
        },
    )
    return result


def status() -> dict[str, Any]:
    digest = authority()
    prior = campaign._read_json(record("read"))
    if prior.get("policy_sha256") != digest or prior.get("state") not in ("reserved", "succeeded"):
        raise ValueError("reserved inventory identity required")
    # Communication recovery only. It never launches the inventory again.
    for attempt in range(1, 4):
        path = record("status-" + str(attempt))
        if not path.exists():
            dc.save_new(path, {"state": "reserved", "policy_sha256": digest})
            break
    else:
        raise ValueError("inventory read communication allowance exhausted")
    result = dc.decode_result(native.ssh("cat " + RUNTIME + "/result.json"))
    validate(result)
    campaign._replace_record(path, {"state": "succeeded", "policy_sha256": digest})
    return result


def final_postflight() -> dict[str, Any]:
    """Bound preparation artifact bytes without starting EDA or changing ledgers."""
    digest = authority()
    before = checkpoint()
    code = """import os,json,stat,hashlib
root='/home/buet/cds_work/.cadence_mcp'
out={}
for version in (1,2,3,4):
    prefix='ade-pvt-prep-v'+str(version)
    for label,path in [(prefix,root+'/'+prefix),
                       ('deployment-'+prefix,root+'/phase-campaign/'+prefix)]:
        if os.path.realpath(path)!=path:raise ValueError('preparation containment')
        records=[]
        total=0
        for current,dirs,files in os.walk(path):
            for name in dirs:
                if os.path.islink(os.path.join(current,name)):raise ValueError('directory link')
            for name in files:
                target=os.path.join(current,name)
                if not stat.S_ISREG(os.lstat(target).st_mode):raise ValueError('file type')
                size=os.stat(target).st_size
                total+=size
                if total>2*1024*1024 or len(records)>=128:raise ValueError('preparation output cap')
                with open(target,'rb') as stream:data=stream.read(2*1024*1024+1)
                records.append((os.path.relpath(target,path),hashlib.sha256(data).hexdigest(),size))
        out[label]={'total_bytes':total,'files':len(records),
                    'sha256':hashlib.sha256(json.dumps(sorted(records)).encode('ascii')).hexdigest()}
print(json.dumps(out,sort_keys=True))"""
    artifacts = dc.decode_result(native.ssh("/usr/bin/python -c " + shlex.quote(code)))
    total = sum(value["total_bytes"] for value in artifacts.values())
    if total > 2 * 1024**2 or before["counter"]["result_reserved_bytes"] + total > 5 * 1024**3:
        raise ValueError("preparation result volume limit")
    after = checkpoint()
    if before["counter"] != after["counter"]:
        raise ValueError("preparation postflight counter drift")
    result = {
        "state": "verified",
        "policy_sha256": digest,
        "postflight": after,
        "preparation_bytes_including_deployment": total,
        "artifacts": artifacts,
        "corrections_used": 3,
        "at": datetime.now(UTC).isoformat(),
    }
    dc.save_new(record("postflight"), result)
    return result


def diagnose() -> dict[str, Any]:
    """Read-only lexical diagnosis of the interrupted v3; never reruns main()."""
    digest = authority()
    checkpoint()
    dc.save_new(record("diagnose"), {"state": "reserved", "policy_sha256": digest})
    code = """import imp,json,re
m=imp.load_source('fixed_pvt_diagnostic','/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-pvt-prep-v3/inventory.py')
n=imp.load_source('fixed_pvt_native','/home/buet/cds_work/.cadence_mcp/phase-campaign/native-mcp-v1/helper.py')
b=n.BASE
before=b.snapshot()
text=b.read(b.guard().NETLIST,10*1024*1024).decode('latin-1')
normal=re.sub(r'\\\\\\r?\\n\\s*',' ',text)
normal=re.sub(r'\\n\\s*\\+\\s*',' ',normal)
out={'physical_nm_pm_prefixes':len(re.findall(r'(?m)^\\s*(?:NM|PM)[0-9]+\\b',text)),
     'continued_nm_pm_prefixes':len(re.findall(r'(?m)^\\s*(?:NM|PM)[0-9]+\\b',normal))}
for label,value in [('physical',text),('joined',normal)]:
    try:
        counts=m.circuit_models(value)
        out[label]={'counts':sorted(counts.values()),
                    'model_ids':sorted(m.sha(x.encode('ascii')) for x in counts)}
    except ValueError as exc:
        out[label]={'fixed_error':str(exc)}
try:
    records=m.files()
    out['model_file_count']=len(records)
except ValueError as exc:
    out['model_file_error']=str(exc)
out['protected_unchanged']=before==b.snapshot()
print(json.dumps(out,sort_keys=True))"""
    result = dc.decode_result(native.ssh("/usr/bin/python -c " + shlex.quote(code)))
    dc.save_new(record("diagnose-result"), result)
    campaign._replace_record(record("diagnose"), {"state": "succeeded", "policy_sha256": digest})
    return result


def diagnose_computation() -> dict[str, Any]:
    """Complete the same fixed read-only diagnosis without creating runtime files."""
    digest = authority()
    checkpoint()
    dc.save_new(record("diagnose-computation"), {"state": "reserved", "policy_sha256": digest})
    code = """import imp,json,os
m=imp.load_source('pvt_computation_diagnostic','/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-pvt-prep-v3/inventory.py')
n=imp.load_source('pvt_computation_native','/home/buet/cds_work/.cadence_mcp/phase-campaign/native-mcp-v1/helper.py')
b=n.BASE
out={}
stage='snapshot'
try:
    before=b.snapshot()
    stage='model_files'
    records=m.files()
    manifest=sorted((os.path.relpath(path,m.MODELS),value['sha256'],value['bytes'])
                    for path,value in records.items())
    stage='manifest_digest'
    out['inventory_sha']=m.sha(json.dumps(manifest,separators=(',',':')).encode('ascii'))
    stage='circuit_models'
    used=m.circuit_models(b.read(b.guard().NETLIST,10*1024*1024).decode('latin-1'))
    stage='closures'
    sections=[value['section'] for value in records[m.MAIN]['metadata']['sections']
              if value['section'] is not None]
    out['sections']=dict((name,m.closure(records,name,used)) for name in sections)
    stage='prior_digest'
    prior=json.loads(b.read(m.ROOT+'/ade-pvt-prep-v1/result.json',32768))
    out['prior_sha']=m.sha(json.dumps(prior,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii'))
    out['prior_matches']=out['prior_sha']==m.PRIOR_RESULT_SHA
    stage='protected_postflight'
    out['protected_unchanged']=before==b.snapshot()
    out['model_files_unchanged']=records==m.files()
    out['runtime_files']=sorted(os.listdir(m.RUNTIME))
    out['stage']='complete'
except (ValueError,IOError,OSError,KeyError,TypeError) as exc:
    out['stage']=stage
    out['error_type']=type(exc).__name__
    if isinstance(exc,ValueError):out['fixed_error']=str(exc)
print(json.dumps(out,sort_keys=True))"""
    result = dc.decode_result(native.ssh("/usr/bin/python -c " + shlex.quote(code)))
    dc.save_new(record("diagnose-computation-result"), result)
    campaign._replace_record(
        record("diagnose-computation"), {"state": "succeeded", "policy_sha256": digest}
    )
    return result


def recover_prior() -> dict[str, Any]:
    """Pin the original remote bytes after comparing their parsed bounded metadata."""
    digest = authority()
    checkpoint()
    dc.save_new(record("prior-recovery"), {"state": "reserved", "policy_sha256": digest})
    raw = native.ssh("cat /home/buet/cds_work/.cadence_mcp/ade-pvt-prep-v1/result.json")
    prior = json.loads((ROOT / ".codex/ade-pvt-prep-v1-result.json").read_bytes())
    if dc.decode_result(raw) != prior:
        raise ValueError("original bounded inventory semantic disagreement")
    with (ROOT / ".codex/ade-pvt-prep-v1-remote-result.bytes.json").open("xb") as stream:
        stream.write(raw)
    result = {
        "semantic_agreement": True,
        "remote_bytes_sha256": dc.digest(raw),
        "local_canonical_sha256": PRIOR_RESULT_SHA,
        "bytes": len(raw),
    }
    campaign._replace_record(
        record("prior-recovery"), {"state": "succeeded", "policy_sha256": digest, "result": result}
    )
    return result


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in (
            "deploy",
            "read",
            "status",
            "postflight",
            "diagnose",
            "diagnose-computation",
            "recover-prior",
            "final-postflight",
        ):
            raise ValueError("usage: ade_pvt_prep.py deploy|read|status|postflight|diagnose")
        action = sys.argv[1]
        authority()
        print(
            json.dumps(
                {
                    "deploy": deploy,
                    "read": read,
                    "status": status,
                    "postflight": checkpoint,
                    "diagnose": diagnose,
                    "diagnose-computation": diagnose_computation,
                    "recover-prior": recover_prior,
                    "final-postflight": final_postflight,
                }[action](),
                sort_keys=True,
            )
        )
    except (ValueError, OSError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
