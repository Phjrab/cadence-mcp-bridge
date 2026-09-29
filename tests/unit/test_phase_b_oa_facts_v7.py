"""Current OA facts stay in private one-shot evidence tied to the original clock."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
oa_v7 = importlib.import_module("phase_b_oa_facts_v7")


def test_v7_policy_pins_exact_files_and_v6_dependency() -> None:
    policy = json.loads(oa_v7.POLICY.read_text(encoding="utf-8"))
    old = json.loads(oa_v7.v6.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == oa_v7._sha(oa_v7.v1._canonical(old))
    assert policy["v6_files"] == old["files"]
    assert policy["operation_ids"] == list(oa_v7.OPERATIONS.values())
    for name, path in oa_v7.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert oa_v7._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()
    assert b"\r" not in oa_v7._manifest(policy)


def test_v7_read_is_distinct_and_once_only(tmp_path: Path) -> None:
    record = oa_v7._reserve(tmp_path, "read", "digest")
    assert record.name == "phaseb-oa-facts-v7-read.json"
    with pytest.raises(oa_v7.OaFactsV7Error, match="already reserved"):
        oa_v7._reserve(tmp_path, "read", "digest")
    assert not (tmp_path / "started-at.json").exists()


def test_v7_requires_parsed_v6_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = json.loads(oa_v7.v6.POLICY.read_text(encoding="utf-8"))
    base = json.loads(oa_v7.v1.POLICY.read_text(encoding="utf-8"))
    digest = "8ce8005a53fb4a25f294671e3c3aa7f0e0dafe7ddb952a95a73c1a1f06e427c6"
    monkeypatch.setattr(oa_v7.v6, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phaseb-role-v6-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "reserved", "policy_sha256": digest}

    monkeypatch.setattr(oa_v7.parent, "_read_json", fake_read)
    with pytest.raises(oa_v7.OaFactsV7Error, match="parsed v6 read not verified"):
        oa_v7._authority()


def test_private_result_is_bounded_and_not_echoed_by_operator() -> None:
    helper = (ROOT / "remote/phase-campaign/role-v7/oa_facts_v7.py").read_text(encoding="utf-8")
    runner = (ROOT / "remote/phase-campaign/role-v7/run.sh").read_text(encoding="utf-8")
    operator = (ROOT / "scripts/phase_b_oa_facts_v7.py").read_text(encoding="utf-8")
    assert "worker.MAX_OUTPUT_BYTES = 32768" in helper
    assert '"instances": instances' in helper
    assert "skill.stdout" not in runner
    assert '| /usr/bin/python "$HELPER" complete' in runner
    assert '"raw_local_file": str(output)' in operator
    assert "print(json.dumps(result, sort_keys=True))" in operator
