from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_forensic_json.py"


def _load_helper(tmp_path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("v3_forensic_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.EVIDENCE_ROOT = str(tmp_path)  # type: ignore[attr-defined]
    return module


def _unchanged_hashes() -> list[str]:
    hashes: list[str] = []
    for character in "abcdef0":
        hashes.extend([character * 64, character * 64])
    return hashes


def test_property_diff_emits_metadata_without_property_values(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "skill.stdout"
    output.write_bytes(
        b"legacy banner \xa9\n"
        b"MCP_V3_FORENSIC_BASELINE|true|35|14|8|8\n"
        b"MCP_V3_FORENSIC_DIFF|schGeometryLastUpdated|int|int|true|true|false|na\n"
        b"MCP_V3_FORENSIC_DIFF|mcpMutationTest|absent|string|false|true|false|true\n"
        b"MCP_V3_FORENSIC_SUMMARY|true|2|35|14|8\n"
    )

    helper.property_diff(str(output), _unchanged_hashes())

    evidence_path = tmp_path / "v3-property-diff-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    serialized = evidence_path.read_text(encoding="utf-8")
    assert evidence["validation_id"] == "0b9bf93c-11e9-416f-9e4a-69b1060fbd8e"
    assert evidence["read_only_verified"] is True
    assert evidence["property_values_included"] is False
    assert evidence["difference_count"] == 2
    assert evidence["differences"] == [
        {
            "name": "schGeometryLastUpdated",
            "backup_type": "int",
            "target_type": "int",
            "backup_present": True,
            "target_present": True,
            "value_equal": False,
            "approved_value_equal": None,
        },
        {
            "name": "mcpMutationTest",
            "backup_type": "absent",
            "target_type": "string",
            "backup_present": False,
            "target_present": True,
            "value_equal": False,
            "approved_value_equal": True,
        },
    ]
    assert "validated-v1" not in serialized


def test_property_diff_rejects_any_changed_protected_fingerprint(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "skill.stdout"
    output.write_text(
        "MCP_V3_FORENSIC_BASELINE|true|35|14|8|8\n"
        "MCP_V3_FORENSIC_DIFF|mcpMutationTest|absent|string|false|true|false|true\n"
        "MCP_V3_FORENSIC_SUMMARY|true|1|35|14|8\n",
        encoding="utf-8",
    )
    hashes = _unchanged_hashes()
    hashes[9] = "9" * 64

    try:
        helper.property_diff(str(output), hashes)
    except ValueError as error:
        assert str(error) == "v3_target changed during V3 read-only forensic inspection"
    else:
        raise AssertionError("changed V3 target fingerprint was accepted")


def test_property_diff_requires_approved_value_equality_metadata(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "skill.stdout"
    output.write_text(
        "MCP_V3_FORENSIC_BASELINE|true|35|14|8|8\n"
        "MCP_V3_FORENSIC_DIFF|mcpMutationTest|absent|string|false|true|false|na\n"
        "MCP_V3_FORENSIC_SUMMARY|true|1|35|14|8\n",
        encoding="utf-8",
    )

    try:
        helper.property_diff(str(output), _unchanged_hashes())
    except ValueError as error:
        assert str(error) == "missing approved-value equality result"
    else:
        raise AssertionError("missing approved-value equality metadata was accepted")
