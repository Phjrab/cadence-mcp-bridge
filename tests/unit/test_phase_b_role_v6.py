"""The ASCII role parser follows the diagnosed v5 encoding error."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
role_v6 = importlib.import_module("phase_b_role_v6")


def test_v6_policy_pins_bytes_and_v5_dependency() -> None:
    policy = json.loads(role_v6.POLICY.read_text(encoding="utf-8"))
    old = json.loads(role_v6.v5.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == role_v6._sha(role_v6.v1._canonical(old))
    assert policy["v5_files"] == old["files"]
    assert policy["operation_ids"] == list(role_v6.OPERATIONS.values())
    for name, path in role_v6.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert role_v6._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()
    assert b"\r" not in role_v6._manifest(policy)


def test_v6_read_is_distinct_and_once_only(tmp_path: Path) -> None:
    record = role_v6._reserve(tmp_path, "read", "digest")
    assert record.name == "phaseb-role-v6-read.json"
    with pytest.raises(role_v6.RoleV6Error, match="already reserved"):
        role_v6._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()


def test_v6_requires_diagnosed_v5_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = json.loads(role_v6.v5.POLICY.read_text(encoding="utf-8"))
    base = json.loads(role_v6.v1.POLICY.read_text(encoding="utf-8"))
    digest = "97e0d6ea2a6e19a6cb6905668cf0b5a1eccffaebfbab6ccd9476e3276f8b6f8b"
    monkeypatch.setattr(role_v6.v5, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phaseb-role-v5-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "reserved", "policy_sha256": digest}

    monkeypatch.setattr(role_v6.parent, "_read_json", fake_read)
    with pytest.raises(role_v6.RoleV6Error, match="diagnosed v5 read not verified"):
        role_v6._authority()


def test_v6_stream_is_anonymous_and_returns_no_names() -> None:
    helper = (ROOT / "remote/phase-campaign/role-v6/role_v6_helper.py").read_text(encoding="utf-8")
    runner = (ROOT / "remote/phase-campaign/role-v6/run.sh").read_text(encoding="utf-8")
    assert "worker.build_complete_result(before, after, filtered)" in helper
    assert 'names_included": False' in helper
    assert "skill.stdout" not in runner
    assert '| /usr/bin/python "$HELPER" complete' in runner
