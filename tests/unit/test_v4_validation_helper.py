from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "v4_validation_json.py"
PLAN = PROJECT_ROOT / "remote" / "config" / "design-write-v4-plan.json"


def _load_helper(tmp_path: Path):  # type: ignore[no-untyped-def]
    stub_directory = tmp_path / "python26-stub"
    stub_directory.mkdir()
    (stub_directory / "fcntl.py").write_text(
        "LOCK_EX = 1\nLOCK_UN = 2\ndef flock(_handle, _operation):\n    return None\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("v4_validation_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(stub_directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(stub_directory))
    return module


def _emit_scope(lines: list[str], scope: str, apply: bool = False) -> None:
    lines.append(f"MCP_V4_TOPOLOGY|{scope}|35|14|8")
    lines.append(f"MCP_V4_PROPERTY|{scope}|baselineStamp|string|\"fixed\"")
    geometry = "101" if apply else "100"
    lines.append(f"MCP_V4_PROPERTY|{scope}|schGeometryLastUpdated|int|{geometry}")
    if apply:
        lines.append(
            f"MCP_V4_PROPERTY|{scope}|mcpMutationTest|string|\"validated-v1\""
        )
    for index in range(35):
        lines.append(f"MCP_V4_INSTANCE|{scope}|I{index}|lib|cell|view")
    for index in range(14):
        lines.append(f"MCP_V4_NET|{scope}|N{index}")
    for index in range(8):
        lines.append(f"MCP_V4_TERMINAL|{scope}|T{index}|input")


def _successful_output(path: Path) -> None:
    lines = ["MCP_V4_STAGE|source_read_only_verify|true|35|14|8|V3_BASELINE_EQUAL"]
    lines.append("MCP_V4_STAGE|V4_copy_from_source|true|35|14|8")
    _emit_scope(lines, "baseline")
    lines.append("MCP_V4_STAGE|baseline_structural_and_property_fingerprint|true")
    lines.append("MCP_V4_STAGE|non_mutating_dry_run|true|absent|1|0|false")
    _emit_scope(lines, "dry_run")
    lines.append("MCP_V4_STAGE|dry_run_unchanged_verification|true")
    _emit_scope(lines, "backup")
    lines.append("MCP_V4_STAGE|V4_backup_from_baseline|true")
    lines.append("MCP_V4_STAGE|apply_approved_property_once|true|1")
    lines.append("MCP_V4_METADATA|schGeometryLastUpdated|int|100|101")
    _emit_scope(lines, "apply", apply=True)
    lines.append(
        "MCP_V4_STAGE|exact_semantic_and_bounded_metadata_diff_verification|true|1|1"
    )
    lines.append("MCP_V4_STAGE|rollback_V4_target_from_V4_backup|true")
    _emit_scope(lines, "rollback")
    _emit_scope(lines, "backup_final")
    lines.append(
        "MCP_V4_STAGE|baseline_restoration_and_property_absence_verification|true"
    )
    lines.append("MCP_V4_COMPLETE|V4_CLEAN_VALIDATION_VERIFIED")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _finalize_arguments(tmp_path: Path, output: Path) -> list[str]:
    arguments = ["12345678-1234-4234-9234-123456789abc", str(output)]
    for index in range(7):
        digest = f"{index + 1:x}" * 64
        arguments.extend((digest, digest))
    arguments.extend(
        (
            "a" * 64,
            "b" * 64,
            "operator",
            "buet",
            str(tmp_path / "v4-audit.jsonl"),
            str(tmp_path / "manifest.json"),
        )
    )
    return arguments


def test_plan_hash_confirmation_and_fixed_contract(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    plan = helper.load_plan(str(PLAN))

    assert plan["plan_id"] == "mcp-cellview-property-v4-clean-validation"
    assert len(plan["sequence"]) == 18
    assert len(plan["acceptance_criteria"]) == 18
    assert helper.CONFIRMATION == "APPROVE_MCP_WRITE_VALIDATED_V4_C5B2F418"


def test_finalize_verifies_all_criteria_manifest_and_audit(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    plan = helper.load_plan(str(PLAN))
    output = tmp_path / "skill.stdout"
    _successful_output(output)
    arguments = _finalize_arguments(tmp_path, output)

    helper.finalize(plan, arguments)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    audit = [
        json.loads(line)
        for line in (tmp_path / "v4-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert manifest["status"] == "V4_CLEAN_VALIDATION_VERIFIED"
    assert len(manifest["acceptance_criteria"]) == 18
    assert all(item["result"] == "PASS" for item in manifest["acceptance_criteria"])
    assert manifest["rollback_verified"] is True
    assert manifest["actual_apply_diff"]["changed_property_names"] == [
        "mcpMutationTest",
        "schGeometryLastUpdated",
    ]
    assert manifest["release_gate"] == "PENDING_REPOSITORY_ACCEPTANCE"
    assert len(audit) == 18
    assert all(record["run_id"] == arguments[0] for record in audit)
    if os.name != "nt":
        assert (tmp_path / "manifest.json").stat().st_mode & 0o777 == 0o400


def test_finalize_rejects_protected_fingerprint_change(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    plan = helper.load_plan(str(PLAN))
    output = tmp_path / "skill.stdout"
    _successful_output(output)
    arguments = _finalize_arguments(tmp_path, output)
    arguments[3] = "f" * 64

    try:
        helper.finalize(plan, arguments)
    except ValueError as error:
        assert str(error) == "source changed during V4 validation"
    else:
        raise AssertionError("changed protected source was accepted")
