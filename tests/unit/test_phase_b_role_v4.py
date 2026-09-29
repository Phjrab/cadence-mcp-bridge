"""The names-only role parser follows verified v3 OA lifecycle evidence."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
role_v4 = importlib.import_module("phase_b_role_v4")


def test_v4_policy_pins_bytes_and_v3_dependency() -> None:
    policy = json.loads(role_v4.POLICY.read_text(encoding="utf-8"))
    old = json.loads(role_v4.v3.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == role_v4._sha(role_v4.v1._canonical(old))
    assert policy["v3_files"] == old["files"]
    assert policy["operation_ids"] == list(role_v4.OPERATIONS.values())
    for name, path in role_v4.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert role_v4._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()
    assert b"\r" not in role_v4._manifest(policy)


def test_v4_read_is_distinct_and_once_only(tmp_path: Path) -> None:
    record = role_v4._reserve(tmp_path, "read", "digest")
    assert record.name == "phaseb-role-v4-read.json"
    with pytest.raises(role_v4.RoleV4Error, match="already reserved"):
        role_v4._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()


def test_v4_requires_observed_v3_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = json.loads(role_v4.v3.POLICY.read_text(encoding="utf-8"))
    base = json.loads(role_v4.v1.POLICY.read_text(encoding="utf-8"))
    digest = "dbc4ec32784966aef3e62a8698c5ebd73ace27556f12973a89015d28e214709d"
    monkeypatch.setattr(role_v4.v3, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phaseb-role-v3-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "reserved", "policy_sha256": digest}

    monkeypatch.setattr(role_v4.parent, "_read_json", fake_read)
    with pytest.raises(role_v4.RoleV4Error, match="observed v3 read not verified"):
        role_v4._authority()


def test_v4_stream_is_anonymous_and_returns_no_names() -> None:
    helper = (ROOT / "remote/phase-campaign/role-v4/role_v4_helper.py").read_text(encoding="utf-8")
    runner = (ROOT / "remote/phase-campaign/role-v4/run.sh").read_text(encoding="utf-8")
    assert "worker.build_complete_result(before, after, stream)" in helper
    assert 'names_included": False' in helper
    assert "skill.stdout" not in runner
    assert '| /usr/bin/python "$HELPER" complete' in runner
