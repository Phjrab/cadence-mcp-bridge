"""Publish operator-reviewed registration or exact explicit user-selection records.

This is not an MCP tool. It cannot copy/delete payloads or alter protected history.
Neither a phase delegation nor a model boolean supplies selected deletion intent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import ade_qual as io
import deploy_native_mcp_v1 as transport
import phase_campaign as campaign
from storage_deploy import CONTROL, PRIVATE, authority

from cadence_mcp_bridge.storage import CleanupRequest, storage_digest


def validate_registration(record: dict[str, Any]) -> str:
    keys = {
        "contract_version",
        "artifact_uuid",
        "analysis_type",
        "measurement_extracted",
        "replay_dependency",
        "evidence_dependency",
        "active_dependency",
        "fingerprint",
        "content_sha256",
    }
    identity = record.get("artifact_uuid")
    if (
        not isinstance(identity, str)
        or str(UUID(identity)) != identity
        or UUID(identity).version != 4
    ):
        raise ValueError("canonical intermediate UUID required")
    if (
        set(record) != keys
        or type(record["contract_version"]) is not int
        or record["contract_version"] != 1
        or record["analysis_type"] not in ("dc", "ac", "tran", "sweep")
        or record["measurement_extracted"] is not True
        or any(
            record[n] is not False
            for n in ("replay_dependency", "evidence_dependency", "active_dependency")
        )
    ):
        raise ValueError("reviewed disposable contract required")
    for name in ("fingerprint", "content_sha256"):
        value = record[name]
        if (
            type(value) is not str
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValueError("canonical fingerprint required")
    return identity


def publish(action: str, record_path: Path, review_path: Path) -> dict[str, Any]:
    authority()
    record = campaign._read_json(record_path)
    review = campaign._read_json(review_path)
    if action == "approve":
        request = CleanupRequest.model_validate_json(json.dumps(record))
        if request.dry_run:
            raise ValueError("dry-run does not need destructive approval")
        raw = request.model_dump(mode="json")
        expected = {
            "contract_version": 1,
            "request_sha256": storage_digest(raw),
            "selected_artifact_ids": raw["selected_artifact_ids"],
            "plan_sha256": raw["plan_sha256"],
            "user_selection": "explicit-selected-items",
        }
        if review != expected:
            raise ValueError("exact separately supplied human selection record required")
        identity, group, value = str(request.operation_id), "approvals", expected
    elif action == "register":
        identity = validate_registration(record)
        if review != {
            "operator_review": "explicit-reviewed-disposable-intermediate",
            "registration_sha256": storage_digest(record),
        }:
            raise ValueError("separate disposable dependency review required")
        group, value = "registrations", record
    else:
        raise ValueError("unsupported operator action")
    source = PRIVATE / ("storage-operator-" + action + "-" + identity + ".private.json")
    with source.open("xb") as stream:
        stream.write(campaign._canonical(value))
    target = CONTROL + "/" + group + "/" + identity + ".json"
    stage = target + ".stage"
    transport.ssh(
        "test ! -e "
        + target
        + " && test ! -L "
        + target
        + " && test ! -e "
        + stage
        + " && test ! -L "
        + stage
    )
    io.command((*io.SCP, str(source), "cadence-vm:" + stage))
    sha = io.digest(source.read_bytes())
    transport.ssh(
        'test "$(sha256sum '
        + stage
        + " | cut -d' ' -f1)\" = "
        + sha
        + " && chmod 600 "
        + stage
        + " && mv -n "
        + stage
        + " "
        + target
    )
    return {
        "state": "operator_record_published",
        "action": action,
        "identity": identity,
        "deleted_artifacts": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Operator-only exact storage review records.")
    parser.add_argument("action", choices=("register", "approve"))
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.action, args.record, args.review)))
