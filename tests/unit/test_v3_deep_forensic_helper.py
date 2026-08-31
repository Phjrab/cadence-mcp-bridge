from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_deep_forensic_json.py"


def _load_helper(tmp_path: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("v3_deep_forensic_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    validation_root = tmp_path / "original-validation"
    validation_root.mkdir()
    (validation_root / "skill.stdout").write_text(
        "MCP_V3_STAGE|source_verify|true|35|14|8\n"
        "MCP_V3_STAGE|backup|true\n"
        "MCP_V3_STAGE|apply|true|1\n"
        "MCP_V3_FAILURE|baseline_restoration_verification_failed\n",
        encoding="ascii",
    )
    module.VALIDATION_ROOT = str(validation_root)  # type: ignore[attr-defined]
    module.AUDIT_PATH = str(tmp_path / "missing-audit.jsonl")  # type: ignore[attr-defined]
    for attribute, name in (
        ("SOURCE_VIEW", "source"),
        ("TARGET_VIEW", "target"),
        ("BACKUP_VIEW", "backup"),
    ):
        view = tmp_path / name
        view.mkdir()
        (view / "master.tag").write_text("-- Master.tag File\nschematic : sch.oa\n")
        (view / "sch.oa").write_bytes((name + "-oa").encode())
        setattr(module, attribute, str(view))
    return module


def _skill_output(path: Path) -> None:
    lines: list[str] = []
    for scope in ("source", "target", "backup"):
        lines.append(f"MCP_V3_DEEP_TOPOLOGY|{scope}|35|14|8")
        geometry = {
            "source": "1600000000",
            "target": "1700000001",
            "backup": "1700000000",
        }[scope]
        lines.extend(
            (
                f"MCP_V3_DEEP_PROPERTY|{scope}|cellview|schGeometryLastUpdated|int|{geometry}",
                f'MCP_V3_DEEP_PROPERTY|{scope}|cellview|dbVersion|string|"4.0"',
            )
        )
        if scope == "target":
            lines.append(
                'MCP_V3_DEEP_PROPERTY|target|cellview|mcpMutationTest|string|"validated-v1"'
            )
        for index in range(35):
            lines.append(
                f"MCP_V3_DEEP_INSTANCE|{scope}|I{index}|gpdk090|nmos1v|symbol"
            )
        for index in range(14):
            lines.append(f"MCP_V3_DEEP_NET|{scope}|net{index}")
        for index in range(8):
            lines.append(f'MCP_V3_DEEP_TERMINAL|{scope}|term{index}|"inputOutput"')
    lines.append("MCP_V3_DEEP_COMPLETE|true")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unchanged_hashes() -> list[str]:
    hashes: list[str] = []
    for character in "abc":
        hashes.extend([character * 64, character * 64])
    return hashes


def test_deep_forensic_classifies_exact_two_property_diff_as_safe_candidate(
    tmp_path: Path,
) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "skill.stdout"
    report = tmp_path / "report.json"
    _skill_output(output)

    helper.deep_forensic(str(output), str(report), _unchanged_hashes())

    evidence = json.loads(report.read_text(encoding="utf-8"))
    assert evidence["forensic_classification"] == "SAFE_ROLLBACK_CANDIDATE"
    assert evidence["read_only_verified"] is True
    assert evidence["rollback_safety"]["actual_rollback_performed"] is False
    assert evidence["backup_validity"]["matches_source_structural_baseline"] is True
    assert evidence["backup_validity"]["property_set_equals_source"] is False
    assert evidence["backup_validity"]["log_proves_backup_before_apply"] is True
    assert evidence["original_validation"]["validation_manifest"] == "missing"
    assert evidence["original_validation"]["audit_record"] == "missing"
    assert [
        item["name"] for item in evidence["property_diffs"]["target_minus_backup"]
    ] == ["mcpMutationTest", "schGeometryLastUpdated"]
    assert evidence["approved_mutation_property"]["value"] == '"validated-v1"'
    assert evidence["identified_baseline_property"]["value"] == "1700000001"
    assert all(
        value["before"] == value["after"]
        for value in evidence["tree_fingerprints"].values()
    )


def test_deep_forensic_rejects_any_changed_three_object_fingerprint(
    tmp_path: Path,
) -> None:
    helper = _load_helper(tmp_path)
    output = tmp_path / "skill.stdout"
    _skill_output(output)
    hashes = _unchanged_hashes()
    hashes[3] = "d" * 64

    try:
        helper.deep_forensic(str(output), str(tmp_path / "report.json"), hashes)
    except ValueError as error:
        assert str(error) == "target changed during deep-forensic inspection"
    else:
        raise AssertionError("changed V3 target fingerprint was accepted")
