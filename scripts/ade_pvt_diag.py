"""Journaled operator diagnosis of five preserved DC MOS operating-point sets."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_pvt_qual as qual
import ade_qual as dc
import deploy_native_mcp_v1 as native
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/ade-pvt-diag-v2"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-pvt-diag-v2"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/ade-pvt-diag-v2"
POLICY = ROOT / "docs/policy/ADE_PVT_DIAG_V2.json"
DELEGATION = ROOT / ".codex/ade-pvt-diag-v2-delegation.json"
REFERENCE = ROOT / ".codex/ade-pvt-qual-pr98-merge-checkpoint.json"
FILES = ("helper.py", "run.sh", "probe.ocn", "extract.ocn")
COUNTER = {"campaign_id": "AUTO-PHASE-01", "count": 32, "result_reserved_bytes": 3088056320}
FIELDS = ["id", "gm", "gds", "gmbs", "vgs", "vds", "vbs", "vth", "vdsat", "region"]
PRIOR_POLICY_SHA = "dfeec327b7918a639ec4eeb3a41c541b21d5d96289c4f46e0ee76d3c804823bd"
FAILURE_SHA = "dea5460b455520fc0e071327ab002a83d2f0f91f75234de6035f210685725352"
FAILURE = ROOT / ".codex/ade-pvt-diag-v1-failure-checkpoint.json"


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-DIAG-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/ade-pvt-diag-v2",
        "source": "preserved_nn_ff_ss_fs_sf_native_dc_psf",
        "new_spectre_attempts": 0,
        "reference_checkpoint_sha256": dc.digest(REFERENCE.read_bytes()),
        "baseline_counter": COUNTER,
        "maximum_corrections_same_change": 3,
        "corrections_used": 1,
        "prior_policy_sha256": PRIOR_POLICY_SHA,
        "failure_checkpoint_sha256": FAILURE_SHA,
        "prior_corrections_preserved": {
            "dc": "5_of_6",
            "native_ac_tran": "3_of_3",
            "candidate": "1_of_3",
            "native_mcp": "1_of_3",
            "pvt_prep": "3_of_3",
            "pvt_qual": "0_of_3",
        },
        "candidate_values_v": [0.32, 0.702],
        "vdd_constraint_v": 1.0,
        "temperature_c": 27,
        "corners": ["NN", "FF", "SS", "FS", "SF"],
        "mos_devices_per_corner": 14,
        "fields": FIELDS,
        "max_read_attempts_per_status": 3,
        "maximum_artifact_bytes": 2 * 1024**2,
        "eda_concurrency": 1,
        "elapsed_ceiling": None,
        "paid_resources": 0,
        "spec_evaluation": "not_evaluated",
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> str:
    parent = campaign._load_authority()
    qual.authority()
    previous = campaign._read_json(ROOT / "docs/policy/ADE_PVT_DIAG_V1.json")
    if dc.digest(campaign._canonical(previous)) != PRIOR_POLICY_SHA:
        raise ValueError("preserved initial diagnostic policy drift")
    for name, digest in previous["files"].items():
        if (
            dc.digest((ROOT / "remote/phase-campaign/ade-pvt-diag-v1" / name).read_bytes())
            != digest
        ):
            raise ValueError("preserved initial diagnostic source drift")
    failure = FAILURE
    if failure.is_symlink() or dc.digest(failure.read_bytes()) != FAILURE_SHA:
        raise ValueError("preserved diagnostic failure drift")
    reference = campaign._read_json(REFERENCE)
    if (
        reference.get("state") != "complete"
        or reference.get("pr") != 98
        or reference["postflight"]["counter"] != COUNTER
    ):
        raise ValueError("qualified corner integration checkpoint absent")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / name).is_symlink() for name in FILES):
        raise ValueError("diagnostic policy or source bytes drift")
    digest = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-DIAG-01",
        "parent_policy_sha256": parent,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_selection": "read_preserved_mos_op_explain_ff_fs_gain_loss",
    }:
        raise ValueError("explicit diagnostic delegation absent")
    return digest


def checkpoint() -> dict[str, Any]:
    value = qual.postflight()
    if (
        value["counter"] != COUNTER
        or not value["protected_unchanged"]
        or not value["reference_results_unchanged"]
    ):
        raise ValueError("read-only diagnosis checkpoint drift")
    return value


def journal(action: str) -> Path:
    if action not in ("deploy", "probe", "extract"):
        raise ValueError("closed diagnostic action")
    return ROOT / (".codex/ade-pvt-diag-v2-" + action + ".json")


def deploy(digest: str) -> dict[str, Any]:
    before = checkpoint()
    dc.save_new(
        journal("deploy"),
        {
            "state": "reserved",
            "policy_sha256": digest,
            "before": before,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    dc.save_new(
        ROOT / ".codex/ade-pvt-diag-correction-1.json",
        {
            "phase": "ADE-PVT-DIAG-01",
            "ordinal": 1,
            "maximum": 3,
            "state": "consumed",
            "policy_sha256": digest,
            "prior_policy_sha256": PRIOR_POLICY_SHA,
            "failure_checkpoint_sha256": FAILURE_SHA,
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
    policy = campaign._read_json(POLICY)
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/ade-pvt-diag-v2-manifest.sha256"
    qual.save_bytes(
        manifest, "".join(policy["files"][name] + "  " + name + "\n" for name in FILES).encode()
    )
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    native.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
        + " && chmod 700 run.sh helper.py && chmod 600 *.ocn manifest.sha256 && mv "
        + stage
        + " "
        + REMOTE
    )
    after = checkpoint()
    result = {
        "state": "succeeded",
        "policy_sha256": digest,
        "manifest_sha256": dc.digest(manifest.read_bytes()),
        "after": after,
    }
    campaign._replace_record(journal("deploy"), result)
    return result


def validate_result(data: dict[str, Any], step: str) -> None:
    common = {
        "state",
        "phase",
        "new_spectre_attempts",
        "protected_unchanged",
        "counter",
        "spec_evaluation",
        "measurement_frame_sha256",
        "model_manifest_sha256",
    }
    extra = {"pv_callable", "selectors"} if step == "probe" else {"operating_points", "field_names"}
    if (
        set(data) != common | extra
        or data.get("state") != "succeeded"
        or data.get("phase") != "ADE-PVT-DIAG-01"
    ):
        raise ValueError("diagnostic projection schema")
    if (
        data.get("counter") != COUNTER
        or data.get("new_spectre_attempts") != 0
        or data.get("protected_unchanged") is not True
        or data.get("spec_evaluation") != "not_evaluated"
    ):
        raise ValueError("diagnostic provenance or budget")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", data["measurement_frame_sha256"])
        or data["model_manifest_sha256"]
        != "4a1fda45bb3738fc7253429903aee30b9c65f40439aee28f6cf22047178fd0d0"
    ):
        raise ValueError("diagnostic evidence hashes")
    if step == "probe":
        if type(data["pv_callable"]) is not bool or set(data["selectors"]) != {
            "NN",
            "FF",
            "SS",
            "FS",
            "SF",
        }:
            raise ValueError("operating-point capability projection")
        for selectors in data["selectors"].values():
            if set(selectors) != {"dcOpInfo-info", "dcOpInfo"} or any(
                type(value) is not bool for value in selectors.values()
            ):
                raise ValueError("operating-point selector projection")
    else:
        if data["field_names"] != FIELDS or set(data["operating_points"]) != {
            "NN",
            "FF",
            "SS",
            "FS",
            "SF",
        }:
            raise ValueError("operating-point field/corner projection")
        for points in data["operating_points"].values():
            if len(points) != 14:
                raise ValueError("operating-point device count")
            for index, point in enumerate(points):
                if (
                    set(point) != {"alias", "fields"}
                    or point["alias"] != f"mos{index + 1:02d}"
                    or set(point["fields"]) != set(data["field_names"])
                ):
                    raise ValueError("operating-point device identity")
                for value in point["fields"].values():
                    if value is not None and (
                        type(value) not in (int, float)
                        or not math.isfinite(value)
                        or abs(value) > 1e12
                    ):
                        raise ValueError("operating-point numeric field")


def run(action: str) -> dict[str, Any]:
    digest = authority()
    if action == "deploy":
        return deploy(digest)
    if action == "postflight":
        return checkpoint()
    if action not in ("probe", "extract", "status-probe", "status-extract"):
        raise ValueError("fixed diagnostic operation")
    status = action.startswith("status-")
    step = action[7:] if status else action
    predecessor = "deploy" if step == "probe" else "probe"
    prior = campaign._read_json(journal(predecessor))
    if prior.get("state") != "succeeded" or prior.get("policy_sha256") != digest:
        raise ValueError("diagnostic predecessor absent")
    if not status:
        dc.save_new(
            journal(step),
            {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
        )
    else:
        claim = ROOT / (".codex/ade-pvt-diag-v2-" + action + "-reads.json")
        attempts = (
            campaign._read_json(claim) if claim.exists() else {"policy_sha256": digest, "count": 0}
        )
        if (
            attempts["policy_sha256"] != digest
            or type(attempts["count"]) is not int
            or not 0 <= attempts["count"] < 3
        ):
            raise ValueError("diagnostic communication read budget")
        campaign._replace_record(claim, {"policy_sha256": digest, "count": attempts["count"] + 1})
    data = dc.decode_result(
        native.ssh(REMOTE + "/run.sh " + ("result " if status else "read ") + step, 120)
    )
    validate_result(data, step)
    if status:
        saved = ROOT / (".codex/ade-pvt-diag-v2-" + step + "-result.json")
        if saved.exists() and saved.read_bytes() != campaign._canonical(data):
            raise ValueError("preserved diagnostic local result drift")
    if not status:
        output = ROOT / (".codex/ade-pvt-diag-v2-" + step + "-result.json")
        qual.save_bytes(output, campaign._canonical(data))
        campaign._replace_record(
            journal(step),
            {
                "state": "succeeded",
                "policy_sha256": digest,
                "local_canonical_result_sha256": dc.digest(output.read_bytes()),
            },
        )
    return data


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("one fixed diagnostic action required")
        print(json.dumps(run(sys.argv[1]), sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
