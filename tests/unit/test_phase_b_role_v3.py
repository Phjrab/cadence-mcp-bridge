"""The diagnostic is pinned, private, and follows only the blocked v2 read."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
role_v3 = importlib.import_module("phase_b_role_v3")


def test_v3_policy_pins_diagnostic_bytes_and_v2_dependency() -> None:
    policy = json.loads(role_v3.POLICY.read_text(encoding="utf-8"))
    old = json.loads(role_v3.v2.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == role_v3._sha(role_v3.v1._canonical(old))
    assert policy["v2_files"] == old["files"]
    assert policy["operation_ids"] == list(role_v3.OPERATIONS.values())
    for name, path in role_v3.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert role_v3._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()
    manifest = role_v3._manifest(policy)
    assert manifest.count(b"\n") == len(role_v3.LOCAL_FILES)
    assert b"\r" not in manifest


def test_v3_operation_is_once_only_and_keeps_original_clock(tmp_path: Path) -> None:
    record = role_v3._reserve(tmp_path, "read", "digest")
    assert record.name == "phaseb-role-v3-read.json"
    with pytest.raises(role_v3.RoleV3Error, match="already reserved"):
        role_v3._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()


def test_v3_requires_blocked_v2_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_policy = json.loads(role_v3.v2.POLICY.read_text(encoding="utf-8"))
    base_policy = json.loads(role_v3.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        role_v3.v2,
        "_authority",
        lambda: (
            old_policy,
            "076994d3ffdc2c02c00bb243fdf32f8c5c2e24d1b7c55102b7f0317f70e7a6ad",
            tmp_path,
            base_policy,
        ),
    )

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phaseb-role-v2-deploy.json":
            return {
                "state": "succeeded",
                "policy_sha256": "076994d3ffdc2c02c00bb243fdf32f8c5c2e24d1b7c55102b7f0317f70e7a6ad",
            }
        return {
            "state": "reserved",
            "policy_sha256": "076994d3ffdc2c02c00bb243fdf32f8c5c2e24d1b7c55102b7f0317f70e7a6ad",
        }

    monkeypatch.setattr(role_v3.parent, "_read_json", fake_read)
    with pytest.raises(role_v3.RoleV3Error, match="blocked v2 read not verified"):
        role_v3._authority()


def test_diagnostic_retains_no_raw_stdout() -> None:
    helper = (ROOT / "remote/phase-campaign/role-v3/role_v3_helper.py").read_text(encoding="utf-8")
    runner = (ROOT / "remote/phase-campaign/role-v3/run.sh").read_text(encoding="utf-8")
    assert "private_marker_count" in helper
    assert 'raw_content_included": False' in helper
    assert "skill.stdout" not in runner
    assert '| /usr/bin/python "$HELPER" complete' in runner
