"""Read-only consistency check of retained layout receipts; never contacts a VM.

A consistent supplied receipt is not authentication of its native provenance.
Actual C1 command/output references belong in the private acceptance record.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from cadence_mcp_bridge.layout_engine import compute_diff, predict_snapshot, validate_plan

from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutResult,
    LayoutSnapshot,
)

MAX_RECEIPT_BYTES = 4 * 1024 * 1024


def verify_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete, mismatched or replayed-as-executed evidence."""
    build = receipt.get("build_sha")
    if not isinstance(build, str) or re.fullmatch(r"[0-9a-f]{40}", build) is None:
        raise ValueError("exact_build_sha_required")
    environment = receipt.get("environment")
    if environment not in ("synthetic_fixture", "actual_vm"):
        raise ValueError("explicit_environment_required")
    before = LayoutSnapshot.model_validate_json(json.dumps(receipt["before"]))
    source_before = LayoutSnapshot.model_validate_json(json.dumps(receipt["source_before"]))
    source_after = LayoutSnapshot.model_validate_json(json.dumps(receipt["source_after"]))
    request = LayoutApplyRequest.model_validate_json(json.dumps(receipt["request"]))
    result = LayoutResult.model_validate_json(json.dumps(receipt["result"]))
    replay = LayoutResult.model_validate_json(json.dumps(receipt["replay"]))
    plan = request.plan
    if request.expected_plan_sha256 != plan.plan_sha256:
        raise ValueError("plan_digest_mismatch")
    if before.binding != plan.request.binding or before.semantic_sha256 != plan.baseline_sha256:
        raise ValueError("baseline_mismatch")
    validate_plan(before, request)
    expected, _ = predict_snapshot(before, plan.request)
    if source_before.owned or not source_before.read_only:
        raise ValueError("source_must_be_read_only")
    if source_before != source_after:
        raise ValueError("source_changed")
    if source_before.source_baseline_sha256 != before.source_baseline_sha256:
        raise ValueError("source_binding_mismatch")
    after = result.snapshot
    if after is None or after.binding != before.binding or not after.owned or after.read_only:
        raise ValueError("owned_readback_required")
    if after.semantic_sha256 != plan.expected_semantic_sha256:
        raise ValueError("readback_does_not_match_plan")
    if result.operation_id != plan.request.operation_id or result.binding != before.binding:
        raise ValueError("result_identity_mismatch")
    if not result.saved or not result.reopened or not result.source_unchanged:
        raise ValueError("save_reopen_source_evidence_required")
    if result.diff is None or (
        result.diff.before_sha256 != before.semantic_sha256
        or result.diff.after_sha256 != after.semantic_sha256
        or result.diff.matches_plan is not True
        or result.diff.unexpected_object_ids
        or result.diff.metadata_changes
    ):
        raise ValueError("matching_diff_required")
    if result.diff != compute_diff(before, after, expected=expected):
        raise ValueError("reported_diff_does_not_match_objects")
    if (
        not replay.replayed
        or replay.executed
        or replay.operation_id != result.operation_id
        or replay.binding != result.binding
        or replay.snapshot != result.snapshot
        or replay.status != result.status
        or replay.diff != result.diff
        or replay.saved != result.saved
        or replay.reopened != result.reopened
        or replay.source_unchanged != result.source_unchanged
        or replay.physical_verification != result.physical_verification
    ):
        raise ValueError("replay_changed_outcome")
    counts = receipt.get("write_counts")
    if (
        not isinstance(counts, dict)
        or set(counts) != {"before_apply", "after_apply", "after_replay"}
        or any(type(value) is not int or value < 0 for value in counts.values())
        or counts["after_apply"] <= counts["before_apply"]
        or counts["after_replay"] != counts["after_apply"]
    ):
        raise ValueError("replay_write_count_mismatch")
    if environment == "actual_vm":
        tree_before = receipt.get("source_tree_before_sha256")
        if (
            not isinstance(tree_before, str)
            or re.fullmatch(r"[0-9a-f]{64}", tree_before) is None
            or receipt.get("source_tree_after_sha256") != tree_before
        ):
            raise ValueError("source_tree_conservation_required")
        if (
            result.status != "EDIT_VERIFIED"
            or not result.executed
            or before.provenance != "native_readback"
            or source_before.provenance != "native_readback"
            or after.provenance != "native_readback"
            or after.technology.provenance != "native_observed"
        ):
            raise ValueError("native_evidence_required")
        added_pins = {edit.object_id for edit in plan.request.edits if edit.kind == "add_pin"}
        if any(
            pin.association != "native_verified"
            for pin in after.pins
            if pin.object_id in added_pins
        ):
            raise ValueError("native_pin_association_required")
    elif result.status != "NOT_VERIFIED" or any(
        snapshot.provenance != "synthetic_fixture"
        for snapshot in (before, source_before, source_after, after)
    ):
        raise ValueError("synthetic_cannot_claim_native_verification")
    return {
        "status": "RECEIPT_CONSISTENT",
        "build_sha": build,
        "environment": environment,
        "evidence_scope": "supplied_receipt_consistency_only",
        "source_unchanged": True,
        "readback_matches_plan": True,
        "replay_additional_writes": 0,
        "physical_verification": result.physical_verification.model_dump(mode="json"),
        "app_status": "APP_NOT_TESTED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        with arguments.receipt.open("rb") as stream:
            data = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(data) > MAX_RECEIPT_BYTES:
            raise ValueError("receipt_size_limit")
        receipt = json.loads(data)
        if not isinstance(receipt, dict):
            raise ValueError("receipt_object_required")
        report = verify_receipt(receipt)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Do not return exception text: validation errors may contain private inputs.
        print(json.dumps({"status": "REJECTED", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
