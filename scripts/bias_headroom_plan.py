"""Bounded plan from preserved OP evidence; never applies or simulates a bias."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import ade_qual as dc
import phase_campaign as campaign
import spectre_limit as budget

ROOT = Path(__file__).resolve().parents[1]
PAIRS_MV = ((300, 702), (320, 650), (300, 650), (310, 676))


def capacity(counter: dict[str, Any], limit: dict[str, Any], overhead: int) -> dict[str, int]:
    if (
        set(counter) != {"campaign_id", "count", "result_reserved_bytes"}
        or counter["campaign_id"] != "AUTO-PHASE-01"
        or any(type(counter[k]) is not int for k in ("count", "result_reserved_bytes"))
        or not 32 <= counter["count"] <= limit["max_spectre_attempts"]
        or not 3088056320 <= counter["result_reserved_bytes"] <= limit["max_new_results_bytes"]
        or type(overhead) is not int
        or overhead < 0
    ):
        raise ValueError("invalid preserved cumulative usage")
    attempts = limit["max_spectre_attempts"] - counter["count"]
    bytes_left = limit["max_new_results_bytes"] - counter["result_reserved_bytes"] - overhead
    jobs = max(0, bytes_left // limit["reservation_bytes_per_job"])
    return {"attempts_remaining": attempts, "reservations_remaining": min(attempts, jobs)}


def headroom_summary(corners: dict[str, Any]) -> dict[str, Any]:
    if set(corners) != {"NN", "FF", "SS", "FS", "SF"}:
        raise ValueError("five-corner preserved evidence required")
    result = {}
    for corner, data in corners.items():
        points = data["mos_metrics"]
        if set(points) != {f"mos{i:02d}" for i in range(1, 15)}:
            raise ValueError("fourteen preserved MOS metrics required")
        margins = [p["headroom_v"] for p in points.values()]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in margins):
            raise ValueError("missing or nonfinite headroom")
        result[corner] = {
            "minimum_headroom_mv": min(margins) * 1000,
            "negative_headroom_devices": sum(v < 0 for v in margins),
        }
    return result


def run() -> dict[str, Any]:
    _, policy_sha = budget.authority()
    deployed = campaign._read_json(budget.JOURNAL)
    e2e = campaign._read_json(ROOT / ".codex/native-mcp-v2-e2e-journal.json")
    if any(
        p.get("state") != "succeeded" or p.get("policy_sha256") != policy_sha
        for p in (deployed, e2e)
    ):
        raise ValueError("effective budget deployment/E2E required")
    reference = campaign._read_json(ROOT / ".codex/ade-pvt-diag-pr99-merge-checkpoint.json")
    evidence = ROOT / ".codex/ade-pvt-diag-v2-analysis.private.json"
    if (
        reference.get("state") != "complete"
        or reference.get("pr") != 99
        or evidence.is_symlink()
        or dc.digest(evidence.read_bytes()) != reference["analysis_sha256"]
    ):
        raise ValueError("preserved OP diagnosis binding drift")
    measured = campaign._read_json(evidence)
    limit = campaign._read_json(budget.LIMIT)
    current = deployed["after"]["native"]["counter"]
    available = capacity(current, limit, 2 * 1024**2)
    max_jobs = len(PAIRS_MV) * 2 + 3 + 5
    if max_jobs > available["reservations_remaining"]:
        raise ValueError("bounded follow-up does not fit remaining budgets")
    return {
        "schema_version": 1,
        "phase": "BIAS-HEADROOM-PREP-01",
        "execution_state": "proposed_not_activated",
        "basis": "ADE-PVT-DIAG-01_PR99_preserved_operating_points",
        "analysis_sha256": reference["analysis_sha256"],
        "budget_policy_sha256": budget.LIMIT_SHA,
        "baseline_counter": current,
        "available": available,
        "original_candidate_mv": [320, 702],
        "vdd_constraint_v": 1.0,
        "temperature_c": 27,
        "vcm_v": 0.5,
        "new_runs_this_preparation": 0,
        "proposed_bounds_mv": {"VBIASN": [300, 320], "VBIASP": [650, 702]},
        "range_basis": "observed_saved_and_qualified_candidate_endpoints_not_PDK_rating",
        "proposed_pairs_mv": [list(p) for p in PAIRS_MV],
        "stage_a": {
            "analysis": "dc_plus_fixed_op_reader",
            "corners": ["FF", "FS"],
            "maximum_attempts": 8,
        },
        "selection": "minimize_worst_negative_device_count_then_maximize_worst_headroom",
        "selection_eligibility": "measured_FF_FS_headroom_improvement_required_no_spec_PASS",
        "selected_pair_mv": None,
        "stage_b": {
            "analysis": "dc_plus_fixed_op_reader",
            "corners": ["NN", "SS", "SF"],
            "reuse_selected_FF_FS": True,
            "maximum_attempts": 3,
        },
        "stage_c": {
            "analysis": "ac",
            "corners": ["NN", "FF", "SS", "FS", "SF"],
            "maximum_attempts": 5,
            "settings": "existing_10Hz_to_100MHz_dec10",
        },
        "maximum_new_spectre_attempts": max_jobs,
        "maximum_cumulative_count_after": current["count"] + max_jobs,
        "maximum_reserved_bytes_after": current["result_reserved_bytes"]
        + max_jobs * limit["reservation_bytes_per_job"],
        "non_job_overhead_allowance_bytes": 2 * 1024**2,
        "spec_evaluation": "not_evaluated",
        "preserved_baseline_headroom": headroom_summary(measured["corners"]),
        "execution_prerequisites": [
            "versioned_finite_pair_owned_state_adapter_and_tests",
            "generated_native_supply_bias_model_stimulus_load_validation",
            "immutable_prior_job_tree_and_PDK_byte_guards",
            "shared_500_attempt_guard_and_5GiB_reservation_no_reset",
            "durable_unique_pair_corner_analysis_replay_and_uncertain_reservation_checks",
            "one_EDA_job_guest_disk_floor_and_fixed_phase_cap",
            "no_automatic_range_extension_or_optimization_on_failure",
        ],
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 1:
            raise ValueError("fixed local preparation takes no arguments")
        print(json.dumps(run(), sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
