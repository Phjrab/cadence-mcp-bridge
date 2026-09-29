"""The marker diagnostic follows the blocked v4 role parser."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
role_v5 = importlib.import_module("phase_b_role_v5")


def test_v5_policy_pins_bytes_and_v4_dependency() -> None:
    policy = json.loads(role_v5.POLICY.read_text(encoding="utf-8"))
    old = json.loads(role_v5.v4.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == role_v5._sha(role_v5.v1._canonical(old))
    assert policy["v4_files"] == old["files"]
    assert policy["operation_ids"] == list(role_v5.OPERATIONS.values())
    for name, path in role_v5.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert role_v5._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()
    assert b"\r" not in role_v5._manifest(policy)


def test_v5_read_is_distinct_and_once_only(tmp_path: Path) -> None:
    record = role_v5._reserve(tmp_path, "read", "digest")
    assert record.name == "phaseb-role-v5-read.json"
    with pytest.raises(role_v5.RoleV5Error, match="already reserved"):
        role_v5._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()


def test_v5_requires_blocked_v4_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = json.loads(role_v5.v4.POLICY.read_text(encoding="utf-8"))
    base = json.loads(role_v5.v1.POLICY.read_text(encoding="utf-8"))
    digest = "88226087cc47b176fe47b31dc1f8435ea0e7ebeb05cbc1d2dc095be15664e9e4"
    monkeypatch.setattr(role_v5.v4, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phaseb-role-v4-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "reserved", "policy_sha256": digest}

    monkeypatch.setattr(role_v5.parent, "_read_json", fake_read)
    with pytest.raises(role_v5.RoleV5Error, match="blocked v4 read not verified"):
        role_v5._authority()


def test_v5_stream_is_anonymous_and_returns_no_names() -> None:
    helper = (ROOT / "remote/phase-campaign/role-v5/role_v5_helper.py").read_text(encoding="utf-8")
    runner = (ROOT / "remote/phase-campaign/role-v5/run.sh").read_text(encoding="utf-8")
    assert "worker.parse_private_stream(stream)" in helper
    assert 'names_included": False' in helper
    assert "skill.stdout" not in runner
    assert '| /usr/bin/python "$HELPER" complete' in runner
