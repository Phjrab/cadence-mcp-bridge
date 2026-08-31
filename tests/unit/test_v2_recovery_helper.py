from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "v2_recovery_json.py"


def _load_helper(tmp_path: Path):  # type: ignore[no-untyped-def]
    stub_directory = tmp_path / "python26-stub"
    stub_directory.mkdir()
    (stub_directory / "fcntl.py").write_text(
        "LOCK_EX = 1\nLOCK_UN = 2\ndef flock(_handle, _operation):\n    return None\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("v2_recovery_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(stub_directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(stub_directory))
    module.EVIDENCE_ROOT = str(tmp_path)
    module.AUDIT_PATH = str(tmp_path / "write-events.jsonl")
    return module


def test_forensic_evidence_requires_read_only_fingerprint_equality(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "forensic.stdout"
    output.write_text(helper.FORENSIC_MARKER + "\n", encoding="utf-8")
    hashes = ["a" * 64, "a" * 64, "b" * 64, "b" * 64]
    hashes.extend(["c" * 64, "c" * 64, "d" * 64, "d" * 64])

    helper.forensic(str(output), hashes)

    evidence = json.loads(
        (tmp_path / "v2-forensic-evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["forensic_verified"] is True
    assert evidence["target_exact_approved_difference"] is True
    assert evidence["source_topology"] == [35, 14, 8]


def test_rollback_evidence_records_fixed_audit_and_changed_target(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "rollback.stdout"
    output.write_text(helper.ROLLBACK_MARKER + "\n", encoding="utf-8")
    hashes = ["a" * 64, "a" * 64, "b" * 64, "b" * 64]
    hashes.extend(["c" * 64, "c" * 64, "d" * 64, "e" * 64])

    helper.rollback(str(output), hashes)

    evidence = json.loads(
        (tmp_path / "v2-rollback-evidence.json").read_text(encoding="utf-8")
    )
    audit = [
        json.loads(line)
        for line in (tmp_path / "write-events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert evidence["rollback_verified"] is True
    assert evidence["approved_property_absent"] is True
    assert audit[0]["event"] == "design_write_v2_recovery_rollback"
    assert audit[0]["validation_id"] == helper.VALIDATION_ID


def test_property_diff_evidence_contains_metadata_but_no_values(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "property-diff.stdout"
    output.write_bytes(
        b"legacy banner \xa9\n"
        b"MCP_V2_PROPERTY_DIFF|baselineStamp|string|string|true|true|false\n"
        b"MCP_V2_PROPERTY_DIFF|mcpMutationTest|absent|string|false|true|false\n"
        b"MCP_V2_PROPERTY_DIFF_SUMMARY|true|2|35|14|8\n"
    )
    hashes = ["a" * 64, "a" * 64, "b" * 64, "b" * 64]
    hashes.extend(["c" * 64, "c" * 64, "d" * 64, "d" * 64])
    hashes.extend(["e" * 64, "e" * 64])

    helper.property_diff(str(output), hashes)

    evidence_path = tmp_path / "v2-property-diff-pdk-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    serialized = evidence_path.read_text(encoding="utf-8")
    assert evidence["property_diff_verified"] is True
    assert evidence["property_values_included"] is False
    assert evidence["difference_count"] == 2
    assert evidence["pdk_fingerprint_before"] == evidence["pdk_fingerprint_after"]
    assert evidence["differences"][0] == {
        "name": "baselineStamp",
        "backup_type": "string",
        "target_type": "string",
        "backup_present": True,
        "target_present": True,
        "value_equal": False,
    }
    assert "validated-v1" not in serialized


def test_property_diff_rejects_changed_fingerprint(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "property-diff.stdout"
    output.write_text(
        "MCP_V2_PROPERTY_DIFF|changed|string|string|true|true|false\n"
        "MCP_V2_PROPERTY_DIFF_SUMMARY|true|1|35|14|8\n",
        encoding="utf-8",
    )
    hashes = ["a" * 64, "e" * 64, "b" * 64, "b" * 64]
    hashes.extend(["c" * 64, "c" * 64, "d" * 64, "d" * 64])
    hashes.extend(["f" * 64, "f" * 64])

    try:
        helper.property_diff(str(output), hashes)
    except ValueError as error:
        assert str(error) == "source changed during V2 property diff inspection"
    else:
        raise AssertionError("changed source fingerprint was accepted")
