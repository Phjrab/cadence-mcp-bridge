from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_exact_rollback_json.py"
PLAN = PROJECT_ROOT / "remote" / "config" / "design-write-v3-exact-conditional-rollback-plan.json"


def _load_helper(tmp_path: Path):  # type: ignore[no-untyped-def]
    stub = tmp_path / "py26-stub"
    stub.mkdir()
    (stub / "fcntl.py").write_text(
        "LOCK_EX = 1\nLOCK_UN = 2\ndef flock(_handle, _operation):\n    return None\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("v3_exact_rollback_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(stub))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(stub))
    return module


def _properties(scope: str) -> list[tuple[str, str, str]]:
    baseline = [
        ("connectivityLastUpdated", "int", "107168"),
        ("instance#", "int", "11"),
        ("lastSchematicExtraction", "time", '"Aug 20 15:13:56 2026"'),
        ("net#", "int", "39"),
        ("pin#", "int", "36"),
        ("schGeometryLastUpdated", "int", "107168"),
        ("schGeometryVersion", "string", '"sch.ds.gm.1.4"'),
        ("schXtrVersion", "string", '"sch.10.0"'),
    ]
    if scope == "target_before":
        baseline[5] = ("schGeometryLastUpdated", "int", "107169")
        baseline.insert(3, ("mcpMutationTest", "string", '"validated-v1"'))
    return baseline


def _write_output(path: Path) -> None:
    lines: list[str] = []
    for scope in (
        "source_before",
        "target_before",
        "backup_before",
        "source_after",
        "target_after",
        "backup_after",
    ):
        lines.append(f"MCP_V3_ROLLBACK_TOPOLOGY|{scope}|35|14|8")
        for name, value_type, value in _properties(scope):
            lines.append(f"MCP_V3_ROLLBACK_PROPERTY|{scope}|{name}|{value_type}|{value}")
        for index in range(35):
            lines.append(
                f"MCP_V3_ROLLBACK_INSTANCE|{scope}|I{index}|gpdk090|nmos1v|symbol"
            )
        for index in range(14):
            lines.append(f"MCP_V3_ROLLBACK_NET|{scope}|net{index}")
        for index in range(8):
            lines.append(
                f'MCP_V3_ROLLBACK_TERMINAL|{scope}|term{index}|"inputOutput"'
            )
        if scope == "backup_before":
            lines.extend(
                (
                    "MCP_V3_ROLLBACK_STAGE|read_only_preconditions|true",
                    "MCP_V3_ROLLBACK_STAGE|dry_run|true|2|0|false",
                )
            )
        if scope == "target_after":
            lines.append("MCP_V3_ROLLBACK_STAGE|rollback|true")
    lines.extend(
        (
            "MCP_V3_ROLLBACK_STAGE|post_verify|true",
            "MCP_V3_ROLLBACK_COMPLETE|V3_ROLLBACK_VERIFIED",
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_synthetic_hashes(helper, plan: dict, output: Path) -> None:  # type: ignore[no-untyped-def]
    properties, records = helper.parse_output(str(output))
    expected = plan["expected_structural_fingerprints"]
    expected["instance_summary_sha256"] = helper.summary_hash(
        records["source_before"]["instance"]
    )
    expected["net_summary_sha256"] = helper.summary_hash(records["source_before"]["net"])
    expected["terminal_summary_sha256"] = helper.summary_hash(
        records["source_before"]["terminal"]
    )
    expected["target_property_summary_before_sha256"] = helper.summary_hash(
        [
            item["name"] + "|" + item["type"] + "|" + item["value"]
            for item in properties["target_before"]
        ]
    )
    expected["backup_property_summary_sha256"] = helper.summary_hash(
        [
            item["name"] + "|" + item["type"] + "|" + item["value"]
            for item in properties["backup_before"]
        ]
    )


def test_exact_rollback_finalize_records_all_fifteen_criteria(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    plan = helper.load_plan(str(PLAN))
    output = tmp_path / "skill.stdout"
    _write_output(output)
    _set_synthetic_hashes(helper, plan, output)
    audit = tmp_path / "audit.jsonl"
    manifest = tmp_path / "rollback-manifest.json"
    run_id = "12345678-1234-4234-9234-123456789abc"
    expected = plan["current_tree_fingerprints"]

    helper.finalize(
        plan,
        [
            run_id,
            str(output),
            expected["source"],
            expected["source"],
            expected["target"],
            "d" * 64,
            expected["backup"],
            expected["backup"],
            helper.REPORT_SHA256,
            "operator",
            "buet",
            str(audit),
            str(manifest),
        ],
    )

    evidence = json.loads(manifest.read_text(encoding="utf-8"))
    audit_records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert evidence["status"] == "V3_ROLLBACK_VERIFIED"
    assert len(evidence["acceptance_criteria"]) == 15
    assert all(item["result"] == "PASS" for item in evidence["acceptance_criteria"])
    assert evidence["source_unchanged"] is True
    assert evidence["backup_unchanged"] is True
    assert evidence["release_gate"] == "FAILED"
    assert len(audit_records) == 14
    assert [record["sequence_index"] for record in audit_records] == list(range(1, 15))


def test_plan_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    helper = _load_helper(tmp_path)
    changed_plan = tmp_path / "changed-plan.json"
    changed_plan.write_bytes(PLAN.read_bytes() + b"\n")

    try:
        helper.load_plan(str(changed_plan))
    except ValueError as error:
        assert str(error) == "BLOCKED_PLAN_HASH_MISMATCH"
    else:
        raise AssertionError("changed rollback plan was accepted")
