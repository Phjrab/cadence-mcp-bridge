from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = PROJECT_ROOT / "remote" / "py26" / "wp14_role_discovery.py"
SKILL_PATH = PROJECT_ROOT / "remote" / "discovery" / "wp14-role-discovery.il"
WORKER_PATH = PROJECT_ROOT / "remote" / "lib" / "run-wp14-role-discovery.sh"
RUNNER_PATH = PROJECT_ROOT / "remote" / "bin" / "cadence-runner"
DEPLOY_PATH = PROJECT_ROOT / "scripts" / "deploy-remote.ps1"
LINEAGE_PATH = PROJECT_ROOT / "remote" / "config" / "runner-lineage.json"
PLAN_PATH = PROJECT_ROOT / "docs" / "plans" / "WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN_V1.json"
PLAN_HASH = "2e44ca523c122744f6b16036785f285fc0f6a3d7b1b904326fe84ecc9165f12d"
SOURCE_HASH = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"


def load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wp14_role_discovery", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def marker(role: str = "VDD", instance: str = "PRIVATE_INSTANCE") -> str:
    return (
        "MCP_WP14_PRIVATE|"
        f"{role}|independent_voltage_source|reference_connected_two_terminal|"
        "voltage_dc_slot|2|"
        f"{instance}|analogLib|vdc|symbol|MINUS:gnd!,PLUS:private_net|dc"
    )


def stream(*markers: str, topology: str = "35|14|8|24") -> str:
    return "\n".join((*markers, f"MCP_WP14_TOPOLOGY|{topology}", "MCP_WP14_COMPLETE|true|true"))


def snapshots() -> tuple[dict[str, object], dict[str, object]]:
    protected = {
        "ade_state_tree": "a" * 64,
        "fixed_profile_registry": "b" * 64,
        "pdk_model_file": "c" * 64,
        "source_cellview_tree": SOURCE_HASH,
        "source_snapshot": "d" * 64,
    }
    before: dict[str, object] = {
        "blockers": [],
        "locks": [],
        "protected": protected,
        "source_tree": {"entry_count": 3, "sha256": SOURCE_HASH, "total_bytes": 10},
    }
    return before, json.loads(json.dumps(before))


def test_plan_hash_and_prior_plans_are_unchanged() -> None:
    normalized = PLAN_PATH.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    assert hashlib.sha256(normalized).hexdigest() == PLAN_HASH
    collector = (
        PROJECT_ROOT / "docs" / "plans" / "WP14_CONDITION_EVIDENCE_COLLECTOR_PLAN_V1.json"
    )
    assert collector.is_file()
    assert (PROJECT_ROOT / "docs" / "decisions" / "WP14_VBIAS_DECISION_PACKAGE_V1.json").is_file()
    for version in range(2, 5):
        decision = (
            PROJECT_ROOT / "docs" / "decisions" / f"WP14_VBIAS_DECISION_RECORD_V{version}.json"
        )
        assert decision.is_file()


def test_runner_is_zero_argument_operator_only_and_not_mcp_exposed() -> None:
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    server = (PROJECT_ROOT / "src" / "cadence_mcp_bridge" / "server.py").read_text(encoding="utf-8")
    service = (PROJECT_ROOT / "src" / "cadence_mcp_bridge" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "RUNNER_VERSION=0.19.0" in runner
    assert "wp14-role-discovery) runner_wp14_role_discovery" in runner
    assert 'runner_wp14_role_discovery()' in runner
    assert '[ "$#" -eq 0 ] || usage' in runner
    assert "flock -n 9" in runner
    assert 'timeout 60 "$WP14_ROLE_DISCOVERY_WORKER"' in runner
    assert "wp14-role-discovery" not in server
    assert "wp14-role-discovery" not in service
    for forbidden in ("eval ", "bash -c", "sh -c", "run-shell", "run-skill"):
        assert forbidden not in runner


def test_lineage_is_explicit_and_deployment_fails_closed() -> None:
    lineage = json.loads(LINEAGE_PATH.read_text(encoding="utf-8"))
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    assert lineage["repository_base_runner_version"] == "0.17.0"
    assert lineage["observed_remote_runner_version"] == "0.18.0"
    assert lineage["observed_remote_reference_head"] == "15d85bf440b86d191a8f9d07e7b9e687ccf003c0"
    assert lineage["repository_runner_version"] == "0.19.0"
    assert lineage["deployment_enabled"] is False
    assert "$lineagePolicy.lineage_status" in deploy
    assert "run-wp14-role-discovery.sh" in deploy
    assert "wp14_role_discovery.py" in deploy
    assert "wp14-role-discovery.il" in deploy


def test_skill_is_fixed_read_only_no_save_and_never_reads_property_values() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    assert 'sourceLib = "MyDesignLib"' in skill
    assert 'sourceCell = "Differential_Amplifier_TB2"' in skill
    assert 'sourceView = "schematic"' in skill
    assert 'dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")' in skill
    assert "dbClose(cv)" in skill
    assert "inst~>prop" in skill and "prop~>name" in skill and "prop~>valueType" in skill
    assert 'mcpWp14EmitBlocker("load_condition")' in skill
    assert re.search(r"~>value(?!Type)", skill) is None
    for forbidden in (
        "dbSave",
        "dbCopyCellView",
        "dbReplaceProp",
        "dbCreateInst",
        "dbDeleteObject",
        "evalstring",
        "load(",
        "system(",
        "ipcBeginProcess",
    ):
        assert forbidden not in skill


def test_worker_persists_only_redacted_bounded_result() -> None:
    worker = WORKER_PATH.read_text(encoding="utf-8")
    assert '[ "$#" -eq 0 ]' in worker
    assert 'timeout 30 "$VIRTUOSO_BIN"' in worker
    assert "-log /dev/null 2> /dev/null" in worker
    assert "skill.stdout" not in worker
    assert "skill.stderr" not in worker
    assert "16384" in worker
    assert '"$CADENCE_MCP_PYTHON" "$HELPER" complete' in worker
    assert "ssh" not in worker and "scp" not in worker


def test_helper_redacts_private_names_and_values_and_preserves_ambiguity() -> None:
    helper = load_helper()
    before, after = snapshots()
    raw = stream(
        marker("VDD", "PRIVATE_VDD_A"),
        marker("VDD", "PRIVATE_VDD_B"),
        marker("VCM", "PRIVATE_VCM"),
        marker("load_condition", "PRIVATE_LOAD"),
    )
    result = helper.build_complete_result(before, after, raw)
    serialized = json.dumps(result, sort_keys=True)
    assert result["status"] == "ambiguous"
    assert result["ambiguity"]["VDD"] == "multiple_candidates"
    assert result["roles"]["VCM"]["candidate_count"] == 1
    assert result["roles"]["VCM"]["candidates"][0]["semantically_confirmed"] is False
    for secret in (
        "PRIVATE_VDD_A",
        "PRIVATE_VDD_B",
        "PRIVATE_VCM",
        "PRIVATE_LOAD",
        "private_net",
        "analogLib",
        "vdc",
        "gnd!",
        "validated-v1",
    ):
        assert secret not in serialized
    assert len(serialized.encode()) <= 16384


def test_commitments_are_deterministic_private_tuple_and_source_bound() -> None:
    helper = load_helper()
    parsed, _unsupported = helper.parse_private_stream(stream(marker("VDD")))
    first = parsed["VDD"][0]["selector_commitment_sha256"]
    parsed_again, _unsupported = helper.parse_private_stream(stream(marker("VDD")))
    second = parsed_again["VDD"][0]["selector_commitment_sha256"]
    changed, _unsupported = helper.parse_private_stream(stream(marker("VDD", "OTHER_PRIVATE")))
    assert first == second
    assert first != changed["VDD"][0]["selector_commitment_sha256"]
    assert len(first) == 64 and set(first) <= set("0123456789abcdef")


def test_unique_candidates_remain_unapproved_hypotheses() -> None:
    helper = load_helper()
    before, after = snapshots()
    result = helper.build_complete_result(
        before,
        after,
        stream(marker("VDD"), marker("VCM"), marker("load_condition")),
    )
    assert result["status"] == "ok"
    for role in ("VDD", "VCM", "load_condition"):
        candidate = result["roles"][role]["candidates"][0]
        assert candidate["semantically_confirmed"] is False
        assert candidate["source_fingerprint_bound"] is True


@pytest.mark.parametrize(
    "bad_stream",
    [
        stream(marker("VDD", "name|injection")),
        stream(marker("VDD", "confusable_İ")),
        stream(marker("VDD"), topology="34|14|8|24"),
        "MCP_WP14_PRIVATE|VDD|unknown|unclassified|voltage_dc_slot|2|a|b|c|d|e:f,g:h|dc",
        "MCP_WP14_TOPOLOGY|35|14|8|24",
    ],
)
def test_malformed_injected_topology_or_lifecycle_input_fails_closed(bad_stream: str) -> None:
    helper = load_helper()
    before, after = snapshots()
    result = helper.build_complete_result(before, after, bad_stream)
    assert result["status"] == "blocked"
    assert result["roles"]["VDD"]["candidate_count"] == 0
    assert result["invariants"]["fingerprints_all_unchanged"] is False


def test_candidate_overflow_and_property_overflow_fail_closed() -> None:
    helper = load_helper()
    before, after = snapshots()
    too_many = [marker("VDD", f"PRIVATE_{index}") for index in range(17)]
    candidate_result = helper.build_complete_result(before, after, stream(*too_many))
    property_result = helper.build_complete_result(
        before, after, stream(marker("VDD"), topology="35|14|8|1025")
    )
    assert candidate_result["blockers"] == ["candidate_limit_exceeded"]
    assert property_result["blockers"] == ["property_limit_exceeded"]


def test_private_stream_size_limit_fails_closed_without_echo() -> None:
    helper = load_helper()
    before, after = snapshots()
    raw = "X" * (helper.MAX_STREAM_BYTES + 1)
    result = helper.build_complete_result(before, after, raw)
    assert result["status"] == "blocked"
    assert result["blockers"] == ["redaction_failure"]
    assert "X" * 64 not in json.dumps(result)


def test_source_fingerprint_lock_and_post_fingerprint_drift_fail_closed() -> None:
    helper = load_helper()
    before, after = snapshots()
    before["source_tree"]["sha256"] = "0" * 64  # type: ignore[index]
    before["blockers"] = ["blocking_lock"]
    after["protected"]["source_snapshot"] = "e" * 64  # type: ignore[index]
    result = helper.build_complete_result(
        before,
        after,
        stream(marker("VDD"), marker("VCM"), marker("load_condition")),
    )
    assert result["status"] == "blocked"
    assert set(result["blockers"]) == {
        "blocking_lock",
        "fingerprint_drift",
        "source_fingerprint_mismatch",
    }
    assert result["invariants"]["source_opened_read_only"] is True
    assert result["invariants"]["source_closed_without_save"] is True
    assert result["invariants"]["fingerprints_all_unchanged"] is False
