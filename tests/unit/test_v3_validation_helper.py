from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_validation_json.py"
PLAN = PROJECT_ROOT / "remote" / "config" / "design-write-v3-plan.json"


def _load_helper(tmp_path: Path):  # type: ignore[no-untyped-def]
    stub_directory = tmp_path / "python26-stub"
    stub_directory.mkdir()
    (stub_directory / "fcntl.py").write_text(
        "LOCK_EX = 1\nLOCK_UN = 2\ndef flock(_handle, _operation):\n    return None\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("v3_validation_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(stub_directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(stub_directory))
    return module


def _successful_output(path: Path) -> None:
    lines = [
        "MCP_V3_STAGE|source_verify|true|35|14|8",
        "MCP_V3_STAGE|V3_destination_absence_check|true",
        "MCP_V3_STAGE|V3_backup_absence_check|true",
        "MCP_V3_STAGE|V3_copy|true|35|14|8",
    ]
    for stage in ("baseline",):
        lines.extend(
            (
                f"MCP_V3_FINGERPRINT|{stage}|topology|35|14|8|8",
                f"MCP_V3_FINGERPRINT|{stage}|property|baselineStamp|int",
            )
        )
    lines.extend(
        (
            "MCP_V3_STAGE|baseline_fingerprint|true|8",
            "MCP_V3_STAGE|dry_run|true|absent|1|0|false",
        )
    )
    for stage in ("dry_run",):
        lines.extend(
            (
                f"MCP_V3_FINGERPRINT|{stage}|topology|35|14|8|8",
                f"MCP_V3_FINGERPRINT|{stage}|property|baselineStamp|int",
            )
        )
    lines.extend(
        (
            "MCP_V3_STAGE|unchanged_verification|true",
            "MCP_V3_FINGERPRINT|backup|topology|35|14|8|8",
            "MCP_V3_FINGERPRINT|backup|property|baselineStamp|int",
            "MCP_V3_STAGE|backup|true",
            "MCP_V3_STAGE|apply|true|1",
            "MCP_V3_STAGE|exact_diff_verification|true|1",
            "MCP_V3_STAGE|rollback|true",
            "MCP_V3_FINGERPRINT|rollback|topology|35|14|8|8",
            "MCP_V3_FINGERPRINT|rollback|property|baselineStamp|int",
            "MCP_V3_FINGERPRINT|backup_final|topology|35|14|8|8",
            "MCP_V3_FINGERPRINT|backup_final|property|baselineStamp|int",
            "MCP_V3_STAGE|baseline_restoration_verification|true",
            "MCP_V3_STAGE|source_unchanged_verification|true",
        )
    )
    path.write_bytes(b"legacy banner \xa9\n" + ("\n".join(lines) + "\n").encode("ascii"))


def test_plan_sha_and_fixed_contract_are_verified(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)

    plan = helper.load_plan(str(PLAN))

    assert plan["plan_id"] == "mcp-cellview-property-v3"
    assert len(plan["acceptance_criteria"]) == 10
    assert plan["sequence"] == helper.FULL_SEQUENCE


def test_finalize_requires_all_protected_fingerprints_and_writes_audit(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    plan = helper.load_plan(str(PLAN))
    output = tmp_path / "skill.stdout"
    _successful_output(output)
    audit = tmp_path / "write-events.jsonl"
    manifest = tmp_path / "validation-manifest.json"
    validation_id = "12345678-1234-4234-9234-123456789abc"
    hashes = [
        "a" * 64,
        "a" * 64,
        "b" * 64,
        "b" * 64,
        "c" * 64,
        "c" * 64,
        "d" * 64,
        "d" * 64,
        "e" * 64,
        "e" * 64,
    ]
    arguments = [validation_id, str(output)]
    arguments.extend(hashes)
    arguments.extend(
        ["f" * 64, "0" * 64, "operator", "buet", str(audit), str(manifest)]
    )

    helper.finalize(plan, arguments)

    evidence = json.loads(manifest.read_text(encoding="utf-8"))
    audit_records = [
        json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()
    ]
    assert evidence["plan_sha256"] == helper.PLAN_SHA256
    assert evidence["rollback_verified"] is True
    assert evidence["audit_verified"] is True
    assert evidence["property_values_included"] is False
    assert len(audit_records) == 14
    assert audit_records[-1]["event"] == "design_write_v3_audit_verification"
    assert all(record["validation_id"] == validation_id for record in audit_records)


def test_finalize_rejects_protected_fingerprint_change(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    plan = helper.load_plan(str(PLAN))
    output = tmp_path / "skill.stdout"
    _successful_output(output)
    hashes = [
        "a" * 64,
        "f" * 64,
        "b" * 64,
        "b" * 64,
        "c" * 64,
        "c" * 64,
        "d" * 64,
        "d" * 64,
        "e" * 64,
        "e" * 64,
    ]
    arguments = ["12345678-1234-4234-9234-123456789abc", str(output)]
    arguments.extend(hashes)
    arguments.extend(
        [
            "1" * 64,
            "2" * 64,
            "operator",
            "buet",
            str(tmp_path / "audit.jsonl"),
            str(tmp_path / "manifest.json"),
        ]
    )

    try:
        helper.finalize(plan, arguments)
    except ValueError as error:
        assert str(error) == "source changed during V3 validation"
    else:
        raise AssertionError("changed protected source was accepted")
