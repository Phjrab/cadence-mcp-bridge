"""Synthetic checks for the separate delegated campaign path."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/phase_campaign.py"
SPEC = importlib.util.spec_from_file_location("phase_campaign", SCRIPT)
assert SPEC and SPEC.loader
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)


def test_exact_delegation_allows_only_versioned_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Policy binding is a unit test; repository origin is a separately tested input.
    # A hosted checkout may omit the .git suffix or belong to a contributing fork.
    def repository_identity(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert argv == ["git", "-C", str(campaign.ROOT), "remote", "get-url", "origin"]
        assert kwargs == {"capture_output": True, "check": False, "timeout": 5}
        return subprocess.CompletedProcess(
            argv, 0, b"https://github.com/Phjrab/cadence-mcp-bridge.git\n", b""
        )

    monkeypatch.setattr(campaign.subprocess, "run", repository_identity)
    policy = json.loads(campaign.POLICY.read_text(encoding="utf-8"))
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    delegation_path = tmp_path / "delegation.json"
    delegation_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign_id": "AUTO-PHASE-01",
                "policy_sha256": digest,
                "user_delegation": "explicit-in-current-task",
            }
        ),
        encoding="utf-8",
    )
    elapsed_policy = json.loads(campaign.ELAPSED_POLICY.read_text(encoding="utf-8"))
    elapsed_policy_path = tmp_path / "elapsed-policy.json"
    elapsed_policy_path.write_text(json.dumps(elapsed_policy), encoding="utf-8")
    elapsed_digest = hashlib.sha256(campaign._canonical(elapsed_policy)).hexdigest()
    elapsed_delegation_path = tmp_path / "elapsed-delegation.json"
    elapsed_delegation_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "campaign_id": "AUTO-PHASE-01",
                "parent_policy_sha256": digest,
                "policy_sha256": elapsed_digest,
                "user_delegation": "explicit-in-current-task",
            }
        ),
        encoding="utf-8",
    )
    assert (
        campaign._load_authority(
            policy_path, delegation_path, elapsed_policy_path, elapsed_delegation_path
        )
        == digest
    )
    elapsed_delegation_bytes = elapsed_delegation_path.read_bytes()
    elapsed_delegation_path.unlink()
    with pytest.raises(campaign.CampaignError, match="policy or delegation file unavailable"):
        campaign._load_authority(
            policy_path, delegation_path, elapsed_policy_path, elapsed_delegation_path
        )
    elapsed_delegation_path.write_bytes(elapsed_delegation_bytes)
    elapsed_policy["max_elapsed_hours"] = 24
    elapsed_policy_path.write_text(json.dumps(elapsed_policy), encoding="utf-8")
    with pytest.raises(campaign.CampaignError, match="elapsed limit policy changed"):
        campaign._load_authority(
            policy_path, delegation_path, elapsed_policy_path, elapsed_delegation_path
        )
    elapsed_policy["max_elapsed_hours"] = None
    elapsed_policy_path.write_text(json.dumps(elapsed_policy), encoding="utf-8")
    policy["managed_root"] = "/"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(campaign.CampaignError, match="DENY_OUT_OF_SCOPE"):
        campaign._load_authority(
            policy_path, delegation_path, elapsed_policy_path, elapsed_delegation_path
        )


def test_elapsed_change_preserves_original_start_and_replay(tmp_path: Path) -> None:
    original = {
        "at": (datetime.now(UTC) - timedelta(hours=12)).isoformat(),
        "policy_sha256": "digest",
    }
    start = tmp_path / "started-at.json"
    start.write_text(json.dumps(original), encoding="utf-8")
    before = start.read_bytes()
    record, attempt = campaign._reserve("identity", "digest", tmp_path)
    assert attempt == 1
    assert start.read_bytes() == before
    with pytest.raises(campaign.CampaignError, match="prior attempt outcome unknown"):
        campaign._reserve("identity", "digest", tmp_path)
    campaign._replace_record(record, {"state": "transport_failed", "attempt": 1})
    assert campaign._reserve("identity", "digest", tmp_path)[1] == 2


def test_future_campaign_start_still_denied(tmp_path: Path) -> None:
    (tmp_path / "started-at.json").write_text(
        json.dumps(
            {
                "at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "policy_sha256": "digest",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(campaign.CampaignError, match="start is in the future"):
        campaign._reserve("identity", "digest", tmp_path)
    assert not (tmp_path / "identity-1.json").exists()


def test_reservation_prevents_duplicate_and_unknown_replay(tmp_path: Path) -> None:
    path, attempt = campaign._reserve("identity", "digest", tmp_path)
    assert attempt == 1
    with pytest.raises(campaign.CampaignError, match="BLOCKED_UNCERTAIN_STATE"):
        campaign._reserve("identity", "digest", tmp_path)
    campaign._replace_record(path, {"state": "transport_failed", "attempt": 1})
    _, attempt = campaign._reserve("identity", "digest", tmp_path)
    assert attempt == 2
    with pytest.raises(campaign.CampaignError, match="DENY_OUT_OF_SCOPE"):
        campaign._reserve("arbitrary_ssh", "digest", tmp_path)


def test_completed_operation_cannot_repeat(tmp_path: Path) -> None:
    path, _ = campaign._reserve("ade_readonly", "digest", tmp_path)
    campaign._replace_record(path, {"state": "succeeded"})
    with pytest.raises(campaign.CampaignError, match="already completed"):
        campaign._reserve("ade_readonly", "digest", tmp_path)


def test_fixed_transport_records_private_output_and_blocks_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(campaign, "_load_authority", lambda: "digest")
    monkeypatch.setattr(campaign, "_state_root", lambda: tmp_path)
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"buet\ncadence\n0.18.0\n", b"")

    monkeypatch.setattr(campaign.subprocess, "run", fake_run)
    result = campaign.run("identity")
    assert result["state"] == "succeeded"
    assert (tmp_path / "identity-1.output").read_bytes() == b"buet\ncadence\n0.18.0\n"
    assert len(calls) == 1
    assert calls[0][-2:] == ["cadence-vm", campaign.REMOTE_COMMANDS["identity"]]
    with pytest.raises(campaign.CampaignError, match="already completed"):
        campaign.run("identity")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "returncode,remote",
    [
        (1, b"https://github.com/Phjrab/cadence-mcp-bridge.git"),
        (0, b"https://github.com/untrusted/cadence-mcp-bridge.git"),
        (0, b"https://github.com/Phjrab/cadence-mcp-bridge"),
        (0, b""),
    ],
)
def test_repository_identity_failure_denies_before_authority_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int, remote: bytes
) -> None:
    monkeypatch.setattr(
        campaign.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, returncode, remote, b""),
    )
    unavailable = tmp_path / "absent.json"
    with pytest.raises(campaign.CampaignError, match="repository remote mismatch"):
        campaign._load_authority(unavailable, unavailable, unavailable, unavailable)
    assert not list(tmp_path.iterdir())
