"""Synthetic applicability cases; no vendor help or private circuit is bundled."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Fictional connectivity only. This is not the reference circuit or an executed
# stability test. In particular, the local diode is not an application loop.
FICTIONAL = """// independent synthetic fixture
Mn (Vop Vp 0 0) nmos w=1u
Mp (Vom Vm VDD VDD) pmos w=2u
Md (bias bias 0 0) nmos
VpSource (Vp 0) vsource dc=0.5
VmSource (Vm 0) vsource dc=0.5
"""


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "pm_audit_test", ROOT / "scripts/phase_margin_qualification.py"
    )
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def synthetic(audit: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(audit, "SOURCE_CIRCUIT", audit.digest(FICTIONAL.encode()))
    return {
        "schema_version": 1,
        "source_input_sha256": audit.SOURCE_INPUT,
        "circuit": FICTIONAL,
        "protected_unchanged": True,
        "counter": {
            "campaign_id": "AUTO-PHASE-01",
            "count": 64,
            "result_reserved_bytes": 7383023616,
        },
        "help": {
            "stb": {"returncode": 0, "stdout": "Stability Analysis", "stderr": ""},
            "iprobe": {"returncode": 0, "stdout": "Current Probe", "stderr": ""},
            "diffstbprobe": {
                "returncode": 0,
                "stdout": "Warning from spectre. no such component, analysis, or other help topic.",
                "stderr": "",
            },
        },
    }


def test_explicit_open_loop_and_local_diode_are_not_phase_margin(audit: Any) -> None:
    result = audit.topology(FICTIONAL)
    assert result["independent_input_voltage_sources"]
    assert result["output_terminals_only_mos_drains"]
    assert result["diode_connected_mos_count"] == 1
    assert result["explicit_application_feedback"] == "ABSENT_IN_INSPECTED_BOUNDARY"
    assert result["model_internal_loops"] == "NOT_ASSESSED"


@pytest.mark.parametrize(
    "change", ["gate-feedback", "source-feedback", "missing-input", "missing-output"]
)
def test_feedback_or_missing_boundaries_require_review(audit: Any, change: str) -> None:
    text = FICTIONAL
    if change == "gate-feedback":
        text = text.replace("Vom Vm", "Vom Vop")
    elif change == "source-feedback":
        text = text.replace("Vop Vp 0 0", "Vop Vp Vom 0")
    elif change == "missing-input":
        text = text.replace("VmSource (Vm 0) vsource dc=0.5", "")
    else:
        text = text.replace("Vom Vm", "other Vm")
    result = audit.topology(text)
    assert result["explicit_application_feedback"] == "REVIEW_REQUIRED"
    assert result["explicit_common_mode_control"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "x" * 65537,
        "subckt user a b",
        "include /private",
        "X (a b) other",
        "M (a b) nmos",
        "V (a b c) vsource",
        "V (a 0) vsource\nV (a 0) vsource",
    ],
    ids=[
        "empty",
        "oversize",
        "subckt",
        "include",
        "unknown",
        "mos-terminals",
        "source-terminals",
        "duplicate",
    ],
)
def test_unknown_or_unbounded_circuit_is_rejected(audit: Any, text: str) -> None:
    with pytest.raises(ValueError):
        audit.topology(text)


def test_zero_exit_unknown_help_does_not_claim_installed_component(audit: Any) -> None:
    assert (
        audit.help_status(
            "diffstbprobe",
            {
                "returncode": 0,
                "stdout": "Warning from spectre. no such component, analysis, or other help topic.",
                "stderr": "",
            },
        )
        == "NOT_DOCUMENTED_BY_INSTALLED_HELP"
    )
    assert (
        audit.help_status("stb", {"returncode": 0, "stdout": "Stability Analysis", "stderr": ""})
        == "HELP_DOCUMENTED_ONLY"
    )
    assert (
        audit.help_status("iprobe", {"returncode": 124, "stdout": "Current Probe", "stderr": ""})
        == "UNVERIFIED"
    )


@pytest.mark.parametrize(
    "row",
    [
        {"returncode": True, "stdout": "Current Probe", "stderr": ""},
        {"returncode": 0, "stdout": "x" * 16385, "stderr": ""},
        {"returncode": 0, "stdout": [], "stderr": ""},
        {"returncode": 0, "stdout": "Current Probe", "stderr": "", "path": "/private"},
    ],
)
def test_help_records_are_closed_and_bounded(audit: Any, row: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        audit.help_status("iprobe", row)


def test_assessment_is_path_free_and_never_reports_a_margin(
    audit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = audit.assessment(synthetic(audit, monkeypatch))
    assert result["qualification"] == "UNQUALIFIED" and result["phase_margin_deg"] is None
    assert result["licensed_STB_execution"] == "NOT_RUN"
    assert result["installed_help"]["stb"]["status"] == "HELP_DOCUMENTED_ONLY"
    assert result["installed_help"]["diffstbprobe"]["status"] == "NOT_DOCUMENTED_BY_INSTALLED_HELP"
    assert result["new_simulation_attempts"] == result["new_reserved_bytes"] == 0
    encoded = json.dumps(result)
    assert (
        len(encoded) < 4096
        and 'circuit"' not in encoded
        and "stdout" not in encoded
        and "/home/" not in encoded
    )


@pytest.mark.parametrize(
    "change", ["source", "circuit", "extra", "help", "protected", "ledger", "version"]
)
def test_evidence_substitution_drift_or_missing_topics_rejected(
    audit: Any, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    raw = synthetic(audit, monkeypatch)
    if change == "source":
        raw["source_input_sha256"] = "0" * 64
    elif change == "circuit":
        raw["circuit"] += "// substituted\n"
    elif change == "extra":
        raw["path"] = "/private"
    elif change == "help":
        del raw["help"]["iprobe"]
    elif change == "protected":
        raw["protected_unchanged"] = False
    elif change == "ledger":
        raw["counter"]["count"] += 1
    else:
        raw["schema_version"] = True
    with pytest.raises(ValueError):
        audit.assessment(raw)


@pytest.mark.parametrize("change", ["valid", "no-delegation", "policy", "script", "parent"])
def test_exact_audit_authority_requires_private_delegation(
    audit: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    monkeypatch.setattr(audit.campaign, "_load_authority", lambda: "a" * 64)
    monkeypatch.setattr(audit, "POLICY", tmp_path / "policy.json")
    monkeypatch.setattr(audit, "DELEGATION", tmp_path / "delegation.json")
    policy = audit.expected_policy("a" * 64)
    if change == "policy":
        policy["max_new_attempts"] = 1
    elif change == "script":
        policy["script_sha256"] = "0" * 64
    elif change == "parent":
        policy["parent_policy_sha256"] = "b" * 64
    value = audit.digest(audit.campaign._canonical(policy))
    audit.POLICY.write_text(json.dumps(policy))
    if change != "no-delegation":
        audit.DELEGATION.write_text(
            json.dumps(
                {
                    "phase": "ANALOG-PM-01",
                    "policy_sha256": value,
                    "user_delegation": "explicit-in-current-task",
                    "user_instruction": "proceed",
                }
            )
        )
    if change == "valid":
        assert audit.authority() == value
    else:
        with pytest.raises((ValueError, audit.campaign.CampaignError)):
            audit.authority()


def test_remote_program_is_read_only_locked_and_uses_help_not_analysis(audit: Any) -> None:
    code = audit.REMOTE_CODE
    assert "fcntl.LOCK_EX|fcntl.LOCK_NB" in code and "os.O_NOFOLLOW" in code
    assert 'exe,"-h",topic' in code and "timeout" in code
    assert "manifest.sha256" in code and "protected reference drift" in code
    assert not any(token in code for token in ("rm ", "os.unlink", "os.mkdir", "O_CREAT", "-raw"))


@pytest.mark.parametrize("case", ["success", "transport-failure", "protected-drift"])
def test_inspect_keeps_durable_intent_and_blocks_blind_replay(
    audit: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    raw = synthetic(audit, monkeypatch)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(audit, "authority", lambda: "a" * 64)
    before = {
        "protected_unchanged": True,
        "counter": raw["counter"],
        "jobs": {"preserved": "hash"},
        "native_jobs": {},
        "phase_attempts": 4,
    }
    after = before | {"jobs": {"preserved": "changed"}} if case == "protected-drift" else before
    snapshots = iter((before, after))
    monkeypatch.setattr(audit.bandwidth, "postflight", lambda: next(snapshots))
    calls = []

    def transport(*args: Any) -> bytes:
        calls.append(args)
        if case == "transport-failure":
            raise OSError("uncertain transport")
        return json.dumps(raw).encode()

    monkeypatch.setattr(audit.io, "command", transport)
    result_path = tmp_path / ".codex/pm01-fixed-audit-result-v1.private.json"
    if case == "success":
        assert audit.inspect()["phase_margin_deg"] is None
        assert result_path.exists()
    else:
        with pytest.raises((ValueError, OSError)):
            audit.inspect()
        assert not result_path.exists()
    intent = tmp_path / ".codex/pm01-fixed-audit-intent-v1.private.json"
    first_bytes = intent.read_bytes()
    assert json.loads(first_bytes)["no_simulation"] is True and len(calls) == 1
    with pytest.raises(FileExistsError):
        audit.inspect()
    assert intent.read_bytes() == first_bytes and len(calls) == 1
