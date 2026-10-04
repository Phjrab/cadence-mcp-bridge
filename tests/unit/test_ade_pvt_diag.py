"""Synthetic operating-point frames and protection boundaries."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
operator = importlib.import_module("ade_pvt_diag")


def helper() -> Any:
    module: Any = ModuleType("diag_test")
    module.P = SimpleNamespace(BASE=SimpleNamespace(), JOBS="synthetic")
    source = (operator.LOCAL / "helper.py").read_text(encoding="utf-8")
    source = source.replace("import imp\n", "").replace(
        'P = imp.load_source("diag_pvt_guard", ROOT + "/phase-campaign/ade-pvt-qual-v1/helper.py")',
        "",
    )
    exec(compile(source, "diag.py", "exec"), module.__dict__)
    return module


def frame() -> str:
    return "\n".join(
        ["BEGIN"]
        + [
            f"OP|{corner}|mos{index:02d}|{field}|value|{2 if field == 'region' else 1e-6}"
            for corner in ("NN", "FF", "SS", "FS", "SF")
            for index in range(1, 15)
            for field in operator.FIELDS
        ]
        + ["END"]
    )


@pytest.mark.parametrize(
    "fault",
    ["none", "partial", "corner", "alias", "field", "nan", "inf", "large", "kind", "missing"],
)
def test_seventy_mos_records_with_exact_fields(fault: str) -> None:
    text = frame()
    if fault == "partial":
        text = text.removesuffix("END")
    elif fault == "corner":
        text = text.replace("OP|FS|", "OP|FF|")
    elif fault == "alias":
        text = text.replace("mos14", "mos15")
    elif fault == "field":
        text = text.replace("|gm|", "|coefficient|")
    elif fault in ("nan", "inf", "large"):
        text = text.replace(
            "value|1e-06", "value|" + {"nan": "nan", "inf": "inf", "large": "1e13"}[fault]
        )
    elif fault == "kind":
        text = text.replace("|value|", "|waveform|")
    elif fault == "missing":
        text = text.replace("|gmbs|value|1e-06", "|gmbs|missing|nil")
    if fault in ("none", "missing"):
        data = helper().parse_frame(text)
        assert len(data["operating_points"]["NN"]) == 14
        assert data["operating_points"]["FS"][0]["fields"]["gmbs"] == (
            None if fault == "missing" else 1e-6
        )
    else:
        with pytest.raises(ValueError):
            helper().parse_frame(text)


@pytest.mark.parametrize("fault", ["none", "selector", "partial", "extra", "boolean"])
def test_probe_only_reports_exact_selector_availability(fault: str) -> None:
    text = "\n".join(
        ["BEGIN", "PV|t"]
        + [
            f"R|{corner}|{selector}|{'t' if selector == 'dcOpInfo-info' else 'nil'}"
            for corner in ("NN", "FF", "SS", "FS", "SF")
            for selector in ("dcOpInfo-info", "dcOpInfo")
        ]
        + ["END"]
    )
    if fault == "selector":
        text = text.replace("dcOpInfo-info", "modelParameter-info")
    elif fault == "partial":
        text = text.removesuffix("END")
    elif fault == "extra":
        text += "\nsecret"
    elif fault == "boolean":
        text = text.replace("PV|t", "PV|1")
    if fault == "none":
        assert helper().parse_probe(text)["selectors"]["FF"] == {
            "dcOpInfo-info": True,
            "dcOpInfo": False,
        }
    else:
        with pytest.raises(ValueError):
            helper().parse_probe(text)


@pytest.mark.parametrize("fault", ["none", "count", "duplicate", "injection"])
def test_device_binding_is_private_and_script_tokens_cannot_escape(fault: str) -> None:
    text = "\n".join(
        f"{prefix}{index} (d g s b) synthetic_mos w=1u"
        for prefix, count in (("NM", 8), ("PM", 6))
        for index in range(count)
    )
    if fault == "count":
        text = "\n".join(text.splitlines()[:-1])
    elif fault == "duplicate":
        text += "\n" + text.splitlines()[0]
    elif fault == "injection":
        text = text.replace("d g s b", 'd g s ";exit(0)')
    module = helper()
    module.B.sha = lambda data: "opaque"
    if fault == "none":
        assert len(module.devices(text)) == 14
    else:
        with pytest.raises(ValueError):
            module.devices(text)


def test_selector_is_generated_as_string_not_hyphenated_skill_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = helper()
    runtime = tmp_path / "runtime"
    module.RUNTIME = str(runtime)
    module.VERSION = str(operator.LOCAL).replace("\\", "/")
    monkeypatch.setattr(module, "snapshot", lambda: {})
    monkeypatch.setattr(module, "inventory", lambda: [])
    module.B.save = lambda *_: None
    module.B.read = lambda path: Path(path).read_bytes()
    generated: list[str] = []
    module.B.write_new = lambda _, text: generated.append(text)
    module.begin("probe")
    assert len(generated) == 1
    assert generated[0].count('mcpHasResult("dcOpInfo-info")') == 5
    assert "'dcOpInfo-info" not in generated[0]


@pytest.mark.parametrize(
    "fault", ["none", "extra", "budget", "target", "boolean", "nan", "hash", "count"]
)
def test_operator_projection_is_finite_and_never_claims_spec_pass(fault: str) -> None:
    data = {
        **helper().parse_frame(frame()),
        "state": "succeeded",
        "phase": "ADE-PVT-DIAG-01",
        "new_spectre_attempts": 0,
        "protected_unchanged": True,
        "counter": operator.COUNTER,
        "spec_evaluation": "not_evaluated",
        "measurement_frame_sha256": "0" * 64,
        "model_manifest_sha256": "4a1fda45bb3738fc7253429903aee30b9c65f40439aee28f6cf22047178fd0d0",
    }
    if fault == "extra":
        data["model_statements"] = "forbidden"
    elif fault == "budget":
        data["new_spectre_attempts"] = 1
    elif fault == "target":
        data["spec_evaluation"] = "pass"
    elif fault in ("boolean", "nan"):
        data["operating_points"]["NN"][0]["fields"]["gm"] = (
            True if fault == "boolean" else float("nan")
        )
    elif fault == "hash":
        data["model_manifest_sha256"] = "1" * 64
    elif fault == "count":
        data["operating_points"]["FF"].pop()
    if fault == "none":
        operator.validate_result(data, "extract")
    else:
        with pytest.raises(ValueError):
            operator.validate_result(data, "extract")


@pytest.mark.parametrize("fault", ["none", "absent", "digest", "counter", "bytes"])
def test_authority_requires_private_explicit_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    checkpoint = tmp_path / "reference.json"
    failure = tmp_path / "failure.json"
    failure.write_bytes(b"synthetic failure checkpoint")
    monkeypatch.setattr(operator, "FAILURE", failure)
    monkeypatch.setattr(operator, "FAILURE_SHA", operator.dc.digest(failure.read_bytes()))
    checkpoint.write_text(
        json.dumps({"state": "complete", "pr": 98, "postflight": {"counter": operator.COUNTER}})
    )
    monkeypatch.setattr(operator, "REFERENCE", checkpoint)
    monkeypatch.setattr(operator.campaign, "_load_authority", lambda: "parent")
    monkeypatch.setattr(operator.qual, "authority", lambda: (None, "prior"))
    policy = operator.expected_policy("parent")
    digest = operator.dc.digest(operator.campaign._canonical(policy))
    delegation = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-DIAG-01",
        "parent_policy_sha256": "parent",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_selection": "read_preserved_mos_op_explain_ff_fs_gain_loss",
    }
    if fault == "absent":
        delegation = {}
    elif fault == "digest":
        delegation["policy_sha256"] = "drift"
    elif fault == "counter":
        checkpoint.write_text(
            json.dumps({"state": "complete", "pr": 98, "postflight": {"counter": {}}})
        )
    elif fault == "bytes":
        policy["files"]["helper.py"] = "drift"

    def read(path: Path) -> Any:
        if path == operator.ROOT / "docs/policy/ADE_PVT_DIAG_V1.json":
            return json.loads(path.read_text())
        return (
            json.loads(path.read_text())
            if path == checkpoint
            else policy
            if path == operator.POLICY
            else delegation
        )

    monkeypatch.setattr(operator.campaign, "_read_json", read)
    if fault == "none":
        assert operator.authority() == digest
    else:
        with pytest.raises(ValueError):
            operator.authority()
