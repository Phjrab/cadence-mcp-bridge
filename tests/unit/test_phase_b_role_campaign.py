"""Checks for the bounded role discovery extension to AUTO-PHASE-01."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
phase_b = importlib.import_module("phase_b_role_campaign")


def test_manifest_matches_reviewed_bytes_and_original_campaign() -> None:
    policy = json.loads(phase_b.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == phase_b._sha(
        phase_b._canonical(json.loads(phase_b.parent.POLICY.read_text(encoding="utf-8")))
    )
    for name, path in phase_b.LOCAL_FILES.items():
        assert phase_b._sha(path.read_bytes()) == policy["files"][name]
    assert policy["operation_ids"] == list(phase_b.OPERATIONS.values())


def test_duplicate_operation_is_blocked_without_budget_reset(tmp_path: Path) -> None:
    record = phase_b._reserve(tmp_path, "read", "digest")
    assert record.exists()
    with pytest.raises(phase_b.PhaseBError, match="already reserved"):
        phase_b._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()


def test_remote_preflight_enforces_source_lock_and_new_disk_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = json.loads(phase_b.POLICY.read_text(encoding="utf-8"))
    lines = (
        "buet\ncadence\n/home/buet/cds_work/.cadence_mcp\nbuet:buet\n"
        "/dev/sda1 60920424 32597684 25233980 57% /\n"
        + policy["installed_preflight_helper_sha256"]
        + "  /home/buet/cds_work/.cadence_mcp/py26/ade_profile_introspection.py\n"
    ).encode()
    snapshot = {
        "locks": {"source": 0, "state": 0},
        "source_tree": {"sha256": policy["source_fingerprint_sha256"]},
    }

    def fake_ssh(command: str, *, timeout: int = 60) -> bytes:
        del timeout
        return lines if command.startswith("set -e; id -un") else json.dumps(snapshot).encode()

    monkeypatch.setattr(phase_b, "_ssh", fake_ssh)
    phase_b._remote_preflight(policy)
    snapshot["locks"]["source"] = 1
    with pytest.raises(phase_b.PhaseBError, match="source or ADE state lock"):
        phase_b._remote_preflight(policy)
    snapshot["locks"]["source"] = 0
    lines = lines.replace(b"25233980", b"1000000")
    with pytest.raises(phase_b.PhaseBError, match="free-space floor"):
        phase_b._remote_preflight(policy)
