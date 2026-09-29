"""The v2 probe inherits the original clock and uses separate one-shot records."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
role_v2 = importlib.import_module("phase_b_role_v2")


def test_v2_policy_pins_reviewed_bytes_and_v1_dependency() -> None:
    policy = json.loads(role_v2.POLICY.read_text(encoding="utf-8"))
    old = json.loads(role_v2.v1.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == role_v2._sha(role_v2.v1._canonical(old))
    assert policy["v1_files"] == old["files"]
    assert policy["operation_ids"] == list(role_v2.OPERATIONS.values())
    for name, path in role_v2.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert role_v2._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()
    manifest = role_v2._manifest(policy)
    assert manifest.count(b"\n") == len(role_v2.LOCAL_FILES)
    assert b"\r" not in manifest


def test_v2_read_is_distinct_and_does_not_reset_clock(tmp_path: Path) -> None:
    record = role_v2._reserve(tmp_path, "read", "digest")
    assert record.name == "phaseb-role-v2-read.json"
    with pytest.raises(role_v2.RoleV2Error, match="already reserved"):
        role_v2._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()
    assert not (tmp_path / "phaseb-role-read-v1.json").exists()


def test_v2_preflight_rejects_existing_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(role_v2.v1, "_remote_preflight", lambda policy: None)

    def fake_ssh(command: str, *, timeout: int = 60) -> bytes:
        del timeout
        if command.startswith("set -e; test ! -L"):
            return b"exists\n"
        return b""

    monkeypatch.setattr(role_v2.v1, "_ssh", fake_ssh)
    with pytest.raises(role_v2.RoleV2Error, match="runtime already exists"):
        role_v2._preflight({})
