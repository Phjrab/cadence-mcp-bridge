"""Fixed WP-14 read-only operation under the user-delegated phase campaign.

This is an operator entry point, not an MCP tool or a general SSH launcher. Legacy
single-use collectors and their claims remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_CAMPAIGN_V1.json"
DELEGATION = ROOT / ".codex/phase-campaign-delegation.json"
ELAPSED_POLICY = ROOT / "docs/policy/PHASE_ELAPSED_LIMIT_V2.json"
ELAPSED_DELEGATION = ROOT / ".codex/phase-elapsed-limit-v2-delegation.json"
REMOTE_COMMANDS = {
    "identity": "id -un; hostname; /home/buet/cds_work/.cadence_mcp/bin/cadence-runner version",
    "ade_readonly": (
        "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner "
        "inspect-ade-profile actual-differential-amplifier-tb2-transient"
    ),
}
MAX_OUTPUT = 131072
MAX_ATTEMPTS = 3  # first attempt plus two communication retries


class CampaignError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise CampaignError("BLOCKED_ENVIRONMENT: policy or delegation file unavailable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: invalid JSON record") from exc
    if not isinstance(value, dict):
        raise CampaignError("BLOCKED_ENVIRONMENT: invalid policy record")
    return value


def _state_root() -> Path:
    app_data = os.environ.get("LOCALAPPDATA")
    if not app_data:
        raise CampaignError("BLOCKED_ENVIRONMENT: LOCALAPPDATA unavailable")
    root = Path(app_data) / "CadenceMcpBridge" / "phase-campaign-v1"
    if root.is_symlink():
        raise CampaignError("BLOCKED_ENVIRONMENT: state path is a link")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_authority(
    policy_path: Path = POLICY,
    delegation_path: Path = DELEGATION,
    elapsed_policy_path: Path = ELAPSED_POLICY,
    elapsed_delegation_path: Path = ELAPSED_DELEGATION,
) -> str:
    repository = subprocess.run(
        ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
        capture_output=True,
        check=False,
        timeout=5,
    )
    if repository.returncode != 0 or repository.stdout.strip() not in (
        b"https://github.com/Phjrab/cadence-mcp-bridge.git",
        b"git@github.com:Phjrab/cadence-mcp-bridge.git",
    ):
        raise CampaignError("DENY_OUT_OF_SCOPE: repository remote mismatch")
    policy = _read_json(policy_path)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "repository": "Phjrab/cadence-mcp-bridge",
        "ssh_alias": "cadence-vm",
        "remote_user": "buet",
        "remote_host": "cadence",
        "managed_root": "/home/buet/cds_work/.cadence_mcp",
        "allowed_operations": ["identity", "ade_readonly"],
        "max_elapsed_hours": 8,
        "max_read_attempts_per_operation": MAX_ATTEMPTS,
    }
    if policy != expected:
        raise CampaignError("DENY_OUT_OF_SCOPE: campaign policy changed")
    delegation = _read_json(delegation_path)
    digest = hashlib.sha256(_canonical(policy)).hexdigest()
    if delegation != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CampaignError("DENY_OUT_OF_SCOPE: delegation binding absent or changed")
    elapsed_policy = _read_json(elapsed_policy_path)
    if elapsed_policy != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": digest,
        "replaces_max_elapsed_hours": 8,
        "max_elapsed_hours": None,
        "preserve_original_started_at": True,
        "preserve_other_cumulative_budgets": True,
        "user_change": "explicit-in-current-task",
    }:
        raise CampaignError("DENY_OUT_OF_SCOPE: elapsed limit policy changed")
    elapsed_digest = hashlib.sha256(_canonical(elapsed_policy)).hexdigest()
    if _read_json(elapsed_delegation_path) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": digest,
        "policy_sha256": elapsed_digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CampaignError("DENY_OUT_OF_SCOPE: elapsed limit delegation absent or changed")
    return digest


def _reserve(operation: str, digest: str, state_root: Path) -> tuple[Path, int]:
    if operation not in REMOTE_COMMANDS:
        raise CampaignError("DENY_OUT_OF_SCOPE: operation is not allowlisted")
    campaign_start = state_root / "started-at.json"
    now = datetime.now(UTC)
    try:
        with campaign_start.open("x", encoding="utf-8") as stream:
            json.dump({"at": now.isoformat(), "policy_sha256": digest}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        pass
    start = _read_json(campaign_start)
    if start.get("policy_sha256") != digest:
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: campaign policy drift")
    try:
        started = datetime.fromisoformat(start["at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: invalid campaign clock") from exc
    if started > now:
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: campaign start is in the future")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        path = state_root / f"{operation}-{attempt}.json"
        if path.exists():
            prior = _read_json(path)
            if prior.get("state") == "succeeded":
                raise CampaignError("BLOCKED_UNCERTAIN_STATE: operation already completed")
            if prior.get("state") != "transport_failed":
                raise CampaignError("BLOCKED_UNCERTAIN_STATE: prior attempt outcome unknown")
            continue
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(
                    {"state": "reserved", "policy_sha256": digest, "at": now.isoformat()},
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
            return path, attempt
        except FileExistsError as exc:
            raise CampaignError("BLOCKED_UNCERTAIN_STATE: concurrent operation") from exc
    raise CampaignError("BUDGET_REACHED: read communication retry limit")


def _replace_record(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".new")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run(operation: str) -> dict[str, Any]:
    if operation not in REMOTE_COMMANDS:
        raise CampaignError("DENY_OUT_OF_SCOPE: operation is not allowlisted")
    digest = _load_authority()
    state_root = _state_root()
    if operation == "ade_readonly":
        identities = [
            _read_json(state_root / f"identity-{index}.json")
            for index in range(1, MAX_ATTEMPTS + 1)
            if (state_root / f"identity-{index}.json").exists()
        ]
        verified = [
            item
            for item in identities
            if item.get("state") == "succeeded" and item.get("policy_sha256") == digest
        ]
        if len(verified) != 1:
            raise CampaignError("BLOCKED_UNCERTAIN_STATE: fresh identity is required")
        observed = datetime.fromisoformat(verified[0]["observed_at"])
        if datetime.now(UTC) - observed > timedelta(hours=1):
            raise CampaignError("BLOCKED_UNCERTAIN_STATE: identity observation is stale")
    record_path, attempt = _reserve(operation, digest, state_root)
    command = REMOTE_COMMANDS[operation]
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=5",
                "cadence-vm",
                command,
            ],
            capture_output=True,
            timeout=180 if operation == "ade_readonly" else 30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _replace_record(record_path, {"state": "transport_failed", "attempt": attempt})
        raise CampaignError("BLOCKED_ENVIRONMENT: fixed transport failed") from None
    if len(result.stdout) + len(result.stderr) > MAX_OUTPUT:
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: oversized remote response")
    if result.returncode != 0:
        if result.returncode == 255:
            _replace_record(record_path, {"state": "transport_failed", "attempt": attempt})
            raise CampaignError("BLOCKED_ENVIRONMENT: fixed SSH transport failed")
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: fixed remote operation failed")
    try:
        output = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CampaignError("BLOCKED_UNCERTAIN_STATE: invalid remote output") from exc
    if operation == "identity":
        lines = output.strip().splitlines()
        if len(lines) < 3 or lines[0] != "buet" or lines[1] != "cadence":
            raise CampaignError("BLOCKED_UNCERTAIN_STATE: remote identity mismatch")
    else:
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise CampaignError("BLOCKED_UNCERTAIN_STATE: invalid ADE response") from exc
        if not isinstance(payload, dict) or any(
            payload.get(key) != expected
            for key, expected in {
                "schema_version": 1,
                "profile_id": "actual-differential-amplifier-tb2-transient",
                "read_only": True,
                "raw_content_included": False,
                "paths_included": False,
            }.items()
        ):
            raise CampaignError("BLOCKED_UNCERTAIN_STATE: ADE response contract mismatch")
    raw_path = state_root / f"{operation}-{attempt}.output"
    with raw_path.open("xb") as stream:
        stream.write(result.stdout)
        stream.flush()
        os.fsync(stream.fileno())
    summary = {
        "state": "succeeded",
        "operation": operation,
        "attempt": attempt,
        "policy_sha256": digest,
        "observed_at": datetime.now(UTC).isoformat(),
        "raw_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "raw_local_file": str(raw_path),
    }
    _replace_record(record_path, summary)
    return summary


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: phase_campaign.py identity|ade_readonly", file=sys.stderr)
        return 2
    try:
        summary = run(sys.argv[1])
    except CampaignError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
