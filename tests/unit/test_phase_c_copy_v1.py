"""The one-shot work copy is bound to the reviewed OA observation and bytes."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
copy_v1 = importlib.import_module("phase_c_copy_v1")


def test_copy_policy_pins_v7_and_exact_lf_files() -> None:
    policy = json.loads(copy_v1.POLICY.read_text(encoding="utf-8"))
    old = json.loads(copy_v1.facts_v7.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == copy_v1._sha(copy_v1.v1._canonical(old))
    assert policy["v7_files"] == old["files"]
    assert policy["operation_ids"] == list(copy_v1.OPERATIONS.values())
    assert policy["target_cell"] == copy_v1.TARGET_CELL
    for name, path in copy_v1.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert copy_v1._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_copy_reservation_is_once_only(tmp_path: Path) -> None:
    record = copy_v1._reserve(tmp_path, "copy", "digest")
    assert record.name == "phasec-copy-v1-run.json"
    with pytest.raises(copy_v1.CopyV1Error, match="already reserved"):
        copy_v1._reserve(tmp_path, "copy", "digest")


def test_copy_requires_successful_v7_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = json.loads(copy_v1.facts_v7.POLICY.read_text(encoding="utf-8"))
    base = json.loads(copy_v1.v1.POLICY.read_text(encoding="utf-8"))
    digest = copy_v1._sha(copy_v1.v1._canonical(old))
    monkeypatch.setattr(copy_v1.facts_v7, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phaseb-oa-facts-v7-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "reserved", "policy_sha256": digest}

    monkeypatch.setattr(copy_v1.parent, "_read_json", fake_read)
    with pytest.raises(copy_v1.CopyV1Error, match="current v7 OA facts not verified"):
        copy_v1._authority()


def test_remote_copy_has_exact_target_and_no_overwrite() -> None:
    skill = copy_v1.LOCAL_FILES["copy-current-oa.il"].read_text(encoding="ascii")
    helper = copy_v1.LOCAL_FILES["copy_helper.py"].read_text(encoding="ascii")
    runner = copy_v1.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert 'targetCell = "WP14_AUTO_PHASE_01_TB2"' in skill
    assert "dbCopyCellView(sourceCv workLib targetCell sourceView nil nil nil)" in skill
    assert 'dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")' in skill
    assert "os.path.lexists(TARGET_CELL)" in helper
    assert 'before["protected"] != after["protected"]' in helper
    assert '"status": "copied"' in helper
    assert "timeout 180" in runner
    assert '"${component_status[0]}" -eq 0' in runner


def test_preflight_uses_nested_role_snapshot_contract() -> None:
    operator = (ROOT / "scripts/phase_c_copy_v1.py").read_text(encoding="utf-8")
    assert 'v1.REMOTE_VERSION + "/wp14_role_discovery.py preflight"' in operator
    assert 'protected.get("ade_state_tree")' in operator
    assert 'snapshot.get("locks") != []' in operator
    assert ' && pwd -P)" = ' in operator
    assert "realpath" not in operator
    assert 'v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)' in operator
    assert 'v1._ssh("test -d " + RUNTIME' not in operator
