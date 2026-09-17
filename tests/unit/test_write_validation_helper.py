from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "remote" / "py26" / "write_validation_json.py"
POLICY = PROJECT_ROOT / "remote" / "config" / "design-write-policy.json"


def _python26_fcntl_stub(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    stub_directory = tmp_path / "python26-stub"
    stub_directory.mkdir()
    (stub_directory / "fcntl.py").write_text(
        "LOCK_EX = 1\nLOCK_UN = 2\ndef flock(_handle, _operation):\n    return None\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(stub_directory)
    # The parent decodes captured streams as UTF-8, including warnings whose
    # filenames can contain Korean characters. Do not inherit CP949 output.
    environment["PYTHONIOENCODING"] = "utf-8"
    return stub_directory, environment


def test_fixture_child_output_is_utf8(tmp_path: Path) -> None:
    _, environment = _python26_fcntl_stub(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-c", "import sys; print(chr(0xD55C), file=sys.stderr)"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert completed.stderr.strip() == "\ud55c"


def test_source_gate_requires_authoritative_master_and_ignores_preserved_auxiliary(
    tmp_path: Path,
) -> None:
    stub_directory, _ = _python26_fcntl_stub(tmp_path)
    spec = importlib.util.spec_from_file_location("write_validation_json", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(stub_directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(stub_directory))

    (tmp_path / "master.tag").write_text("-- Master.tag File, Rev:1.0\nsch.oa\n", encoding="ascii")
    (tmp_path / "sch.oa").write_bytes(b"authoritative")
    (tmp_path / "sch.oa-").write_bytes(b"preserved auxiliary")

    assert module.source_master_is_authoritative(str(tmp_path)) is True
    assert module.has_lock_or_recovery_artifact(str(tmp_path)) is False
    (tmp_path / "sch.oa.cdslck.RHEL30.cadence.25425").write_text("lock", encoding="utf-8")
    assert module.has_lock_or_recovery_artifact(str(tmp_path)) is True


def test_source_gate_rejects_non_authoritative_master(tmp_path: Path) -> None:
    stub_directory, _ = _python26_fcntl_stub(tmp_path)
    spec = importlib.util.spec_from_file_location("write_validation_json_bad_master", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(stub_directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(stub_directory))

    (tmp_path / "master.tag").write_text("other.oa\n", encoding="ascii")
    (tmp_path / "sch.oa").write_bytes(b"present but not authoritative")

    assert module.source_master_is_authoritative(str(tmp_path)) is False


def test_v2_helper_requires_matching_logical_fingerprints_and_records_audit(
    tmp_path: Path,
) -> None:
    output = tmp_path / "skill.stdout"
    output.write_text(
        "\n".join(
            (
                "MCP_STAGE|source_verify|true",
                "MCP_STAGE|copy|1|2|3",
                "MCP_STAGE|baseline|1|2|3",
                "MCP_FINGERPRINT|baseline|topology|1|2|3|0",
                "MCP_STAGE|dry_run|absent|validated-v1|1|0|false",
                "MCP_FINGERPRINT|dry_run|topology|1|2|3|0",
                "MCP_STAGE|dry_run_unchanged|true",
                "MCP_FINGERPRINT|backup|topology|1|2|3|0",
                "MCP_STAGE|backup|true",
                "MCP_STAGE|apply|validated-v1|1",
                "MCP_STAGE|verify_apply|true|1|2|3",
                "MCP_STAGE|source_unchanged_before_rollback|true",
                "MCP_STAGE|rollback|true|1",
                "MCP_FINGERPRINT|rollback|topology|1|2|3|0",
                "MCP_STAGE|verify_rollback|true|1|2|3",
                "MCP_STAGE|source_unchanged|true",
                "MCP_STAGE|complete|true",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    audit = tmp_path / "write-events.jsonl"
    manifest = tmp_path / "manifest.json"
    _, environment = _python26_fcntl_stub(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            str(POLICY),
            "finalize",
            "12345678-1234-4234-8234-123456789abc",
            str(output),
            "source-fingerprint",
            "source-fingerprint",
            "preserved-fingerprint",
            "preserved-fingerprint",
            "mcp",
            "cadence-mcp-bridge",
            str(audit),
            str(manifest),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )

    result = json.loads(completed.stdout)
    evidence = json.loads(manifest.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert result["plan_id"] == "mcp-cellview-property-v2"
    assert result["baseline_fingerprint"] == result["rollback_fingerprint"]
    assert result["preserved_target_unchanged"] is True
    assert evidence["baseline_logical_fingerprint"] == evidence["rollback_logical_fingerprint"]
    assert len(records) == 13
    assert records[0]["event"] == "design_write_source_verify"
    assert records[-1]["event"] == "design_write_complete"


def test_v2_helper_rejects_a_changed_rollback_fingerprint(tmp_path: Path) -> None:
    output = tmp_path / "skill.stdout"
    stages = [
        "source_verify|true",
        "copy|1|2|3",
        "baseline|1|2|3",
        "dry_run|absent|validated-v1|1|0|false",
        "dry_run_unchanged|true",
        "backup|true",
        "apply|validated-v1|1",
        "verify_apply|true|1|2|3",
        "source_unchanged_before_rollback|true",
        "rollback|true|1",
        "verify_rollback|true|1|2|3",
        "source_unchanged|true",
        "complete|true",
    ]
    lines = ["MCP_STAGE|" + stage for stage in stages]
    lines.extend(
        [
            "MCP_FINGERPRINT|baseline|topology|1|2|3|0",
            "MCP_FINGERPRINT|dry_run|topology|1|2|3|0",
            "MCP_FINGERPRINT|backup|topology|1|2|3|0",
            "MCP_FINGERPRINT|rollback|topology|9|2|3|0",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _, environment = _python26_fcntl_stub(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            str(POLICY),
            "finalize",
            "12345678-1234-4234-8234-123456789abc",
            str(output),
            "same",
            "same",
            "preserved",
            "preserved",
            "mcp",
            "cadence-mcp-bridge",
            str(tmp_path / "audit.jsonl"),
            str(tmp_path / "manifest.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )

    assert completed.returncode != 0
    assert "baseline logical fingerprint was not restored" in completed.stderr
