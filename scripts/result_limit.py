"""Fixed immutable native/sweep deployment for the explicit 10 GiB delegation."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_qual as io
import deploy_native_mcp_v1 as native
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_RESULT_LIMIT_V4.json"
POLICY_SHA = "851567cae8e50a6dbfe95ed8d1276f4b11a944d7038b72f72358d721b947b0e2"
PRIVATE = ROOT / ".codex"
DELEGATION = PRIVATE / "result-limit-v4-delegation.private.json"
JOURNAL = PRIVATE / "result-limit-v4-deploy.private.json"
VERSIONS = {"native-mcp-v3": native.FILES, "sweep-mcp-v2": ("run.sh", "budget.py")}
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/"


def activation() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": "RESULT-LIMIT-10GIB-01",
        "policy_sha256": POLICY_SHA,
        "user_delegation": "explicit-in-current-task",
    }


def authority() -> dict[str, Any]:
    campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if io.digest(campaign._canonical(policy)) != POLICY_SHA:
        raise ValueError("result ceiling policy drift")
    expected = {
        version: {
            name: io.digest((ROOT / "remote/phase-campaign" / version / name).read_bytes())
            for name in names
        }
        for version, names in VERSIONS.items()
    }
    record = campaign._read_json(DELEGATION)
    if record != {**activation(), "files": expected, "maximum_new_simulations": 0}:
        raise ValueError("exact user result ceiling deployment delegation missing")
    if any(
        (ROOT / "remote/phase-campaign" / version / name).is_symlink()
        for version, names in VERSIONS.items()
        for name in names
    ):
        raise ValueError("unsafe deployment source")
    return record


def postflight(version: str) -> dict[str, Any]:
    return io.decode_result(
        native.ssh(REMOTE + version + "/run.sh postflight " + native.PREFLIGHT_ID + " dc")
    )


def deploy() -> dict[str, Any]:
    record = authority()
    before = postflight("native-mcp-v2")
    if before["counter"] != campaign._read_json(POLICY)["baseline_counter"]:
        raise ValueError("cumulative baseline changed")
    io.save_new(
        JOURNAL,
        {
            "state": "reserved",
            "before": before,
            "at": datetime.now(UTC).isoformat(),
            "policy_sha256": POLICY_SHA,
        },
    )
    activated = PRIVATE / "result-limit-v4-activation.private.json"
    io.save_new(activated, activation())
    for version, names in VERSIONS.items():
        destination = REMOTE + version
        stage = destination + ".stage"
        native.ssh(
            "test ! -e "
            + destination
            + " && test ! -L "
            + destination
            + " && test ! -e "
            + stage
            + " && test ! -L "
            + stage
        )
        native.ssh("umask 077; mkdir -m 700 " + stage)
        files = {name: ROOT / "remote/phase-campaign" / version / name for name in names}
        files.update({"budget-policy.json": POLICY, "activation.private.json": activated})
        manifest = PRIVATE / (version + "-result-limit.manifest.private.sha256")
        with manifest.open("xb") as stream:
            stream.write(
                "".join(
                    io.digest(p.read_bytes()) + "  " + n + "\n" for n, p in files.items()
                ).encode("ascii")
            )
        files["manifest.sha256"] = manifest
        for name, source in files.items():
            io.command((*io.SCP, str(source), "cadence-vm:" + stage + "/" + name))
        python_file = "helper.py" if version == "native-mcp-v3" else "budget.py"
        native.ssh(
            "cd "
            + stage
            + " && sha256sum -c manifest.sha256 >/dev/null"
            + " && bash -n run.sh && /usr/bin/python -c 'compile(open(\""
            + python_file
            + '","rb").read(),"helper","exec")\''
            + " && chmod 700 run.sh "
            + python_file
            + " && chmod 600 *.json manifest.sha256"
            + (" && chmod 600 *.ocn" if version == "native-mcp-v3" else "")
            + " && mv "
            + stage
            + " "
            + destination
        )
        # Journal each committed version; never restart by deleting a partial deployment.
        campaign._replace_record(
            JOURNAL,
            {
                "state": "deploying",
                "before": before,
                "completed_version": version,
                "policy_sha256": POLICY_SHA,
            },
        )
    after = postflight("native-mcp-v3")
    if (
        before["counter"] != after["counter"]
        or not after["protected_unchanged"]
        or not after["reference_results_unchanged"]
        or after["active_eda"] != 0
    ):
        raise ValueError("protected state or cumulative accounting changed")
    result = {
        "state": "succeeded",
        "before": before,
        "after": after,
        "policy_sha256": POLICY_SHA,
        "files": record["files"],
        "new_spectre_attempts": 0,
    }
    campaign._replace_record(JOURNAL, result)
    return result


def verify() -> dict[str, Any]:
    """Read-only Python 2.6 guard boundaries; never call reserve or simulator."""
    authority()
    code = (
        'import imp,json; r="/home/buet/cds_work/.cadence_mcp/phase-campaign/"; '
        'n=imp.load_source("native_limit",r+"native-mcp-v3/helper.py"); '
        's=imp.load_source("sweep_limit",r+"sweep-mcp-v2/budget.py"); '
        "checks=[]\n"
        "for m in (n,s):\n"
        " p=m.authorization()\n"
        " for count,reserved,expected in ((62,7114588160,True),"
        "(499,10603200512,True),(500,7114588160,False),(62,10603200513,False)):\n"
        '  c={"campaign_id":"AUTO-PHASE-01","count":count,"result_reserved_bytes":reserved}\n'
        "  try:\n"
        "   m.validate_counter(c,p); allowed=True\n"
        "  except ValueError:\n"
        "   allowed=False\n"
        '  if allowed!=expected: raise ValueError("boundary mismatch")\n'
        "  checks.append(allowed)\n"
        'print(json.dumps({"boundary_checks":len(checks),"new_reservations":0}))'
    )
    result = json.loads(native.ssh("/usr/bin/python -B -c '" + code + "'"))
    after = postflight("native-mcp-v3")
    if after["counter"] != campaign._read_json(POLICY)["baseline_counter"]:
        raise ValueError("verification changed cumulative counter")
    io.save_new(
        PRIVATE / "result-limit-v4-guest-boundaries.private.json",
        {"boundaries": result, "after": after},
    )
    return result


if __name__ == "__main__":
    try:
        if sys.argv[1:] not in (["deploy"], ["verify"]):
            raise ValueError("fixed deployment action required")
        if sys.argv[1:] == ["verify"]:
            print(json.dumps(verify()))
            sys.exit(0)
        value = deploy()
        print(
            json.dumps(
                {
                    "state": value["state"],
                    "counter": value["after"]["counter"],
                    "limit_bytes": 10 * 1024**3,
                    "new_spectre_attempts": 0,
                }
            )
        )
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
